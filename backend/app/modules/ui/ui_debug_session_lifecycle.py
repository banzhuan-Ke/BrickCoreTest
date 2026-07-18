"""UI 交互调试会话：超时恢复、空闲关闭、僵尸清理。"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.infra.mq_producer import MQProducer
from app.models.ui import UiDebugSession

logger = logging.getLogger(__name__)

STALE_JOB_ID = "ui_debug_session_stale_cleanup"
STALE_RUNNING_SECONDS = 180
STALE_STARTING_SECONDS = 120
STALE_CLOSING_SECONDS = 60
CLOSE_STOP_RESEND_SECONDS = 30
UI_DEBUG_IDLE_MINUTES = int(os.getenv("UI_DEBUG_IDLE_MINUTES", "30"))
UI_DEBUG_IDLE_SECONDS = max(300, UI_DEBUG_IDLE_MINUTES * 60)
_ACTIVE_STATUSES = frozenset({"starting", "ready", "running", "closing"})

# Runner / 平台关闭原因 → 前端展示文案（last_result.message 单一来源）
_CLOSE_REASON_MESSAGES: dict[str, str] = {
    "browser_closed_by_user": "检测到浏览器窗口已关闭，调试会话已结束",
    "user_close": "调试浏览器已关闭",
    "用户关闭": "调试浏览器已关闭",
    "idle_timeout": "长时间无操作，调试会话已自动关闭",
    "空闲超时自动关闭": "长时间无操作，调试会话已自动关闭",
    "runner_idle_timeout": "调试会话在 Runner 侧空闲超时，已自动结束",
    "force_closed": "关闭耗时过长，系统已强制结束会话",
    "关闭超时，系统已强制结束会话": "关闭耗时过长，系统已强制结束会话",
    "stop_requested": "收到停止指令，调试会话已结束",
}


def close_message_for_reason(reason: str) -> str:
    text = (reason or "").strip()
    if not text:
        return _CLOSE_REASON_MESSAGES["user_close"]
    if text in _CLOSE_REASON_MESSAGES:
        return _CLOSE_REASON_MESSAGES[text]
    if "空闲" in text or "超时" in text:
        return _CLOSE_REASON_MESSAGES["idle_timeout"]
    return text


def build_closed_last_result(reason: str) -> dict[str, Any]:
    text = (reason or "").strip() or "user_close"
    return {
        "type": "closed",
        "reason": text,
        "message": close_message_for_reason(text),
    }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def resolve_idle_timeout_seconds(session: UiDebugSession) -> int:
    env = session.env if isinstance(session.env, dict) else {}
    raw = env.get("debug_idle_timeout_seconds")
    try:
        return max(300, int(raw or UI_DEBUG_IDLE_SECONDS))
    except (TypeError, ValueError):
        return UI_DEBUG_IDLE_SECONDS


def compute_idle_remaining_seconds(session: UiDebugSession) -> Optional[int]:
    if session.status != "ready":
        return None
    ref = session.update_time or session.create_time
    if not ref:
        return None
    elapsed = (utc_now() - as_utc(ref)).total_seconds()
    return max(0, int(resolve_idle_timeout_seconds(session) - elapsed))


def serialize_idle_meta(session: UiDebugSession) -> dict[str, Any]:
    timeout = resolve_idle_timeout_seconds(session)
    remaining = compute_idle_remaining_seconds(session)
    return {
        "idle_timeout_seconds": timeout,
        "idle_remaining_seconds": remaining,
    }


async def recover_stale_session(session: UiDebugSession) -> bool:
    """Runner 异常退出时，避免会话长期卡在中间态。返回是否已修改会话。"""
    now = utc_now()
    changed = False

    if session.status == "running" and session.update_time:
        elapsed = (now - as_utc(session.update_time)).total_seconds()
        if elapsed > STALE_RUNNING_SECONDS:
            session.status = "ready"
            session.pending_command = None
            if not session.error:
                session.error = "上次执行超时未收到 Runner 回调，已自动恢复为就绪"
            await session.save()
            return True
        return False

    ref_time = session.update_time or session.create_time
    if not ref_time:
        return False
    elapsed = (now - as_utc(ref_time)).total_seconds()

    if session.status == "starting" and elapsed > STALE_STARTING_SECONDS:
        session.status = "error"
        session.pending_command = None
        session.error = session.error or "浏览器启动超时，请关闭后重试"
        changed = True
    elif session.status == "closing" and elapsed > STALE_CLOSING_SECONDS:
        reason = "关闭超时，系统已强制结束会话"
        session.status = "closed"
        session.pending_command = None
        session.last_result = build_closed_last_result(reason)
        if not session.error:
            session.error = session.last_result.get("message")
        changed = True

    if changed:
        await session.save()
    return changed


def _send_stop_task(session: UiDebugSession) -> None:
    mq = MQProducer()
    try:
        mq.send_stop_task(session.device_id, debug_session_id=session.id)
    finally:
        mq.close()


async def request_close_session(session: UiDebugSession, *, reason: str = "") -> None:
    """发起关闭：标记 closing、写入 close 命令、通知 Runner 停止。"""
    if session.status in ("closed", "closing"):
        return

    pending = session.pending_command if isinstance(session.pending_command, dict) else {}
    session.status = "closing"
    session.pending_command = {
        "command_id": pending.get("command_id") or str(uuid.uuid4()),
        "action": "close",
        "status": "pending",
        "close_reason": reason,
        "stop_sent_at": utc_now().isoformat(),
    }
    await session.save()
    _send_stop_task(session)


async def resend_close_stop(session: UiDebugSession) -> None:
    pending = dict(session.pending_command or {})
    pending["stop_resent_at"] = utc_now().isoformat()
    session.pending_command = pending
    await session.save()
    _send_stop_task(session)


async def force_close_session(session: UiDebugSession, reason: str) -> None:
    if session.status not in ("closed",) and session.device_id:
        try:
            _send_stop_task(session)
        except Exception as exc:
            logger.warning(
                "[ui_debug_session] force_close 发送停止失败 session=%s: %s",
                session.id,
                exc,
            )
    session.status = "closed"
    session.pending_command = None
    session.last_result = build_closed_last_result(reason or "force_closed")
    if reason and not session.error:
        session.error = session.last_result.get("message")
    await session.save()


async def cleanup_stale_debug_sessions() -> dict[str, int]:
    """定时清理：恢复僵尸态、空闲自动关闭、关闭超时强制结束。"""
    counts = {"recovered": 0, "idle_closed": 0, "stop_resent": 0, "force_closed": 0}
    sessions = await UiDebugSession.filter(status__in=list(_ACTIVE_STATUSES)).all()
    now = utc_now()

    for session in sessions:
        if await recover_stale_session(session):
            counts["recovered"] += 1
            continue

        ref_time = session.update_time or session.create_time
        if not ref_time:
            continue
        elapsed = (now - as_utc(ref_time)).total_seconds()

        if session.status == "closing":
            pending = session.pending_command if isinstance(session.pending_command, dict) else {}
            if elapsed > STALE_CLOSING_SECONDS:
                await force_close_session(session, "关闭超时，系统已强制结束会话")
                counts["force_closed"] += 1
            elif elapsed > CLOSE_STOP_RESEND_SECONDS and not pending.get("stop_resent_at"):
                await resend_close_stop(session)
                counts["stop_resent"] += 1
            continue

        if session.status != "ready":
            continue

        idle_timeout = resolve_idle_timeout_seconds(session)
        if elapsed >= idle_timeout:
            await request_close_session(session, reason="空闲超时自动关闭")
            counts["idle_closed"] += 1
            logger.info(
                "[ui_debug_session] 空闲超时关闭: session_id=%s device=%s idle=%ss",
                session.id,
                session.device_id,
                int(elapsed),
            )

    if any(counts.values()):
        logger.info("[ui_debug_session] 定时清理: %s", counts)
    return counts


def register_debug_session_cleanup_job(scheduler) -> None:
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(
        cleanup_stale_debug_sessions,
        trigger=IntervalTrigger(minutes=3),
        id=STALE_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
