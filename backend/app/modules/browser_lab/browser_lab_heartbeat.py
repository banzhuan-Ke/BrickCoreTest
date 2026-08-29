"""Browser Lab Runner 心跳超时检测（Phase 1-E）。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.core.platform import config as settings
from app.core.platform.datetime_utils import as_utc, now_app
from app.models.ai import BrowserLabTask

logger = logging.getLogger(__name__)


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


def _runner_dispatch_active(task: BrowserLabTask, cfg: dict) -> bool:
    """仅在本轮 started_at 已写入且已派发 Runner 后才做心跳巡检。"""
    if not as_utc(task.started_at):
        return False
    if task.engine == "browser_use_runner":
        return True
    if cfg.get("dispatch_status") == "runner":
        return True
    return False


def _runner_heartbeat_timeout_seconds(cfg: dict) -> int:
    """按任务步数/单步超时动态放宽；browser-use 单步可达数分钟。"""
    from app.modules.browser_dispatch import estimate_job_token_ttl_seconds

    max_steps = int(cfg.get("max_steps") or 25)
    step_timeout = int(cfg.get("step_timeout") or settings.BROWSER_LAB_STEP_TIMEOUT)
    floor = max(60, int(getattr(settings, "BROWSER_LAB_RUNNER_HEARTBEAT_TIMEOUT", 120)))
    per_step_budget = step_timeout * 2 + 120
    job_half = estimate_job_token_ttl_seconds(
        max_steps=max_steps,
        step_timeout=step_timeout,
    ) // 2
    return min(max(floor, per_step_budget), max(floor, job_half))


async def maybe_fail_stale_runner_task(task: BrowserLabTask) -> BrowserLabTask:
    """Runner 模式任务心跳超时则标记 failed。"""
    if task.status not in ("pending", "running"):
        return task
    cfg = task.config_json or {}
    if (cfg.get("run_mode") or "local").strip().lower() != "runner":
        return task
    if not _runner_dispatch_active(task, cfg):
        return task

    timeout = _runner_heartbeat_timeout_seconds(cfg)
    started_at = as_utc(task.started_at)
    last_hb = _parse_iso_ts(cfg.get("last_runner_heartbeat"))
    # 重跑可能复制了上一轮心跳；早于本轮 started_at 的一律忽略
    if last_hb and started_at and last_hb < started_at:
        last_hb = None
    if not last_hb:
        baseline = started_at or as_utc(getattr(task, "create_time", None))
        if not baseline:
            return task
        last_hb = baseline

    age = (datetime.now(timezone.utc) - last_hb).total_seconds()
    if age <= timeout:
        return task

    task.status = "failed"
    task.error_message = f"Runner 心跳超时（{int(age)}s 无响应，上限 {timeout}s）"
    task.result_summary = task.error_message
    task.finished_at = now_app()
    log = list(task.step_log or [])
    if not any(e.get("type") == "done" for e in log):
        log.append({"type": "done", "status": "failed", "summary": task.error_message})
    task.step_log = log
    await task.save(
        update_fields=["status", "error_message", "result_summary", "finished_at", "step_log"]
    )
    try:
        from app.modules.browser_lab.browser_lab_usage import ensure_browser_lab_usage_logged

        await ensure_browser_lab_usage_logged(task)
    except Exception as exc:
        logger.warning("[browser_lab] heartbeat fail usage log task=%s: %s", task.id, exc)
    return task
