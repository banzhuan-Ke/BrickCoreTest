"""智能浏览器任务描述 AI 优化（browser-use 可执行性）。"""
from __future__ import annotations

from typing import Optional

from app.modules.ai.description_text_optimizer import (
    SCENE_BROWSER_LAB,
    SCENE_UI_AGENT_SOLIDIFY,
    optimize_description_text,
)


async def optimize_browser_lab_task_text(
    *,
    task_text: str,
    start_url: str = "",
    case_name: str = "",
    ai_config_id: Optional[int] = None,
    username: str = "",
    project_id: Optional[int] = None,
    optimize_mode: str = "browser_use",
) -> dict:
    """优化任务描述，返回 { task_text, changes_summary, tokens_used }。"""
    mode = (optimize_mode or "browser_use").strip().lower()
    scene = SCENE_UI_AGENT_SOLIDIFY if mode in ("solidify", "agent_solidify") else SCENE_BROWSER_LAB
    return await optimize_description_text(
        scene,
        task_text=task_text,
        start_url=start_url,
        case_name=case_name,
        ai_config_id=ai_config_id,
        username=username,
        project_id=project_id,
    )
