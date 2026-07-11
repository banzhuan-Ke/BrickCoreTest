"""执行器安装包发布配置（网盘外链等）"""
from fastapi import APIRouter, Depends

from app.core.platform.auth import get_current_username, is_authenticated, require_permissions
from app.core.platform.permissions import DEVICE_EDIT
from app.core.runner.runner_release_config_service import (
    get_runner_release_config_for_admin,
    save_runner_release_config,
)
from app.schemas.runner import RunnerReleaseConfigForm

router = APIRouter(
    prefix="/runner-release",
    tags=["执行器发布"],
    dependencies=[Depends(is_authenticated)],
)


@router.get(
    "/config",
    summary="获取执行器发布配置",
    dependencies=[Depends(require_permissions(DEVICE_EDIT))],
)
async def get_runner_release_config():
    return await get_runner_release_config_for_admin()


@router.put(
    "/config",
    summary="保存执行器发布配置",
    dependencies=[Depends(require_permissions(DEVICE_EDIT))],
)
async def update_runner_release_config(
    item: RunnerReleaseConfigForm,
    username: str = Depends(get_current_username),
):
    return await save_runner_release_config(
        external_download_url=item.external_download_url,
        external_download_label=item.external_download_label,
        username=username,
    )
