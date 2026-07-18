"""
项目设置路由（项目级：执行与自愈 / 功能用例策略等）

归属「项目配置 → 项目设置」；平台级 LLM/场景/提示词仍在 /ai/configs。
旧路径 GET/PUT /ai/configs/execution-settings 作为兼容别名保留。

权限：
- 查看：project_settings:view 或兼容 ai_config:view
- 编辑：project_settings:edit 或兼容 ai_config:edit
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.platform.auth import is_authenticated, require_any_permissions
from app.core.platform.permissions import (
    AI_CONFIG_EDIT,
    AI_CONFIG_VIEW,
    PROJECT_SETTINGS_EDIT,
    PROJECT_SETTINGS_VIEW,
)
from app.modules.ai.ai_project_settings import load_ai_project_settings, save_ai_project_settings
from app.models.sys import Project
from app.routers.ai.requirements import _resolve_project_id
from app.schemas.ai import StandardResponse
from app.schemas.project_settings import (
    AiExecutionSettingsBody,
    payload_from_execution_settings_body,
)

router = APIRouter(
    prefix="/project-settings",
    tags=["项目设置"],
    dependencies=[Depends(is_authenticated)],
)


@router.get(
    "",
    summary="项目设置概览（当前项目 + 执行策略摘要）",
    dependencies=[Depends(require_any_permissions(PROJECT_SETTINGS_VIEW, AI_CONFIG_VIEW))],
)
async def get_project_settings_overview(
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    """供项目设置页展示当前项目上下文；执行明细见 GET /execution。"""
    pid = _resolve_project_id(user_info, project_id)
    project = await Project.get_or_none(id=pid, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    settings = await load_ai_project_settings(pid)
    rc = settings.get("requirement_case") or {}
    return StandardResponse(
        data={
            "project_id": pid,
            "project_name": project.name,
            "scope": "project",
            "sections": {
                "execution": True,
                "notification": True,
            },
            "execution_summary": {
                "locator_heal_enabled": settings.get("locator_heal_enabled"),
                "ai_act_enabled": settings.get("ai_act_enabled"),
                "failure_analysis_enabled": settings.get("failure_analysis_enabled"),
                "auto_count_enabled_default": rc.get("auto_count_enabled_default"),
                "auto_count_min_floor": rc.get("auto_count_min_floor"),
                "auto_count_max_cap": rc.get("auto_count_max_cap"),
                "fixed_count_hard_max": rc.get("fixed_count_hard_max"),
            },
        }
    )


@router.get(
    "/execution",
    summary="获取项目执行设置（自愈/AI Act/功能用例软区间等）",
    dependencies=[Depends(require_any_permissions(PROJECT_SETTINGS_VIEW, AI_CONFIG_VIEW))],
)
async def get_project_execution_settings(
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    settings = await load_ai_project_settings(pid)
    return StandardResponse(data=settings)


@router.put(
    "/execution",
    summary="保存项目执行设置",
    dependencies=[Depends(require_any_permissions(PROJECT_SETTINGS_EDIT, AI_CONFIG_EDIT))],
)
async def update_project_execution_settings(
    body: AiExecutionSettingsBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    try:
        saved = await save_ai_project_settings(pid, payload_from_execution_settings_body(body))
    except ValueError as e:
        msg = str(e)
        status_code = 404 if msg == "项目不存在" else 422
        raise HTTPException(status_code=status_code, detail=msg) from e
    return StandardResponse(data=saved, message="执行设置已保存")


__all__ = [
    "router",
    "AiExecutionSettingsBody",
    "get_project_execution_settings",
    "update_project_execution_settings",
]
