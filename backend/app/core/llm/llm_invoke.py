"""统一 LLM 调用（带重试、场景参数覆盖），供 modules 与 routers 共用。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from app.core.llm.llm_client import LLMClientFactory
from app.core.platform.encryption import decrypt_value
from app.models.ai import AiConfig

logger = logging.getLogger(__name__)

VISION_MAX_TOKENS_LIMIT = 32768


def resolve_vision_max_tokens(config: AiConfig, *, cap: int = VISION_MAX_TOKENS_LIMIT) -> int:
    """Vision API 对 max_tokens 上限更严（如通义 VL 为 32768），避免配置过大导致 400。"""
    raw = int(getattr(config, "max_tokens", None) or 4096)
    return max(1, min(raw, cap))


def build_extra_body(config: AiConfig, *, disable_thinking: bool = False) -> dict[str, Any]:
    """根据配置构造 extra_body（用于 thinking 等供应商特定参数）"""
    if disable_thinking:
        return {}
    if config.thinking_enabled:
        return {"thinking": {"type": "enabled"}}
    return {}


def is_retryable_llm_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        k in msg
        for k in (
            "timeout",
            "timed out",
            "stream timeout",
            "connection",
            "503",
            "502",
            "504",
            "429",
            "rate limit",
        )
    )


async def call_llm(
    system_prompt: str,
    user_prompt: str,
    config: AiConfig,
    *,
    min_timeout: int = 0,
    max_retries: int = 0,
    param_overrides: dict | None = None,
    disable_thinking: bool = False,
) -> dict[str, Any]:
    """调用 LLM，返回 {"content": str, "tokens": int, ...}"""
    po = param_overrides or {}
    api_key = decrypt_value(config.api_key)
    eff_timeout = int(po.get("timeout") or config.timeout or 60)
    if po.get("min_timeout") is not None:
        eff_timeout = max(eff_timeout, int(po["min_timeout"]))
    timeout = max(eff_timeout, int(min_timeout or 0))
    eff_temperature = po.get("temperature", config.temperature)
    eff_max_tokens = int(po.get("max_tokens") or config.max_tokens or 4096)
    client = LLMClientFactory.create(
        provider=config.provider,
        api_key=api_key,
        api_base=config.api_base,
        model=config.model,
        timeout=timeout,
    )
    extra_body = build_extra_body(config, disable_thinking=disable_thinking)
    kwargs: dict[str, Any] = {}
    if not disable_thinking and config.thinking_enabled and config.reasoning_effort:
        kwargs["reasoning_effort"] = config.reasoning_effort
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    last_err: Optional[Exception] = None
    attempts = max_retries + 1
    for attempt in range(attempts):
        try:
            return await client.chat(
                messages=messages,
                temperature=eff_temperature,
                max_tokens=eff_max_tokens,
                extra_body=extra_body or None,
                stream=False,
                **kwargs,
            )
        except Exception as e:
            last_err = e
            if attempt < attempts - 1 and is_retryable_llm_error(e):
                wait_s = 3 * (attempt + 1)
                logger.warning(
                    "[call_llm] 第 %s/%s 次失败(%s)，%ss 后重试 model=%s prompt_len=%s",
                    attempt + 1,
                    attempts,
                    e,
                    wait_s,
                    config.model,
                    len(user_prompt or ""),
                )
                await asyncio.sleep(wait_s)
                continue
            raise
    if last_err:
        raise last_err
    raise RuntimeError("LLM 调用失败")
