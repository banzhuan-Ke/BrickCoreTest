"""资产映射 API"""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import TEST_RELEASE_EDIT, TEST_RELEASE_VIEW
from app.modules.test_management import service as svc
from app.schemas.test_management import (
    AssetLinkCreateBody,
    AssetLinkUpdateBody,
    SeedLinksBody,
    StandardResponse,
)

router = APIRouter(prefix="/asset-links", tags=["测试管理-资产映射"])


def _username(user_info: dict) -> str:
    return user_info.get("username") or user_info.get("sub") or "system"


@router.get("", response_model=StandardResponse, dependencies=[Depends(require_permissions(TEST_RELEASE_VIEW))])
async def list_links(
    project_id: int = Query(...),
    functional_case_id: Optional[int] = Query(None),
    asset_type: Optional[str] = Query(None),
    asset_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    data = await svc.list_asset_links(
        project_id,
        functional_case_id=functional_case_id,
        asset_type=asset_type,
        asset_id=asset_id,
    )
    return StandardResponse(data=data)


@router.post("", response_model=StandardResponse, dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))])
async def create_link(
    body: AssetLinkCreateBody,
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.create_asset_link(
        project_id=body.project_id,
        functional_case_id=body.functional_case_id,
        asset_type=body.asset_type,
        asset_id=body.asset_id,
        link_type=body.link_type,
        coverage_note=body.coverage_note,
        username=_username(user_info),
    )
    return StandardResponse(data=svc.asset_link_to_dict(row))


@router.get(
    "/preview",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_VIEW))],
)
async def preview_asset(
    project_id: int = Query(...),
    asset_type: str = Query(...),
    asset_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    name = await svc.preview_asset_name(project_id, asset_type, asset_id)
    return StandardResponse(data={"asset_type": asset_type, "asset_id": asset_id, "name": name})


@router.patch("/{link_id}", response_model=StandardResponse, dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))])
async def update_link(
    link_id: int,
    body: AssetLinkUpdateBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.update_asset_link(
        link_id, project_id, body.model_dump(exclude_unset=True), _username(user_info)
    )
    return StandardResponse(data=svc.asset_link_to_dict(row))


@router.delete("/{link_id}", response_model=StandardResponse, dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))])
async def delete_link(
    link_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    await svc.delete_asset_link(link_id, project_id, _username(user_info))
    return StandardResponse(message="已删除")


@router.post(
    "/seed-from-imports",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))],
)
async def seed_from_imports(
    body: SeedLinksBody,
    user_info: dict = Depends(is_authenticated),
):
    data = await svc.seed_asset_links_from_imports(body.project_id, _username(user_info))
    return StandardResponse(data=data)
