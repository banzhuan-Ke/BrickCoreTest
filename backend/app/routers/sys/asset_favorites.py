"""用户资产收藏（接口 / Web 用例）"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.platform.auth import get_current_username, require_permissions
from app.core.platform.permissions import API_MANAGE_VIEW, UI_CASE_VIEW
from app.models.sys import AssetFavorite, Project, User
from app.schemas.ai import StandardResponse

router = APIRouter(prefix="/asset-favorites", tags=["资产收藏"])


class AssetFavoriteItem(BaseModel):
    asset_type: str = Field(..., description="api | ui_case")
    asset_id: int = Field(..., ge=1)


async def _user_id(username: str) -> int:
    user = await User.get_or_none(username=username, is_del=False)
    if not user:
        raise HTTPException(status_code=422, detail="用户不存在")
    return user.id


@router.get("", summary="收藏列表")
async def list_asset_favorites(
    project_id: int = Query(...),
    username: str = Depends(get_current_username),
):
    if not await Project.get_or_none(id=project_id, is_del=False):
        raise HTTPException(status_code=404, detail="项目不存在")
    user_id = await _user_id(username)
    rows = await AssetFavorite.filter(user_id=user_id, project_id=project_id).order_by("sort_order", "id")
    return StandardResponse(
        data=[
            {"asset_type": r.asset_type, "asset_id": r.asset_id, "sort_order": r.sort_order}
            for r in rows
        ]
    )


@router.post("", summary="添加收藏")
async def add_asset_favorite(
    project_id: int = Query(...),
    body: AssetFavoriteItem = ...,
    username: str = Depends(get_current_username),
):
    if not await Project.get_or_none(id=project_id, is_del=False):
        raise HTTPException(status_code=404, detail="项目不存在")
    asset_type = (body.asset_type or "").strip().lower()
    if asset_type not in ("api", "ui_case"):
        raise HTTPException(status_code=422, detail="asset_type 须为 api 或 ui_case")
    user_id = await _user_id(username)
    exists = await AssetFavorite.filter(
        user_id=user_id, project_id=project_id, asset_type=asset_type, asset_id=body.asset_id
    ).exists()
    if not exists:
        count = await AssetFavorite.filter(user_id=user_id, project_id=project_id).count()
        await AssetFavorite.create(
            user_id=user_id,
            project_id=project_id,
            asset_type=asset_type,
            asset_id=body.asset_id,
            sort_order=count,
        )
    return StandardResponse(message="已收藏")


@router.delete("", summary="取消收藏")
async def remove_asset_favorite(
    project_id: int = Query(...),
    asset_type: str = Query(...),
    asset_id: int = Query(..., ge=1),
    username: str = Depends(get_current_username),
):
    user_id = await _user_id(username)
    await AssetFavorite.filter(
        user_id=user_id,
        project_id=project_id,
        asset_type=asset_type.strip().lower(),
        asset_id=asset_id,
    ).delete()
    return StandardResponse(message="已取消收藏")
