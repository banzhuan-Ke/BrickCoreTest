"""需求可测性评审 API"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import TEST_REVIEW_MANAGE, TEST_REVIEW_SUBMIT, TEST_REVIEW_VIEW
from app.modules.test_management import requirement_review_service as svc
from app.schemas.test_management import (
    RequirementReviewCompleteBody,
    RequirementReviewCreateBody,
    RequirementReviewDecisionBody,
    RequirementReviewItemBody,
    StandardResponse,
)

router = APIRouter(tags=["测试管理-需求评审"])


def _username(user_info: dict) -> str:
    return user_info.get("username") or user_info.get("sub") or "system"


def _user_id(user_info: dict) -> Optional[int]:
    uid = user_info.get("id") or user_info.get("user_id")
    try:
        return int(uid) if uid is not None else None
    except (TypeError, ValueError):
        return None


@router.get(
    "/requirement-reviews",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_VIEW))],
)
async def list_requirement_reviews(
    project_id: int = Query(...),
    requirement_id: Optional[int] = Query(None),
    release_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    rows = await svc.list_reviews(
        project_id,
        requirement_id=requirement_id,
        release_id=release_id,
    )
    return StandardResponse(data=[svc.review_to_dict(r) for r in rows])


@router.post(
    "/requirement-reviews",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_MANAGE))],
)
async def create_requirement_review(
    body: RequirementReviewCreateBody,
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.create_review(
        project_id=body.project_id,
        requirement_id=body.requirement_id,
        reviewer_ids=body.reviewer_ids,
        username=_username(user_info),
        ai_assist_summary=body.ai_assist_summary,
    )
    await svc.notify_requirement_review_created(row, actor_user_id=_user_id(user_info))
    return StandardResponse(data=svc.review_to_dict(row))


@router.get(
    "/requirement-reviews/{review_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_VIEW))],
)
async def get_requirement_review(
    review_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    from app.models.test_management import RequirementReview

    review = await RequirementReview.get_or_none(
        id=review_id, project_id=project_id, is_del=False
    )
    if not review:
        raise HTTPException(status_code=404, detail="评审不存在")
    items = await svc.list_review_items(review)
    requirement_preview = await svc.build_requirement_preview(review.requirement_id, project_id)
    return StandardResponse(
        data={
            "review": svc.review_to_dict(review),
            "items": items,
            "stats": svc.build_reviewer_stats(review),
            "requirement_preview": requirement_preview,
        }
    )


@router.post(
    "/requirement-reviews/{review_id}/items",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_SUBMIT))],
)
async def add_requirement_review_item(
    review_id: int,
    body: RequirementReviewItemBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    from app.core.platform.permissions import get_user_permissions
    from app.models.test_management import RequirementReview

    review = await RequirementReview.get_or_none(
        id=review_id, project_id=project_id, is_del=False
    )
    if not review:
        raise HTTPException(status_code=404, detail="评审不存在")
    uid = _user_id(user_info)
    perms = set(await get_user_permissions(uid)) if uid else set()
    is_manager = bool(user_info.get("is_superuser") or TEST_REVIEW_MANAGE in perms)
    item = await svc.add_review_item(
        review,
        category=body.category,
        comment=body.comment,
        suggested_fix=body.suggested_fix,
        section_id=body.section_id,
        severity=body.severity,
        username=_username(user_info),
        actor_user_id=uid,
        is_manager=is_manager,
    )
    return StandardResponse(data=svc.item_to_dict(item))


@router.post(
    "/requirement-reviews/{review_id}/decision",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_SUBMIT))],
)
async def submit_requirement_review_decision(
    review_id: int,
    body: RequirementReviewDecisionBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    """评审人提交个人结论（多人聚合，非覆盖）。"""
    from app.models.test_management import RequirementReview

    review = await RequirementReview.get_or_none(
        id=review_id, project_id=project_id, is_del=False
    )
    if not review:
        raise HTTPException(status_code=404, detail="评审不存在")
    auth_uid = _user_id(user_info)
    if auth_uid is None:
        raise HTTPException(status_code=401, detail="无法识别当前用户")
    reviewer_id = auth_uid
    if body.reviewer_id is not None and int(body.reviewer_id) != auth_uid:
        if not user_info.get("is_superuser"):
            raise HTTPException(status_code=403, detail="不可代他人提交评审结论")
        reviewer_id = int(body.reviewer_id)
    review = await svc.submit_reviewer_decision(
        review,
        reviewer_id=reviewer_id,
        decision=body.decision,
        comment=body.comment,
        username=_username(user_info),
        auth_user_id=auth_uid,
        allow_delegate=bool(user_info.get("is_superuser")),
    )
    return StandardResponse(
        data={
            "review": svc.review_to_dict(review),
            "stats": svc.build_reviewer_stats(review),
        },
        message="已提交结论",
    )


@router.post(
    "/requirement-reviews/{review_id}/complete",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_MANAGE))],
)
async def complete_requirement_review(
    review_id: int,
    body: RequirementReviewCompleteBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    from app.models.test_management import RequirementReview

    review = await RequirementReview.get_or_none(
        id=review_id, project_id=project_id, is_del=False
    )
    if not review:
        raise HTTPException(status_code=404, detail="评审不存在")
    review = await svc.complete_review(
        review,
        decision=body.decision,
        summary=body.summary,
        username=_username(user_info),
    )
    return StandardResponse(data=svc.review_to_dict(review))


@router.post(
    "/ai-requirements/{requirement_id}/reopen-review",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_SUBMIT))],
)
async def reopen_requirement_for_review(
    requirement_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    req = await svc.reopen_for_revise(requirement_id, project_id, _username(user_info))
    return StandardResponse(
        data={
            "id": req.id,
            "review_status": req.review_status,
        }
    )
