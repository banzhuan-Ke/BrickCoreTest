"""AI 模型调用使用记录"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.modules.ai.ai_scene_config import AI_SCENE_DEFINITIONS
from app.models.ai import AiUsageLog

logger = logging.getLogger(__name__)

MAX_SUMMARY_LEN = 2000


@dataclass
class AiUsageMeta:
    scene: str
    user_id: int | None = None
    username: str = ""
    project_id: int | None = None
    project_name: str = ""
    input_summary: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def _clip(text: str | None, limit: int = MAX_SUMMARY_LEN) -> str:
    s = (text or "").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def usage_meta_from_user(
    user_info: dict,
    scene: str,
    *,
    project_id: int | None = None,
    input_summary: str = "",
    **extra: Any,
) -> AiUsageMeta:
    pid = project_id
    if pid is None:
        pid = user_info.get("project_id") or user_info.get("current_project_id")
    return AiUsageMeta(
        scene=scene,
        user_id=user_info.get("id"),
        username=user_info.get("username") or user_info.get("sub") or "",
        project_id=pid,
        input_summary=input_summary,
        extra=dict(extra),
    )


async def record_ai_usage(
    *,
    scene: str,
    user_id: int | None = None,
    username: str = "",
    project_id: int | None = None,
    project_name: str = "",
    ai_config_id: int | None = None,
    model: str = "",
    provider: str = "",
    tokens_used: int = 0,
    duration_ms: int = 0,
    status: str = "success",
    input_summary: str = "",
    output_summary: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """写入一条 LLM 使用记录（失败时仅打日志，不影响主流程）。"""
    label = AI_SCENE_DEFINITIONS.get(scene, (scene, ""))[0]
    resolved_name = (project_name or "").strip()
    if project_id and not resolved_name:
        try:
            from app.models.sys import Project

            proj = await Project.get_or_none(id=project_id, is_del=False)
            if proj:
                resolved_name = proj.name or ""
        except Exception:
            pass
    try:
        await AiUsageLog.create(
            scene=scene,
            scene_label=label,
            user_id=user_id,
            username=username or "",
            project_id=project_id,
            project_name=resolved_name,
            ai_config_id=ai_config_id,
            model=model or "",
            provider=provider or "",
            tokens_used=max(int(tokens_used or 0), 0),
            duration_ms=max(int(duration_ms or 0), 0),
            status=status if status in ("success", "failed") else "success",
            input_summary=_clip(input_summary),
            output_summary=_clip(output_summary) or None,
            extra=extra or {},
        )
    except Exception:
        logger.exception("[ai_usage] record failed scene=%s user=%s", scene, username)


async def record_ai_usage_for_config(
    config: Any,
    meta: AiUsageMeta,
    *,
    tokens_used: int = 0,
    duration_ms: int = 0,
    status: str = "success",
    output_summary: str = "",
) -> None:
    """基于 AiConfig + AiUsageMeta 写入使用记录。"""
    await record_ai_usage(
        scene=meta.scene,
        user_id=meta.user_id,
        username=meta.username,
        project_id=meta.project_id,
        project_name=meta.project_name,
        ai_config_id=getattr(config, "id", None) if config else None,
        model=getattr(config, "model", "") or "",
        provider=getattr(config, "provider", "") or "",
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        status=status,
        input_summary=meta.input_summary,
        output_summary=output_summary,
        extra=meta.extra,
    )


async def log_ai_usage(
    config: Any,
    scene: str,
    *,
    user_info: dict | None = None,
    user_id: int | None = None,
    username: str = "",
    project_id: int | None = None,
    project_name: str = "",
    tokens_used: int = 0,
    duration_ms: int = 0,
    status: str = "success",
    input_summary: str = "",
    output_summary: str = "",
    **extra: Any,
) -> None:
    """各 AI 路由统一埋点入口。"""
    if user_info:
        meta = usage_meta_from_user(
            user_info,
            scene,
            project_id=project_id,
            input_summary=input_summary,
            **extra,
        )
        if project_name:
            meta.project_name = project_name
    else:
        meta = AiUsageMeta(
            scene=scene,
            user_id=user_id,
            username=username,
            project_id=project_id,
            project_name=project_name,
            input_summary=input_summary,
            extra=dict(extra),
        )
    await record_ai_usage_for_config(
        config,
        meta,
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        status=status,
        output_summary=output_summary,
    )
