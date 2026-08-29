"""智能浏览器 AI 使用记录：LLM 代理累计 + 任务结束时幂等写入。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.llm.ai_usage_log import log_ai_usage
from app.models.ai import AiUsageLog, BrowserLabTask

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"done", "failed", "stopped"})


def _task_cfg(task: BrowserLabTask) -> dict:
    return dict(task.config_json or {})


def _usage_tokens_from_task(task: BrowserLabTask, *, override: int | None = None) -> int:
    return resolve_browser_lab_tokens(task, runner_reported=override)


def resolve_browser_lab_tokens(
    task: BrowserLabTask, *, runner_reported: int | None = None
) -> int:
    """统一 Token 口径：LLM 代理累计与 Runner 终态上报取较大值。"""
    cfg = _task_cfg(task)
    acc = int(cfg.get("llm_tokens_accumulated") or 0)
    runner = int(
        runner_reported if runner_reported is not None else task.tokens_used or 0
    )
    return max(acc, runner, 0)


async def _sync_task_tokens(task: BrowserLabTask, *, override: int | None = None) -> int:
    resolved = _usage_tokens_from_task(task, override=override)
    if resolved > int(task.tokens_used or 0):
        task.tokens_used = resolved
        await task.save(update_fields=["tokens_used"])
    return resolved


async def _find_browser_lab_usage_log(task_id: int) -> Optional[AiUsageLog]:
    rows = await AiUsageLog.filter(scene="browser_lab").order_by("-id").limit(80)
    for row in rows:
        extra = row.extra if isinstance(row.extra, dict) else {}
        if int(extra.get("browser_lab_task_id") or 0) == int(task_id):
            return row
    return None


async def _load_usage_log_for_task(task: BrowserLabTask) -> Optional[AiUsageLog]:
    cfg = _task_cfg(task)
    log_id = cfg.get("usage_log_id")
    if log_id:
        row = await AiUsageLog.get_or_none(id=int(log_id))
        if row:
            return row
    return await _find_browser_lab_usage_log(task.id)


async def accumulate_browser_lab_llm_tokens(task: BrowserLabTask, usage: Any) -> None:
    """LLM 代理每次转发成功后累计 token（Runner 终态上报可能缺失或不准确）。"""
    tokens = 0
    if usage is not None:
        tokens = int(getattr(usage, "total_tokens", 0) or 0)
        if tokens <= 0 and isinstance(usage, dict):
            tokens = int(usage.get("total_tokens") or 0)
    if tokens <= 0:
        return
    cfg = _task_cfg(task)
    cfg["llm_tokens_accumulated"] = int(cfg.get("llm_tokens_accumulated") or 0) + tokens
    task.config_json = cfg
    task.tokens_used = int(task.tokens_used or 0) + tokens
    await task.save(update_fields=["config_json", "tokens_used"])


async def ensure_browser_lab_usage_logged(
    task: BrowserLabTask,
    *,
    config: Any = None,
    tokens: int | None = None,
    username: str | None = None,
) -> bool:
    """任务终态后写入/更新 AiUsageLog；失败/误标失败也保留已消耗 token。"""
    if (task.status or "") not in _TERMINAL_STATUSES:
        return False

    cfg = _task_cfg(task)
    resolved_tokens = await _sync_task_tokens(task, override=tokens)

    if (
        resolved_tokens <= 0
        and task.status == "done"
        and task.engine == "action_cache"
    ):
        if not cfg.get("usage_logged"):
            cfg["usage_logged"] = True
            cfg["usage_logged_tokens"] = 0
            cfg["usage_logged_status"] = "success"
            task.config_json = cfg
            await task.save(update_fields=["config_json"])
        return False

    status = "success" if task.status == "done" else "failed"
    logged_tokens = int(cfg.get("usage_logged_tokens") or 0)
    logged_status = (cfg.get("usage_logged_status") or "").strip()

    if cfg.get("usage_logged"):
        if resolved_tokens <= logged_tokens and logged_status == status:
            return False
        row = await _load_usage_log_for_task(task)
        if row:
            row.tokens_used = max(int(row.tokens_used or 0), resolved_tokens)
            if task.started_at and task.finished_at:
                row.duration_ms = max(
                    int(row.duration_ms or 0),
                    int((task.finished_at - task.started_at).total_seconds() * 1000),
                )
            row.status = status
            summary = (task.result_summary or task.error_message or "")[:500]
            if summary:
                row.output_summary = summary
            await row.save()
            cfg["usage_logged"] = True
            cfg["usage_logged_at"] = datetime.now(timezone.utc).isoformat()
            cfg["usage_logged_tokens"] = int(row.tokens_used or 0)
            cfg["usage_logged_status"] = status
            cfg["usage_log_id"] = row.id
            task.config_json = cfg
            await task.save(update_fields=["config_json"])
            return True

    if config is None:
        from app.modules.ai.ai_scene_config import resolve_config_for_scene

        ai_config_id = cfg.get("ai_config_id") or task.ai_config_id
        try:
            config = await resolve_config_for_scene("browser_lab", ai_config_id)
        except Exception as exc:
            logger.warning("[browser_lab] resolve config for usage log failed task=%s: %s", task.id, exc)
            return False

    duration_ms = 0
    if task.started_at and task.finished_at:
        duration_ms = int((task.finished_at - task.started_at).total_seconds() * 1000)

    actor = (username or task.created_by or "").strip()
    output_summary = (task.result_summary or task.error_message or "")[:500]
    try:
        await log_ai_usage(
            config,
            "browser_lab",
            username=actor,
            project_id=task.project_id,
            tokens_used=resolved_tokens,
            duration_ms=duration_ms,
            status=status,
            input_summary=(task.task_text or "")[:500],
            output_summary=output_summary,
            browser_lab_task_id=task.id,
            steps=task.steps_count,
            engine=task.engine or "",
        )
    except Exception as exc:
        logger.warning("[browser_lab] usage log failed task=%s: %s", task.id, exc)
        return False

    row = await _find_browser_lab_usage_log(task.id)
    cfg["usage_logged"] = True
    cfg["usage_logged_at"] = datetime.now(timezone.utc).isoformat()
    cfg["usage_logged_tokens"] = resolved_tokens
    cfg["usage_logged_status"] = status
    if row:
        cfg["usage_log_id"] = row.id
    task.config_json = cfg
    await task.save(update_fields=["config_json"])
    return True
