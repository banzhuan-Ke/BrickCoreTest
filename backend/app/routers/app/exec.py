"""App 自动化执行调度"""
import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from tortoise import transactions

from app.core.platform.auth import get_current_username, is_authenticated, require_permissions
from app.modules.data_tools.inline_tools import ensure_dt_cache
from app.modules.data_tools.tag_service import merge_execution_variables
from app.core.db.db_factory_service import run_sql_templates_by_ids
from app.modules.ai.ai_project_settings import resolve_locator_heal_for_execute
from app.modules.app.app_device_lock import acquire_device_lock, release_device_lock, resolve_exec_lock_holder_id
from app.modules.app.app_locator_service import expand_locator_refs_in_steps
from app.modules.app.app_step_expand import FragmentExpandError, expand_fragment_refs
from app.core.infra.mq_producer import MQProducer
from app.modules.app.app_execution_stop import stop_case_execution, stop_plan_execution, stop_suite_execution
from app.core.platform.permissions import APP_CASE_EXECUTE, APP_PLAN_EXECUTE, APP_SUITE_EXECUTE
from app.modules.ui.ui_project_guard import assert_environment_for_project, assert_user_project_member
from app.models.app import (
    AppCase,
    AppCaseExecution,
    AppPlan,
    AppPlanExecution,
    AppSuite,
    AppSuiteExecution,
    AppSuiteStep,
)
from app.models.sys import Device, Environment
from app.modules.app.app_locator_validate import validate_case_steps_driver_mode_for_project, validate_driver_mode
from app.modules.app.app_execution_env import build_case_env, normalize_trigger_source
from app.schemas.app import AppCaseDebugForm, AppRunForm

router = APIRouter(prefix="/exec", dependencies=[Depends(is_authenticated)], tags=["App执行"])


async def expand_app_steps(steps: list, project_id: int) -> list:
    try:
        expanded = await expand_fragment_refs(steps or [], project_id)
    except FragmentExpandError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await expand_locator_refs_in_steps(expanded, project_id)


class AppExecutionService:
    @staticmethod
    async def build_env_payload(
        env: Environment,
        project_id: int,
        device: Device,
        item: AppRunForm,
        plan_record_video: bool | None = None,
    ) -> Dict[str, Any]:
        variables = ensure_dt_cache(await merge_execution_variables(project_id, env.id))
        udid = (item.app_udid or device.app_udid or "").strip()
        record_video = item.record_video
        if record_video is None and plan_record_video is not None:
            record_video = plan_record_video
        if record_video is None:
            record_video = True
        ai_heal_enabled = await resolve_locator_heal_for_execute(project_id, item.ai_heal_enabled)
        return {
            "engine_type": "app",
            "platform": device.app_platform or "android",
            "device_udid": udid,
            "app_id": item.app_id or "",
            "no_reset": item.no_reset,
            "auto_grant_permissions": item.auto_grant_permissions,
            "implicit_wait": item.implicit_wait,
            "record_video": record_video,
            "environment_id": env.id,
            "project_id": project_id,
            "env_name": env.name,
            "variables": variables,
            "device_id": item.device_id,
            "ai_heal_enabled": ai_heal_enabled,
        }

    @staticmethod
    def with_trigger_source(env_payload: Dict[str, Any], trigger_source: str | None) -> Dict[str, Any]:
        out = dict(env_payload)
        out["trigger_source"] = normalize_trigger_source(trigger_source)
        return out

    @staticmethod
    async def run_suite_setup_sql(suite: AppSuite, env_id: int) -> None:
        if not (suite.setup_sql_ids or []):
            return
        variables = await merge_execution_variables(suite.project_id, env_id)
        setup_res = await run_sql_templates_by_ids(
            suite.setup_sql_ids, variables, env_id, suite.project_id, phase="setup"
        )
        if not setup_res.get("success"):
            detail = (setup_res.get("logs") or [{}])[0].get("message", "前置 SQL 执行失败")
            raise HTTPException(status_code=422, detail=f"App 套件前置 SQL 失败: {detail}")

    @staticmethod
    async def build_case_item(case_execution: AppCaseExecution, case: AppCase, step_meta: AppSuiteStep | None):
        steps = await expand_app_steps(case.steps or [], case.project_id)
        return {
            "execution_id": case_execution.id,
            "id": case.id,
            "name": case.name,
            "skip": step_meta.skip if step_meta else False,
            "driver_mode": case.driver_mode,
            "steps": steps,
        }

    @staticmethod
    async def build_suite_payload(
        suite: AppSuite,
        suite_record: AppSuiteExecution,
        cases: List[Dict],
        plan_record: AppPlanExecution | None = None,
    ) -> Dict[str, Any]:
        payload = {
            "engine_type": "app",
            "id": suite.id,
            "suite_execution_id": suite_record.id,
            "name": suite.name,
            "username": suite_record.username,
            "pre_actions": await expand_app_steps(suite.pre_actions or [], suite.project_id),
            "stop_on_failure": suite.stop_on_failure,
            "propagate_variables": suite.propagate_variables,
            "cases": cases,
        }
        if plan_record:
            payload["plan_execution_id"] = plan_record.id
        return payload

    @staticmethod
    def _resolve_exec_holder_id(suite_payload: Dict[str, Any]) -> str:
        return resolve_exec_lock_holder_id(suite_payload)

    @staticmethod
    async def dispatch_to_device(env_payload: Dict, suite_payload: Dict, device_id: str) -> bool:
        device = await Device.get_or_none(id=device_id, is_del=False)
        if not device or device.status != "在线":
            return False
        engine_types = device.runner_engine_types or ["web"]
        if "app" not in engine_types:
            return False
        udid = (env_payload.get("device_udid") or device.app_udid or "").strip()
        if not udid:
            return False
        holder_id = AppExecutionService._resolve_exec_holder_id(suite_payload)
        if holder_id:
            await acquire_device_lock(
                udid,
                holder_type="exec",
                holder_id=holder_id,
                username=str(suite_payload.get("username") or ""),
            )
        mq = MQProducer()
        try:
            last_exc: Exception | None = None
            for attempt in range(3):
                try:
                    mq.send_test_task(env_payload, suite_payload, device_id)
                    return True
                except Exception as exc:
                    last_exc = exc
                    if attempt < 2:
                        await asyncio.sleep(0.5 * (attempt + 1))
            if holder_id:
                await release_device_lock(udid, holder_type="exec", holder_id=holder_id)
            if last_exc:
                raise last_exc
            return False
        finally:
            mq.close()


async def _get_device_or_422(device_id: str) -> Device:
    device = await Device.get_or_none(id=device_id, is_del=False)
    if not device:
        raise HTTPException(status_code=422, detail="设备不存在")
    return device


@router.post(
    "/cases/{case_id}/debug",
    status_code=201,
    summary="调试 App 用例至指定步骤",
    dependencies=[Depends(require_permissions(APP_CASE_EXECUTE))],
)
async def debug_app_case(
    case_id: int,
    item: AppCaseDebugForm,
    user_info: dict = Depends(require_permissions(APP_CASE_EXECUTE)),
    username: str = Depends(get_current_username),
):
    """执行 steps[0:through_index+1] 后停止，支持使用编辑器中未保存的步骤。"""
    if not item.steps:
        raise HTTPException(status_code=422, detail="步骤列表不能为空")
    if item.through_index >= len(item.steps):
        raise HTTPException(
            status_code=422,
            detail=f"through_index 超出范围（共 {len(item.steps)} 步）",
        )

    env_payload: Dict[str, Any] = {}
    suite_payload: Dict[str, Any] = {}
    case_execution_id: int | None = None
    debug_step_count = item.through_index + 1
    driver_mode = validate_driver_mode((item.driver_mode or "hybrid").strip() or "hybrid")

    async with transactions.in_transaction():
        case = await AppCase.get_or_none(id=case_id, is_del=False)
        if not case:
            raise HTTPException(status_code=422, detail="用例不存在")
        await assert_user_project_member(user_info, case.project_id)
        if not item.device_id:
            raise HTTPException(status_code=422, detail="请选择执行设备")
        env = assert_environment_for_project(
            await Environment.get_or_none(id=item.env_id, is_del=False), case.project_id
        )
        device = await _get_device_or_422(item.device_id)
        debug_slice = item.steps[: item.through_index + 1]
        debug_steps = await expand_app_steps(debug_slice, case.project_id)
        try:
            await validate_case_steps_driver_mode_for_project(
                driver_mode, debug_steps, case.project_id
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        env_payload = AppExecutionService.with_trigger_source(
            await AppExecutionService.build_env_payload(env, case.project_id, device, item),
            item.trigger_source,
        )
        env_payload["debug_mode"] = True
        env_payload["debug_through_index"] = item.through_index
        env_payload = build_case_env(env_payload, case, trigger_source=item.trigger_source)
        env_payload["driver_mode"] = driver_mode
        case_execution = await AppCaseExecution.create(
            case=case,
            username=username,
            env=env_payload,
            is_del=False,
        )
        case_execution_id = case_execution.id
        suite_payload = {
            "engine_type": "app",
            "id": case.id,
            "name": f"{case.name}（调试至第 {item.through_index + 1} 步）",
            "case_execution_id": case_execution.id,
            "pre_actions": [],
            "username": username,
            "cases": [
                {
                    "execution_id": case_execution.id,
                    "id": case.id,
                    "name": case.name,
                    "skip": False,
                    "driver_mode": driver_mode,
                    "steps": debug_steps,
                }
            ],
        }

    dispatched = await AppExecutionService.dispatch_to_device(
        env_payload, suite_payload, item.device_id
    )
    return {
        "msg": "App 调试任务已加入执行队列" if dispatched else "调试记录已创建，暂无支持 App 的在线 Runner",
        "dispatched": dispatched,
        "execution_id": case_execution_id,
        "through_index": item.through_index,
        "step_count": debug_step_count,
    }


@router.post("/cases/{case_id}", status_code=201, dependencies=[Depends(require_permissions(APP_CASE_EXECUTE))])
async def run_case(
    case_id: int,
    item: AppRunForm,
    user_info: dict = Depends(require_permissions(APP_CASE_EXECUTE)),
    username: str = Depends(get_current_username),
):
    env_payload: Dict[str, Any] = {}
    suite_payload: Dict[str, Any] = {}
    case_execution_id: int | None = None

    async with transactions.in_transaction():
        case = await AppCase.get_or_none(id=case_id, is_del=False)
        if not case:
            raise HTTPException(status_code=422, detail="用例不存在")
        await assert_user_project_member(user_info, case.project_id)
        if not item.device_id:
            raise HTTPException(status_code=422, detail="请选择执行设备")
        env = assert_environment_for_project(
            await Environment.get_or_none(id=item.env_id, is_del=False), case.project_id
        )
        device = await _get_device_or_422(item.device_id)
        env_payload = AppExecutionService.with_trigger_source(
            await AppExecutionService.build_env_payload(env, case.project_id, device, item),
            item.trigger_source,
        )
        env_payload = build_case_env(env_payload, case, trigger_source=item.trigger_source)
        case_execution = await AppCaseExecution.create(
            case=case, username=username, env=env_payload, is_del=False
        )
        case_execution_id = case_execution.id
        expanded_steps = await expand_app_steps(case.steps or [], case.project_id)
        suite_payload = {
            "engine_type": "app",
            "id": case.id,
            "name": case.name,
            "case_execution_id": case_execution.id,
            "pre_actions": [],
            "username": username,
            "cases": [
                {
                    "execution_id": case_execution.id,
                    "id": case.id,
                    "name": case.name,
                    "skip": False,
                    "driver_mode": case.driver_mode,
                    "steps": expanded_steps,
                }
            ],
        }

    dispatched = await AppExecutionService.dispatch_to_device(env_payload, suite_payload, item.device_id)
    return {
        "msg": "App 用例已加入执行队列" if dispatched else "记录已创建，暂无支持 App 的在线 Runner 或未检测到 Android 设备",
        "dispatched": dispatched,
        "execution_id": case_execution_id,
    }


async def execute_app_suite_internal(
    suite_id: int,
    item: AppRunForm,
    username: str,
    *,
    cronjob_id: str | None = None,
) -> dict:
    """内部套件执行（定时任务等），不做权限校验。"""
    env_payload: Dict[str, Any] = {}
    suite_payload: Dict[str, Any] = {}
    suite_execution_id: int | None = None

    async with transactions.in_transaction():
        suite = await AppSuite.get_or_none(id=suite_id, is_del=False)
        if not suite:
            raise HTTPException(status_code=422, detail="套件不存在")
        env = assert_environment_for_project(
            await Environment.get_or_none(id=item.env_id, is_del=False), suite.project_id
        )
        device = await _get_device_or_422(item.device_id)
        env_payload = AppExecutionService.with_trigger_source(
            await AppExecutionService.build_env_payload(env, suite.project_id, device, item),
            item.trigger_source,
        )
        steps = await AppSuiteStep.filter(suite_id=suite.id, is_del=False).order_by("sort").all()
        suite_record = await AppSuiteExecution.create(
            suite=suite,
            username=username,
            env=env_payload,
            case_count=0,
            device_id=item.device_id,
            cronjob_id=cronjob_id,
            is_del=False,
        )
        suite_execution_id = suite_record.id
        cases_payload = []
        for step in steps:
            case = await AppCase.get_or_none(id=step.case_id, is_del=False)
            if not case or case.project_id != suite.project_id:
                continue
            case_exec = await AppCaseExecution.create(
                case=case,
                suite_execution=suite_record,
                username=username,
                env=build_case_env(
                    env_payload,
                    case,
                    trigger_source=item.trigger_source,
                    cronjob_id=cronjob_id,
                ),
                is_del=False,
            )
            cases_payload.append(
                await AppExecutionService.build_case_item(case_exec, case, step)
            )

        suite_record.case_count = len(cases_payload)
        await suite_record.save()

        if not cases_payload:
            suite_record.status = "执行完成"
            await suite_record.save()
            return {
                "msg": "套件中没有可执行的用例",
                "dispatched": False,
                "execution_id": suite_record.id,
            }

        await AppExecutionService.run_suite_setup_sql(suite, env.id)
        suite_payload = await AppExecutionService.build_suite_payload(suite, suite_record, cases_payload)

    dispatched = await AppExecutionService.dispatch_to_device(env_payload, suite_payload, item.device_id)
    return {
        "msg": "App 套件已加入执行队列" if dispatched else "记录已创建，暂无支持 App 的在线 Runner 或未检测到 Android 设备",
        "dispatched": dispatched,
        "execution_id": suite_execution_id,
    }


@router.post("/suites/{suite_id}", status_code=201, dependencies=[Depends(require_permissions(APP_SUITE_EXECUTE))])
async def run_suite(
    suite_id: int,
    item: AppRunForm,
    user_info: dict = Depends(require_permissions(APP_SUITE_EXECUTE)),
    username: str = Depends(get_current_username),
):
    suite = await AppSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=422, detail="套件不存在")
    await assert_user_project_member(user_info, suite.project_id)
    if not item.device_id:
        raise HTTPException(status_code=422, detail="请选择执行设备")
    return await execute_app_suite_internal(suite_id, item, username)


@router.post("/plans/{plan_id}", status_code=201, dependencies=[Depends(require_permissions(APP_PLAN_EXECUTE))])
async def run_plan(
    plan_id: int,
    item: AppRunForm,
    user_info: dict = Depends(require_permissions(APP_PLAN_EXECUTE)),
    username: str = Depends(get_current_username),
):
    from app.modules.app.app_plan_runner import execute_app_plan

    plan = await AppPlan.get_or_none(id=plan_id, is_del=False)
    if not plan:
        raise HTTPException(status_code=422, detail="计划不存在")
    await assert_user_project_member(user_info, plan.project_id)

    devices_payload = None
    if item.devices:
        devices_payload = [d.model_dump() for d in item.devices]
    elif not item.device_id:
        raise HTTPException(status_code=422, detail="请选择执行设备")

    return await execute_app_plan(
        plan,
        env_id=item.env_id,
        username=username,
        run_form=item,
        device_id=item.device_id or None,
        devices=devices_payload,
        concurrency=item.concurrency,
        trigger_source=item.trigger_source,
    )


@router.post("/stop/{record_id}", summary="停止 App 计划执行", status_code=status.HTTP_200_OK,
             dependencies=[Depends(require_permissions(APP_PLAN_EXECUTE))])
async def stop_plan_execution_route(
    record_id: int,
    user_info: dict = Depends(require_permissions(APP_PLAN_EXECUTE)),
):
    record = await AppPlanExecution.get_or_none(id=record_id, is_del=False)
    if not record:
        raise HTTPException(status_code=422, detail="执行记录不存在")
    await assert_user_project_member(user_info, record.project_id)
    return await stop_plan_execution(record_id)


@router.post("/stop/suite/{record_id}", summary="停止 App 套件执行", status_code=status.HTTP_200_OK,
             dependencies=[Depends(require_permissions(APP_SUITE_EXECUTE))])
async def stop_suite_execution_route(
    record_id: int,
    user_info: dict = Depends(require_permissions(APP_SUITE_EXECUTE)),
):
    record = await AppSuiteExecution.get_or_none(id=record_id, is_del=False).prefetch_related("suite")
    if not record:
        raise HTTPException(status_code=422, detail="套件执行记录不存在")
    suite = await record.suite
    if not suite:
        raise HTTPException(status_code=422, detail="套件执行记录不存在")
    await assert_user_project_member(user_info, suite.project_id)
    return await stop_suite_execution(record_id)


@router.post("/stop/case/{record_id}", summary="停止 App 用例执行", status_code=status.HTTP_200_OK,
             dependencies=[Depends(require_permissions(APP_CASE_EXECUTE))])
async def stop_case_execution_route(
    record_id: int,
    user_info: dict = Depends(require_permissions(APP_CASE_EXECUTE)),
):
    record = await AppCaseExecution.get_or_none(id=record_id, is_del=False).prefetch_related("case")
    if not record:
        raise HTTPException(status_code=422, detail="用例执行记录不存在")
    case = await record.case
    if not case:
        raise HTTPException(status_code=422, detail="用例执行记录不存在")
    await assert_user_project_member(user_info, case.project_id)
    return await stop_case_execution(record_id)
