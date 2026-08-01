"""资料库向量 Embedding 配置（平台默认 + 项目覆盖）"""
from __future__ import annotations

from typing import Any, Optional

from app.core.llm.embed_providers import (
    model_supports_dimensions,
    normalize_embed_provider,
    resolve_embed_dimensions,
)
from app.core.platform.config import (
    KNOWLEDGE_EMBED_BATCH_SIZE,
    KNOWLEDGE_EMBED_DEFAULT_MODEL,
    KNOWLEDGE_EMBED_DEFAULT_PROVIDER,
    KNOWLEDGE_RETRIEVE_STRATEGY,
)
from app.modules.knowledge.constants import DOC_TYPES

# 兼容：旧调用方仍可从本模块导入 normalize / dimensions
__all__ = [
    "DOCUMENT_EMBED_MODES",
    "RETRIEVE_STRATEGIES",
    "EMBED_PROVIDER_DEFINITIONS",
    "DEFAULT_VECTOR_EMBED_DOC_TYPES",
    "platform_vector_embed_allowed",
    "normalize_embed_provider",
    "normalize_retrieve_strategy",
    "normalize_document_embed_mode",
    "embed_providers_payload",
    "resolve_embed_provider_model",
    "normalize_vector_embed_doc_types",
    "model_supports_dimensions",
    "resolve_embed_dimensions",
    "effective_embed_batch_size",
    "embed_capabilities_payload",
    "document_should_vector_embed",
]

DOCUMENT_EMBED_MODES: dict[str, str] = {
    "inherit": "跟随项目",
    "lexical_only": "仅词法索引",
    "vector": "启用向量 Embedding",
    "none": "不建立索引",
}

RETRIEVE_STRATEGIES: dict[str, str] = {
    "lexical": "词法检索（默认，无 Embedding 费用）",
    "vector": "向量检索",
    "hybrid": "混合检索（词法 + 向量）",
}

# Provider 定义：默认通义千问；其余 OpenAI 兼容
EMBED_PROVIDER_DEFINITIONS: dict[str, dict[str, Any]] = {
    "qwen": {
        "label": "通义千问",
        "default_model": "text-embedding-v3",
        "models": [
            {"value": "text-embedding-v3", "label": "text-embedding-v3（推荐）"},
            {"value": "text-embedding-v2", "label": "text-embedding-v2"},
        ],
    },
    "openai": {
        "label": "OpenAI",
        "default_model": "text-embedding-3-small",
        "models": [
            {"value": "text-embedding-3-small", "label": "text-embedding-3-small"},
            {"value": "text-embedding-3-large", "label": "text-embedding-3-large"},
        ],
    },
    "deepseek": {
        "label": "DeepSeek",
        "default_model": "deepseek-embedding",
        "models": [
            {"value": "deepseek-embedding", "label": "deepseek-embedding"},
        ],
    },
    "custom": {
        "label": "自定义 OpenAI 兼容",
        "default_model": "",
        "models": [],
        "allow_custom_model": True,
    },
}

DEFAULT_VECTOR_EMBED_DOC_TYPES = [
    "requirement",
    "bug_export",
    "summary",
    "test_plan",
    "iteration_plan",
]


def platform_vector_embed_allowed() -> bool:
    """向量能力由项目级「启用向量 Embedding」控制；不再依赖部署环境变量。"""
    return True


def normalize_retrieve_strategy(strategy: Any) -> str:
    key = str(strategy or KNOWLEDGE_RETRIEVE_STRATEGY or "lexical").strip().lower()
    if key in RETRIEVE_STRATEGIES:
        return key
    return "lexical"


def normalize_document_embed_mode(mode: Any) -> str:
    key = str(mode or "inherit").strip().lower()
    if key in DOCUMENT_EMBED_MODES:
        return key
    return "inherit"


def embed_providers_payload() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key, meta in EMBED_PROVIDER_DEFINITIONS.items():
        items.append(
            {
                "value": key,
                "label": meta["label"],
                "default_model": meta.get("default_model") or "",
                "models": meta.get("models") or [],
                "allow_custom_model": bool(meta.get("allow_custom_model")),
            }
        )
    return items


def resolve_embed_provider_model(settings: dict[str, Any]) -> tuple[str, str]:
    provider = normalize_embed_provider(settings.get("vector_embed_provider") or KNOWLEDGE_EMBED_DEFAULT_PROVIDER)
    meta = EMBED_PROVIDER_DEFINITIONS.get(provider) or EMBED_PROVIDER_DEFINITIONS["qwen"]
    model = str(settings.get("vector_embed_model") or "").strip()
    if not model:
        model = str(meta.get("default_model") or KNOWLEDGE_EMBED_DEFAULT_MODEL or "text-embedding-v3")
    return provider, model


def normalize_vector_embed_doc_types(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return list(DEFAULT_VECTOR_EMBED_DOC_TYPES)
    out: list[str] = []
    for item in raw:
        key = str(item or "").strip()
        if key in DOC_TYPES and key not in out:
            out.append(key)
    return out or list(DEFAULT_VECTOR_EMBED_DOC_TYPES)


def document_should_vector_embed(
    *,
    doc_type: str,
    embed_mode: str,
    project_settings: dict[str, Any],
    platform_allowed: Optional[bool] = None,
) -> bool:
    """判断文档是否应走向量 Embedding（Phase 4b 索引任务使用）。"""
    allowed = platform_vector_embed_allowed() if platform_allowed is None else platform_allowed
    mode = normalize_document_embed_mode(embed_mode)
    if mode == "none" or mode == "lexical_only":
        return False
    if not allowed or not project_settings.get("vector_embed_enabled"):
        return False
    if mode == "vector":
        return True
    doc_types = normalize_vector_embed_doc_types(project_settings.get("vector_embed_doc_types"))
    return doc_type in doc_types


def effective_embed_batch_size(config: Any) -> int:
    """按 Provider API 限制裁剪批大小（通义单批最多 10 条）。"""
    provider = normalize_embed_provider(getattr(config, "provider", "") or "")
    cap = 10 if provider == "qwen" else 25
    return max(1, min(KNOWLEDGE_EMBED_BATCH_SIZE, cap))


def embed_capabilities_payload() -> dict[str, Any]:
    return {
        "platform_vector_embed_enabled": platform_vector_embed_allowed(),
        "default_provider": normalize_embed_provider(KNOWLEDGE_EMBED_DEFAULT_PROVIDER),
        "default_model": KNOWLEDGE_EMBED_DEFAULT_MODEL,
        "default_retrieve_strategy": normalize_retrieve_strategy(KNOWLEDGE_RETRIEVE_STRATEGY),
        "providers": embed_providers_payload(),
        "document_embed_modes": [
            {"value": k, "label": v} for k, v in DOCUMENT_EMBED_MODES.items()
        ],
        "retrieve_strategies": [
            {"value": k, "label": v} for k, v in RETRIEVE_STRATEGIES.items()
        ],
        "doc_type_options": [{"value": k, "label": v} for k, v in DOC_TYPES.items()],
    }
