"""版本 / 范围 / 需求 API"""
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import TEST_QUALITY_VIEW, TEST_RELEASE_EDIT, TEST_RELEASE_VIEW
from app.models.test_management import TestReleaseRequirement
from app.modules.test_management import service as svc
from app.schemas.test_management import (
    ReleaseCreateBody,
    ReleaseTransitionBody,
    ReleaseUpdateBody,
    RequirementCreateBody,
    RequirementUpdateBody,
    RequirementUpgradeBody,
    ScopeBatchAddBody,
    ScopeBatchUpdateBody,
    ScopeUpdateBody,
    StandardResponse,
)

router = APIRouter(prefix="/releases", tags=["测试管理-版本"])


def _username(user_info: dict) -> str:
    return user_info.get("username") or user_info.get("sub") or "system"


def _user_id(user_info: dict) -> Optional[int]:
    uid = user_info.get("id")
    return int(uid) if uid is not None else None


@router.get("", response_model=StandardResponse, dependencies=[Depends(require_permissions(TEST_RELEASE_VIEW))])
async def list_releases(
    project_id: int = Query(...),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    rows = await svc.list_releases(project_id, status=status, keyword=keyword)
    return StandardResponse(data=[svc.release_to_dict(r) for r in rows])


@router.post("", response_model=StandardResponse, dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))])
async def create_release(
    body: ReleaseCreateBody,
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.create_release(
        project_id=body.project_id,
        release_key=body.release_key,
        name=body.name,
        description=body.description,
        owner_id=body.owner_id,
        planned_start_at=body.planned_start_at,
        planned_release_at=body.planned_release_at,
        external_url=body.external_url,
        username=_username(user_info),
    )
    return StandardResponse(data=svc.release_to_dict(row))


@router.get("/{release_id}", response_model=StandardResponse, dependencies=[Depends(require_permissions(TEST_RELEASE_VIEW))])
async def get_release(
    release_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.get_release_or_404(release_id, project_id)
    return StandardResponse(data=svc.release_to_dict(row))


@router.patch("/{release_id}", response_model=StandardResponse, dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))])
async def update_release(
    release_id: int,
    body: ReleaseUpdateBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.get_release_or_404(release_id, project_id)
    payload = body.model_dump(exclude_unset=True)
    row = await svc.update_release(row, payload, _username(user_info))
    return StandardResponse(data=svc.release_to_dict(row))


@router.post(
    "/{release_id}/transition",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))],
)
async def transition_release(
    release_id: int,
    body: ReleaseTransitionBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.get_release_or_404(release_id, project_id)
    row, warnings = await svc.transition_release(row, body.status, _username(user_info))
    data = svc.release_to_dict(row)
    if warnings:
        data = {"release": data, "warnings": warnings}
    return StandardResponse(data=data)


@router.delete("/{release_id}", response_model=StandardResponse, dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))])
async def delete_release(
    release_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.get_release_or_404(release_id, project_id)
    await svc.soft_delete_release(row, _username(user_info))
    return StandardResponse(message="已删除")


@router.get(
    "/{release_id}/overview",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_VIEW))],
)
async def get_overview(
    release_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.get_release_or_404(release_id, project_id)
    data = await svc.release_overview(row)
    return StandardResponse(data=data)


@router.get(
    "/{release_id}/export-package",
    dependencies=[Depends(require_permissions(TEST_RELEASE_VIEW, TEST_QUALITY_VIEW))],
)
async def export_release_package(
    release_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    """导出版本包：追溯矩阵 CSV + 质量摘要 JSON（ZIP）。"""
    from io import BytesIO

    from app.modules.test_management.export_service import build_release_export_package
    from app.modules.test_management.premium_gateway import require_tm_premium

    require_tm_premium()
    release = await svc.get_release_or_404(release_id, project_id)
    content, filename = await build_release_export_package(release)
    encoded = quote(filename)
    return StreamingResponse(
        BytesIO(content),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
        },
    )


@router.get(
    "/{release_id}/requirements",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_VIEW))],
)
async def list_requirements(
    release_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    await svc.get_release_or_404(release_id, project_id)
    rows = await svc.list_requirements(release_id, project_id)
    return StandardResponse(data=await svc.requirements_to_dicts(rows))


@router.post(
    "/{release_id}/requirements",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))],
)
async def add_requirement(
    release_id: int,
    body: RequirementCreateBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    release = await svc.get_release_or_404(release_id, project_id)
    row = await svc.add_requirement(
        release,
        requirement_key=body.requirement_key,
        title=body.title,
        url=body.url,
        note=body.note,
        username=_username(user_info),
    )
    rows = await svc.requirements_to_dicts([row])
    return StandardResponse(data=rows[0] if rows else svc.requirement_to_dict(row))


@router.put(
    "/{release_id}/requirements/{req_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))],
)
async def update_requirement(
    release_id: int,
    req_id: int,
    body: RequirementUpdateBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    await svc.get_release_or_404(release_id, project_id)
    row = await svc.update_release_requirement(
        req_id,
        release_id,
        project_id,
        title=body.title,
        url=body.url,
        note=body.note,
        username=_username(user_info),
    )
    rows = await svc.requirements_to_dicts([row])
    return StandardResponse(data=rows[0] if rows else svc.requirement_to_dict(row))


@router.get(
    "/{release_id}/requirements/{req_id}/preview",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_VIEW))],
)
async def preview_requirement(
    release_id: int,
    req_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    await svc.get_release_or_404(release_id, project_id)
    row = await TestReleaseRequirement.get_or_none(
        id=req_id, release_id=release_id, project_id=project_id, is_del=False
    )
    if not row:
        raise HTTPException(status_code=404, detail="需求条目不存在")
    return StandardResponse(data=await svc.get_requirement_preview(row, project_id))


@router.post(
    "/{release_id}/requirements/{req_id}/upgrade-to-ai",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))],
)
async def upgrade_requirement_to_ai(
    release_id: int,
    req_id: int,
    body: RequirementUpgradeBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    release = await svc.get_release_or_404(release_id, project_id)
    row = await TestReleaseRequirement.get_or_none(
        id=req_id, release_id=release_id, project_id=project_id, is_del=False
    )
    if not row:
        raise HTTPException(status_code=404, detail="需求条目不存在")
    row = await svc.upgrade_requirement_to_ai(
        row,
        release,
        name=body.name,
        initial_content=body.initial_content,
        username=_username(user_info),
    )
    rows = await svc.requirements_to_dicts([row])
    return StandardResponse(
        message="已升级为项目需求",
        data=rows[0] if rows else svc.requirement_to_dict(row),
    )


@router.delete(
    "/{release_id}/requirements/{req_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))],
)
async def delete_requirement(
    release_id: int,
    req_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    await svc.get_release_or_404(release_id, project_id)
    await svc.delete_requirement(req_id, release_id, project_id, _username(user_info))
    return StandardResponse(message="已删除")


@router.get(
    "/{release_id}/scopes",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_VIEW))],
)
async def list_scopes(
    release_id: int,
    project_id: int = Query(...),
    keyword: Optional[str] = Query(None),
    module: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    automation_status: Optional[str] = Query(None),
    owner_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    release = await svc.get_release_or_404(release_id, project_id)
    data = await svc.list_scopes(
        release,
        keyword=keyword,
        module=module,
        risk_level=risk_level,
        automation_status=automation_status,
        owner_id=owner_id,
    )
    return StandardResponse(data=data)


@router.post(
    "/{release_id}/scopes",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))],
)
async def batch_add_scopes(
    release_id: int,
    body: ScopeBatchAddBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    release = await svc.get_release_or_404(release_id, project_id)
    data = await svc.batch_add_scopes(
        release,
        functional_case_ids=body.functional_case_ids,
        risk_level=body.risk_level,
        owner_id=body.owner_id,
        requirement_key=body.requirement_key,
        username=_username(user_info),
        actor_user_id=_user_id(user_info),
    )
    return StandardResponse(data=data)


@router.patch(
    "/{release_id}/scopes/{scope_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))],
)
async def update_scope(
    release_id: int,
    scope_id: int,
    body: ScopeUpdateBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    release = await svc.get_release_or_404(release_id, project_id)
    row = await svc.update_scope(
        scope_id, release, body.model_dump(exclude_unset=True), _username(user_info),
        actor_user_id=_user_id(user_info),
    )
    return StandardResponse(data=await svc.scope_dict_with_case(row, project_id))


@router.post(
    "/{release_id}/scopes/batch-update",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))],
)
async def batch_update_scopes(
    release_id: int,
    body: ScopeBatchUpdateBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    release = await svc.get_release_or_404(release_id, project_id)
    data = await svc.batch_update_scopes(
        release,
        scope_ids=body.scope_ids,
        risk_level=body.risk_level,
        owner_id=body.owner_id,
        clear_owner=body.clear_owner,
        username=_username(user_info),
        actor_user_id=_user_id(user_info),
    )
    return StandardResponse(data=data)


@router.post(
    "/{release_id}/scopes/notify-owners",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))],
)
async def notify_scope_owners(
    release_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    """分配完成后手动通知：每位负责人一条汇总站内信。"""
    release = await svc.get_release_or_404(release_id, project_id)
    data = await svc.notify_scope_owners(
        release,
        actor_user_id=_user_id(user_info),
    )
    return StandardResponse(data=data, message="已推送负责人通知")


@router.delete(
    "/{release_id}/scopes/{scope_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))],
)
async def remove_scope(
    release_id: int,
    scope_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    release = await svc.get_release_or_404(release_id, project_id)
    cascade = await svc.remove_scope(scope_id, release, _username(user_info))
    return StandardResponse(message="已移除", data=cascade)
