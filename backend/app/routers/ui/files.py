"""Web 自动化测试文件管理（MinIO ui-test-files）"""
from __future__ import annotations

import re
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from app.core.auth import get_current_username, require_permissions
from app.core.config import UI_TEST_FILE_BUCKET, UI_TEST_FILE_MAX_BYTES
from app.core.minio_client import is_minio_storage, minio_client
from app.core.test_file_service import get_test_file_download_url, get_test_file_preview_payload
from app.core.permissions import UI_CASE_EDIT, UI_CASE_VIEW
from app.core.ui_test_file_refs import (
    build_file_reference_map,
    collect_file_references,
    scan_legacy_upload_steps,
    empty_reference_summary,
)
from app.models.sys import Project
from app.models.ui import UiTestFile
from app.schemas.ai import StandardResponse

router = APIRouter(prefix="/files", tags=["UI测试文件"])

_ALLOWED_EXT = frozenset({
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".md",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip", ".xmind", ".json",
})


def _file_to_dict(row: UiTestFile) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "file_name": row.file_name,
        "file_key": row.file_key,
        "file_bucket": row.file_bucket,
        "mime_type": row.mime_type,
        "size": row.size,
        "username": row.username,
        "create_time": row.create_time.isoformat() if row.create_time else None,
        "update_time": row.update_time.isoformat() if row.update_time else None,
    }


async def _ensure_project(project_id: int) -> Project:
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def _validate_upload_filename(filename: str) -> str:
    name = (filename or "upload.bin").replace("\\", "/").split("/")[-1].strip()
    if not name or ".." in name:
        raise HTTPException(status_code=422, detail="非法文件名")
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext and ext not in _ALLOWED_EXT:
        raise HTTPException(status_code=422, detail=f"不支持的文件类型: {ext}")
    return name


def _build_object_key(project_id: int, filename: str) -> str:
    return f"{project_id}/{uuid4().hex}/{filename}"


class UiTestFileUploadResponse(BaseModel):
    id: int
    project_id: int
    file_name: str
    file_key: str
    file_bucket: str
    mime_type: str
    size: int


@router.get("", summary="测试文件列表", dependencies=[Depends(require_permissions(UI_CASE_VIEW))])
async def list_ui_test_files(
    project_id: int = Query(..., description="项目ID"),
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
):
    await _ensure_project(project_id)
    qs = UiTestFile.filter(project_id=project_id, is_del=False)
    if keyword:
        qs = qs.filter(file_name__icontains=keyword.strip())
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    ref_map = await build_file_reference_map(project_id)
    items = []
    for row in rows:
        item = _file_to_dict(row)
        item["references"] = ref_map.get(row.file_key, empty_reference_summary())
        items.append(item)
    return StandardResponse(data={
        "items": items,
        "total": total,
        "page": page,
        "size": size,
    })


@router.get("/migration-scan", summary="扫描 legacy files_path 上传步骤", dependencies=[Depends(require_permissions(UI_CASE_VIEW))])
async def migration_scan(project_id: int = Query(..., description="项目ID")):
    await _ensure_project(project_id)
    data = await scan_legacy_upload_steps(project_id)
    return StandardResponse(data=data)


@router.get("/{file_id}", summary="测试文件详情", dependencies=[Depends(require_permissions(UI_CASE_VIEW))])
async def get_ui_test_file(file_id: int, project_id: int = Query(..., description="项目ID")):
    await _ensure_project(project_id)
    row = await UiTestFile.get_or_none(id=file_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="测试文件不存在")
    return StandardResponse(data=_file_to_dict(row))


@router.get("/{file_id}/references", summary="测试文件引用统计", dependencies=[Depends(require_permissions(UI_CASE_VIEW))])
async def get_ui_test_file_references(file_id: int, project_id: int = Query(..., description="项目ID")):
    await _ensure_project(project_id)
    row = await UiTestFile.get_or_none(id=file_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="测试文件不存在")
    refs = await collect_file_references(project_id, row.file_key)
    return StandardResponse(data=refs)


@router.post(
    "/upload",
    summary="上传 UI 测试文件",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(UI_CASE_EDIT))],
)
async def upload_ui_test_file(
    project_id: int = Query(..., description="项目ID"),
    file: UploadFile = File(...),
    username: str = Depends(get_current_username),
):
    if not is_minio_storage():
        raise HTTPException(status_code=400, detail="当前平台存储非 MinIO，无法上传 UI 测试文件")

    await _ensure_project(project_id)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="文件内容为空")
    if len(content) > UI_TEST_FILE_MAX_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"文件过大，上限 {UI_TEST_FILE_MAX_BYTES // (1024 * 1024)}MB",
        )

    safe_name = _validate_upload_filename(file.filename or "upload.bin")
    object_key = _build_object_key(project_id, safe_name)
    mime_type = file.content_type or "application/octet-stream"
    ok = minio_client.upload_bytes(
        object_name=object_key,
        data=content,
        content_type=mime_type,
        bucket_name=UI_TEST_FILE_BUCKET,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="文件上传失败")

    row = await UiTestFile.create(
        project_id=project_id,
        file_name=safe_name,
        file_key=object_key,
        file_bucket=UI_TEST_FILE_BUCKET,
        mime_type=mime_type,
        size=len(content),
        username=username,
    )
    return StandardResponse(data=UiTestFileUploadResponse(
        id=row.id,
        project_id=row.project_id,
        file_name=row.file_name,
        file_key=row.file_key,
        file_bucket=row.file_bucket,
        mime_type=row.mime_type,
        size=row.size,
    ))


@router.get("/{file_id}/preview-content", summary="获取测试文件预览内容", dependencies=[Depends(require_permissions(UI_CASE_VIEW))])
async def get_ui_test_file_preview_content(file_id: int, project_id: int = Query(..., description="项目ID")):
    await _ensure_project(project_id)
    row = await UiTestFile.get_or_none(id=file_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="测试文件不存在")
    data = await get_test_file_preview_payload(row, default_bucket=UI_TEST_FILE_BUCKET)
    return StandardResponse(data=data)


@router.get("/{file_id}/download-url", summary="获取测试文件下载/预览地址", dependencies=[Depends(require_permissions(UI_CASE_VIEW))])
async def get_ui_test_file_download_url(file_id: int, project_id: int = Query(..., description="项目ID")):
    await _ensure_project(project_id)
    row = await UiTestFile.get_or_none(id=file_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="测试文件不存在")
    data = await get_test_file_download_url(row, default_bucket=UI_TEST_FILE_BUCKET)
    return StandardResponse(data=data)


@router.delete("/{file_id}", summary="删除测试文件", dependencies=[Depends(require_permissions(UI_CASE_EDIT))])
async def delete_ui_test_file(
    file_id: int,
    project_id: int = Query(..., description="项目ID"),
    force: bool = Query(False, description="强制删除（忽略引用）"),
):
    await _ensure_project(project_id)
    row = await UiTestFile.get_or_none(id=file_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="测试文件不存在")

    refs = await collect_file_references(project_id, row.file_key)
    if refs["total"] > 0 and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"该文件仍被 {refs['total']} 处步骤引用，无法删除",
                "references": refs,
            },
        )

    row.is_del = True
    await row.save()
    return StandardResponse(data={"id": file_id, "deleted": True})
