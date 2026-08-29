"""用例评审 API"""
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import (
    TEST_REVIEW_MANAGE,
    TEST_REVIEW_SUBMIT,
    TEST_REVIEW_VIEW,
)
from app.modules.test_management import review_service as svc
from app.schemas.test_management import (
    ReviewCreateBody,
    ReviewFinalizeBody,
    ReviewItemDecisionBody,
    ReviewTemplateCreateBody,
    ReviewTemplateUpdateBody,
    StandardResponse,
)

router = APIRouter(tags=["测试管理-评审"])


def _username(user_info: dict) -> str:
    return user_info.get("username") or user_info.get("sub") or "system"


def _user_id(user_info: dict) -> Optional[int]:
    uid = user_info.get("id") or user_info.get("user_id")
    try:
        return int(uid) if uid is not None else None
    except (TypeError, ValueError):
        return None


@router.get(
    "/review-templates",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_VIEW))],
)
async def list_templates(
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    rows = await svc.list_templates(project_id)
    return StandardResponse(data=[svc.template_to_dict(r) for r in rows])


@router.post(
    "/review-templates",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_MANAGE))],
)
async def create_template(
    body: ReviewTemplateCreateBody,
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.create_template(
        project_id=body.project_id,
        name=body.name,
        checklist=body.checklist,
        description=body.description,
        is_default=body.is_default,
        username=_username(user_info),
    )
    return StandardResponse(data=svc.template_to_dict(row))


@router.patch(
    "/review-templates/{template_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_MANAGE))],
)
async def update_template(
    template_id: int,
    body: ReviewTemplateUpdateBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    from app.models.test_management import CaseReviewTemplate

    template = await CaseReviewTemplate.get_or_none(
        id=template_id, project_id=project_id, is_del=False
    )
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    row = await svc.update_template(
        template,
        body.model_dump(exclude_unset=True),
        _username(user_info),
    )
    return StandardResponse(data=svc.template_to_dict(row))


@router.delete(
    "/review-templates/{template_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_MANAGE))],
)
async def delete_template(
    template_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    from app.models.test_management import CaseReviewTemplate

    template = await CaseReviewTemplate.get_or_none(
        id=template_id, project_id=project_id, is_del=False
    )
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    await svc.soft_delete_template(template, _username(user_info))
    return StandardResponse(message="已删除")


@router.get(
    "/reviews",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_VIEW))],
)
async def list_reviews(
    project_id: int = Query(...),
    release_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    rows = await svc.list_reviews(project_id, release_id=release_id, status=status)
    return StandardResponse(data=[svc.review_to_dict(r) for r in rows])


@router.post(
    "/reviews",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_MANAGE))],
)
async def create_review(
    body: ReviewCreateBody,
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.create_review(
        project_id=body.project_id,
        title=body.title,
        functional_case_ids=body.functional_case_ids,
        reviewer_ids=body.reviewer_ids,
        release_id=body.release_id,
        template_id=body.template_id,
        due_at=body.due_at,
        username=_username(user_info),
    )
    await svc.notify_review_created(row, actor_user_id=_user_id(user_info))
    return StandardResponse(data=svc.review_to_dict(row))


@router.get(
    "/reviews/{review_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_VIEW))],
)
async def get_review(
    review_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    review = await svc.get_review_or_404(review_id, project_id)
    items = await svc.list_review_items(review)
    release_owner_id = None
    if review.release_id:
        from app.modules.test_management.service import get_release_or_404

        release = await get_release_or_404(review.release_id, project_id)
        release_owner_id = release.owner_id
    return StandardResponse(
        data={
            "review": svc.review_to_dict(review),
            "items": items,
            "stats": svc.build_review_stats(review, items),
            "release_owner_id": release_owner_id,
        }
    )


@router.post(
    "/reviews/{review_id}/items/{item_id}/decision",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_SUBMIT))],
)
async def submit_decision(
    review_id: int,
    item_id: int,
    body: ReviewItemDecisionBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    review = await svc.get_review_or_404(review_id, project_id)
    auth_uid = _user_id(user_info)
    if auth_uid is None:
        raise HTTPException(status_code=400, detail="无法识别评审人")
    reviewer_id = auth_uid
    if body.reviewer_id is not None and int(body.reviewer_id) != auth_uid:
        if not user_info.get("is_superuser"):
            raise HTTPException(status_code=403, detail="不可代他人提交评审结论")
        reviewer_id = int(body.reviewer_id)
    item = await svc.submit_item_decision(
        review=review,
        item_id=item_id,
        reviewer_id=reviewer_id,
        decision=body.decision,
        comment=body.comment,
        checklist_result=body.checklist_result,
        username=_username(user_info),
        auth_user_id=auth_uid,
        allow_delegate=bool(user_info.get("is_superuser")),
        attachments=body.attachments,
    )
    review = await svc.get_review_or_404(review_id, project_id)
    items = await svc.list_review_items(review)
    return StandardResponse(
        data={
            "item": svc.review_item_to_dict(item),
            "review": svc.review_to_dict(review),
            "stats": svc.build_review_stats(review, items),
        }
    )


@router.post(
    "/reviews/{review_id}/finalize",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_VIEW))],
)
async def finalize_review(
    review_id: int,
    body: ReviewFinalizeBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    """最终定版写操作。

    路由保留 VIEW：版本负责人常见仅有查看权。真正定版权在服务层校验
    （版本负责人或 ``test_review:manage`` / 超管）。
    """
    from app.core.platform.permissions import TEST_REVIEW_MANAGE, get_user_permissions

    review = await svc.get_review_or_404(review_id, project_id)
    uid = _user_id(user_info)
    perms = set(await get_user_permissions(uid)) if uid else set()
    is_manager = bool(user_info.get("is_superuser") or TEST_REVIEW_MANAGE in perms)
    review = await svc.finalize_review(
        review,
        decision=body.decision,
        comment=body.comment,
        username=_username(user_info),
        actor_user_id=uid,
        is_manager=is_manager,
    )
    return StandardResponse(data=svc.review_to_dict(review), message="已最终定版")


@router.post(
    "/reviews/{review_id}/items/{item_id}/finalize",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_VIEW))],
)
async def finalize_review_item(
    review_id: int,
    item_id: int,
    body: ReviewFinalizeBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    """版本负责人对单条用例最终定版（非整批）。"""
    from app.core.platform.permissions import TEST_REVIEW_MANAGE, get_user_permissions
    from app.models.test_management import CaseReviewItem

    review = await svc.get_review_or_404(review_id, project_id)
    item = await CaseReviewItem.get_or_none(
        id=item_id, review_id=review.id, project_id=project_id, is_del=False
    )
    if not item:
        raise HTTPException(status_code=404, detail="评审项不存在")
    uid = _user_id(user_info)
    perms = set(await get_user_permissions(uid)) if uid else set()
    is_manager = bool(user_info.get("is_superuser") or TEST_REVIEW_MANAGE in perms)
    item = await svc.finalize_review_item(
        review,
        item,
        decision=body.decision,
        comment=body.comment,
        username=_username(user_info),
        actor_user_id=uid,
        is_manager=is_manager,
    )
    review = await svc.get_review_or_404(review_id, project_id)
    items = await svc.list_review_items(review)
    item_dict = next((x for x in items if x.get("id") == item.id), None)
    return StandardResponse(
        data={
            "item": item_dict,
            "review": svc.review_to_dict(review),
            "stats": svc.build_review_stats(review, items),
        },
        message="已对该用例定版",
    )


@router.post(
    "/reviews/attachments/upload",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_SUBMIT))],
)
async def upload_review_attachment(
    project_id: int = Query(...),
    file: UploadFile = File(...),
    user_info: dict = Depends(is_authenticated),
):
    """评审意见截图/附件上传（复用缺陷附件 MinIO 桶）。"""
    from uuid import uuid4

    from app.core.infra.minio_client import is_minio_storage, minio_client
    from app.core.platform.config import TEST_DEFECT_FILE_BUCKET, TEST_DEFECT_FILE_MAX_BYTES
    from app.models.sys import Project

    if not is_minio_storage():
        raise HTTPException(status_code=400, detail="当前平台存储非 MinIO，无法上传附件")
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="文件内容为空")
    if len(content) > TEST_DEFECT_FILE_MAX_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"文件过大，上限 {TEST_DEFECT_FILE_MAX_BYTES // (1024 * 1024)}MB",
        )
    name = (file.filename or "upload.bin").replace("\\", "/").split("/")[-1].strip()
    if not name or ".." in name:
        raise HTTPException(status_code=422, detail="非法文件名")
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    uid = uuid4().hex
    object_key = f"reviews/{project_id}/{uid}/{name}"
    mime_type = file.content_type or "application/octet-stream"
    ok = minio_client.upload_bytes(
        object_name=object_key,
        data=content,
        content_type=mime_type,
        bucket_name=TEST_DEFECT_FILE_BUCKET,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="文件上传失败")
    image_ext = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
    kind = "image" if (mime_type.startswith("image/") or ext in image_ext) else "file"
    return StandardResponse(
        data={
            "uid": uid,
            "name": name,
            "key": object_key,
            "bucket": TEST_DEFECT_FILE_BUCKET,
            "mime": mime_type,
            "size": len(content),
            "kind": kind,
        }
    )


@router.get(
    "/reviews/attachments/url",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_VIEW))],
)
async def get_review_attachment_url(
    project_id: int = Query(...),
    key: str = Query(...),
    bucket: Optional[str] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.core.infra.minio_client import is_minio_storage, minio_client
    from app.core.platform.config import TEST_DEFECT_FILE_BUCKET

    if not is_minio_storage():
        raise HTTPException(status_code=400, detail="当前平台存储非 MinIO")
    raw_key = (key or "").strip().lstrip("/")
    if not raw_key or ".." in raw_key:
        raise HTTPException(status_code=422, detail="非法对象键")
    if not (raw_key.startswith(f"{project_id}/") or raw_key.startswith(f"reviews/{project_id}/")):
        raise HTTPException(status_code=403, detail="无权访问该附件")
    target_bucket = (bucket or TEST_DEFECT_FILE_BUCKET).strip() or TEST_DEFECT_FILE_BUCKET
    url = minio_client.get_presigned_url(raw_key, bucket_name=target_bucket, expires=3600)
    if not url:
        raise HTTPException(status_code=404, detail="附件不存在或无法生成链接")
    return StandardResponse(data={"url": url})


@router.post(
    "/reviews/{review_id}/cancel",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_REVIEW_MANAGE))],
)
async def cancel_review(
    review_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    review = await svc.get_review_or_404(review_id, project_id)
    review = await svc.cancel_review(review, _username(user_info), user_id=_user_id(user_info))
    return StandardResponse(data=svc.review_to_dict(review))
