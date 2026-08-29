"""UI 交互调试会话命令下发（供 debug 路由与录制接录复用）。"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException

from app.models.ui import UiDebugSession

# 拖拽改步时高频下发：未派发给 Runner 前可互相覆盖，避免 409 刷屏
_LIGHT_ACTIONS = frozenset({"sync_steps", "select_step"})


def can_coalesce_pending_command(pending_action: str | None, new_action: str) -> bool:
    """仅当旧命令仍为 pending（未 dispatched）时可合并。"""
    old = (pending_action or "").strip()
    new = (new_action or "").strip()
    if new == "sync_steps":
        return old in _LIGHT_ACTIONS
    if new == "select_step":
        return old == "select_step"
    return False


async def dispatch_debug_command(
    session: UiDebugSession,
    action: str,
    payload: dict,
    *,
    session_status: str = "running",
    update_session_status: bool = True,
) -> dict[str, Any]:
    if session.status == "closing":
        raise HTTPException(status_code=409, detail="会话正在关闭，无法执行新命令")
    pending = session.pending_command if isinstance(session.pending_command, dict) else None
    if pending and pending.get("status") in ("pending", "dispatched"):
        if not (
            pending.get("status") == "pending"
            and can_coalesce_pending_command(pending.get("action"), action)
        ):
            raise HTTPException(status_code=409, detail="上一条命令尚未执行，请稍候")

    command_id = str(uuid.uuid4())
    session.pending_command = {
        "command_id": command_id,
        "action": action,
        "status": "pending",
        **payload,
    }
    if update_session_status:
        session.status = session_status
    await session.save()
    return {
        "session_id": session.id,
        "command_id": command_id,
        "action": action,
        "status": session.status,
    }
