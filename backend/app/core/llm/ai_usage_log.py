"""AI 模型调用使用记录"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.modules.ai.ai_scene_config import AI_SCENE_DEFINITIONS
from app.models.ai import AiUsageLog

logger = logging.getLogger(__name__)

MAX_SUMMARY_LEN = 2000

SKILL_CODE_LABELS: dict[str, str] = {
    "ui_failure_analysis": "失败分析",
    "knowledge_qa": "资料库问答",
    "project_health_digest": "项目健康摘要",
}

# 独立 AI 场景本身就是某个 Skill（旧记录 extra 可能没有 skill_code）
SCENE_AS_SKILL: dict[str, str] = {
    "knowledge_qa": "knowledge_qa",
}


def _skill_codes_from_extra(extra: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    raw_skill = extra.get("skill_code")
    if isinstance(raw_skill, str) and raw_skill.strip():
        codes.append(raw_skill.strip())
    used = extra.get("skills_used") or []
    if isinstance(used, list):
        for item in used:
            if isinstance(item, str) and item.strip():
                codes.append(item.strip())
            elif isinstance(item, dict):
                code = str(item.get("skill_code") or item.get("code") or "").strip()
                if code:
                    codes.append(code)
    out: list[str] = []
    seen: set[str] = set()
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _tools_from_extra(extra: dict[str, Any]) -> list[str]:
    tools = extra.get("tools_used") or extra.get("tools") or []
    if not isinstance(tools, list):
        return []
    out: list[str] = []
    for t in tools:
        name = str(t).strip() if not isinstance(t, dict) else str(t.get("name") or "").strip()
        if name and name not in out:
            out.append(name)
    return out


def summarize_usage_path(
    *,
    scene: str = "",
    input_summary: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """从 extra/scene 推导展示用路径：Agent / Skill / 确认 / 工具。旧记录也能推断。"""
    extra = extra if isinstance(extra, dict) else {}
    skills = _skill_codes_from_extra(extra)
    scene_skill = SCENE_AS_SKILL.get(scene or "")
    if scene_skill and scene_skill not in skills:
        skills = [scene_skill, *skills]
    tools = _tools_from_extra(extra)
    mode = str(extra.get("mode") or "").strip().lower()
    if mode not in ("lite", "standard"):
        mode = ""
    mode_label = {"lite": "精简", "standard": "标准"}.get(mode, "")
    action = str(extra.get("action") or "").strip()
    inp = (input_summary or "").strip()
    if not action and inp.lower().startswith("confirm:"):
        action = inp.split(":", 1)[-1].strip()

    skill_names = [SKILL_CODE_LABELS.get(c, c) for c in skills]
    if action:
        kind = "confirm"
        path_label = f"确认执行 · {action}"
    elif scene == "platform_assistant":
        kind = "agent"
        path_label = "小测 Agent"
        if mode_label:
            path_label += f" · {mode_label}"
        if skill_names:
            path_label += " · " + "、".join(skill_names)
    elif skills:
        kind = "skill"
        path_label = "Skill · " + "、".join(skill_names)
    elif tools:
        kind = "tool"
        path_label = "工具 · " + "、".join(tools[:4])
    else:
        kind = "other"
        path_label = ""

    return {
        "path_kind": kind,
        "path_label": path_label,
        "mode": mode or None,
        "skills": skills,
        "skill_labels": [SKILL_CODE_LABELS.get(c, c) for c in skills],
        "tools": tools,
        "action": action or None,
    }


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
