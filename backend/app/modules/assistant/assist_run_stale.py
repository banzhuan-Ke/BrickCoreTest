"""僵死 Skill RunRecord 清理（超时仍 running）。"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _stale_minutes() -> int:
    raw = os.getenv("ASSIST_RUN_STALE_MINUTES", "30").strip()
    try:
        return max(5, min(24 * 60, int(raw)))
    except ValueError:
        return 30


async def cleanup_stale_skill_runs(*, minutes: int | None = None) -> int:
    """将超时仍为 running 的 RunRecord 置为 failed（stale_auto_closed）。"""
    from app.models.ai import AiSkillRunRecord

    mins = minutes if minutes is not None else _stale_minutes()
    cutoff = datetime.now() - timedelta(minutes=mins)
    rows = await AiSkillRunRecord.filter(status="running", create_time__lt=cutoff).all()
    if not rows:
        return 0
    count = 0
    for rec in rows:
        rec.status = "failed"
        rec.error_message = (rec.error_message or "")[:1800]
        if not rec.error_message:
            rec.error_message = "stale_auto_closed"
        elif "stale_auto_closed" not in rec.error_message:
            rec.error_message = f"{rec.error_message}; stale_auto_closed"
        await rec.save(update_fields=["status", "error_message"])
        count += 1
    logger.warning(
        "[assist] cleaned %s stale skill run(s) older than %s min", count, mins
    )
    return count


async def recover_stale_skill_runs_on_startup() -> int:
    try:
        return await cleanup_stale_skill_runs()
    except Exception as exc:
        logger.warning("[assist] stale skill run cleanup skipped: %s", exc)
        return 0
