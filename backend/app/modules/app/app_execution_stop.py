"""App 自动化执行停止（MQ 通知 Runner 中断）"""
from __future__ import annotations

from typing import Iterable, Optional, Set

from fastapi import HTTPException

from app.core.infra.mq_producer import MQProducer
from app.modules.app.app_device_lock import release_device_lock
from app.models.app import AppCaseExecution, AppPlanExecution, AppSuiteExecution
from app.models.sys import Device

STOPPABLE_PLAN_STATUSES = {"执行中", "等待执行"}
STOPPABLE_SUITE_STATUSES = {"执行中", "等待执行"}
STOPPABLE_CASE_STATUSES = {"running"}


def _split_device_ids(raw: str | None) -> Set[str]:
    ids: Set[str] = set()
    if not raw:
        return ids
    for part in str(raw).split(","):
        part = part.strip()
        if part:
            ids.add(part)
    return ids


async def _collect_plan_device_ids(record: AppPlanExecution) -> Set[str]:
    device_ids: Set[str] = set()
    env = record.env if isinstance(record.env, dict) else {}

    if env.get("device_id"):
        device_ids.add(str(env["device_id"]))

    device_ids.update(_split_device_ids(record.device_id))

    suite_device_ids = await AppSuiteExecution.filter(
        plan_execution_id=record.id,
        is_del=False,
    ).exclude(device_id=None).values_list("device_id", flat=True)
    for did in suite_device_ids:
        if did:
            device_ids.update(_split_device_ids(str(did)))

    return device_ids


def _send_stop_to_devices(
    device_ids: Iterable[str],
    *,
    plan_execution_id: Optional[int] = None,
    suite_execution_id: Optional[int] = None,
    case_execution_id: Optional[int] = None,
) -> int:
    targets = list(device_ids)
    if not targets:
        return 0
    mq = MQProducer()
    try:
        for device_id in targets:
            mq.send_stop_task(
                device_id,
                plan_execution_id=plan_execution_id,
                suite_execution_id=suite_execution_id,
                case_execution_id=case_execution_id,
            )
    finally:
        mq.close()
    return len(targets)


async def stop_plan_execution(record_id: int) -> dict:
    record = await AppPlanExecution.get_or_none(id=record_id, is_del=False)
    if not record:
        raise HTTPException(status_code=422, detail="执行记录不存在")
    if record.status not in STOPPABLE_PLAN_STATUSES:
        raise HTTPException(status_code=400, detail=f"当前状态「{record.status}」不可停止")

    device_ids = await _collect_plan_device_ids(record)

    record.status = "已停止"
    if not record.device_id and device_ids:
        record.device_id = next(iter(device_ids))
    await record.save()

    await AppSuiteExecution.filter(
        plan_execution_id=record_id,
        is_del=False,
        status__in=list(STOPPABLE_SUITE_STATUSES),
    ).update(status="已停止")

    stopped_suite_ids = await AppSuiteExecution.filter(
        plan_execution_id=record_id,
        is_del=False,
        status="已停止",
    ).values_list("id", flat=True)
    if stopped_suite_ids:
        await AppCaseExecution.filter(
            suite_execution_id__in=list(stopped_suite_ids),
            is_del=False,
            status__in=list(STOPPABLE_CASE_STATUSES),
        ).update(status="no_run")

    sent = _send_stop_to_devices(device_ids, plan_execution_id=record_id)
    await _release_plan_exec_locks(record_id)
    detail = "停止成功，已通知执行器中断" if sent else "停止成功，但未找到可通知的执行设备"
    return {"detail": detail, "devices_notified": sent}


async def stop_suite_execution(record_id: int) -> dict:
    record = await AppSuiteExecution.get_or_none(id=record_id, is_del=False)
    if not record:
        raise HTTPException(status_code=422, detail="套件执行记录不存在")
    if record.status not in STOPPABLE_SUITE_STATUSES:
        raise HTTPException(status_code=400, detail=f"当前状态「{record.status}」不可停止")

    device_ids: Set[str] = set()
    device_ids.update(_split_device_ids(record.device_id))
    env = record.env if isinstance(record.env, dict) else {}
    if env.get("device_id"):
        device_ids.add(str(env["device_id"]))

    record.status = "已停止"
    if not record.device_id and device_ids:
        record.device_id = next(iter(device_ids))
    await record.save()

    await AppCaseExecution.filter(
        suite_execution_id=record_id,
        is_del=False,
        status__in=list(STOPPABLE_CASE_STATUSES),
    ).update(status="no_run")

    sent = _send_stop_to_devices(
        device_ids,
        plan_execution_id=record.plan_execution_id,
        suite_execution_id=record_id,
    )
    await _release_suite_exec_lock(record)
    detail = "停止成功，已通知执行器中断" if sent else "停止成功，但未找到可通知的执行设备"
    return {"detail": detail, "devices_notified": sent}


async def stop_case_execution(record_id: int) -> dict:
    record = await AppCaseExecution.get_or_none(id=record_id, is_del=False)
    if not record:
        raise HTTPException(status_code=422, detail="用例执行记录不存在")
    if record.status not in STOPPABLE_CASE_STATUSES:
        raise HTTPException(status_code=400, detail=f"当前状态「{record.status}」不可停止")

    env = record.env if isinstance(record.env, dict) else {}
    device_ids: Set[str] = set()
    if env.get("device_id"):
        device_ids.add(str(env["device_id"]))

    record.status = "no_run"
    await record.save()

    sent = _send_stop_to_devices(
        device_ids,
        suite_execution_id=record.suite_execution_id,
        case_execution_id=record_id,
    )
    await _release_case_exec_lock(record)
    detail = "停止成功，已通知执行器中断" if sent else "停止成功，但未找到可通知的执行设备"
    return {"detail": detail, "devices_notified": sent}


async def stop_executions_for_device(device_id: str) -> dict:
    """管理员强制停止设备时，联动停止该设备上的进行中 App 执行。"""
    device_id = (device_id or "").strip()
    if not device_id:
        return {"plans_stopped": 0, "suites_stopped": 0, "cases_stopped": 0}

    plans_stopped = 0
    suites_stopped = 0
    cases_stopped = 0

    plan_records = await AppPlanExecution.filter(
        is_del=False,
        status__in=list(STOPPABLE_PLAN_STATUSES),
    ).all()
    for plan in plan_records:
        if device_id in await _collect_plan_device_ids(plan):
            await stop_plan_execution(plan.id)
            plans_stopped += 1

    suite_records = await AppSuiteExecution.filter(
        is_del=False,
        status__in=list(STOPPABLE_SUITE_STATUSES),
        plan_execution_id=None,
    ).all()
    for suite in suite_records:
        env = suite.env if isinstance(suite.env, dict) else {}
        suite_devices = _split_device_ids(suite.device_id)
        if env.get("device_id"):
            suite_devices.add(str(env["device_id"]))
        if device_id in suite_devices:
            await stop_suite_execution(suite.id)
            suites_stopped += 1

    case_records = await AppCaseExecution.filter(
        is_del=False,
        status__in=list(STOPPABLE_CASE_STATUSES),
        suite_execution_id=None,
    ).all()
    for case_rec in case_records:
        env = case_rec.env if isinstance(case_rec.env, dict) else {}
        if str(env.get("device_id") or "") == device_id:
            await stop_case_execution(case_rec.id)
            cases_stopped += 1

    _send_stop_to_devices([device_id])
    return {
        "plans_stopped": plans_stopped,
        "suites_stopped": suites_stopped,
        "cases_stopped": cases_stopped,
    }


async def _release_suite_exec_lock(record: AppSuiteExecution) -> None:
    env = record.env if isinstance(record.env, dict) else {}
    udid = (env.get("device_udid") or "").strip()
    if not udid:
        return
    holder_id = str(record.plan_execution_id or record.id)
    await release_device_lock(udid, holder_type="exec", holder_id=holder_id)


async def _release_case_exec_lock(record: AppCaseExecution) -> None:
    """仅独立用例执行持有设备锁；套件/计划内用例不单独释放。"""
    if record.suite_execution_id:
        return
    env = record.env if isinstance(record.env, dict) else {}
    udid = (env.get("device_udid") or "").strip()
    if udid:
        await release_device_lock(udid, holder_type="exec", holder_id=str(record.id))


async def _release_plan_exec_locks(plan_id: int) -> None:
    plan = await AppPlanExecution.get_or_none(id=plan_id, is_del=False)
    if not plan:
        return
    env = plan.env if isinstance(plan.env, dict) else {}
    udid = (env.get("device_udid") or "").strip()
    if udid:
        await release_device_lock(udid, holder_type="exec", holder_id=str(plan_id))
