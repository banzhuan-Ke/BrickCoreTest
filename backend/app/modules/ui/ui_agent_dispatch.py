"""UI Agent Runner 派发。"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException

from app.core.infra.mq_producer import MQProducer
from app.core.platform import config as settings
from app.models.ai import UiAgentJob
from app.modules.browser_dispatch import (
    build_internal_token,
    estimate_job_token_ttl_seconds,
    read_headless_from_mapping,
    resolve_platform_base_url_async,
    validate_device_online,
)
from app.modules.ui.ui_agent_timeouts import resolve_ui_agent_plan_timeouts

logger = logging.getLogger(__name__)


def _read_job_platform_base(job: UiAgentJob) -> str | None:
    ref = job.source_ref if isinstance(job.source_ref, dict) else {}
    base = (ref.get("_platform_base_url") or "").strip().rstrip("/")
    return base or None


def _platform_callback_base(job_id: int, *, platform_base: str) -> str:
    return f"{platform_base.rstrip('/')}/ai/ui-agent-jobs/{job_id}"


async def build_ui_agent_runner_payload(job: UiAgentJob, *, config: Any) -> dict[str, Any]:
    device_id = (job.device_id or "").strip()
    if not device_id:
        raise HTTPException(status_code=400, detail="Runner 模式须选择在线执行设备")
    callback_base = _platform_callback_base(
        job.id,
        platform_base=await resolve_platform_base_url_async(
            request_base_url=_read_job_platform_base(job),
        ),
    )
    task_type = "ui_case_explore" if (job.source or "") == "ui_case_explore" else "ui_agent_explore"
    llm_timeout, plan_request_timeout = resolve_ui_agent_plan_timeouts(config)
    internal_token = build_internal_token(
        job_id=str(job.id),
        project_id=job.project_id,
        task_type=task_type,
        ttl_seconds=estimate_job_token_ttl_seconds(
            max_steps=int(job.max_steps or 15),
            step_timeout=max(120, llm_timeout),
        ),
    )
    return {
        "task_type": task_type,
        "ui_agent_job_id": job.id,
        "project_id": job.project_id,
        "page_url": job.page_url,
        "description": job.description,
        "max_steps": job.max_steps,
        "source": job.source,
        "source_ref": job.source_ref or {},
        "callback_base": callback_base,
        "internal_token": internal_token,
        "llm": {
            "mode": "proxy",
            "base_url": f"{callback_base}/llm/v1",
            "model": config.model,
            "timeout": llm_timeout,
        },
        "plan_request_timeout": plan_request_timeout,
        "ai_config_id": config.id,
    }


async def dispatch_ui_agent_to_runner(job: UiAgentJob, *, config: Any) -> None:
    if not settings.BROWSER_RUN_DISPATCH_ENABLED:
        raise HTTPException(status_code=400, detail="Runner 派发未启用")
    await validate_device_online(job.device_id)
    run_suite = await build_ui_agent_runner_payload(job, config=config)
    ref = job.source_ref if isinstance(job.source_ref, dict) else {}
    env_config = {
        "device_id": job.device_id,
        "headless": read_headless_from_mapping(ref),
        "browser_type": "chromium",
    }
    mq = MQProducer()
    try:
        mq.send_test_task(env_config, run_suite, job.device_id)
        logger.info("[ui_agent] dispatched job %s to device %s", job.id, job.device_id)
    except Exception as exc:
        logger.exception("[ui_agent] MQ dispatch failed job %s", job.id)
        raise HTTPException(status_code=500, detail=f"派发 Runner 任务失败: {exc}") from exc
    finally:
        mq.close()


def send_ui_agent_stop(device_id: str, job_id: int) -> None:
    did = (device_id or "").strip()
    if not did:
        return
    mq = MQProducer()
    try:
        mq.send_stop_task(did, ui_agent_job_id=job_id)
    except Exception as exc:
        logger.warning("[ui_agent] stop MQ failed job %s: %s", job_id, exc)
    finally:
        mq.close()
