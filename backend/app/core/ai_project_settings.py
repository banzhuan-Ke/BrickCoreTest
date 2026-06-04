"""
项目级 AI 执行设置（存 Project.global_vars['ai_settings']）
"""
from __future__ import annotations

import copy
from typing import Any, Optional

from app.models.sys import Project

AI_SETTINGS_GLOBAL_VARS_KEY = "ai_settings"

DEFAULT_AI_PROJECT_SETTINGS: dict[str, bool] = {
    "locator_heal_enabled": True,
    "locator_heal_default_on_execute": True,
    "locator_heal_allow_run_override": True,
}


def normalize_ai_project_settings(raw: Any) -> dict[str, bool]:
    base = copy.deepcopy(DEFAULT_AI_PROJECT_SETTINGS)
    if isinstance(raw, dict):
        for key in DEFAULT_AI_PROJECT_SETTINGS:
            if key in raw and raw[key] is not None:
                base[key] = bool(raw[key])
    return base


def get_ai_project_settings_from_project(project: Project) -> dict[str, bool]:
    gv = project.global_vars if isinstance(project.global_vars, dict) else {}
    return normalize_ai_project_settings(gv.get(AI_SETTINGS_GLOBAL_VARS_KEY))


async def load_ai_project_settings(project_id: int) -> dict[str, bool]:
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        return normalize_ai_project_settings(None)
    return get_ai_project_settings_from_project(project)


async def save_ai_project_settings(project_id: int, updates: dict[str, Any]) -> dict[str, bool]:
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise ValueError("项目不存在")
    current = get_ai_project_settings_from_project(project)
    for key in DEFAULT_AI_PROJECT_SETTINGS:
        if key in updates and updates[key] is not None:
            current[key] = bool(updates[key])
    gv = dict(project.global_vars or {})
    gv[AI_SETTINGS_GLOBAL_VARS_KEY] = current
    project.global_vars = gv
    await project.save()
    return current


async def resolve_locator_heal_for_execute(
    project_id: int,
    user_override: Optional[bool] = None,
) -> bool:
    """
    计算本次 UI 执行是否启用定位器自愈。
    优先级：项目总开关 OFF → False；允许覆盖且用户传参 → 用户值；否则 → 项目默认。
    """
    settings = await load_ai_project_settings(project_id)
    if not settings["locator_heal_enabled"]:
        return False
    if user_override is not None and settings["locator_heal_allow_run_override"]:
        return bool(user_override)
    return settings["locator_heal_default_on_execute"]
