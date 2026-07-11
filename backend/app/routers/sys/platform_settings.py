"""平台全局设置 API"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.platform.auth import get_current_username, is_authenticated, require_permissions
from app.core.platform.permissions import PLATFORM_SETTINGS_EDIT, PLATFORM_SETTINGS_VIEW
from app.core.platform.platform_settings_service import (
    DELETE_MODE_LOGICAL,
    DELETE_MODE_PHYSICAL,
    DELETE_MODE_RECYCLE_BIN,
    get_platform_settings,
    save_platform_settings,
)

router = APIRouter(prefix="/platform-settings", tags=["平台设置"])


class PlatformSettingsForm(BaseModel):
    ui_case_record_delete_mode: str | None = Field(
        default=None,
        description="UI用例运行记录删除模式：logical|physical|recycle_bin",
    )
    knowledge_report_delete_mode: str | None = Field(
        default=None,
        description="资料库删除模式（生成记录、上传文档）：logical|physical",
    )


@router.get(
    "/config",
    summary="获取平台全局设置",
    dependencies=[Depends(is_authenticated), Depends(require_permissions(PLATFORM_SETTINGS_VIEW))],
)
async def get_admin_platform_settings():
    return await get_platform_settings()


@router.put(
    "/config",
    summary="保存平台全局设置",
    dependencies=[Depends(is_authenticated), Depends(require_permissions(PLATFORM_SETTINGS_EDIT))],
)
async def update_platform_settings(
    item: PlatformSettingsForm,
    username: str = Depends(get_current_username),
):
    ui_mode = item.ui_case_record_delete_mode
    if ui_mode is not None and ui_mode not in {DELETE_MODE_LOGICAL, DELETE_MODE_PHYSICAL, DELETE_MODE_RECYCLE_BIN}:
        ui_mode = DELETE_MODE_LOGICAL
    report_mode = item.knowledge_report_delete_mode
    if report_mode is not None and report_mode not in {DELETE_MODE_LOGICAL, DELETE_MODE_PHYSICAL}:
        report_mode = DELETE_MODE_LOGICAL
    return await save_platform_settings(
        ui_case_record_delete_mode=ui_mode,
        knowledge_report_delete_mode=report_mode,
        username=username,
    )
