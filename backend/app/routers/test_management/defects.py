"""缺陷 API"""
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.core.infra.minio_client import is_minio_storage, minio_client
from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.config import (
    TEST_DEFECT_FILE_BUCKET,
    TEST_DEFECT_FILE_MAX_BYTES,
)
from app.core.platform.permissions import TEST_DEFECT_EDIT, TEST_DEFECT_VIEW
from app.models.sys import Project
from app.modules.test_management import defect_service as svc
from app.modules.test_management.plan_service import get_run_or_404
from app.schemas.test_management import (
    DefectCommentBody,
    DefectCreateBody,
    DefectFromRunItemBody,
    DefectLinkBody,
    DefectTransitionBody,
    DefectUpdateBody,
    StandardResponse,
)

router = APIRouter(tags=["测试管理-缺陷"])

_ALLOWED_EXT = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".md",
    ".zip", ".rar", ".7z", ".log", ".json", ".xml",
})
_IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"})


def _username(user_info: dict) -> str:
    return user_info.get("username") or user_info.get("sub") or "system"


def _user_id(user_info: dict):
    uid = user_info.get("id")
    return int(uid) if uid is not None else None


def _safe_filename(filename: str) -> str:
    name = (filename or "upload.bin").replace("\\", "/").split("/")[-1].strip()
    if not name or ".." in name:
        raise HTTPException(status_code=422, detail="非法文件名")
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext and ext not in _ALLOWED_EXT:
        raise HTTPException(status_code=422, detail=f"不支持的文件类型: {ext}")
    return name


@router.post(
    "/defects/attachments/upload",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_DEFECT_EDIT))],
)
async def upload_defect_attachment(
    project_id: int = Query(...),
    file: UploadFile = File(...),
    user_info: dict = Depends(is_authenticated),
):
    """上传缺陷图片/附件到 MinIO，返回可写入 attachments 的元数据。"""
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

    safe_name = _safe_filename(file.filename or "upload.bin")
    ext = ("." + safe_name.rsplit(".", 1)[-1].lower()) if "." in safe_name else ""
    uid = uuid4().hex
    object_key = f"{project_id}/{uid}/{safe_name}"
    mime_type = file.content_type or "application/octet-stream"
    ok = minio_client.upload_bytes(
        object_name=object_key,
        data=content,
        content_type=mime_type,
        bucket_name=TEST_DEFECT_FILE_BUCKET,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="文件上传失败")

    kind = "image" if (mime_type.startswith("image/") or ext in _IMAGE_EXT) else "file"
    return StandardResponse(
        data={
            "uid": uid,
            "name": safe_name,
            "key": object_key,
            "bucket": TEST_DEFECT_FILE_BUCKET,
            "mime": mime_type,
            "size": len(content),
            "kind": kind,
        }
    )


@router.get(
    "/defects/attachments/url",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_DEFECT_VIEW))],
)
async def get_defect_attachment_url(
    project_id: int = Query(...),
    key: str = Query(..., min_length=1, max_length=500),
    bucket: Optional[str] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    """生成缺陷附件预签名下载/预览 URL。"""
    if not is_minio_storage():
        raise HTTPException(status_code=400, detail="当前平台存储非 MinIO")
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    # 仅允许本项目前缀，防止越权读其它对象
    prefix = f"{project_id}/"
    if ".." in key or not key.startswith(prefix):
        raise HTTPException(status_code=403, detail="无权访问该附件")
    target_bucket = (bucket or TEST_DEFECT_FILE_BUCKET).strip() or TEST_DEFECT_FILE_BUCKET
    url = minio_client.get_presigned_url(key, 7200, target_bucket)
    if not url:
        raise HTTPException(status_code=500, detail="生成下载链接失败")
    return StandardResponse(data={"url": url})


@router.get(
    "/defects/stats",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_DEFECT_VIEW))],
)
async def defect_stats(
    project_id: int = Query(...),
    release_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    data = await svc.get_defect_stats(project_id, release_id=release_id)
    return StandardResponse(data=data)


@router.get(
    "/defects",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_DEFECT_VIEW))],
)
async def list_defects(
    project_id: int = Query(...),
    release_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    assignee_id: Optional[int] = Query(None),
    functional_case_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    rows = await svc.list_defects(
        project_id,
        release_id=release_id,
        status=status,
        keyword=keyword,
        severity=severity,
        assignee_id=assignee_id,
        functional_case_id=functional_case_id,
    )
    return StandardResponse(data=rows)


@router.post(
    "/defects",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_DEFECT_EDIT))],
)
async def create_defect(
    body: DefectCreateBody,
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.create_defect(
        project_id=body.project_id,
        title=body.title,
        username=_username(user_info),
        release_id=body.release_id,
        description=body.description,
        severity=body.severity,
        priority=body.priority,
        status=body.status,
        found_in=body.found_in,
        assignee_id=body.assignee_id,
        reporter_id=body.reporter_id,
        external_system=body.external_system,
        external_key=body.external_key,
        external_url=body.external_url,
        attachments=body.attachments,
        links=body.links,
        actor_user_id=_user_id(user_info),
    )
    return StandardResponse(data=await svc.get_defect_detail(row))


@router.post(
    "/defects/{defect_id}/transition",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_DEFECT_VIEW))],
)
async def transition_defect(
    defect_id: int,
    body: DefectTransitionBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    """负责人处理：填写意见后进入下一状态（可改处理人）。超管可强制。"""
    row = await svc.get_defect_or_404(defect_id, project_id)
    force = bool(user_info.get("is_superuser"))
    row = await svc.transition_defect(
        row,
        to_status=body.to_status,
        username=_username(user_info),
        actor_user_id=_user_id(user_info),
        comment=body.comment,
        assignee_id=body.assignee_id,
        handler_id=body.handler_id,
        attributor_id=body.attributor_id,
        resolution_type=body.resolution_type,
        resolution_detail=body.resolution_detail,
        force=force,
    )
    return StandardResponse(data=await svc.get_defect_detail(row))


@router.get(
    "/defects/{defect_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_DEFECT_VIEW))],
)
async def get_defect(
    defect_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.get_defect_or_404(defect_id, project_id)
    return StandardResponse(data=await svc.get_defect_detail(row))


@router.patch(
    "/defects/{defect_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_DEFECT_EDIT))],
)
async def update_defect(
    defect_id: int,
    body: DefectUpdateBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.get_defect_or_404(defect_id, project_id)
    row = await svc.update_defect(
        row, body.model_dump(exclude_unset=True), _username(user_info),
        actor_user_id=_user_id(user_info),
    )
    return StandardResponse(data=await svc.get_defect_detail(row))


@router.delete(
    "/defects/{defect_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_DEFECT_EDIT))],
)
async def delete_defect(
    defect_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.get_defect_or_404(defect_id, project_id)
    await svc.soft_delete_defect(row, _username(user_info))
    return StandardResponse(message="已删除")


@router.post(
    "/defects/{defect_id}/comments",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_DEFECT_EDIT))],
)
async def add_defect_comment(
    defect_id: int,
    body: DefectCommentBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.get_defect_or_404(defect_id, project_id)
    comment = await svc.add_defect_comment(row, body.body, _username(user_info))
    return StandardResponse(data=svc.comment_to_dict(comment))


@router.delete(
    "/defects/{defect_id}/comments/{comment_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_DEFECT_EDIT))],
)
async def delete_defect_comment(
    defect_id: int,
    comment_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.get_defect_or_404(defect_id, project_id)
    await svc.soft_delete_comment(row, comment_id, _username(user_info))
    return StandardResponse(message="已删除评论")


@router.post(
    "/defects/{defect_id}/links",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_DEFECT_EDIT))],
)
async def add_defect_link(
    defect_id: int,
    body: DefectLinkBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.get_defect_or_404(defect_id, project_id)
    link = await svc.add_defect_link(
        row, body.model_dump(exclude_unset=True), _username(user_info)
    )
    enriched = await svc._enrich_links([link], project_id)
    return StandardResponse(data=enriched[0] if enriched else svc.link_to_dict(link))


@router.delete(
    "/defects/{defect_id}/links/{link_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_DEFECT_EDIT))],
)
async def remove_defect_link(
    defect_id: int,
    link_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.get_defect_or_404(defect_id, project_id)
    await svc.remove_defect_link(row, link_id, _username(user_info))
    return StandardResponse(message="已移除关联")


@router.post(
    "/plan-run-items/{item_id}/defects",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_DEFECT_EDIT))],
)
async def create_defect_from_run_item(
    item_id: int,
    body: DefectFromRunItemBody,
    project_id: int = Query(...),
    run_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    run = await get_run_or_404(run_id, project_id)
    data = await svc.create_defect_from_run_item(
        run,
        item_id,
        username=_username(user_info),
        title=body.title,
        description=body.description,
        severity=body.severity,
        priority=body.priority,
        assignee_id=body.assignee_id,
        reporter_id=body.reporter_id,
    )
    return StandardResponse(data=data)


@router.get(
    "/releases/{release_id}/defect-stats",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_DEFECT_VIEW))],
)
async def release_defect_stats(
    release_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    data = await svc.count_open_defects_for_release(release_id, project_id)
    return StandardResponse(data=data)


@router.get(
    "/releases/{release_id}/defect-report",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_DEFECT_VIEW))],
)
async def release_defect_report(
    release_id: int,
    project_id: int = Query(...),
    limit: int = Query(200, ge=1, le=500),
    user_info: dict = Depends(is_authenticated),
):
    data = await svc.build_release_defect_report(project_id, release_id, limit=limit)
    return StandardResponse(data=data)
