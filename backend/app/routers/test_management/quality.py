"""版本质量门禁 API"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import TEST_QUALITY_APPROVE_EXCEPTION, TEST_QUALITY_VIEW, TEST_RELEASE_EDIT
from app.modules.test_management import quality_service as qsvc
from app.modules.test_management import service as release_svc
from app.modules.test_management.premium_gateway import require_tm_premium
from app.schemas.test_management import (
    QualitySnapshotCreateBody,
    QualityWaiverBody,
    StandardResponse,
)

router = APIRouter(
    prefix="/releases",
    tags=["测试管理-质量门禁"],
    dependencies=[Depends(require_tm_premium)],
)


def _username(user_info: dict) -> str:
    return user_info.get("username") or user_info.get("sub") or "system"


async def _can_approve_waiver(user_info: dict) -> bool:
    """仅超管或持有 approve_exception 可豁免（不再允许版本负责人自批）。"""
    if user_info.get("is_superuser"):
        return True
    from app.core.platform.permissions import get_user_permissions

    uid = user_info.get("id") or user_info.get("user_id")
    if not uid:
        return False
    perms = set(await get_user_permissions(uid))
    return TEST_QUALITY_APPROVE_EXCEPTION in perms


@router.get(
    "/{release_id}/quality/preview",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_QUALITY_VIEW))],
)
async def quality_preview(
    release_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    release = await release_svc.get_release_or_404(release_id, project_id)
    data = await qsvc.compute_release_quality_preview(release)
    latest = await qsvc.get_latest_snapshot(release_id, project_id)
    snap = qsvc.snapshot_to_dict(latest) if latest else None
    data["latest_snapshot"] = snap
    live_ok = qsvc.is_release_quality_ok(data.get("conclusion"))
    data["snapshot_stale"] = bool(snap and snap.get("conclusion") == "pass" and not live_ok)
    data["has_valid_waiver"] = bool(snap and snap.get("waiver_valid"))
    # 实时未过且当前无有效豁免时，授权人可（重新）批准豁免
    data["can_reapprove_waiver"] = bool(not live_ok and not data["has_valid_waiver"])
    return StandardResponse(data=data)


@router.get(
    "/{release_id}/quality/report",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_QUALITY_VIEW))],
)
async def quality_report(
    release_id: int,
    project_id: int = Query(...),
    limit: int = Query(50, ge=1, le=200),
    user_info: dict = Depends(is_authenticated),
):
    release = await release_svc.get_release_or_404(release_id, project_id)
    data = await qsvc.build_quality_report(release, limit=limit)
    return StandardResponse(data=data)


@router.get(
    "/{release_id}/quality/snapshots",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_QUALITY_VIEW))],
)
async def list_quality_snapshots(
    release_id: int,
    project_id: int = Query(...),
    limit: int = Query(50, ge=1, le=200),
    user_info: dict = Depends(is_authenticated),
):
    await release_svc.get_release_or_404(release_id, project_id)
    rows = await qsvc.list_snapshots(release_id, project_id, limit=limit)
    return StandardResponse(data=rows)


@router.post(
    "/{release_id}/quality/snapshots",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_RELEASE_EDIT))],
)
async def create_quality_snapshot(
    release_id: int,
    body: QualitySnapshotCreateBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    release = await release_svc.get_release_or_404(release_id, project_id)
    row = await qsvc.create_quality_snapshot(
        release,
        username=_username(user_info),
        note=body.note,
        force=bool(body.force),
    )
    await qsvc.maybe_notify_quality_snapshot(
        release,
        row,
        actor_user_id=user_info.get("id"),
    )
    return StandardResponse(
        message="质量快照已生成",
        data=qsvc.snapshot_to_dict(row),
    )


@router.post(
    "/{release_id}/quality/waiver",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_QUALITY_APPROVE_EXCEPTION))],
)
async def approve_quality_waiver(
    release_id: int,
    body: QualityWaiverBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    release = await release_svc.get_release_or_404(release_id, project_id)
    if not await _can_approve_waiver(user_info):
        raise HTTPException(status_code=403, detail="无权批准质量豁免")
    row = await qsvc.approve_quality_waiver(
        release,
        reason=body.reason,
        username=_username(user_info),
        note=body.note,
    )
    await qsvc.maybe_notify_quality_snapshot(
        release,
        row,
        actor_user_id=user_info.get("id"),
    )
    return StandardResponse(
        message="已记录有条件通过（豁免）",
        data=qsvc.snapshot_to_dict(row),
    )
