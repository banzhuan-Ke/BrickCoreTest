"""独立设备 APM 会话超时扫描：僵死会话标记终态、落库并释锁。"""

from __future__ import annotations

import logging
import os

from app.modules.app import device_apm_session_service as apm_sess
from app.modules.app.app_device_lock import release_device_lock, release_device_lock_by_holder

logger = logging.getLogger(__name__)

STALE_JOB_ID = "app_device_apm_stale_cleanup"
STALE_SCAN_SECONDS = int(os.getenv("APP_DEVICE_APM_STALE_SCAN_SECONDS", "60"))


async def cleanup_stale_device_apm_sessions() -> dict[str, int]:
    """扫描 active 集合 + 落库失败补偿队列（限流），避免打满服务器。"""
    closed = 0
    persisted = 0
    unlocked = 0
    scanned = 0
    persist_retried = 0

    try:
        session_ids = await apm_sess.list_active_session_ids()
    except Exception:
        logger.exception("APM stale scan: list active failed")
        return {
            "scanned": 0,
            "closed": 0,
            "persisted": 0,
            "unlocked": 0,
            "persist_retried": 0,
        }

    for session_id in session_ids:
        scanned += 1
        try:
            before = await apm_sess.get_session(session_id)
            if not before:
                continue
            before_status = str(before.get("status") or "")
            data = await apm_sess.fail_if_stale(session_id)
            if not data:
                continue
            status = str(data.get("status") or "")
            if status in ("finished", "failed") and before_status not in ("finished", "failed"):
                closed += 1
            if status not in ("finished", "failed"):
                continue

            result = await apm_sess.persist_session_to_db(data)
            if result == "ok":
                persisted += 1

            udid = str(data.get("app_udid") or "")
            try:
                await release_device_lock(udid, holder_type="apm", holder_id=session_id)
            except Exception:
                await release_device_lock_by_holder("apm", session_id)
            unlocked += 1
        except Exception:
            logger.exception("APM stale scan failed session=%s", session_id)

    # 落库失败补偿：每轮最多 N 条，失败会话已延长 TTL
    try:
        pending_ids = await apm_sess.list_persist_pending_session_ids()
    except Exception:
        logger.exception("APM persist pending list failed")
        pending_ids = []

    for session_id in pending_ids:
        try:
            data = await apm_sess.get_session(session_id)
            if not data:
                await apm_sess.clear_persist_pending(session_id)
                continue
            if str(data.get("status") or "") not in ("finished", "failed"):
                continue
            result = await apm_sess.persist_session_to_db(data)
            persist_retried += 1
            if result == "ok":
                persisted += 1
        except Exception:
            logger.exception("APM persist retry failed session=%s", session_id)

    if closed or persisted or persist_retried:
        logger.info(
            "APM stale scan scanned=%s closed=%s persisted=%s unlocked=%s persist_retried=%s",
            scanned,
            closed,
            persisted,
            unlocked,
            persist_retried,
        )
    return {
        "scanned": scanned,
        "closed": closed,
        "persisted": persisted,
        "unlocked": unlocked,
        "persist_retried": persist_retried,
    }


def register_device_apm_stale_job(scheduler) -> None:
    from apscheduler.triggers.interval import IntervalTrigger

    seconds = max(30, STALE_SCAN_SECONDS)
    scheduler.add_job(
        cleanup_stale_device_apm_sessions,
        trigger=IntervalTrigger(seconds=seconds),
        id=STALE_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
