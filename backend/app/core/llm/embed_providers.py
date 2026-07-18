"""Embedding Provider 工具（与资料库模块解耦，供平台 Embedding 配置 API 使用）。"""
from __future__ import annotations

from typing import Any, Optional

from app.core.llm.llm_client import DEFAULT_BASE_URLS
from app.core.platform.config import KNOWLEDGE_EMBED_DEFAULT_PROVIDER

_EMBED_PROVIDERS = frozenset({"openai", "deepseek", "qwen", "claude", "custom"})


def normalize_embed_provider(provider: Any) -> str:
    key = str(provider or "").strip().lower()
    if key in _EMBED_PROVIDERS:
        return key
    default = str(KNOWLEDGE_EMBED_DEFAULT_PROVIDER or "qwen").strip().lower()
    return default if default in _EMBED_PROVIDERS else "qwen"


def resolve_embed_api_base(config: Any) -> str:
    api_base = getattr(config, "api_base", None)
    if api_base:
        return str(api_base).strip()
    return DEFAULT_BASE_URLS.get(
        normalize_embed_provider(getattr(config, "provider", "")),
        DEFAULT_BASE_URLS["openai"],
    )


def model_supports_dimensions(model: str) -> bool:
    m = (model or "").lower()
    return (
        "embedding-v3" in m
        or "embedding-v4" in m
        or "text-embedding-3" in m
    )


def resolve_embed_dimensions(config: Any, model: str) -> Optional[int]:
    """解析 API 请求的 dimensions；不支持维度的模型返回 None。"""
    if not model_supports_dimensions(model):
        return None
    dim = getattr(config, "dimensions", None)
    if dim is not None and int(dim) > 0:
        return int(dim)
    return 1024
