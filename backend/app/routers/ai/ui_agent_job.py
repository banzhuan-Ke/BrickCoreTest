"""UI Agent Job API（Phase 2 · AI-AGENT-RUN）。"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.platform import config as settings
from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import AI_TEST_EXECUTE, AI_TEST_VIEW
from app.models.ai import UiAgentJob
from app.modules.ui.ui_agent_callback import handle_ui_agent_runner_callback
from app.modules.ui.ui_agent_dispatch import dispatch_ui_agent_to_runner, send_ui_agent_stop
from app.modules.ui.ui_agent_job_service import (
    create_ui_agent_job,
    is_job_terminal,
    job_to_dict,
    mark_job_running,
    request_stop_ui_agent_job,
)
from app.modules.ui.ui_agent_plan import plan_ui_agent_step
from app.schemas.ai import StandardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ui-agent-jobs", tags=["UI Agent 探索"])


class UiAgentPlanStepBody(BaseModel):
    accessibility_snapshot: str = Field(default="", max_length=200000)
    snapshot_type: str = Field(default="accessibility", max_length=32)
    executed_steps: list = Field(default_factory=list, max_length=80)
    current_url: str = Field(default="", max_length=500)
    step_index: int = Field(default=1, ge=1, le=50)
    stuck_hint: str = Field(default="", max_length=2000)


class UiExploreRoundBody(BaseModel):
    page_elements: list = Field(default_factory=list, max_length=500)
    executed_steps: list = Field(default_factory=list, max_length=80)
    current_url: str = Field(default="", max_length=500)
    round_index: int = Field(default=1, ge=1, le=10)


class UiAgentRunnerCallbackBody(BaseModel):
    event: str = Field(..., min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


def _extract_job_token(authorization: Optional[str], x_internal_token: Optional[str]) -> str:
    token = (x_internal_token or "").strip()
    if not token and authorization:
        auth = authorization.strip()
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else auth
    if not token:
        raise HTTPException(status_code=401, detail="缺少任务鉴权 token")
    return token


def _verify_job_token(job_id: int, token: str, *, project_id: int) -> dict[str, Any]:
    from app.modules.browser_dispatch import verify_internal_job_token

    data = verify_internal_job_token(token, expected_project_id=project_id)
    if str(data.get("job_id")) != str(job_id):
        raise HTTPException(status_code=403, detail="任务 token 与 job ID 不匹配")
    return data


async def _load_runner_job(job_id: int, token: str) -> UiAgentJob:
    job = await UiAgentJob.get_or_none(id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    _verify_job_token(job_id, token, project_id=job.project_id)
    return job


@router.get(
    "/{job_id}",
    summary="查询 UI Agent 任务",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_ui_agent_job(
    job_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = project_id or user_info.get("project_id") or user_info.get("current_project_id")
    job = await UiAgentJob.get_or_none(id=job_id, project_id=int(pid))
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    from app.modules.ui.ui_agent_heartbeat import maybe_fail_stale_runner_job

    job = await maybe_fail_stale_runner_job(job)
    from app.modules.ui.ui_agent_usage import ensure_ui_agent_usage_logged

    await ensure_ui_agent_usage_logged(job)
    return StandardResponse(data=job_to_dict(job))


@router.post(
    "/{job_id}/stop",
    summary="停止 UI Agent 任务",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def stop_ui_agent_job(
    job_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = project_id or user_info.get("project_id") or user_info.get("current_project_id")
    job = await UiAgentJob.get_or_none(id=job_id, project_id=int(pid))
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if is_job_terminal(job.status):
        return StandardResponse(data=job_to_dict(job), message="任务已结束")
    if job.run_mode == "runner" and job.device_id:
        send_ui_agent_stop(job.device_id, job.id)
    job = await request_stop_ui_agent_job(job.id)
    return StandardResponse(data=job_to_dict(job), message="任务已停止")


@router.get(
    "/{job_id}/stream",
    summary="SSE 订阅 UI Agent 进度（已废弃，请用 GET /{id} 轮询）",
    include_in_schema=False,
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def stream_ui_agent_job(
    job_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = project_id or user_info.get("project_id") or user_info.get("current_project_id")

    async def event_generator():
        from app.modules.ui.ui_agent_heartbeat import maybe_fail_stale_runner_job

        last_log = 0
        last_steps = 0
        idle = 0
        while True:
            job = await UiAgentJob.get_or_none(id=job_id, project_id=int(pid))
            if not job:
                yield f"data: {json.dumps({'type': 'error', 'message': '任务不存在'}, ensure_ascii=False)}\n\n"
                break
            job = await maybe_fail_stale_runner_job(job)
            agent_log = job.agent_log_json or []
            steps = job.steps_json or []
            while last_log < len(agent_log):
                evt = agent_log[last_log]
                last_log += 1
                yield f"data: {json.dumps({'type': 'progress', 'entry': evt}, ensure_ascii=False)}\n\n"
            if len(steps) > last_steps:
                new_steps = steps[last_steps:]
                last_steps = len(steps)
                yield f"data: {json.dumps({'type': 'steps', 'steps': new_steps, 'total': last_steps}, ensure_ascii=False)}\n\n"
            if job.status in ("done", "failed", "stopped"):
                yield f"data: {json.dumps({'type': 'done', 'status': job.status, 'data': job_to_dict(job)}, ensure_ascii=False)}\n\n"
                break
            idle += 1
            if idle > 600:
                yield f"data: {json.dumps({'type': 'timeout'}, ensure_ascii=False)}\n\n"
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{job_id}/runner-plan", include_in_schema=False)
async def ui_agent_runner_plan(
    job_id: int,
    body: UiAgentPlanStepBody,
    authorization: Optional[str] = Header(None),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
):
    """Runner 侧单步规划（LLM 在平台）。"""
    token = _extract_job_token(authorization, x_internal_token)
    job = await _load_runner_job(job_id, token)
    if job.status in ("failed", "stopped", "done"):
        raise HTTPException(status_code=400, detail="任务已结束")

    from app.routers.ai.generate import _call_llm, _get_ai_config
    from app.modules.ui.ui_agent_timeouts import resolve_ui_agent_plan_timeouts

    config = await _get_ai_config(job.ai_config_id, scene="ui_case_agent")
    llm_timeout, _plan_http = resolve_ui_agent_plan_timeouts(config)

    async def call_llm(system_prompt: str, user_prompt: str):
        return await _call_llm(
            system_prompt,
            user_prompt,
            config,
            min_timeout=llm_timeout,
            max_retries=1,
        )

    result = await plan_ui_agent_step(
        config=config,
        description=job.description,
        accessibility_snapshot=body.accessibility_snapshot,
        snapshot_type=body.snapshot_type,
        executed_steps=body.executed_steps,
        current_url=body.current_url,
        step_index=body.step_index,
        stuck_hint=body.stuck_hint,
        call_llm=call_llm,
    )
    if result.get("tokens"):
        job.tokens_used = int(job.tokens_used or 0) + int(result["tokens"])
        await job.save(update_fields=["tokens_used"])
    if job.status == "pending":
        await mark_job_running(job)
    return StandardResponse(data=result)


@router.post("/{job_id}/runner-explore-round", include_in_schema=False)
async def ui_agent_runner_explore_round(
    job_id: int,
    body: UiExploreRoundBody,
    authorization: Optional[str] = Header(None),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
):
    """Runner 侧单轮探索：平台 LLM 根据 DOM 生成一批步骤。"""
    token = _extract_job_token(authorization, x_internal_token)
    job = await _load_runner_job(job_id, token)
    if job.status in ("failed", "stopped", "done"):
        raise HTTPException(status_code=400, detail="任务已结束")
    if (job.source or "") != "ui_case_explore":
        raise HTTPException(status_code=400, detail="非多轮探索任务")

    from app.routers.ai.generate import _call_llm, _extract_json_array, _get_ai_config, _normalize_ui_steps
    from app.modules.ui.ui_agent_timeouts import resolve_ui_agent_plan_timeouts
    from app.modules.ui.ui_explore_round import generate_explore_round_steps

    config = await _get_ai_config(job.ai_config_id, scene="ui_case_generate")
    llm_timeout, _plan_http = resolve_ui_agent_plan_timeouts(config)

    async def call_llm(system_prompt: str, user_prompt: str):
        return await _call_llm(
            system_prompt,
            user_prompt,
            config,
            min_timeout=llm_timeout,
            max_retries=1,
        )

    steps, tokens, _raw = await generate_explore_round_steps(
        config=config,
        description=job.description,
        page_elements=body.page_elements,
        executed_steps=body.executed_steps,
        current_url=body.current_url,
        round_index=body.round_index,
        call_llm=call_llm,
        normalize_steps=_normalize_ui_steps,
        extract_json_array=_extract_json_array,
    )
    if tokens:
        job.tokens_used = int(job.tokens_used or 0) + int(tokens)
        await job.save(update_fields=["tokens_used"])
    if job.status == "pending":
        await mark_job_running(job)
    return StandardResponse(data={"steps": steps, "tokens": tokens})


@router.post("/{job_id}/runner-callback", include_in_schema=False)
async def ui_agent_runner_callback(
    job_id: int,
    body: UiAgentRunnerCallbackBody,
    authorization: Optional[str] = Header(None),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
):
    token = _extract_job_token(authorization, x_internal_token)
    job = await _load_runner_job(job_id, token)
    updated = await handle_ui_agent_runner_callback(job, body.event, body.payload)
    return StandardResponse(data=job_to_dict(updated))


@router.post("/{job_id}/llm/v1/chat/completions", include_in_schema=False)
async def ui_agent_llm_proxy(
    job_id: int,
    request: Request,
    authorization: Optional[str] = Header(None),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
):
    """预留 OpenAI 兼容代理（Runner 直调 LLM 时使用）。"""
    token = _extract_job_token(authorization, x_internal_token)
    job = await _load_runner_job(job_id, token)

    from app.core.platform.encryption import decrypt_value
    from app.modules.ai.ai_scene_config import get_scene_llm_overrides, resolve_config_for_scene
    from app.modules.ai.browser_use_llm import build_deepseek_thinking_options, needs_openai_compat_for_browser_use
    from openai import AsyncOpenAI

    config = await resolve_config_for_scene("ui_case_agent", job.ai_config_id)
    scene_overrides = await get_scene_llm_overrides("ui_case_agent")
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="无效请求体")

    api_key = decrypt_value(config.api_key)
    base_url = (config.api_base or "").strip() or None
    llm_timeout = max(120, int(scene_overrides.get("timeout") or config.timeout or 180))
    extra_body, reasoning_effort = build_deepseek_thinking_options(config)
    create_kwargs = dict(body)
    if extra_body:
        merged = dict(extra_body)
        merged.update(create_kwargs.pop("extra_body", None) or {})
        create_kwargs["extra_body"] = merged
    if reasoning_effort:
        create_kwargs["reasoning_effort"] = reasoning_effort
    if needs_openai_compat_for_browser_use(config):
        create_kwargs.pop("tool_choice", None)

    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=float(llm_timeout))
    try:
        response = await client.chat.completions.create(**create_kwargs)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM 转发失败: {exc}") from exc

    usage = getattr(response, "usage", None)
    if usage is not None:
        from app.modules.ui.ui_agent_usage import accumulate_ui_agent_llm_tokens

        try:
            await accumulate_ui_agent_llm_tokens(job, usage)
        except Exception as exc:
            logger.warning("[ui_agent] llm token accumulate failed job=%s: %s", job_id, exc)

    return response.model_dump()
