"""AI 生成 Mock 响应体"""
from __future__ import annotations

import json
import re
import time
import logging
from typing import Any, Optional

from fastapi import HTTPException, status

from app.core.ai_prompts import PromptManager
from app.core.ai_scene_config import resolve_config_for_scene
from app.core.ai_usage_log import log_ai_usage
from app.core.encryption import decrypt_value
from app.core.llm_client import LLMClientFactory
from app.models.ai import AiConfig

logger = logging.getLogger(__name__)


def _extract_json_object(text: str) -> dict:
    if not text:
        return {}
    text = text.strip()
    code_block_pattern = r"```(?:json)?\s*([\s\S]*?)```"
    for match in re.findall(code_block_pattern, text):
        try:
            data = json.loads(match.strip())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


def _build_extra_body(config: AiConfig) -> dict:
    extra_body = {}
    if config.thinking_enabled:
        extra_body["thinking"] = {"type": "enabled"}
    return extra_body


async def _call_llm(system_prompt: str, user_prompt: str, config: AiConfig) -> dict:
    api_key = decrypt_value(config.api_key)
    timeout = int(config.timeout or 60)
    client = LLMClientFactory.create(
        provider=config.provider,
        api_key=api_key,
        api_base=config.api_base,
        model=config.model,
        timeout=timeout,
    )
    extra_body = _build_extra_body(config)
    kwargs = {}
    if config.thinking_enabled and config.reasoning_effort:
        kwargs["reasoning_effort"] = config.reasoning_effort
    return await client.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=config.temperature,
        max_tokens=config.max_tokens or 4096,
        extra_body=extra_body or None,
        **kwargs,
    )


async def generate_mock_response_body(
    *,
    method: str,
    path: str,
    name: str = "",
    description: str = "",
    response_status: int = 200,
    ai_config_id: Optional[int] = None,
    user_info: dict,
    project_id: Optional[int] = None,
) -> dict[str, Any]:
    """调用 LLM 生成 Mock 响应 JSON 与可选状态码。"""
    start_time = time.time()
    config = await resolve_config_for_scene("mock_data_generate", ai_config_id)

    try:
        system_prompt, user_prompt = await PromptManager.render(
            "mock_data_generation",
            {
                "method": method or "GET",
                "path": path or "/",
                "name": name or "",
                "description": description or "",
                "response_status": response_status,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    try:
        resp = await _call_llm(system_prompt, user_prompt, config)
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        await log_ai_usage(
            config,
            "mock_data_generate",
            user_info=user_info,
            project_id=project_id,
            tokens_used=0,
            duration_ms=duration_ms,
            status="failed",
            input_summary=f"{method} {path}"[:500],
            output_summary=str(e)[:500],
        )
        logger.error("[mock_ai] LLM 调用失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM 调用失败: {e}",
        ) from e

    raw = resp.get("content") or ""
    tokens = int(resp.get("tokens") or 0)
    parsed = _extract_json_object(raw)

    response_body = parsed.get("response_body")
    if response_body is None and "data" in parsed:
        response_body = parsed.get("data")
    if response_body is None and parsed and "response_body" not in parsed:
        # 若 LLM 直接返回业务 JSON 对象
        if any(k in parsed for k in ("code", "message", "msg", "success", "result", "list", "items")):
            response_body = parsed
    if response_body is None:
        response_body = {}

    gen_status = parsed.get("response_status", response_status)
    try:
        gen_status = int(gen_status)
    except (TypeError, ValueError):
        gen_status = response_status

    duration_ms = int((time.time() - start_time) * 1000)
    await log_ai_usage(
        config,
        "mock_data_generate",
        user_info=user_info,
        project_id=project_id,
        tokens_used=tokens,
        duration_ms=duration_ms,
        status="success",
        input_summary=(description or f"{method} {path}")[:500],
        output_summary=json.dumps(response_body, ensure_ascii=False)[:500],
    )

    return {
        "response_body": response_body,
        "response_status": gen_status,
        "raw_response": raw[:2000] if raw else "",
    }
