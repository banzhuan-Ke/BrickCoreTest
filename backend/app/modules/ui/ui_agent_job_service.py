"""UI Agent Job 服务（Phase 2 · AI-AGENT-RUN）。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from app.models.ai import UiAgentJob

logger = logging.getLogger(__name__)

_ACTIVE = frozenset({"pending", "running"})
_TERMINAL = frozenset({"done", "failed", "stopped"})


def is_job_terminal(status: str | None) -> bool:
    return (status or "").strip().lower() in _TERMINAL


def job_stop_requested(job: UiAgentJob) -> bool:
    ref = job.source_ref if isinstance(job.source_ref, dict) else {}
    return bool(ref.get("stop_requested"))


def job_to_dict(job: UiAgentJob) -> dict[str, Any]:
    from app.modules.browser_dispatch import pop_internal_platform_base_url

    ref = pop_internal_platform_base_url(job.source_ref if isinstance(job.source_ref, dict) else {})
    explore_info = ref.get("explore_info") if isinstance(ref.get("explore_info"), dict) else None
    return {
        "id": job.id,
        "project_id": job.project_id,
        "source": job.source,
        "source_ref": ref,
        "status": job.status,
        "run_mode": job.run_mode,
        "device_id": job.device_id,
        "page_url": job.page_url,
        "description": job.description,
        "max_steps": job.max_steps,
        "steps": job.steps_json or [],
        "agent_log": job.agent_log_json or [],
        "explore_info": explore_info,
        "tokens_used": job.tokens_used,
        "error_message": job.error_message,
        "ai_config_id": job.ai_config_id,
        "created_by": job.created_by,
        "stop_requested": bool(ref.get("stop_requested")),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "create_time": job.create_time.isoformat() if job.create_time else None,
    }


async def create_ui_agent_job(
    *,
    project_id: int,
    page_url: str,
    description: str,
    max_steps: int,
    ai_config_id: Optional[int],
    created_by: str,
    run_mode: str = "local",
    device_id: Optional[str] = None,
    source: str = "ui_case_edit",
    source_ref: Optional[dict] = None,
) -> UiAgentJob:
    return await UiAgentJob.create(
        project_id=project_id,
        page_url=page_url.strip(),
        description=description.strip(),
        max_steps=max(1, min(int(max_steps), 30)),
        ai_config_id=ai_config_id,
        created_by=created_by or "",
        run_mode=(run_mode or "local").strip().lower(),
        device_id=(device_id or "").strip() or None,
        source=(source or "ui_case_edit").strip()[:64],
        source_ref=source_ref or {},
        status="pending",
        steps_json=[],
        agent_log_json=[],
    )


async def mark_job_running(job: UiAgentJob) -> UiAgentJob:
    job.status = "running"
    if not job.started_at:
        job.started_at = datetime.now(timezone.utc)
    await job.save(update_fields=["status", "started_at"])
    return job


async def append_agent_log(job_id: int, entry: dict[str, Any]) -> UiAgentJob:
    job = await UiAgentJob.get_or_none(id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Agent 任务不存在")
    log = list(job.agent_log_json or [])
    log.append(entry)
    job.agent_log_json = log
    await job.save(update_fields=["agent_log_json"])
    return job


async def append_committed_step(job_id: int, step: dict[str, Any]) -> UiAgentJob:
    job = await UiAgentJob.get_or_none(id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Agent 任务不存在")
    steps = list(job.steps_json or [])
    steps.append(step)
    job.steps_json = steps
    await job.save(update_fields=["steps_json"])
    return job


async def finish_ui_agent_job(
    job: UiAgentJob,
    *,
    status: str,
    error_message: Optional[str] = None,
    tokens_used: Optional[int] = None,
    steps: Optional[list] = None,
    agent_log: Optional[list] = None,
) -> UiAgentJob:
    job.status = status
    job.error_message = (error_message or "")[:4000] or None
    if tokens_used is not None:
        job.tokens_used = int(tokens_used)
    if steps is not None:
        job.steps_json = steps
    if agent_log is not None:
        job.agent_log_json = agent_log
    job.finished_at = datetime.now(timezone.utc)
    await job.save()
    return job


def prepend_agent_browser_steps(steps: list, start_url: str) -> list:
    """Runner/Agent 产出步骤补 open_browser / open_url 前缀。"""
    import time

    methods = {s.get("method") for s in steps if isinstance(s, dict)}
    prefix: list[dict] = []
    ts = int(time.time() * 1000)
    if "open_browser" not in methods:
        prefix.append({
            "id": f"step_{ts}_pre0",
            "keyword": "打开浏览器",
            "method": "open_browser",
            "desc": "打开浏览器",
            "params": {"browser_type": "chromium"},
            "children": [],
        })
    if "open_url" not in methods and (start_url or "").strip():
        url = start_url.strip()
        prefix.append({
            "id": f"step_{ts}_pre1",
            "keyword": "访问页面url",
            "method": "open_url",
            "desc": f"访问 {url}",
            "params": {"url": url, "wait_until": "domcontentloaded", "timeout": 30000},
            "children": [],
        })
    return prefix + list(steps)


async def request_stop_ui_agent_job(job_id: int) -> UiAgentJob:
    """标记停止请求并写日志；Runner/local 仍在跑时保持 running，由 worker 回调 stopped。"""
    job = await UiAgentJob.get_or_none(id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Agent 任务不存在")
    if job.status not in _ACTIVE:
        raise HTTPException(status_code=400, detail="任务已结束，无法停止")

    ref = dict(job.source_ref or {})
    ref["stop_requested"] = True
    ref["stop_requested_at"] = datetime.now(timezone.utc).isoformat()
    job.source_ref = ref
    await job.save(update_fields=["source_ref"])

    log = list(job.agent_log_json or [])
    log.append({
        "phase": "stop",
        "message": "用户已请求停止",
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    job.agent_log_json = log
    await job.save(update_fields=["agent_log_json"])
    return job


def _agent_step_fingerprint(step: dict) -> tuple:
    if not isinstance(step, dict):
        return ("", "")
    params = step.get("params") if isinstance(step.get("params"), dict) else {}
    loc = str(params.get("locator") or params.get("selector") or "").strip()
    val = str(params.get("value") or params.get("url") or params.get("script") or "").strip()
    return ((step.get("method") or "").strip(), loc, val)


def steps_match_agent_job(client_steps: list | None, job_steps: list | None) -> bool:
    """校验客户端步骤与 Agent job 产出一致（允许微调 desc，禁止改 method/语义参数）。"""
    if not isinstance(client_steps, list) or not isinstance(job_steps, list):
        return False
    if len(client_steps) != len(job_steps):
        return False
    for client_step, job_step in zip(client_steps, job_steps):
        if _agent_step_fingerprint(client_step) != _agent_step_fingerprint(job_step):
            return False
    return True
