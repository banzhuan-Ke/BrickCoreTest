"""AI 配置多模态（Vision）能力：显式标记优先，启发式仅作回填/兜底。"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

# 场景绑定必须使用多模态模型
VISION_REQUIRED_SCENES = frozenset(
    {
        "failure_analysis_vision",
        "requirement_doc_understand",
        "knowledge_doc_image_vision",
    }
)


def is_likely_vision_model(model: str) -> bool:
    """启发式：模型名是否像 Vision / 多模态。"""
    m = (model or "").lower()
    hints = ("vl", "vision", "gpt-4o", "gpt-4-turbo", "claude-3", "gemini", "qvq")
    return any(h in m for h in hints)


def config_supports_vision(config: Any) -> bool:
    """是否支持多模态：以 AiConfig.supports_vision 为准。"""
    if config is None:
        return False
    flag = getattr(config, "supports_vision", None)
    if flag is not None:
        return bool(flag)
    return is_likely_vision_model(getattr(config, "model", "") or "")


def vision_unsupported_message(config: Any, *, action: str) -> str:
    name = (getattr(config, "name", None) or "当前配置").strip()
    model = (getattr(config, "model", None) or "").strip()
    label = f"「{name}」" + (f"（{model}）" if model else "")
    return (
        f"{label}未开启「支持多模态」，无法用于{action}。"
        "请到「平台配置 → AI 模型」开启该开关，或改选已支持多模态的配置（如 qwen-vl、gpt-4o）。"
    )


def raise_if_vision_unsupported(config: Any, *, action: str) -> None:
    if not config_supports_vision(config):
        raise HTTPException(
            status_code=400,
            detail=vision_unsupported_message(config, action=action),
        )
