"""UI 测试计划执行编排（串行 / 并行分设备）。"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException, status

from app.core.ui_task_dispatch import (
    device_weight_pairs,
    distribute_suite_indices_by_weight,
    max_device_concurrency,
    normalize_device_assignments,
)
from app.models.sys import Device, Environment
from app.models.ui import Suite, Task, UiCaseExecution, UiPlanExecution, UiSuiteExecution


async def _count_runnable_cases(suite_: Suite) -> int:
    count = 0
    for step in await suite_.steps.filter(is_del=False).order_by("sort"):
        case_ = await step.cases
        if case_ and not case_.is_del:
            count += 1
    return count


async def _validate_online_devices(device_assignments: list[tuple[str, int, int]]) -> None:
    for dev_id, _, _ in device_assignments:
        device = await Device.get_or_none(id=dev_id, is_del=False)
        if not device or device.status != "在线":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"执行器 {dev_id} 不存在或不在线",
            )
        types = device.runner_engine_types or ["web"]
        if "web" not in types:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"执行器 {dev_id} 未启用 Web 自动化，请选择勾选了 Web 的 Runner",
            )


async def _prepare_suite_execution(
    suite_: Suite,
    *,
    env_payload: dict[str, Any],
    username: str,
    device_id: str,
    plan_record: UiPlanExecution,
) -> tuple[UiSuiteExecution, list[dict[str, Any]], int]:
    from app.routers.ui.exec import ExecutionService

    suite_record = await UiSuiteExecution.create(
        suite=suite_,
        username=username,
        env=env_payload,
        device_id=device_id,
        plan_execution=plan_record,
        is_del=False,
    )
    cases: list[dict[str, Any]] = []
    for step in await suite_.steps.filter(is_del=False).order_by("sort"):
        case_ = await step.cases
        if not case_ or case_.is_del:
            continue
        case_execution = await UiCaseExecution.create(
            case=case_,
            username=username,
            suite_execution=suite_record,
            env=env_payload,
            is_del=False,
        )
        cases.append(
            await ExecutionService.build_case_item(
                case_execution, case_, step, suite_.project_id
            )
        )
    suite_record.case_count = len(cases)
    await suite_record.save()
    return suite_record, cases, len(cases)


async def _ordered_task_suites(task_: Task) -> list[Suite]:
    """返回任务关联套件列表（按 suite.id 稳定排序）。"""
    return list(await task_.suites.filter(is_del=False).order_by("id").all())


async def execute_ui_plan(
    task_: Task,
    *,
    env_id: int,
    browser_type: str | None,
    headless: bool,
    username: str,
    device_id: str | None = None,
    devices: list[dict[str, Any]] | None = None,
    concurrency: int = 1,
    ai_heal_enabled: Optional[bool] = None,
    trigger_source: Optional[str] = None,
    cronjob_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    执行 UI 测试计划。
    - task_.parallel=False：全部套件发往单一执行器，串行消费 MQ。
    - task_.parallel=True：按权重将套件分到多个执行器；Runner 可并发处理（plan_parallel）。
    - 单执行器可通过 concurrency>1 在同一设备上并发跑多个套件（如 4 套件并发 3，先 3 后 1）。
    """
    from app.routers.ui.exec import ExecutionService

    from app.core.ui_project_guard import assert_environment_for_project

    env = assert_environment_for_project(
        await Environment.get_or_none(id=env_id, is_del=False),
        task_.project_id,
    )

    device_assignments = normalize_device_assignments(
        device_id, devices, default_concurrency=concurrency
    )
    if not device_assignments:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请至少选择一个在线执行器",
        )
    if not task_.parallel:
        device_assignments = [device_assignments[0]]

    await _validate_online_devices(device_assignments)

    env_payload = await ExecutionService.build_env_payload(
        env,
        browser_type,
        headless,
        task_.project_id,
        ai_heal_enabled,
    )
    env_payload = ExecutionService.with_trigger_source(env_payload, trigger_source)
    if task_.parallel or max_device_concurrency(device_assignments) > 1:
        env_payload["plan_parallel"] = True
    env_payload["device_assignments"] = [
        {"device_id": d, "weight": w, "concurrency": c} for d, w, c in device_assignments
    ]

    primary_device = (
        device_assignments[0][0]
        if len(device_assignments) == 1
        else ",".join(d for d, _, _ in device_assignments)
    )
    plan_record = await UiPlanExecution.create(
        task=task_,
        username=username,
        env=env_payload,
        device_id=primary_device,
        project=task_.project,
        is_del=False,
        execution_log=[],
        cronjob_id=cronjob_id,
    )

    ordered_suites: list[Suite] = []
    suite_case_counts: list[int] = []
    for suite_ in await _ordered_task_suites(task_):
        suite_ = await Suite.get_or_none(id=suite_.id, is_del=False).prefetch_related("steps")
        if not suite_:
            continue
        ordered_suites.append(suite_)
        suite_case_counts.append(await _count_runnable_cases(suite_))

    if not ordered_suites:
        plan_record.case_count = 0
        await plan_record.save()
        return {"msg": "计划中没有可执行的套件", "task_record_id": plan_record.id}

    grouped_indices: dict[str, list[int]] = {d: [] for d, _, _ in device_assignments}
    weight_pairs = device_weight_pairs(device_assignments)
    if task_.parallel and len(device_assignments) > 1:
        dev_indices = distribute_suite_indices_by_weight(suite_case_counts, weight_pairs)
        for idx, dev_idx in enumerate(dev_indices):
            grouped_indices[device_assignments[dev_idx][0]].append(idx)
    else:
        dev_id = device_assignments[0][0]
        grouped_indices[dev_id] = list(range(len(ordered_suites)))

    total_cases = 0
    dispatched_any = False
    concurrency_by_device = {d: c for d, _, c in device_assignments}

    for dev_id, _, dev_concurrency in device_assignments:
        for idx in grouped_indices.get(dev_id, []):
            suite_ = ordered_suites[idx]
            dev_payload = dict(env_payload)
            dev_payload["device_id"] = dev_id
            dev_payload["device_concurrency"] = concurrency_by_device.get(dev_id, dev_concurrency)

            suite_record, cases, case_count = await _prepare_suite_execution(
                suite_,
                env_payload=dev_payload,
                username=username,
                device_id=dev_id,
                plan_record=plan_record,
            )
            total_cases += case_count

            if not cases:
                suite_record.status = "执行完成"
                await suite_record.save()
                continue

            try:
                await ExecutionService.run_suite_setup_sql(suite_, env_id)
            except HTTPException as exc:
                suite_record.status = "执行完成"
                suite_record.error = case_count
                suite_record.no_run = 0
                suite_record.execution_log = [{"type": "setup_sql_failed", "message": str(exc.detail)}]
                await suite_record.save()
                continue

            suite_payload = await ExecutionService.build_suite_payload(
                suite_, suite_record, cases, plan_record
            )
            if await ExecutionService.dispatch_to_device(dev_payload, suite_payload, dev_id):
                dispatched_any = True
            else:
                suite_record.status = "执行完成"
                suite_record.error = case_count
                suite_record.no_run = 0
                suite_record.execution_log = [{"type": "dispatch_failed", "message": "执行器不可用，套件未下发"}]
                await suite_record.save()

    plan_record.case_count = total_cases
    await plan_record.save()

    from app.core.runner_results import _reaggregate_plan_execution

    await _reaggregate_plan_execution(plan_record.id)

    if task_.parallel and len(device_assignments) > 1:
        msg = (
            f"并行计划已分发到 {len(device_assignments)} 个执行器，正在等待执行"
            if dispatched_any
            else "并行计划已创建，但所选执行器均不可用"
        )
    else:
        msg = (
            "测试计划已加入执行队列，正在等待执行器处理"
            if dispatched_any
            else "测试计划已创建，但暂无在线设备可执行"
        )

    return {
        "msg": msg,
        "dispatched": dispatched_any,
        "task_record_id": plan_record.id,
        "plan_execution_id": plan_record.id,
    }
