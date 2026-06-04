"""UI 自动化执行停止（MQ 通知 Runner 真正中断）"""
from __future__ import annotations

from typing import Iterable, Optional, Set

from fastapi import HTTPException

from app.core.mq_producer import MQProducer
from app.models.sys import Device
from app.models.ui import UiCaseExecution, UiPlanExecution, UiSuiteExecution

STOPPABLE_PLAN_STATUSES = {"执行中", "等待执行"}
STOPPABLE_SUITE_STATUSES = {"执行中", "等待执行"}
STOPPABLE_CASE_STATUSES = {"running"}


async def _online_device_ids() -> list[str]:
    rows = await Device.filter(status="在线", is_del=False).values_list("id", flat=True)
    return list(rows)


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
    record = await UiPlanExecution.get_or_none(id=record_id, is_del=False)
    if not record:
        raise HTTPException(status_code=422, detail="执行记录不存在")
    if record.status not in STOPPABLE_PLAN_STATUSES:
        raise HTTPException(status_code=400, detail=f"当前状态「{record.status}」不可停止")

    device_ids: Set[str] = set()
    if record.device_id:
        device_ids.add(record.device_id)
    env = record.env if isinstance(record.env, dict) else {}
    if env.get("device_id"):
        device_ids.add(env["device_id"])
    if not device_ids:
        device_ids = set(await _online_device_ids())

    record.status = "已停止"
    if not record.device_id and device_ids:
        record.device_id = next(iter(device_ids))
    await record.save()

    await UiSuiteExecution.filter(
        plan_execution_id=record_id,
        is_del=False,
        status__in=list(STOPPABLE_SUITE_STATUSES),
    ).update(status="已停止")

    sent = _send_stop_to_devices(device_ids, plan_execution_id=record_id)
    return {"detail": "停止成功，已通知执行器中断", "devices_notified": sent}


async def stop_suite_execution(record_id: int) -> dict:
    record = await UiSuiteExecution.get_or_none(id=record_id, is_del=False)
    if not record:
        raise HTTPException(status_code=422, detail="套件执行记录不存在")
    if record.status not in STOPPABLE_SUITE_STATUSES:
        raise HTTPException(status_code=400, detail=f"当前状态「{record.status}」不可停止")

    device_ids: Set[str] = set()
    if record.device_id:
        device_ids.add(record.device_id)
    env = record.env if isinstance(record.env, dict) else {}
    if env.get("device_id"):
        device_ids.add(env["device_id"])
    if not device_ids:
        device_ids = set(await _online_device_ids())

    record.status = "已停止"
    if not record.device_id and device_ids:
        record.device_id = next(iter(device_ids))
    await record.save()

    await UiCaseExecution.filter(
        suite_execution_id=record_id,
        is_del=False,
        status__in=list(STOPPABLE_CASE_STATUSES),
    ).update(status="error")

    sent = _send_stop_to_devices(
        device_ids,
        plan_execution_id=record.plan_execution_id,
        suite_execution_id=record_id,
    )
    return {"detail": "停止成功，已通知执行器中断", "devices_notified": sent}


async def stop_case_execution(record_id: int) -> dict:
    record = await UiCaseExecution.get_or_none(id=record_id, is_del=False)
    if not record:
        raise HTTPException(status_code=422, detail="用例执行记录不存在")
    if record.status not in STOPPABLE_CASE_STATUSES:
        raise HTTPException(status_code=400, detail=f"当前状态「{record.status}」不可停止")

    env = record.env if isinstance(record.env, dict) else {}
    device_ids: Set[str] = set()
    if env.get("device_id"):
        device_ids.add(env["device_id"])
    if not device_ids:
        device_ids = set(await _online_device_ids())

    record.status = "error"
    await record.save()

    sent = _send_stop_to_devices(
        device_ids,
        suite_execution_id=record.suite_execution_id,
        case_execution_id=record_id,
    )
    return {"detail": "停止成功，已通知执行器中断", "devices_notified": sent}
