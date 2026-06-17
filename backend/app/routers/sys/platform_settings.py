"""平台全局设置 API"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.auth import get_current_username, is_authenticated, require_permissions
from app.core.permissions import PLATFORM_SETTINGS_EDIT, PLATFORM_SETTINGS_VIEW
from app.core.platform_settings_service import (
    DELETE_MODE_LOGICAL,
    DELETE_MODE_PHYSICAL,
    DELETE_MODE_RECYCLE_BIN,
    get_platform_settings,
    save_platform_settings,
)

router = APIRouter(prefix="/platform-settings", tags=["平台设置"])


class PlatformSettingsForm(BaseModel):
    ui_case_record_delete_mode: str = Field(
        default=DELETE_MODE_LOGICAL,
        description="UI用例运行记录删除模式：logical|physical|recycle_bin",
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
    mode = item.ui_case_record_delete_mode
    if mode not in {DELETE_MODE_LOGICAL, DELETE_MODE_PHYSICAL, DELETE_MODE_RECYCLE_BIN}:
        mode = DELETE_MODE_LOGICAL
    return await save_platform_settings(
        ui_case_record_delete_mode=mode,
        username=username,
    )
