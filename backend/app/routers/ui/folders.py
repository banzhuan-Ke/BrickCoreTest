"""Web 自动化测试文件夹资源（MinIO ui-test-files，保留相对路径）"""
from __future__ import annotations

import re
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.core.platform.auth import get_current_username, require_permissions
from app.core.platform.config import (
    UI_TEST_FILE_BUCKET,
    UI_TEST_FOLDER_MAX_BYTES,
    UI_TEST_FOLDER_MAX_FILES,
)
from app.core.infra.minio_client import is_minio_storage, minio_client
from app.core.platform.permissions import UI_CASE_EDIT, UI_CASE_VIEW
from app.modules.ui.ui_test_folder_refs import (
    build_folder_reference_map,
    collect_folder_references,
    empty_folder_reference_summary,
)
from app.models.sys import Project
from app.models.ui import UiTestFolder
from app.schemas.ai import StandardResponse

router = APIRouter(prefix="/folders", tags=["UI测试文件夹"])

_FOLDER_KEY_RE = re.compile(r"^[0-9]+/[A-Fa-f0-9]{32}$")
# 允许中文等 Unicode 文件名；仅拦截控制字符、反斜杠与路径穿越
_FORBIDDEN_PATH_CHARS = re.compile(r"[\x00-\x1f\\]")


def _folder_to_dict(row: UiTestFolder) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "folder_name": row.folder_name,
        "folder_key": row.folder_key,
        "file_bucket": row.file_bucket,
        "file_count": row.file_count,
        "total_size": row.total_size,
        "entries": row.entries or [],
        "username": row.username,
        "create_time": row.create_time.isoformat() if row.create_time else None,
        "update_time": row.update_time.isoformat() if row.update_time else None,
    }


async def _ensure_project(project_id: int) -> Project:
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def _normalize_relative_path(raw: str) -> str:
    name = (raw or "").replace("\\", "/").strip().lstrip("/")
    if not name:
        raise HTTPException(status_code=422, detail=f"非法相对路径: {raw}")
    if _FORBIDDEN_PATH_CHARS.search(name):
        raise HTTPException(status_code=422, detail=f"路径包含非法字符: {raw}")
    segments = name.split("/")
    if ".." in segments or any(not seg or seg == "." for seg in segments):
        raise HTTPException(status_code=422, detail=f"非法相对路径: {raw}")
    return name


def _build_folder_prefix(project_id: int) -> str:
    return f"{project_id}/{uuid4().hex}"


def _build_object_key(folder_prefix: str, relative_path: str) -> str:
    return f"{folder_prefix}/{relative_path}"


@router.get("", summary="测试文件夹列表", dependencies=[Depends(require_permissions(UI_CASE_VIEW))])
async def list_ui_test_folders(
    project_id: int = Query(..., description="项目ID"),
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
):
    await _ensure_project(project_id)
    qs = UiTestFolder.filter(project_id=project_id, is_del=False)
    if keyword:
        qs = qs.filter(folder_name__icontains=keyword.strip())
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    ref_map = await build_folder_reference_map(project_id)
    items = []
    for row in rows:
        item = _folder_to_dict(row)
        item["references"] = ref_map.get(row.folder_key, empty_folder_reference_summary())
        items.append(item)
    return StandardResponse(data={
        "items": items,
        "total": total,
        "page": page,
        "size": size,
    })


@router.get("/{folder_id}", summary="测试文件夹详情", dependencies=[Depends(require_permissions(UI_CASE_VIEW))])
async def get_ui_test_folder(folder_id: int, project_id: int = Query(..., description="项目ID")):
    await _ensure_project(project_id)
    row = await UiTestFolder.get_or_none(id=folder_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="测试文件夹不存在")
    return StandardResponse(data=_folder_to_dict(row))


@router.get("/{folder_id}/references", summary="文件夹引用统计", dependencies=[Depends(require_permissions(UI_CASE_VIEW))])
async def get_ui_test_folder_references(folder_id: int, project_id: int = Query(..., description="项目ID")):
    await _ensure_project(project_id)
    row = await UiTestFolder.get_or_none(id=folder_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="测试文件夹不存在")
    refs = await collect_folder_references(project_id, row.folder_key)
    return StandardResponse(data=refs)


@router.post(
    "/upload",
    summary="上传测试文件夹（保留目录结构）",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(UI_CASE_EDIT))],
)
async def upload_ui_test_folder(
    project_id: int = Query(..., description="项目ID"),
    folder_name: str = Query("", description="文件夹显示名称"),
    files: list[UploadFile] = File(...),
    username: str = Depends(get_current_username),
):
    if not is_minio_storage():
        raise HTTPException(status_code=400, detail="当前平台存储非 MinIO，无法上传测试文件夹")
    if not files:
        raise HTTPException(status_code=422, detail="未选择任何文件")
    if len(files) > UI_TEST_FOLDER_MAX_FILES:
        raise HTTPException(status_code=422, detail=f"文件数量超过上限 {UI_TEST_FOLDER_MAX_FILES}")

    await _ensure_project(project_id)
    folder_prefix = _build_folder_prefix(project_id)
    entries: list[dict[str, Any]] = []
    total_size = 0
    display_name = (folder_name or "").strip()

    for upload in files:
        content = await upload.read()
        if not content:
            continue
        relative_path = _normalize_relative_path(upload.filename or "file.bin")
        if not display_name:
            display_name = relative_path.split("/")[0]
        total_size += len(content)
        if total_size > UI_TEST_FOLDER_MAX_BYTES:
            raise HTTPException(
                status_code=422,
                detail=f"文件夹总大小超过上限 {UI_TEST_FOLDER_MAX_BYTES // (1024 * 1024)}MB",
            )
        object_key = _build_object_key(folder_prefix, relative_path)
        mime_type = upload.content_type or "application/octet-stream"
        ok = minio_client.upload_bytes(
            object_name=object_key,
            data=content,
            content_type=mime_type,
            bucket_name=UI_TEST_FILE_BUCKET,
        )
        if not ok:
            raise HTTPException(status_code=500, detail=f"上传失败: {relative_path}")
        entries.append({
            "relative_path": relative_path,
            "object_key": object_key,
            "size": len(content),
            "mime_type": mime_type,
        })

    if not entries:
        raise HTTPException(status_code=422, detail="文件夹内没有有效文件")

    if not display_name:
        display_name = f"文件夹_{folder_prefix.split('/')[-1][:8]}"

    row = await UiTestFolder.create(
        project_id=project_id,
        folder_name=display_name,
        folder_key=folder_prefix,
        file_bucket=UI_TEST_FILE_BUCKET,
        file_count=len(entries),
        total_size=total_size,
        entries=entries,
        username=username,
    )
    return StandardResponse(data=_folder_to_dict(row))


@router.delete("/{folder_id}", summary="删除测试文件夹", dependencies=[Depends(require_permissions(UI_CASE_EDIT))])
async def delete_ui_test_folder(
    folder_id: int,
    project_id: int = Query(..., description="项目ID"),
    force: bool = Query(False, description="强制删除（忽略引用）"),
):
    await _ensure_project(project_id)
    row = await UiTestFolder.get_or_none(id=folder_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="测试文件夹不存在")

    refs = await collect_folder_references(project_id, row.folder_key)
    if refs["total"] > 0 and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"该文件夹仍被 {refs['total']} 处步骤引用，无法删除",
                "references": refs,
            },
        )

    row.is_del = True
    await row.save()
    return StandardResponse(data={"id": folder_id, "deleted": True})


def validate_folder_key(folder_key: str) -> str:
    key = (folder_key or "").replace("\\", "/").strip().strip("/")
    if not key or ".." in key or not _FOLDER_KEY_RE.match(key):
        raise ValueError(f"非法 folder_key: {folder_key}")
    return key
