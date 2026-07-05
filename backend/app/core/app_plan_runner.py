"""App 测试计划执行编排（串行 / 多设备并行分套件）。"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException, status

from app.core.app_execution_env import build_case_env
from app.core.ui_task_dispatch import (
    device_weight_pairs,
    distribute_suite_indices_by_weight,
    normalize_device_assignments,
)
from app.models.app import AppCase, AppPlan, AppPlanExecution, AppCaseExecution, AppSuite, AppSuiteExecution, AppSuiteStep
from app.models.sys import Device, Environment


async def _count_runnable_cases(suite_: AppSuite) -> int:
    count = 0
    for step in await AppSuiteStep.filter(suite_id=suite_.id, is_del=False).order_by("sort"):
        case_ = await AppCase.get_or_none(id=step.case_id, is_del=False)
        if case_ and case_.project_id == suite_.project_id:
            count += 1
    return count


async def _validate_app_online_devices(device_assignments: list[tuple[str, int, int]]) -> None:
    seen_udids: dict[str, str] = {}
    for dev_id, _, _ in device_assignments:
        device = await Device.get_or_none(id=dev_id, is_del=False)
        if not device or device.status != "在线":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"执行器 {dev_id} 不存在或不在线",
            )
        types = device.runner_engine_types or ["web"]
        if "app" not in types:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"执行器 {dev_id} 不支持 App 自动化",
            )
        udid = (device.app_udid or "").strip()
        if not udid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"执行器 {dev_id} 未登记 app_udid",
            )
        if udid in seen_udids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"多台执行器登记了相同 UDID（{udid}）：{seen_udids[udid]} 与 {dev_id}",
            )
        seen_udids[udid] = dev_id


async def _ordered_plan_suites(plan_: AppPlan) -> list[AppSuite]:
    await plan_.fetch_related("suites")
    return [s for s in plan_.suites if not s.is_del and s.project_id == plan_.project_id]


async def execute_app_plan(
    plan_: AppPlan,
    *,
    env_id: int,
    username: str,
    run_form: Any,
    device_id: str | None = None,
    devices: list[dict[str, Any]] | None = None,
    concurrency: int = 1,
    trigger_source: Optional[str] = None,
    cronjob_id: Optional[str] = None,
) -> dict[str, Any]:
    """执行 App 测试计划。parallel=True 时按权重将套件分到多台 App Runner（一 UDID 一锁）。"""
    from app.core.ui_project_guard import assert_environment_for_project
    from app.routers.app.exec import AppExecutionService

    env = assert_environment_for_project(
        await Environment.get_or_none(id=env_id, is_del=False),
        plan_.project_id,
    )

    device_assignments = normalize_device_assignments(device_id, devices, default_concurrency=1)
    if not device_assignments:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请至少选择一个支持 App 的在线执行器",
        )
    if not plan_.parallel:
        device_assignments = [device_assignments[0]]
    # App 真机同一 UDID 仅允许单会话，并发固定为 1
    device_assignments = [(d, w, 1) for d, w, _ in device_assignments]

    await _validate_app_online_devices(device_assignments)

    primary_device = (
        device_assignments[0][0]
        if len(device_assignments) == 1
        else ",".join(d for d, _, _ in device_assignments)
    )

    env_payload = AppExecutionService.with_trigger_source(
        await AppExecutionService.build_env_payload(
            env, plan_.project_id, await Device.get(id=device_assignments[0][0]), run_form, plan_.record_video
        ),
        trigger_source,
    )
    env_payload["device_assignments"] = [
        {"device_id": d, "weight": w, "concurrency": 1} for d, w, _ in device_assignments
    ]

    plan_record = await AppPlanExecution.create(
        project_id=plan_.project_id,
        plan=plan_,
        username=username,
        env=env_payload,
        device_id=primary_device,
        cronjob_id=cronjob_id,
        is_del=False,
    )

    ordered_suites = await _ordered_plan_suites(plan_)
    suite_case_counts: list[int] = []
    for suite_ in ordered_suites:
        suite_case_counts.append(await _count_runnable_cases(suite_))

    if not ordered_suites:
        plan_record.status = "执行完成"
        plan_record.case_count = 0
        await plan_record.save()
        return {"msg": "计划中没有可执行的套件", "dispatched": False, "execution_id": plan_record.id}

    grouped_indices: dict[str, list[int]] = {d: [] for d, _, _ in device_assignments}
    weight_pairs = device_weight_pairs(device_assignments)
    if plan_.parallel and len(device_assignments) > 1:
        dev_indices = distribute_suite_indices_by_weight(suite_case_counts, weight_pairs)
        for idx, dev_idx in enumerate(dev_indices):
            grouped_indices[device_assignments[dev_idx][0]].append(idx)
    else:
        dev_id = device_assignments[0][0]
        grouped_indices[dev_id] = list(range(len(ordered_suites)))

    total_cases = 0
    dispatched_any = False

    for dev_id, _, _ in device_assignments:
        device = await Device.get(id=dev_id)
        dev_form = run_form.model_copy(update={"device_id": dev_id}) if hasattr(run_form, "model_copy") else run_form
        dev_env = AppExecutionService.with_trigger_source(
            await AppExecutionService.build_env_payload(
                env, plan_.project_id, device, dev_form, plan_.record_video
            ),
            trigger_source,
        )

        for idx in grouped_indices.get(dev_id, []):
            suite_ = ordered_suites[idx]
            steps = await AppSuiteStep.filter(suite_id=suite_.id, is_del=False).order_by("sort").all()
            suite_record = await AppSuiteExecution.create(
                suite=suite_,
                plan_execution=plan_record,
                username=username,
                env=dev_env,
                case_count=0,
                device_id=dev_id,
                is_del=False,
            )
            cases_payload = []
            for step in steps:
                case = await AppCase.get_or_none(id=step.case_id, is_del=False)
                if not case or case.project_id != plan_.project_id:
                    continue
                case_exec = await AppCaseExecution.create(
                    case=case,
                    suite_execution=suite_record,
                    username=username,
                    env=build_case_env(
                        dev_env,
                        case,
                        trigger_source=trigger_source,
                        cronjob_id=cronjob_id,
                    ),
                    is_del=False,
                )
                cases_payload.append(
                    await AppExecutionService.build_case_item(case_exec, case, step)
                )

            suite_record.case_count = len(cases_payload)
            await suite_record.save()
            total_cases += len(cases_payload)

            if not cases_payload:
                suite_record.status = "执行完成"
                await suite_record.save()
                continue

            try:
                await AppExecutionService.run_suite_setup_sql(suite_, env.id)
            except HTTPException as exc:
                suite_record.status = "执行完成"
                suite_record.error = len(cases_payload)
                suite_record.execution_log = [{"type": "setup_sql_failed", "message": str(exc.detail)}]
                await suite_record.save()
                continue

            suite_payload = await AppExecutionService.build_suite_payload(
                suite_, suite_record, cases_payload, plan_record
            )
            if await AppExecutionService.dispatch_to_device(dev_env, suite_payload, dev_id):
                dispatched_any = True
            else:
                suite_record.status = "执行完成"
                suite_record.error = len(cases_payload)
                suite_record.execution_log = [{"type": "dispatch_failed", "message": "执行器不可用，套件未下发"}]
                await suite_record.save()

    plan_record.case_count = total_cases
    await plan_record.save()

    if plan_.parallel and len(device_assignments) > 1:
        msg = (
            f"App 并行计划已分发到 {len(device_assignments)} 台设备"
            if dispatched_any
            else "App 计划已创建，但所选执行器均不可用"
        )
    else:
        msg = (
            "App 计划已加入执行队列"
            if dispatched_any
            else "App 计划已创建，暂无支持 App 的在线 Runner"
        )

    return {"msg": msg, "dispatched": dispatched_any, "execution_id": plan_record.id}
