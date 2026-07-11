"""UI 交互调试会话 API（场景 B：手动就位 + 按步试跑）。"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.infra.mq_producer import MQProducer
from app.core.platform.auth import (
    resolve_current_username,
    verify_runner_or_internal,
    require_permissions,
)
from app.core.platform.permissions import UI_CASE_EXECUTE
from app.models.sys import Device, Environment
from app.models.ui import Case, UiDebugSession
from app.modules.ui.ui_project_guard import (
    assert_environment_for_project,
    assert_user_project_member,
    assert_user_project_viewer,
)
from app.modules.ui.ui_device_guard import assert_device_available_for_debug, get_active_debug_session
from app.modules.ui.ui_debug_steps import (
    compute_steps_fingerprint,
    resolve_debug_initial_url,
    resolve_debug_initial_url_with_variables,
)
from app.modules.ui.ui_debug_index_map import resolve_editor_indices_to_run_segments
from app.modules.ui.ui_debug_session_lifecycle import (
    UI_DEBUG_IDLE_SECONDS,
    recover_stale_session,
    request_close_session,
    serialize_idle_meta,
)
from app.core.shared.media_presign import presign_media_urls_in_result
from app.routers.ui.exec import ExecutionService
from app.schemas.ui import (
    DebugSessionCompareForm,
    DebugSessionCreateForm,
    DebugSessionPickModeForm,
    DebugSessionResolveRunForm,
    DebugSessionRunForm,
    DebugSessionStepActionForm,
    DebugSessionSyncForm,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debug", tags=["UI交互调试"])

_ACTIVE_STATUSES = frozenset({"starting", "ready", "running", "closing"})


class RunnerCallbackForm(BaseModel):
    command_id: Optional[str] = None
    event: str = Field(
        description="ready | step_result | steps_synced | highlight_result | verify_result | pick_result | pick_mode | closed | error"
    )
    payload: dict = Field(default_factory=dict)


def _serialize_session(session: UiDebugSession) -> dict[str, Any]:
    steps = session.steps or []
    env = session.env if isinstance(session.env, dict) else {}
    pending = session.pending_command if isinstance(session.pending_command, dict) else None
    pending_public = None
    if pending:
        pending_public = {
            "action": pending.get("action"),
            "status": pending.get("status"),
            "from_index": pending.get("from_index"),
            "through_index": pending.get("through_index"),
            "step_index": pending.get("step_index"),
        }
    return {
        "id": session.id,
        "case_id": session.case_id,
        "project_id": session.project_id,
        "device_id": session.device_id,
        "username": session.username,
        "status": session.status,
        "steps_count": len(steps),
        "steps_fingerprint": compute_steps_fingerprint(steps),
        "initial_url": resolve_debug_initial_url_with_variables(env, steps)
            or resolve_debug_initial_url(env, steps),
        "last_result": presign_media_urls_in_result(session.last_result or {}),
        "pending_command": pending_public,
        "error": session.error,
        **serialize_idle_meta(session),
        "create_time": session.create_time.isoformat() if session.create_time else None,
        "update_time": session.update_time.isoformat() if session.update_time else None,
    }


async def _expand_editor_steps(session: UiDebugSession, raw_steps: list) -> list:
    return await ExecutionService.expand_steps_or_raise(raw_steps, session.project_id)


async def _get_open_session_on_device(device_id: str) -> Optional[UiDebugSession]:
    return await get_active_debug_session(device_id)


async def _recover_stale_session(session: UiDebugSession) -> None:
    await recover_stale_session(session)


async def _reject_if_still_active(
    session: Optional[UiDebugSession],
    detail_template: str,
) -> None:
    """创建新会话前：先尝试恢复僵尸态，仍活跃则 409。"""
    if not session:
        return
    await _recover_stale_session(session)
    if session.status in _ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail=detail_template.format(id=session.id))


async def _get_session_for_user(
    session_id: int,
    user_info: dict,
    *,
    require_execute: bool = False,
) -> UiDebugSession:
    session = await UiDebugSession.get_or_none(id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="调试会话不存在")
    if require_execute:
        await assert_user_project_member(user_info, session.project_id)
    else:
        await assert_user_project_viewer(user_info, session.project_id)
    await _recover_stale_session(session)
    return session


async def _dispatch_debug_command(
    session: UiDebugSession,
    action: str,
    payload: dict,
    *,
    session_status: str = "running",
) -> dict:
    if session.status == "closing":
        raise HTTPException(status_code=409, detail="会话正在关闭，无法执行新命令")
    pending = session.pending_command if isinstance(session.pending_command, dict) else None
    if pending and pending.get("status") in ("pending", "dispatched"):
        raise HTTPException(status_code=409, detail="上一条命令尚未执行，请稍候")

    command_id = str(uuid.uuid4())
    session.pending_command = {
        "command_id": command_id,
        "action": action,
        "status": "pending",
        **payload,
    }
    session.status = session_status
    await session.save()
    return {
        "session_id": session.id,
        "command_id": command_id,
        "action": action,
        "status": session.status,
    }


@router.post("/sessions", summary="打开交互调试浏览器", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))])
async def create_debug_session(
    body: DebugSessionCreateForm,
    request: Request,
    user_info: dict = Depends(require_permissions(UI_CASE_EXECUTE)),
):
    """在 Runner 上打开有头浏览器；不自动跑业务步骤，等待用户手动就位后按步试跑。"""
    steps = body.steps or []
    if not steps:
        raise HTTPException(status_code=422, detail="步骤列表不能为空")

    case = await Case.get_or_none(id=body.case_id, is_del=False)
    if not case:
        raise HTTPException(status_code=422, detail="用例不存在")
    await assert_user_project_member(user_info, case.project_id)

    device = await Device.get_or_none(id=body.device_id, status="在线", is_del=False)
    if not device:
        raise HTTPException(status_code=503, detail="指定的 Runner 设备不在线")
    types = device.runner_engine_types or ["web"]
    if "web" not in types:
        raise HTTPException(status_code=422, detail="该设备不支持 Web 自动化")

    existing = await _get_open_session_on_device(body.device_id)
    await _reject_if_still_active(
        existing,
        f"设备 {body.device_id} 已有进行中的调试会话 #{{id}}，请先关闭",
    )
    existing_case = await UiDebugSession.filter(
        case_id=case.id,
        status__in=list(_ACTIVE_STATUSES),
    ).order_by("-id").first()
    await _reject_if_still_active(
        existing_case,
        "用例已有进行中的调试会话 #{id}，请先关闭后再开新会话",
    )
    await assert_device_available_for_debug(body.device_id)

    env_obj = assert_environment_for_project(
        await Environment.get_or_none(id=body.env_id, is_del=False),
        case.project_id,
    )

    expanded_steps = await ExecutionService.expand_steps_or_raise(steps, case.project_id)
    env_payload = await ExecutionService.build_env_payload(
        env_obj,
        body.browser_type,
        body.config,
        case.project_id,
        body.ai_heal_enabled,
        body.ai_act_enabled,
    )
    env_payload["headless"] = False
    env_payload["device_id"] = body.device_id
    env_payload["debug_idle_timeout_seconds"] = UI_DEBUG_IDLE_SECONDS

    username = await resolve_current_username(user_info)

    session = await UiDebugSession.create(
        case_id=case.id,
        project_id=case.project_id,
        device_id=body.device_id,
        username=username,
        status="starting",
        env=env_payload,
        steps=expanded_steps,
        last_result={},
    )

    base_url = str(request.base_url).rstrip("/")
    callback_base = f"{base_url}/ui/debug/sessions/{session.id}"
    initial_url = resolve_debug_initial_url_with_variables(env_payload, expanded_steps)

    mq = MQProducer()
    try:
        mq.send_test_task(
            env_payload,
            {
                "task_type": "ui_debug_session",
                "debug_session_id": session.id,
                "steps": expanded_steps,
                "callback_base": callback_base,
                "max_idle_seconds": UI_DEBUG_IDLE_SECONDS,
                "auto_navigate": bool(body.auto_navigate),
                "initial_url": initial_url,
            },
            body.device_id,
        )
    except Exception as exc:
        session.status = "error"
        session.error = f"下发调试任务失败: {exc}"
        await session.save()
        raise HTTPException(status_code=500, detail=session.error) from exc
    finally:
        mq.close()

    return {"data": _serialize_session(session), "dispatched": True}


@router.get("/sessions/active", summary="查询用例进行中的调试会话",
            dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))])
async def get_active_case_debug_session(
    case_id: int,
    user_info: dict = Depends(require_permissions(UI_CASE_EXECUTE)),
):
    """刷新编辑页时恢复当前用例的活跃调试会话。"""
    case = await Case.get_or_none(id=case_id, is_del=False)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    await assert_user_project_viewer(user_info, case.project_id)

    session = await UiDebugSession.filter(
        case_id=case_id,
        status__in=list(_ACTIVE_STATUSES),
    ).order_by("-id").first()
    if not session:
        return {"data": None}
    await _recover_stale_session(session)
    if session.status not in _ACTIVE_STATUSES:
        return {"data": None}
    return {"data": _serialize_session(session)}


@router.get("/sessions/{session_id}", summary="查询调试会话",
            dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))])
async def get_debug_session(
    session_id: int,
    user_info: dict = Depends(require_permissions(UI_CASE_EXECUTE)),
):
    session = await _get_session_for_user(session_id, user_info)
    return {"data": _serialize_session(session)}


@router.post("/sessions/{session_id}/compare-steps", summary="比对编辑器步骤与会话快照",
             dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))])
async def compare_debug_steps(
    session_id: int,
    body: DebugSessionCompareForm,
    user_info: dict = Depends(require_permissions(UI_CASE_EXECUTE)),
):
    session = await _get_session_for_user(session_id, user_info)
    editor_steps = body.steps or []
    if not editor_steps:
        raise HTTPException(status_code=422, detail="步骤列表不能为空")

    expanded = await _expand_editor_steps(session, editor_steps)
    session_fp = compute_steps_fingerprint(session.steps or [])
    editor_fp = compute_steps_fingerprint(expanded)
    return {
        "data": {
            "stale": session_fp != editor_fp,
            "session_fingerprint": session_fp,
            "editor_fingerprint": editor_fp,
            "session_steps_count": len(session.steps or []),
            "editor_steps_count": len(expanded),
        }
    }


@router.post("/sessions/{session_id}/sync-steps", summary="同步编辑器步骤到调试会话",
             dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))])
async def sync_debug_steps(
    session_id: int,
    body: DebugSessionSyncForm,
    user_info: dict = Depends(require_permissions(UI_CASE_EXECUTE)),
):
    session = await _get_session_for_user(session_id, user_info, require_execute=True)
    if session.status != "ready":
        raise HTTPException(status_code=409, detail=f"会话状态为 {session.status}，无法同步步骤")

    editor_steps = body.steps or []
    if not editor_steps:
        raise HTTPException(status_code=422, detail="步骤列表不能为空")

    expanded = await _expand_editor_steps(session, editor_steps)
    session.steps = expanded
    data = await _dispatch_debug_command(session, "sync_steps", {"steps": expanded})

    return {
        "data": {
            **data,
            "steps_count": len(expanded),
            "steps_fingerprint": compute_steps_fingerprint(expanded),
        }
    }


@router.post("/sessions/{session_id}/highlight", summary="高亮选中步定位器",
             dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))])
async def highlight_debug_step(
    session_id: int,
    body: DebugSessionStepActionForm,
    user_info: dict = Depends(require_permissions(UI_CASE_EXECUTE)),
):
    session = await _get_session_for_user(session_id, user_info, require_execute=True)
    if session.status != "ready":
        raise HTTPException(status_code=409, detail=f"会话状态为 {session.status}，无法高亮")
    steps = session.steps or []
    if body.step_index >= len(steps):
        raise HTTPException(status_code=422, detail="step_index 超出步骤范围")
    data = await _dispatch_debug_command(session, "highlight", {"step_index": body.step_index})
    return {"data": data}


@router.post("/sessions/{session_id}/verify-locator", summary="验证选中步定位器（不执行动作）",
             dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))])
async def verify_debug_locator(
    session_id: int,
    body: DebugSessionStepActionForm,
    user_info: dict = Depends(require_permissions(UI_CASE_EXECUTE)),
):
    session = await _get_session_for_user(session_id, user_info, require_execute=True)
    if session.status != "ready":
        raise HTTPException(status_code=409, detail=f"会话状态为 {session.status}，无法验证")
    steps = session.steps or []
    if body.step_index >= len(steps):
        raise HTTPException(status_code=422, detail="step_index 超出步骤范围")
    data = await _dispatch_debug_command(session, "verify_locator", {"step_index": body.step_index})
    return {"data": data}


@router.post("/sessions/{session_id}/pick-mode", summary="开启/关闭元素拾取模式",
             dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))])
async def set_debug_pick_mode(
    session_id: int,
    body: DebugSessionPickModeForm,
    user_info: dict = Depends(require_permissions(UI_CASE_EXECUTE)),
):
    session = await _get_session_for_user(session_id, user_info, require_execute=True)
    if session.status != "ready":
        raise HTTPException(status_code=409, detail=f"会话状态为 {session.status}，无法切换拾取模式")
    data = await _dispatch_debug_command(session, "pick_mode", {"enabled": bool(body.enabled)})
    return {"data": data}


@router.post("/sessions/{session_id}/run", summary="执行指定步骤（保活浏览器）",
             dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))])
async def run_debug_steps(
    session_id: int,
    body: DebugSessionRunForm,
    user_info: dict = Depends(require_permissions(UI_CASE_EXECUTE)),
):
    session = await _get_session_for_user(session_id, user_info, require_execute=True)
    if session.status != "ready":
        raise HTTPException(status_code=409, detail=f"会话状态为 {session.status}，无法执行步骤")

    steps = session.steps or []
    through = body.through_index if body.through_index is not None else body.from_index
    if body.from_index < 0:
        raise HTTPException(status_code=422, detail="from_index 不能为负数")
    if body.from_index >= len(steps):
        raise HTTPException(status_code=422, detail="from_index 超出步骤范围")
    if through >= len(steps):
        raise HTTPException(status_code=422, detail="through_index 超出步骤范围")
    if through < body.from_index:
        raise HTTPException(status_code=422, detail="through_index 不能小于 from_index")

    data = await _dispatch_debug_command(
        session,
        "run",
        {"from_index": body.from_index, "through_index": through},
    )

    return {
        "data": {
            **data,
            "from_index": body.from_index,
            "through_index": through,
        }
    }


@router.post("/sessions/{session_id}/resolve-run-segments", summary="解析编辑器多选步骤为会话执行区间",
             dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))])
async def resolve_debug_run_segments(
    session_id: int,
    body: DebugSessionResolveRunForm,
    user_info: dict = Depends(require_permissions(UI_CASE_EXECUTE)),
):
    """将编辑器勾选的步骤下标映射为 Runner 会话（展开后）上的连续执行区间。"""
    session = await _get_session_for_user(session_id, user_info, require_execute=True)
    editor_steps = body.steps or []
    if not editor_steps:
        raise HTTPException(status_code=422, detail="步骤列表不能为空")
    if not body.editor_indices:
        raise HTTPException(status_code=422, detail="请至少选择一个步骤")

    expanded = await _expand_editor_steps(session, editor_steps)
    session_fp = compute_steps_fingerprint(session.steps or [])
    editor_fp = compute_steps_fingerprint(expanded)
    stale = session_fp != editor_fp

    segments, editor_map, invalid = await resolve_editor_indices_to_run_segments(
        editor_steps,
        body.editor_indices,
        session.project_id,
    )
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"以下步骤下标无效: {invalid}",
        )
    if not segments:
        raise HTTPException(status_code=422, detail="未能解析出可执行的步骤区间")

    editor_map_payload = [
        {"editor_index": idx, "from_index": pair[0], "through_index": pair[1]}
        for idx, pair in sorted(editor_map.items())
    ]
    return {
        "data": {
            "segments": [
                {"from_index": f, "through_index": t} for f, t in segments
            ],
            "editor_map": editor_map_payload,
            "stale": stale,
        }
    }


@router.post("/sessions/{session_id}/close", summary="关闭调试会话",
             dependencies=[Depends(require_permissions(UI_CASE_EXECUTE))])
async def close_debug_session(
    session_id: int,
    user_info: dict = Depends(require_permissions(UI_CASE_EXECUTE)),
):
    session = await _get_session_for_user(session_id, user_info, require_execute=True)
    if session.status == "closed":
        return {"data": _serialize_session(session)}
    if session.status == "closing":
        return {"data": _serialize_session(session), "closing": True}
    if session.status not in ("starting", "ready", "running", "error"):
        raise HTTPException(status_code=409, detail=f"会话状态为 {session.status}，无法关闭")

    await request_close_session(session, reason="用户关闭")

    return {"data": _serialize_session(session), "closing": True}


# ========== Runner 内部接口 ==========

@router.get("/sessions/{session_id}/runner-status", summary="Runner 校验会话")
async def runner_debug_status(
    session_id: int,
    _ctx: dict = Depends(verify_runner_or_internal),
):
    session = await UiDebugSession.get_or_none(id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="调试会话不存在")
    return {"data": {"id": session.id, "status": session.status}}


@router.get("/sessions/{session_id}/runner-command", summary="Runner 拉取待执行命令")
async def runner_poll_command(
    session_id: int,
    _ctx: dict = Depends(verify_runner_or_internal),
):
    session = await UiDebugSession.get_or_none(id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="调试会话不存在")
    await _recover_stale_session(session)

    cmd = session.pending_command
    if not isinstance(cmd, dict) or cmd.get("status") != "pending":
        return {"data": None}

    cmd = dict(cmd)
    cmd["status"] = "dispatched"
    session.pending_command = cmd
    await session.save()
    return {"data": cmd}


_RESULT_EVENTS = frozenset({
    "step_result",
    "steps_synced",
    "highlight_result",
    "verify_result",
    "pick_result",
    "pick_mode",
})


def _should_accept_runner_callback(session: UiDebugSession, event: str, command_id: Optional[str]) -> bool:
    """忽略与当前 pending 命令不匹配的过期回调，避免覆盖最新结果。"""
    if event not in _RESULT_EVENTS:
        return True
    pending = session.pending_command if isinstance(session.pending_command, dict) else None
    if not pending:
        return True
    pending_id = pending.get("command_id")
    if not pending_id or not command_id:
        return True
    if pending_id != command_id:
        logger.warning(
            "忽略过期 Runner 回调: session=%s event=%s pending=%s got=%s",
            session.id,
            event,
            pending_id,
            command_id,
        )
        return False
    return True


@router.post("/sessions/{session_id}/runner-callback", summary="Runner 上报调试事件")
async def runner_debug_callback(
    session_id: int,
    body: RunnerCallbackForm,
    _ctx: dict = Depends(verify_runner_or_internal),
):
    session = await UiDebugSession.get_or_none(id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="调试会话不存在")

    event = (body.event or "").strip().lower()
    payload = body.payload or {}

    if not _should_accept_runner_callback(session, event, body.command_id):
        return {"data": _serialize_session(session), "ignored": True}

    if event == "ready":
        session.status = "ready"
        session.error = None
        session.pending_command = None
    elif event == "step_result":
        session.status = "ready"
        session.last_result = {"type": "run", **payload}
        session.pending_command = None
        session.error = None
    elif event == "steps_synced":
        session.status = "ready"
        session.pending_command = None
    elif event == "highlight_result":
        session.status = "ready"
        session.last_result = {"type": "highlight", **payload}
        session.pending_command = None
        session.error = None
    elif event == "verify_result":
        session.status = "ready"
        session.last_result = {"type": "verify", **payload}
        session.pending_command = None
        session.error = None
    elif event == "pick_result":
        session.status = "ready"
        session.last_result = {"type": "pick", **payload}
        session.pending_command = None
        session.error = None
    elif event == "pick_mode":
        session.status = "ready"
        session.pending_command = None
    elif event == "closed":
        session.status = "closed"
        session.pending_command = None
    elif event == "error":
        session.status = "error"
        session.error = payload.get("message") or payload.get("error") or "调试会话异常"
        session.pending_command = None
    else:
        raise HTTPException(status_code=422, detail=f"未知 event: {event}")

    await session.save()
    return {"data": _serialize_session(session)}
