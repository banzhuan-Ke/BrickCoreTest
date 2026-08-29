"""UI Agent Job Runner 心跳超时检测（与 Browser Lab 对齐）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.core.platform import config as settings
from app.core.platform.datetime_utils import as_utc
from app.models.ai import UiAgentJob
from app.modules.ui.ui_agent_job_service import finish_ui_agent_job, is_job_terminal


def _parse_iso_ts(raw: str | None) -> Optional[datetime]:
    if not raw:
        return None
    try:
        text = str(raw).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _job_ref(job: UiAgentJob) -> dict:
    return dict(job.source_ref) if isinstance(job.source_ref, dict) else {}


async def maybe_fail_stale_runner_job(job: UiAgentJob) -> UiAgentJob:
    """Runner 模式 ui_agent_job 心跳超时则标记 failed。"""
    if is_job_terminal(job.status):
        return job
    if (job.run_mode or "").strip().lower() != "runner":
        return job
    if not as_utc(job.started_at):
        return job

    timeout = max(60, int(getattr(settings, "BROWSER_LAB_RUNNER_HEARTBEAT_TIMEOUT", 120)))
    ref = _job_ref(job)
    started_at = as_utc(job.started_at)
    last_hb = _parse_iso_ts(ref.get("last_runner_heartbeat"))
    if last_hb and started_at and last_hb < started_at:
        last_hb = None
    if not last_hb:
        baseline = started_at or as_utc(job.create_time)
        if not baseline:
            return job
        last_hb = baseline

    age = (datetime.now(timezone.utc) - last_hb).total_seconds()
    if age <= timeout:
        return job

    return await finish_ui_agent_job(
        job,
        status="failed",
        error_message=f"Runner 心跳超时（{int(age)}s 无响应，上限 {timeout}s）",
    )
