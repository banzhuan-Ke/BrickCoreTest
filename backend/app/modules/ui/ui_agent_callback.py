"""UI Agent Runner 回调处理。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.models.ai import UiAgentJob
from app.modules.ui.ui_agent_job_service import (
    append_agent_log,
    append_committed_step,
    finish_ui_agent_job,
    is_job_terminal,
    job_stop_requested,
    mark_job_running,
    prepend_agent_browser_steps,
)
from app.modules.ui.ui_agent_completion_guard import (
    is_premature_agent_done,
    is_stepwise_ui_agent_job,
)

logger = logging.getLogger(__name__)


async def handle_ui_agent_runner_callback(
    job: UiAgentJob,
    event: str,
    payload: dict[str, Any],
) -> UiAgentJob:
    event = (event or "").strip().lower()
    payload = payload or {}

    if event == "heartbeat":
        if is_job_terminal(job.status):
            return job
        ref = dict(job.source_ref or {}) if isinstance(job.source_ref, dict) else {}
        ref["last_runner_heartbeat"] = datetime.now(timezone.utc).isoformat()
        job.source_ref = ref
        await job.save(update_fields=["source_ref"])
        return job

    if is_job_terminal(job.status):
        logger.debug("[ui_agent] ignore callback %s for terminal job %s", event, job.id)
        return job

    if event == "progress":
        if job.status == "pending":
            job = await mark_job_running(job)
        entry = {
            "phase": payload.get("phase") or "execute",
            "step_index": payload.get("step_index"),
            "message": payload.get("message") or "",
            "locator": payload.get("locator"),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        return await append_agent_log(job.id, entry)

    if event == "step_committed":
        step = payload.get("step")
        if isinstance(step, dict):
            job = await append_committed_step(job.id, step)
            await append_agent_log(
                job.id,
                {
                    "phase": "committed",
                    "step_index": payload.get("step_index"),
                    "message": step.get("desc") or step.get("method") or "",
                    "method": step.get("method"),
                },
            )
        job = await UiAgentJob.get(id=job.id)
        if job.status == "pending":
            job = await mark_job_running(job)
        return job

    if event in ("done", "fail", "stopped"):
        status = {"done": "done", "fail": "failed", "stopped": "stopped"}[event]
        job = await UiAgentJob.get(id=job.id)
        if job_stop_requested(job) and status in ("done", "failed"):
            status = "stopped"
        steps = payload.get("steps")
        if steps is None:
            steps = list(job.steps_json or [])
        error_message = (payload.get("error_message") or payload.get("message") or "").strip()
        meaningful_steps = [
            s
            for s in (steps if isinstance(steps, list) else [])
            if isinstance(s, dict)
            and (s.get("method") or "").strip() not in ("open_browser", "open_url")
        ]
        if (
            status == "done"
            and is_stepwise_ui_agent_job(job.source)
            and not meaningful_steps
        ):
            status = "failed"
            error_message = (
                "Agent 未产出有效操作步骤（可能误判目标已完成）。"
                "请检查任务描述或改用其他生成方式。"
            )
        elif (
            status == "done"
            and is_stepwise_ui_agent_job(job.source)
            and is_premature_agent_done(
                job.description or "",
                meaningful_steps,
                done_message=error_message or payload.get("message") or "",
            )
        ):
            status = "failed"
            error_message = (
                error_message
                or "Agent 步骤过少或未完整执行多步目标（如未填登录凭证、未搜索验证）。"
                "请提高最大步数后重试。"
            )
        if isinstance(steps, list) and status == "done":
            if (job.source or "") != "ui_case_explore":
                steps = prepend_agent_browser_steps(steps, job.page_url)
        agent_log = payload.get("agent_log")
        explore_info = payload.get("explore_info")
        if explore_info and isinstance(explore_info, dict):
            ref = dict(job.source_ref or {})
            ref["explore_info"] = explore_info
            job.source_ref = ref
            await job.save(update_fields=["source_ref"])
        if status == "stopped" and not error_message:
            error_message = "用户已停止"
        job = await finish_ui_agent_job(
            job,
            status=status,
            error_message=error_message or None,
            tokens_used=int(payload.get("tokens_used") or job.tokens_used or 0),
            steps=steps if isinstance(steps, list) else None,
            agent_log=agent_log if isinstance(agent_log, list) else None,
        )
        try:
            from app.modules.ui.ui_agent_usage import ensure_ui_agent_usage_logged

            await ensure_ui_agent_usage_logged(job, tokens=job.tokens_used)
        except Exception as exc:
            logger.warning("[ui_agent] callback usage log failed job=%s: %s", job.id, exc)
        return job

    logger.warning("[ui_agent] unknown callback event: %s", event)
    return job
