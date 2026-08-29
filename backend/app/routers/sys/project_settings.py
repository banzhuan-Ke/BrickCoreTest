"""
项目设置路由（项目级：执行与自愈 / 功能用例策略等）

归属「项目配置 → 项目设置」；平台级 LLM/场景/提示词仍在 /ai/configs。
旧路径 GET/PUT /ai/configs/execution-settings 作为兼容别名保留。

权限：
- 查看：project_settings:view 或兼容 ai_config:view
- 编辑：project_settings:edit 或兼容 ai_config:edit
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

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


class TestNotifySettingsBody(BaseModel):
    inbox_enabled: Optional[bool] = None
    external_enabled: Optional[bool] = None
    external_channels: Optional[List[str]] = None
    on_scope_owner_assigned: Optional[bool] = None
    on_defect_assigned: Optional[bool] = None
    on_review_invited: Optional[bool] = None
    on_plan_run_item_assigned: Optional[bool] = None
    on_review_item_pending: Optional[bool] = None
    on_quality_gate_failed: Optional[bool] = None
    default_scope_owner_id: Optional[int] = None
    digest_minutes: Optional[int] = Field(None, ge=0, le=1440)


class QualityGateSettingsBody(BaseModel):
    required_completion_min: Optional[float] = Field(None, ge=0, le=1)
    required_pass_rate_min: Optional[float] = Field(None, ge=0, le=1)
    blocker_open_max: Optional[int] = Field(None, ge=0)
    critical_open_max: Optional[int] = Field(None, ge=0)
    high_risk_without_result_max: Optional[int] = Field(None, ge=0)


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
                "test_notify": True,
                "quality_gate": True,
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


@router.get(
    "/test-notify",
    summary="获取测试管理通知策略",
    dependencies=[Depends(require_any_permissions(PROJECT_SETTINGS_VIEW, AI_CONFIG_VIEW))],
)
async def get_test_notify_settings(
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.test_management.premium_gateway import tm_premium_ready
    from app.modules.test_management.tm_premium_defaults import DEFAULT_TM_NOTIFY_SETTINGS

    pid = _resolve_project_id(user_info, project_id)
    if not tm_premium_ready():
        return StandardResponse(data={**DEFAULT_TM_NOTIFY_SETTINGS, "premium_required": True})
    from app.modules.test_management.tm_notify_settings import load_tm_notify_settings

    data = await load_tm_notify_settings(pid)
    return StandardResponse(data=data)


@router.put(
    "/test-notify",
    summary="保存测试管理通知策略",
    dependencies=[Depends(require_any_permissions(PROJECT_SETTINGS_EDIT, AI_CONFIG_EDIT))],
)
async def update_test_notify_settings(
    body: TestNotifySettingsBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.test_management.premium_gateway import raise_tm_premium_required, tm_premium_ready
    from app.modules.test_management.tm_notify_settings import save_tm_notify_settings

    if not tm_premium_ready():
        raise_tm_premium_required()
    pid = _resolve_project_id(user_info, project_id)
    try:
        saved = await save_tm_notify_settings(pid, body.model_dump(exclude_unset=True))
    except ValueError as e:
        msg = str(e)
        status_code = 404 if msg == "项目不存在" else 422
        raise HTTPException(status_code=status_code, detail=msg) from e
    return StandardResponse(data=saved, message="测试通知策略已保存")


@router.get(
    "/quality-gate",
    summary="获取测试管理质量门禁阈值",
    dependencies=[Depends(require_any_permissions(PROJECT_SETTINGS_VIEW, AI_CONFIG_VIEW))],
)
async def get_quality_gate_settings(
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.test_management.premium_gateway import tm_premium_ready
    from app.modules.test_management.tm_premium_defaults import DEFAULT_QUALITY_RULES

    pid = _resolve_project_id(user_info, project_id)
    if not tm_premium_ready():
        return StandardResponse(data={**DEFAULT_QUALITY_RULES, "premium_required": True})
    from app.modules.test_management.tm_quality_gate_settings import load_tm_quality_gate_settings

    data = await load_tm_quality_gate_settings(pid)
    return StandardResponse(data=data)


@router.put(
    "/quality-gate",
    summary="保存测试管理质量门禁阈值",
    dependencies=[Depends(require_any_permissions(PROJECT_SETTINGS_EDIT, AI_CONFIG_EDIT))],
)
async def update_quality_gate_settings(
    body: QualityGateSettingsBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.test_management.premium_gateway import raise_tm_premium_required, tm_premium_ready
    from app.modules.test_management.tm_quality_gate_settings import save_tm_quality_gate_settings

    if not tm_premium_ready():
        raise_tm_premium_required()
    pid = _resolve_project_id(user_info, project_id)
    try:
        saved = await save_tm_quality_gate_settings(pid, body.model_dump(exclude_unset=True))
    except ValueError as e:
        msg = str(e)
        status_code = 404 if msg == "项目不存在" else 422
        raise HTTPException(status_code=status_code, detail=msg) from e
    return StandardResponse(data=saved, message="质量门禁阈值已保存")


__all__ = [
    "router",
    "AiExecutionSettingsBody",
    "get_project_execution_settings",
    "update_project_execution_settings",
]
