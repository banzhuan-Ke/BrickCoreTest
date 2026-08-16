"""执行器下线/失联后的联动收尾：调试会话、UI/App 在途执行、录制会话。"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Optional

from app.models.sys import Device

logger = logging.getLogger(__name__)

RUNNER_HEARTBEAT_TIMEOUT_SECONDS = int(os.getenv("RUNNER_HEARTBEAT_TIMEOUT_SECONDS", "300"))
STALE_DEVICE_JOB_ID = "runner_device_heartbeat_stale"


async def on_runner_device_offline(
    device_id: str,
    *,
    udid: Optional[str] = None,
) -> dict[str, Any]:
    """设备已离线后的业务收尾（幂等：终态记录不会被重复改坏）。"""
    device_id = (device_id or "").strip()
    summary: dict[str, Any] = {
        "debug_sessions": 0,
        "recordings": 0,
        "ui": {},
        "app": {},
    }
    if not device_id:
        return summary

    from app.modules.ui.ui_debug_session_lifecycle import close_debug_sessions_for_device
    from app.modules.ui.ui_execution_stale import close_inflight_ui_executions_for_device
    from app.modules.ai.record_session_lifecycle import fail_active_recordings_for_device

    try:
        summary["debug_sessions"] = await close_debug_sessions_for_device(
            device_id,
            reason="runner_offline",
            notify_runner=False,
        )
    except Exception as exc:
        logger.warning("下线收尾：关闭调试会话失败 device=%s: %s", device_id, exc)

    try:
        summary["recordings"] = await fail_active_recordings_for_device(device_id)
    except Exception as exc:
        logger.warning("下线收尾：结束录制失败 device=%s: %s", device_id, exc)

    try:
        summary["ui"] = await close_inflight_ui_executions_for_device(device_id)
    except Exception as exc:
        logger.warning("下线收尾：结束 UI 执行失败 device=%s: %s", device_id, exc)

    resolved_udid = (udid or "").strip()
    if not resolved_udid:
        device = await Device.get_or_none(id=device_id, is_del=False)
        if device:
            resolved_udid = (device.app_udid or "").strip()

    if resolved_udid:
        from app.modules.app.app_execution_stale import close_inflight_executions_for_udid

        try:
            summary["app"] = await close_inflight_executions_for_udid(resolved_udid)
        except Exception as exc:
            logger.warning("下线收尾：结束 App 执行失败 udid=%s: %s", resolved_udid, exc)

    if any(
        [
            summary["debug_sessions"],
            summary["recordings"],
            (summary.get("ui") or {}).get("cases"),
            (summary.get("ui") or {}).get("suites"),
            (summary.get("ui") or {}).get("plans"),
            (summary.get("app") or {}).get("cases"),
            (summary.get("app") or {}).get("suites"),
            (summary.get("app") or {}).get("plans"),
        ]
    ):
        logger.info("执行器下线联动收尾 device=%s summary=%s", device_id, summary)
    return summary


async def _mark_device_offline_row(device: Device) -> tuple[str, str]:
    """写离线状态并清空会话字段；返回原 MQ/Redis 用户名供吊销。"""
    mq_user = getattr(device, "runner_mq_username", None) or ""
    redis_user = getattr(device, "runner_redis_username", None) or ""
    await Device.filter(id=device.id).update(
        status="离线",
        runner_session_jti="",
        runner_bound_user_id=None,
        runner_mq_username="",
        runner_mq_password="",
        runner_redis_username="",
        runner_redis_password="",
    )
    return mq_user, redis_user


async def cleanup_stale_runner_heartbeats() -> dict[str, int]:
    """心跳超时：标离线 + 吊销凭证 + 业务收尾（覆盖进程被杀未调 disconnect 的情况）。

    默认 300s：客户端心跳约 30s 一次；过短会在心跳写库软降级（1205）时误杀仍在线的执行器。
    """
    timeout = max(120, RUNNER_HEARTBEAT_TIMEOUT_SECONDS)
    cutoff = datetime.now() - timedelta(seconds=timeout)
    marked = 0
    cleaned = 0

    devices = await Device.filter(
        status="在线",
        is_del=False,
        runner_last_heartbeat__lt=cutoff,
    ).all()

    from app.core.runner.runner_middleware import revoke_device_middleware

    for device in devices:
        udid = (getattr(device, "app_udid", None) or "").strip()
        try:
            mq_user, redis_user = await _mark_device_offline_row(device)
            marked += 1
        except Exception as exc:
            logger.warning("心跳超时标离线失败 device=%s: %s", device.id, exc)
            continue

        try:
            await revoke_device_middleware(
                device.id,
                mq_username=mq_user,
                redis_username=redis_user,
            )
        except Exception:
            pass

        try:
            await on_runner_device_offline(device.id, udid=udid)
            cleaned += 1
        except Exception as exc:
            logger.warning("心跳超时联动收尾失败 device=%s: %s", device.id, exc)

    if marked:
        logger.info(
            "[runner_heartbeat_stale] 心跳超时离线=%s 收尾=%s (>%ss)",
            marked,
            cleaned,
            timeout,
        )
    return {"marked_offline": marked, "cleaned": cleaned}


def register_runner_heartbeat_stale_job(scheduler) -> None:
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(
        cleanup_stale_runner_heartbeats,
        trigger=IntervalTrigger(seconds=30),
        id=STALE_DEVICE_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
