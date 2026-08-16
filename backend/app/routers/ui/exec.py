"""
执行相关路由
"""
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from tortoise import transactions

from app.models.sys import Device, Environment
from app.models.ui import Suite, Case, Task, UiPlanExecution, UiSuiteExecution, UiCaseExecution
from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import UI_CASE_EXECUTE, UI_SUITE_EXECUTE, UI_TASK_EXECUTE
from app.core.infra.mq_producer import MQProducer
from app.modules.ai.ai_project_settings import (
    resolve_locator_heal_for_execute,
    load_ai_project_settings,
    resolve_ai_act_for_execute,
    resolve_failure_analysis_for_report,
)
from app.modules.ui.ui_execution_stop import stop_plan_execution, stop_suite_execution, stop_case_execution
from app.modules.ui.ui_device_guard import (
    assert_device_available_for_ui_execution,
    lock_device_row,
)
from app.modules.ui.ui_project_guard import assert_environment_for_project, assert_user_project_member
from app.modules.ui.ui_step_expand import FragmentExpandError, expand_fragment_refs
from app.schemas.ui import RunForm, CaseDebugForm

router = APIRouter(
    prefix="/exec",
    dependencies=[Depends(is_authenticated)],
    tags=["测试运行"]
)


class ExecutionService:
    """
    测试执行服务层
    
    负责组装执行上下文、创建执行记录、分发任务到执行器
    """
    
    @staticmethod
    async def build_env_payload(
        env: Environment,
        browser_type: str,
        headless: bool,
        project_id: int,
        user_heal_override: Optional[bool] = None,
        user_act_override: Optional[bool] = None,
        user_failure_analysis_override: Optional[bool] = None,
        user_timeout_scale_override: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        构建执行环境负载；ai_heal_enabled / ai_act_enabled 由 Backend 项目配置计算。
        """
        from app.modules.data_tools.tag_service import merge_execution_variables
        from app.modules.data_tools.inline_tools import ensure_dt_cache
        from app.core.shared.ui_env_exec_strategy import build_ui_exec_strategy_payload

        ai_heal_enabled = await resolve_locator_heal_for_execute(project_id, user_heal_override)
        ai_act_enabled = await resolve_ai_act_for_execute(project_id, user_act_override)
        failure_analysis_on_report = await resolve_failure_analysis_for_report(
            project_id, user_failure_analysis_override
        )
        settings = await load_ai_project_settings(project_id)
        variables = ensure_dt_cache(await merge_execution_variables(project_id, env.id))
        resolved_browser = browser_type if browser_type in ["chromium", "firefox", "webkit"] else "chromium"
        from app.modules.ui.ui_debug_steps import get_env_default_start_url
        payload = {
            "headless": headless,
            "browser": resolved_browser,
            "browser_type": resolved_browser,
            "target_host": env.host,
            "environment_id": env.id,
            "project_id": project_id,
            "env_name": env.name,
            "variables": variables,
            "env_default_start_url": get_env_default_start_url(env.global_vars),
            "project_default_start_url": str(settings.get("default_start_url") or "").strip(),
            "ai_heal_enabled": ai_heal_enabled,
            "ai_act_enabled": ai_act_enabled,
            "ai_act_max_per_case": int(settings.get("ai_act_max_per_case") or 3),
            "failure_analysis_on_report": failure_analysis_on_report,
        }
        payload.update(
            build_ui_exec_strategy_payload(
                env.global_vars,
                timeout_scale_override=user_timeout_scale_override,
            )
        )
        return payload

    @staticmethod
    def with_trigger_source(env_payload: Dict[str, Any], trigger_source: Optional[str]) -> Dict[str, Any]:
        if not trigger_source:
            return env_payload
        out = dict(env_payload)
        out["trigger_source"] = trigger_source.strip()
        return out
    
    @staticmethod
    async def run_suite_setup_sql(suite_: Suite, env_id: int) -> None:
        """执行 UI 套件前置 SQL（数据工厂 setup）"""
        if not (suite_.setup_sql_ids or []):
            return
        from app.core.db.db_factory_service import run_sql_templates_by_ids
        from app.models.sys import Project

        from app.modules.data_tools.tag_service import merge_execution_variables

        variables = await merge_execution_variables(suite_.project_id, env_id)
        setup_res = await run_sql_templates_by_ids(
            suite_.setup_sql_ids, variables, env_id, suite_.project_id, phase="setup"
        )
        if not setup_res.get("success"):
            logs = setup_res.get("logs") or []
            detail = logs[0].get("message") if logs else "前置 SQL 执行失败"
            raise HTTPException(status_code=422, detail=f"套件前置 SQL 执行失败: {detail}")

    @staticmethod
    async def expand_steps_or_raise(steps: List, project_id: int) -> List:
        try:
            return await expand_fragment_refs(steps or [], project_id)
        except FragmentExpandError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @staticmethod
    async def build_case_item(
        case_execution: UiCaseExecution,
        case_: Case,
        step_meta: Any,
        project_id: int,
    ) -> Dict[str, Any]:
        """构建单个用例执行项（展开片段引用）"""
        expanded_steps = await ExecutionService.expand_steps_or_raise(case_.steps, project_id)
        return {
            "execution_id": case_execution.id,
            "id": case_.id,
            "name": case_.name,
            "skip": step_meta.skip if step_meta else False,
            "run_mode": (step_meta.run_mode if step_meta else None) or "standalone",
            "steps": expanded_steps,
        }
    
    @staticmethod
    async def build_suite_payload(
        suite_: Suite,
        suite_record: UiSuiteExecution,
        cases: List[Dict],
        plan_record: UiPlanExecution = None,
    ) -> Dict[str, Any]:
        """构建套件执行负载（展开前置步骤中的片段引用）"""
        pre_actions = await ExecutionService.expand_steps_or_raise(
            suite_.pre_actions or [], suite_.project_id
        )
        payload = {
            "id": suite_.id,
            "suite_execution_id": suite_record.id,
            "name": suite_.name,
            "username": suite_record.username,
            "pre_actions": pre_actions,
            "stop_on_failure": bool(getattr(suite_, "stop_on_failure", False)),
            "propagate_variables": bool(getattr(suite_, "propagate_variables", False)),
            "cases": cases
        }
        if plan_record:
            payload["plan_execution_id"] = plan_record.id
        return payload
    
    @staticmethod
    async def dispatch_to_device(env_payload: Dict, suite_payload: Dict, device_id: str) -> bool:
        """将执行任务分发到指定设备"""
        device = await Device.get_or_none(id=device_id)
        if not device or device.status != "在线":
            return False
        types = device.runner_engine_types or ["web"]
        if "web" not in types:
            return False
        
        mq = MQProducer()
        try:
            mq.send_test_task(env_payload, suite_payload, device_id)
            return True
        finally:
            mq.close()


# 执行单条用例
@router.post("/cases/{case_id}", summary="执行用例", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))])
async def run_case(
    case_id: int,
    item: RunForm,
    user_info: dict = Depends(require_permissions(UI_CASE_EXECUTE)),
):
    """执行单条用例"""
    case_ = await Case.get_or_none(id=case_id, is_del=False)
    if not case_:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="目标用例不存在或已被移除"
        )
    await assert_user_project_member(user_info, case_.project_id)

    env = assert_environment_for_project(
        await Environment.get_or_none(id=item.env_id, is_del=False),
        case_.project_id,
    )

    env_payload = await ExecutionService.build_env_payload(
        env,
        item.browser_type,
        item.config,
        case_.project_id,
        item.ai_heal_enabled,
        item.ai_act_enabled,
        item.failure_analysis_on_report,
        item.ui_timeout_scale,
    )
    env_payload = ExecutionService.with_trigger_source(env_payload, item.trigger_source)
    env_payload["device_id"] = item.device_id

    # 设备行锁仅覆盖「占用检查 + 创建执行记录」，勿把展开步骤 / MQ 下发放进事务
    async with transactions.in_transaction():
        await lock_device_row(item.device_id)
        await assert_device_available_for_ui_execution(item.device_id)
        case_execution = await UiCaseExecution.create(
            case=case_,
            username=item.username,
            env=env_payload,
            is_del=False
        )
        case_id_db = case_.id
        case_name = case_.name
        project_id = case_.project_id
        case_steps = case_.steps
        case_execution_id = case_execution.id

    expanded_steps = await ExecutionService.expand_steps_or_raise(case_steps, project_id)
    suite_payload = {
        "id": case_id_db,
        "name": case_name,
        "case_execution_id": case_execution_id,
        "pre_actions": [],
        "username": item.username,
        "cases": [
            {
                "execution_id": case_execution_id,
                "id": case_id_db,
                "name": case_name,
                "skip": False,
                "steps": expanded_steps,
            }
        ]
    }

    dispatched = await ExecutionService.dispatch_to_device(
        env_payload, suite_payload, item.device_id
    )

    return {
        "msg": "用例已加入执行队列，正在等待执行器处理" if dispatched else "用例已创建，但暂无在线设备可执行",
        "dispatched": dispatched,
        "execution_id": case_execution_id
    }


# 步骤级调试：仅执行前 N 步（含当前步）
@router.post(
    "/cases/{case_id}/debug",
    summary="调试用例至指定步骤",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))],
)
async def debug_case(
    case_id: int,
    item: CaseDebugForm,
    user_info: dict = Depends(require_permissions(UI_CASE_EXECUTE)),
):
    """执行 steps[0:through_index+1] 后停止，支持使用编辑器中未保存的步骤。"""
    if not item.steps:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="步骤列表不能为空",
        )
    if item.through_index >= len(item.steps):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"through_index 超出范围（共 {len(item.steps)} 步）",
        )

    case_ = await Case.get_or_none(id=case_id, is_del=False)
    if not case_:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="目标用例不存在或已被移除",
        )
    await assert_user_project_member(user_info, case_.project_id)

    env = assert_environment_for_project(
        await Environment.get_or_none(id=item.env_id, is_del=False),
        case_.project_id,
    )

    debug_steps = await ExecutionService.expand_steps_or_raise(
        item.steps[: item.through_index + 1], case_.project_id
    )
    env_payload = await ExecutionService.build_env_payload(
        env,
        item.browser_type,
        item.config,
        case_.project_id,
        item.ai_heal_enabled,
        item.ai_act_enabled,
        item.failure_analysis_on_report,
        item.ui_timeout_scale,
    )
    env_payload["debug_mode"] = True
    env_payload["debug_through_index"] = item.through_index
    env_payload["device_id"] = item.device_id

    async with transactions.in_transaction():
        await lock_device_row(item.device_id)
        await assert_device_available_for_ui_execution(item.device_id)
        case_execution = await UiCaseExecution.create(
            case=case_,
            username=item.username,
            env=env_payload,
            is_del=False,
        )
        case_id_db = case_.id
        case_name = case_.name
        case_execution_id = case_execution.id

    suite_payload = {
        "id": case_id_db,
        "name": f"{case_name}（调试至第 {item.through_index + 1} 步）",
        "case_execution_id": case_execution_id,
        "pre_actions": [],
        "username": item.username,
        "cases": [
            {
                "execution_id": case_execution_id,
                "id": case_id_db,
                "name": case_name,
                "skip": False,
                "steps": debug_steps,
            }
        ],
    }

    dispatched = await ExecutionService.dispatch_to_device(
        env_payload, suite_payload, item.device_id
    )

    return {
        "msg": "调试任务已加入执行队列" if dispatched else "调试记录已创建，但暂无在线设备可执行",
        "dispatched": dispatched,
        "execution_id": case_execution_id,
        "through_index": item.through_index,
        "step_count": len(debug_steps),
    }


# 运行测试套件
@router.post("/suites/{suite_id}", summary="执行套件", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(UI_SUITE_EXECUTE))])
async def run_suite(
    suite_id: int,
    item: RunForm,
    user_info: dict = Depends(require_permissions(UI_SUITE_EXECUTE)),
):
    """运行测试套件"""
    suite_ = await Suite.get_or_none(id=suite_id, is_del=False).prefetch_related("steps")
    if not suite_:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="目标套件不存在或已被移除"
        )
    await assert_user_project_member(user_info, suite_.project_id)

    env = assert_environment_for_project(
        await Environment.get_or_none(id=item.env_id, is_del=False),
        suite_.project_id,
    )

    env_payload = await ExecutionService.build_env_payload(
        env,
        item.browser_type,
        item.config,
        suite_.project_id,
        item.ai_heal_enabled,
        item.ai_act_enabled,
        item.failure_analysis_on_report,
        item.ui_timeout_scale,
    )
    env_payload = ExecutionService.with_trigger_source(env_payload, item.trigger_source)
    env_payload["device_id"] = item.device_id

    # 设备行锁仅覆盖占用检查与执行记录创建；步骤展开 / setup_sql / MQ 下发在锁外
    case_rows: list[tuple[Any, Any, Any]] = []
    async with transactions.in_transaction():
        await lock_device_row(item.device_id)
        await assert_device_available_for_ui_execution(item.device_id)

        suite_record = await UiSuiteExecution.create(
            suite=suite_,
            username=item.username,
            env=env_payload,
            device_id=item.device_id,
            is_del=False
        )

        for step in await suite_.steps.filter(is_del=False).order_by("sort"):
            case_ = await step.cases
            if case_.is_del:
                continue
            case_execution = await UiCaseExecution.create(
                case=case_,
                username=item.username,
                suite_execution=suite_record,
                env=env_payload,
                is_del=False
            )
            case_rows.append((case_execution, case_, step))

        suite_record.case_count = len(case_rows)
        await suite_record.save()
        suite_record_id = suite_record.id
        project_id = suite_.project_id

    if not case_rows:
        suite_record.status = "执行完成"
        await suite_record.save()
        return {
            "msg": "套件中没有可执行的用例",
            "dispatched": False,
            "suite_record_id": suite_record_id,
        }

    cases = [
        await ExecutionService.build_case_item(case_execution, case_, step, project_id)
        for case_execution, case_, step in case_rows
    ]

    await ExecutionService.run_suite_setup_sql(suite_, item.env_id)

    suite_payload = await ExecutionService.build_suite_payload(
        suite_, suite_record, cases
    )

    dispatched = await ExecutionService.dispatch_to_device(
        env_payload, suite_payload, item.device_id
    )

    return {
        "msg": "套件已加入执行队列，正在等待执行器处理" if dispatched else "套件已创建，但暂无在线设备可执行",
        "dispatched": dispatched,
        "suite_record_id": suite_record_id
    }


# 运行测试计划
@router.post("/tasks/{task_id}", summary="执行任务", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(UI_TASK_EXECUTE))])
async def run_task(
    task_id: int,
    item: RunForm,
    user_info: dict = Depends(require_permissions(UI_TASK_EXECUTE)),
):
    """运行测试计划"""
    # 校验与计划编排/下发不得包在同一事务：嵌套 FOR UPDATE 会拖到最外层提交才放锁
    task_ = await Task.get_or_none(id=task_id, is_del=False).prefetch_related("suites", "project")
    if not task_:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="目标测试计划不存在或已被移除",
        )
    await assert_user_project_member(user_info, task_.project_id)
    assert_environment_for_project(
        await Environment.get_or_none(id=item.env_id, is_del=False),
        task_.project_id,
    )

    from app.modules.ui.ui_plan_runner import execute_ui_plan

    devices_payload = [
        {"device_id": d.device_id, "weight": d.weight, "concurrency": d.concurrency}
        for d in (item.devices or [])
    ]
    return await execute_ui_plan(
        task_,
        env_id=item.env_id,
        browser_type=item.browser_type,
        headless=item.config,
        username=item.username,
        device_id=item.device_id,
        devices=devices_payload,
        concurrency=item.concurrency,
        ai_heal_enabled=item.ai_heal_enabled,
        ai_act_enabled=item.ai_act_enabled,
        failure_analysis_on_report=item.failure_analysis_on_report,
        ui_timeout_scale=item.ui_timeout_scale,
        trigger_source=item.trigger_source,
    )


@router.post("/stop/{record_id}", summary="停止 UI 计划执行", status_code=status.HTTP_200_OK,
               dependencies=[Depends(require_permissions(UI_TASK_EXECUTE))])
async def stop_execution(
    record_id: int,
    user_info: dict = Depends(require_permissions(UI_TASK_EXECUTE)),
):
    """停止 UI 测试计划执行（通过 MQ 通知 Runner 真正中断）"""
    record = await UiPlanExecution.get_or_none(id=record_id, is_del=False)
    if not record:
        raise HTTPException(status_code=422, detail="执行记录不存在")
    await assert_user_project_member(user_info, record.project_id)
    return await stop_plan_execution(record_id)


@router.post("/stop/suite/{record_id}", summary="停止 UI 套件执行", status_code=status.HTTP_200_OK,
             dependencies=[Depends(require_permissions(UI_SUITE_EXECUTE))])
async def stop_suite_execution_route(
    record_id: int,
    user_info: dict = Depends(require_permissions(UI_SUITE_EXECUTE)),
):
    """停止 UI 套件执行"""
    record = await UiSuiteExecution.get_or_none(id=record_id, is_del=False).prefetch_related("suite")
    if not record:
        raise HTTPException(status_code=422, detail="套件执行记录不存在")
    suite = await record.suite
    if not suite:
        raise HTTPException(status_code=422, detail="套件执行记录不存在")
    await assert_user_project_member(user_info, suite.project_id)
    return await stop_suite_execution(record_id)


@router.post("/stop/case/{record_id}", summary="停止 UI 用例执行", status_code=status.HTTP_200_OK,
             dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))])
async def stop_case_execution_route(
    record_id: int,
    user_info: dict = Depends(require_permissions(UI_CASE_EXECUTE)),
):
    """停止 UI 单用例/调试执行"""
    record = await UiCaseExecution.get_or_none(id=record_id, is_del=False).prefetch_related("case")
    if not record:
        raise HTTPException(status_code=422, detail="用例执行记录不存在")
    case = await record.case
    if not case:
        raise HTTPException(status_code=422, detail="用例执行记录不存在")
    await assert_user_project_member(user_info, case.project_id)
    return await stop_case_execution(record_id)
