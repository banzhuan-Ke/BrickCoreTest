"""UI Runner 设备占用互斥：交互调试 vs 录制 vs UI 执行任务。"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from app.models.ui import UiCaseExecution, UiDebugSession, UiPlanExecution, UiSuiteExecution
from app.modules.ai.record_session_lifecycle import get_active_recording_on_device

_DEBUG_ACTIVE_STATUSES = frozenset({"starting", "ready", "running", "closing"})
_UI_RUNNING_SUITE_STATUSES = ("执行中", "等待执行")
_UI_RUNNING_PLAN_STATUSES = ("执行中", "等待执行")


async def get_active_debug_session(device_id: str) -> Optional[UiDebugSession]:
    if not device_id:
        return None
    return await UiDebugSession.filter(
        device_id=device_id,
        status__in=list(_DEBUG_ACTIVE_STATUSES),
    ).order_by("-id").first()


async def get_active_ui_execution_on_device(
    device_id: str,
    *,
    exclude_plan_id: Optional[int] = None,
) -> Optional[dict]:
    """查询设备上进行中的 UI 执行任务（计划/套件/单用例）。"""
    if not device_id:
        return None

    plan_q = UiPlanExecution.filter(
        device_id=device_id,
        status__in=_UI_RUNNING_PLAN_STATUSES,
        is_del=False,
    )
    if exclude_plan_id:
        plan_q = plan_q.exclude(id=exclude_plan_id)
    plan = await plan_q.order_by("-id").first()
    if plan:
        return {"kind": "plan", "id": plan.id, "label": f"计划执行 #{plan.id}"}

    suite_q = UiSuiteExecution.filter(
        device_id=device_id,
        status__in=_UI_RUNNING_SUITE_STATUSES,
        is_del=False,
    )
    if exclude_plan_id:
        suite_q = suite_q.exclude(plan_execution_id=exclude_plan_id)
    suite = await suite_q.order_by("-id").first()
    if suite:
        return {"kind": "suite", "id": suite.id, "label": f"套件执行 #{suite.id}"}

    running_cases = await UiCaseExecution.filter(
        status="running",
        is_del=False,
        suite_execution_id__isnull=True,
    ).all()
    for case_exec in running_cases:
        env = case_exec.env if isinstance(case_exec.env, dict) else {}
        if str(env.get("device_id") or "") == device_id:
            return {"kind": "case", "id": case_exec.id, "label": f"用例执行 #{case_exec.id}"}

    return None


async def assert_device_available_for_debug(device_id: str) -> None:
    """创建交互调试会话前：设备不得录制或执行 UI 任务。"""
    record = await get_active_recording_on_device(device_id)
    if record:
        raise HTTPException(
            status_code=409,
            detail=f"设备 {device_id} 正在录制 #{record.id}，请先停止录制",
        )

    ui_exec = await get_active_ui_execution_on_device(device_id)
    if ui_exec:
        raise HTTPException(
            status_code=409,
            detail=f"设备 {device_id} 正在{ui_exec['label']}，请等待完成后再开调试",
        )


async def assert_device_available_for_record(device_id: str) -> None:
    """启动录制前：设备不得有进行中的调试会话或其它录制。"""
    debug = await get_active_debug_session(device_id)
    if debug:
        raise HTTPException(
            status_code=409,
            detail=f"设备 {device_id} 已有进行中的调试会话 #{debug.id}，请先关闭",
        )

    record = await get_active_recording_on_device(device_id)
    if record:
        raise HTTPException(
            status_code=409,
            detail=f"设备 {device_id} 正在录制 #{record.id}，请先停止录制",
        )


async def assert_device_available_for_ui_execution(
    device_id: str,
    *,
    exclude_plan_id: Optional[int] = None,
) -> None:
    """下发 UI 执行任务前：设备不得调试或录制。"""
    debug = await get_active_debug_session(device_id)
    if debug:
        raise HTTPException(
            status_code=409,
            detail=f"设备 {device_id} 已有进行中的调试会话 #{debug.id}，请先关闭",
        )

    record = await get_active_recording_on_device(device_id)
    if record:
        raise HTTPException(
            status_code=409,
            detail=f"设备 {device_id} 正在录制 #{record.id}，请等待完成后再执行",
        )

    ui_exec = await get_active_ui_execution_on_device(
        device_id,
        exclude_plan_id=exclude_plan_id,
    )
    if ui_exec:
        raise HTTPException(
            status_code=409,
            detail=f"设备 {device_id} 正在{ui_exec['label']}，请等待完成后再提交任务",
        )
