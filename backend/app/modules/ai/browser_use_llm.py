"""将平台 AiConfig 映射为 browser-use LLM 客户端。"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from openai import AsyncOpenAI

# ChatDeepSeek 等路径常返回 usage=None，在此暂存最近一次 API usage 供补全
_last_openai_usage: contextvars.ContextVar[Any] = contextvars.ContextVar("_last_openai_usage", default=None)

from app.core.platform.encryption import decrypt_value
from app.models.ai import AiConfig

# browser-use Agent 依赖 function calling；DeepSeek 思考模式不支持 tool_choice
_THINKING_MODEL_MARKERS = ("thinking", "reasoner", "-r1", "_r1")
_DEEPSEEK_LEGACY_CHAT_MODELS = frozenset({"deepseek-chat"})


def _model_lower(config: AiConfig) -> str:
    return (config.model or "").lower()


def is_deepseek_v4_model(model: str) -> bool:
    m = (model or "").lower()
    return m.startswith("deepseek-v4") or m in {"deepseek-v4-flash", "deepseek-v4-pro"}


def build_deepseek_thinking_options(config: AiConfig) -> tuple[dict[str, Any], str | None]:
    """
    DeepSeek v4 思考开关（官方默认 enabled，须显式 disabled 才能 function calling）。
    返回 (extra_body, reasoning_effort)。
    """
    model = _model_lower(config)
    if not is_deepseek_v4_model(model):
        if config.thinking_enabled:
            return {"thinking": {"type": "enabled"}}, config.reasoning_effort or None
        return {}, None

    if config.thinking_enabled:
        effort = config.reasoning_effort or "high"
        return {"thinking": {"type": "enabled"}}, effort
    # v4 默认思考开启，browser-use 需关闭思考以使用 tool_choice
    return {"thinking": {"type": "disabled"}}, None


def needs_openai_compat_for_browser_use(config: AiConfig) -> bool:
    """思考模式开启时走 OpenAI 兼容路径（避免 tool_choice）。"""
    model = _model_lower(config)
    if config.thinking_enabled:
        return True
    if any(marker in model for marker in _THINKING_MODEL_MARKERS):
        return True
    provider = (config.provider or "").lower()
    if provider == "deepseek" and "reasoner" in model:
        return True
    # deepseek-v4-* 在 thinking 关闭时可走 ChatDeepSeek + tool_choice
    return False


def browser_use_supports_vision(config: AiConfig) -> bool:
    """browser-use 内置：DeepSeek 系列暂不支持 vision。"""
    provider = (config.provider or "").lower()
    model = _model_lower(config)
    if provider == "deepseek" or "deepseek" in model:
        return False
    return True


def _usage_from_openai_raw(usage: Any):
    """OpenAI ChatCompletion.usage → browser-use ChatInvokeUsage。"""
    if not usage:
        return None
    from browser_use.llm.views import ChatInvokeUsage

    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    cached_tokens = None
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached_tokens = getattr(details, "cached_tokens", None)
    total = int(getattr(usage, "total_tokens", 0) or 0) or (prompt + completion)
    return ChatInvokeUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        prompt_cached_tokens=cached_tokens,
        prompt_cache_creation_tokens=None,
        prompt_image_tokens=None,
    )


def _patch_client_capture_usage(client: AsyncOpenAI) -> AsyncOpenAI:
    """拦截 completions.create，记录 response.usage。"""
    orig_create = client.chat.completions.create

    async def create_capture_usage(*args: Any, **kwargs: Any):
        response = await orig_create(*args, **kwargs)
        if getattr(response, "usage", None):
            _last_openai_usage.set(response.usage)
        return response

    client.chat.completions.create = create_capture_usage  # type: ignore[method-assign]
    return client


def _patch_client_extra_body(
    client: AsyncOpenAI,
    extra_body: dict[str, Any] | None,
    reasoning_effort: str | None,
) -> AsyncOpenAI:
    """在 OpenAI 兼容客户端注入 DeepSeek thinking / reasoning_effort 参数。"""
    client = _patch_client_capture_usage(client)
    if not extra_body and not reasoning_effort:
        return client

    orig_create = client.chat.completions.create

    async def create_with_extra(*args: Any, **kwargs: Any):
        if extra_body:
            merged = dict(extra_body)
            merged.update(kwargs.pop("extra_body", None) or {})
            kwargs["extra_body"] = merged
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
        response = await orig_create(*args, **kwargs)
        if getattr(response, "usage", None):
            _last_openai_usage.set(response.usage)
        return response

    client.chat.completions.create = create_with_extra  # type: ignore[method-assign]
    return client


def _wrap_llm_for_usage_tracking(llm: Any) -> Any:
    """补全 upstream 未返回的 usage，使 browser-use TokenCost 与平台统计可用。"""
    if getattr(llm, "_browser_lab_usage_wrapped", False):
        return llm

    if hasattr(llm, "get_client"):
        orig_get_client = llm.get_client

        def get_client_with_usage():
            return _patch_client_capture_usage(orig_get_client())

        object.__setattr__(llm, "get_client", get_client_with_usage)

    if hasattr(llm, "_client"):
        orig_client = llm._client

        def client_with_usage():
            return _patch_client_capture_usage(orig_client())

        object.__setattr__(llm, "_client", client_with_usage)

    orig_ainvoke = llm.ainvoke

    async def ainvoke_with_usage(messages, output_format=None, **kwargs):
        _last_openai_usage.set(None)
        result = await orig_ainvoke(messages, output_format=output_format, **kwargs)
        if getattr(result, "usage", None) is not None:
            return result
        usage = _usage_from_openai_raw(_last_openai_usage.get())
        if usage is not None:
            return result.model_copy(update={"usage": usage})
        return result

    object.__setattr__(llm, "ainvoke", ainvoke_with_usage)
    llm._browser_lab_usage_wrapped = True
    return llm


def _make_browser_use_chat_deepseek(
    *,
    model: str,
    api_key: str,
    base_url: str,
    temperature: float,
    timeout: float,
    request_extra_body: dict[str, Any] | None = None,
    reasoning_effort: str | None = None,
):
    """ChatDeepSeek 子类：注入 DeepSeek v4 thinking 参数，保留 model_name 等协议字段。"""
    from browser_use.llm.deepseek.chat import ChatDeepSeek

    extra = request_extra_body or {}
    effort = reasoning_effort

    @dataclass
    class BrowserUseChatDeepSeek(ChatDeepSeek):
        def _client(self) -> AsyncOpenAI:
            client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                **(self.client_params or {}),
            )
            return _patch_client_extra_body(client, extra or None, effort)

    return BrowserUseChatDeepSeek(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        timeout=timeout,
    )


def _openai_compat_llm(
    *,
    model: str,
    api_key: str,
    base_url: str | None,
    temperature: float,
    timeout: float,
    request_extra_body: dict[str, Any] | None = None,
    reasoning_effort: str | None = None,
):
    from browser_use.llm.openai.chat import ChatOpenAI

    @dataclass
    class _BrowserUseChatOpenAI(ChatOpenAI):
        _request_extra_body: dict[str, Any] = field(default_factory=dict)
        _reasoning_effort: str | None = None

        def get_client(self) -> AsyncOpenAI:
            client = super().get_client()
            return _patch_client_extra_body(
                client,
                self._request_extra_body or None,
                self._reasoning_effort,
            )

    return _BrowserUseChatOpenAI(
        model=model,
        api_key=api_key,
        temperature=temperature,
        timeout=timeout,
        base_url=base_url,
        dont_force_structured_output=True,
        add_schema_to_system_prompt=True,
        remove_min_items_from_schema=True,
        _request_extra_body=request_extra_body or {},
        _reasoning_effort=reasoning_effort,
    )


def build_browser_use_llm(config: AiConfig):
    """根据 AiConfig 构造 browser-use BaseChatModel。"""
    api_key = decrypt_value(config.api_key)
    if not api_key:
        raise HTTPException(status_code=400, detail="AI 配置 API Key 无效")

    provider = (config.provider or "").lower()
    model = config.model or "gpt-4o"
    timeout = float(config.timeout or 120)
    temperature = config.temperature if config.temperature is not None else 0.2
    base_url = (config.api_base or "").strip() or None
    deepseek_base = base_url or "https://api.deepseek.com/v1"
    extra_body, reasoning_effort = build_deepseek_thinking_options(config)

    try:
        llm: Any
        if needs_openai_compat_for_browser_use(config):
            default_base = None
            if provider == "deepseek":
                default_base = deepseek_base
            elif provider == "qwen":
                default_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            llm = _openai_compat_llm(
                model=model,
                api_key=api_key,
                base_url=base_url or default_base,
                temperature=temperature,
                timeout=timeout,
                request_extra_body=extra_body,
                reasoning_effort=reasoning_effort,
            )
        elif provider == "deepseek":
            if _model_lower(config) in _DEEPSEEK_LEGACY_CHAT_MODELS and not extra_body:
                from browser_use.llm.deepseek.chat import ChatDeepSeek

                llm = ChatDeepSeek(
                    model=model,
                    api_key=api_key,
                    base_url=deepseek_base,
                    temperature=temperature,
                    timeout=timeout,
                )
            else:
                llm = _make_browser_use_chat_deepseek(
                    model=model,
                    api_key=api_key,
                    base_url=deepseek_base,
                    temperature=temperature,
                    timeout=timeout,
                    request_extra_body=extra_body,
                    reasoning_effort=reasoning_effort,
                )
        elif provider == "claude":
            from browser_use.llm.anthropic.chat import ChatAnthropic

            llm = ChatAnthropic(
                model=model,
                api_key=api_key,
                temperature=temperature,
                timeout=timeout,
            )
        elif provider in ("openai", "custom", "qwen"):
            default_base = "https://dashscope.aliyuncs.com/compatible-mode/v1" if provider == "qwen" else None
            llm = _openai_compat_llm(
                model=model,
                api_key=api_key,
                base_url=base_url or default_base,
                temperature=temperature,
                timeout=timeout,
            )
        else:
            llm = _openai_compat_llm(
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=temperature,
                timeout=timeout,
            )
        return _wrap_llm_for_usage_tracking(llm)
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail="未安装 browser-use，请在 Backend 执行 pip install browser-use 后重启服务",
        ) from e
