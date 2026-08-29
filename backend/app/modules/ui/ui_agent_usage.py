"""UI Agent / 多轮探索 AI 使用记录：LLM 代理累计 + 任务结束时幂等写入。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.llm.ai_usage_log import log_ai_usage
from app.models.ai import AiUsageLog, UiAgentJob

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"done", "failed", "stopped"})


def _job_ref(job: UiAgentJob) -> dict:
    return dict(job.source_ref) if isinstance(job.source_ref, dict) else {}


def _usage_scene_for_job(job: UiAgentJob) -> str:
    if (job.source or "") == "ui_case_explore":
        return "ui_case_generate"
    return "ui_case_agent"


def _usage_mode_for_job(job: UiAgentJob) -> str:
    if (job.source or "") == "ui_case_explore":
        return "explore"
    return "agent"


def _usage_tokens_from_job(job: UiAgentJob, *, override: int | None = None) -> int:
    ref = _job_ref(job)
    acc = int(ref.get("llm_tokens_accumulated") or 0)
    runner = int(override if override is not None else job.tokens_used or 0)
    return max(acc, runner, 0)


async def _sync_job_tokens(job: UiAgentJob, *, override: int | None = None) -> int:
    resolved = _usage_tokens_from_job(job, override=override)
    if resolved > int(job.tokens_used or 0):
        job.tokens_used = resolved
        await job.save(update_fields=["tokens_used"])
    return resolved


async def _find_ui_agent_usage_log(job_id: int, scene: str) -> Optional[AiUsageLog]:
    rows = await AiUsageLog.filter(scene=scene).order_by("-id").limit(80)
    for row in rows:
        extra = row.extra if isinstance(row.extra, dict) else {}
        if int(extra.get("ui_agent_job_id") or 0) == int(job_id):
            return row
    return None


async def _load_usage_log_for_job(job: UiAgentJob, scene: str) -> Optional[AiUsageLog]:
    ref = _job_ref(job)
    log_id = ref.get("usage_log_id")
    if log_id:
        row = await AiUsageLog.get_or_none(id=int(log_id))
        if row:
            return row
    return await _find_ui_agent_usage_log(job.id, scene)


async def accumulate_ui_agent_llm_tokens(job: UiAgentJob, usage: Any) -> None:
    """LLM 代理每次转发成功后累计 token。"""
    tokens = 0
    if usage is not None:
        tokens = int(getattr(usage, "total_tokens", 0) or 0)
        if tokens <= 0 and isinstance(usage, dict):
            tokens = int(usage.get("total_tokens") or 0)
    if tokens <= 0:
        return
    ref = _job_ref(job)
    ref["llm_tokens_accumulated"] = int(ref.get("llm_tokens_accumulated") or 0) + tokens
    job.source_ref = ref
    job.tokens_used = int(job.tokens_used or 0) + tokens
    await job.save(update_fields=["source_ref", "tokens_used"])


async def ensure_ui_agent_usage_logged(
    job: UiAgentJob,
    *,
    config: Any = None,
    tokens: int | None = None,
    username: str | None = None,
) -> bool:
    """任务终态后写入/更新 AiUsageLog；失败也保留已消耗 token。"""
    if (job.status or "") not in _TERMINAL_STATUSES:
        return False

    ref = _job_ref(job)
    resolved_tokens = await _sync_job_tokens(job, override=tokens)
    scene = _usage_scene_for_job(job)
    mode = _usage_mode_for_job(job)
    status = "success" if job.status == "done" else "failed"
    logged_tokens = int(ref.get("usage_logged_tokens") or 0)
    logged_status = (ref.get("usage_logged_status") or "").strip()

    if ref.get("usage_logged"):
        if resolved_tokens <= logged_tokens and logged_status == status:
            return False
        row = await _load_usage_log_for_job(job, scene)
        if row:
            row.tokens_used = max(int(row.tokens_used or 0), resolved_tokens)
            if job.started_at and job.finished_at:
                row.duration_ms = max(
                    int(row.duration_ms or 0),
                    int((job.finished_at - job.started_at).total_seconds() * 1000),
                )
            row.status = status
            steps = job.steps_json if isinstance(job.steps_json, list) else []
            if job.status == "done":
                row.output_summary = f"生成 {len(steps)} 步"
            elif job.error_message:
                row.output_summary = str(job.error_message)[:500]
            await row.save()
            ref["usage_logged"] = True
            ref["usage_logged_at"] = datetime.now(timezone.utc).isoformat()
            ref["usage_logged_tokens"] = int(row.tokens_used or 0)
            ref["usage_logged_status"] = status
            ref["usage_log_id"] = row.id
            job.source_ref = ref
            await job.save(update_fields=["source_ref"])
            return True

    if config is None:
        from app.modules.ai.ai_scene_config import resolve_config_for_scene

        try:
            config = await resolve_config_for_scene(scene, job.ai_config_id)
        except Exception as exc:
            logger.warning("[ui_agent] resolve config for usage log failed job=%s: %s", job.id, exc)
            return False

    duration_ms = 0
    if job.started_at and job.finished_at:
        duration_ms = int((job.finished_at - job.started_at).total_seconds() * 1000)

    steps = job.steps_json if isinstance(job.steps_json, list) else []
    actor = (username or job.created_by or "").strip()
    output_summary = ""
    if job.status == "done":
        output_summary = f"生成 {len(steps)} 步"
    elif job.error_message:
        output_summary = str(job.error_message)[:500]

    try:
        await log_ai_usage(
            config,
            scene,
            username=actor,
            project_id=job.project_id,
            tokens_used=resolved_tokens,
            duration_ms=duration_ms,
            status=status,
            input_summary=(job.description or "")[:500],
            output_summary=output_summary,
            mode=mode,
            ui_agent_job_id=job.id,
            steps=len(steps),
        )
    except Exception as exc:
        logger.warning("[ui_agent] usage log failed job=%s: %s", job.id, exc)
        return False

    row = await _find_ui_agent_usage_log(job.id, scene)
    ref["usage_logged"] = True
    ref["usage_logged_at"] = datetime.now(timezone.utc).isoformat()
    ref["usage_logged_tokens"] = resolved_tokens
    ref["usage_logged_status"] = status
    if row:
        ref["usage_log_id"] = row.id
    job.source_ref = ref
    await job.save(update_fields=["source_ref"])
    return True
