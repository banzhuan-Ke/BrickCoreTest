"""Runner 下载预签名 API（UI 测试文件/文件夹等）"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.core.auth import verify_runner_token
from app.core.config import UI_TEST_FILE_BUCKET
from app.core.minio_client import is_minio_storage, minio_client
from app.models.ui import UiTestFolder
from app.routers.ui.folders import validate_folder_key
from app.schemas.runner import (
    RunnerAppTemplateDownloadRequest,
    RunnerDownloadPresignRequest,
    RunnerDownloadPresignResponse,
    RunnerFolderManifestFile,
    RunnerFolderManifestRequest,
    RunnerFolderManifestResponse,
)

router = APIRouter(prefix="/runner", tags=["Runner 客户端"])

PRESIGN_EXPIRES = 3600

_ALLOWED_BUCKETS = frozenset({UI_TEST_FILE_BUCKET})

_FILE_OBJECT_KEY_RE = re.compile(r"^[0-9]+/[A-Fa-f0-9]{32}/.+$")


def _validate_file_object_key(value: str) -> str:
    name = value.replace("\\", "/").lstrip("/")
    if not name or ".." in name:
        raise ValueError("非法 object key")
    if not _FILE_OBJECT_KEY_RE.match(name):
        raise ValueError("object key 格式不正确")
    return name


@router.post(
    "/download/app-template",
    summary="下载 App 元素库图像模板（Runner 直取字节，不依赖本机 MinIO 配置）",
    status_code=status.HTTP_200_OK,
)
async def runner_download_app_template(
    item: RunnerAppTemplateDownloadRequest,
    _ctx: dict = Depends(verify_runner_token),
):
    if not is_minio_storage():
        raise HTTPException(status_code=400, detail="当前平台存储非 MinIO")

    data = minio_client.download_app_element_template(item.object_key)
    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"图像模板不存在: {item.object_key}，请在元素库重新上传识别图",
        )

    lower = item.object_key.lower()
    media_type = "image/png"
    if lower.endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    elif lower.endswith(".webp"):
        media_type = "image/webp"
    return Response(content=data, media_type=media_type)


@router.post(
    "/download/presign",
    summary="获取 MinIO 预签名下载 URL（单文件）",
    response_model=RunnerDownloadPresignResponse,
    status_code=status.HTTP_200_OK,
)
async def runner_download_presign(
    item: RunnerDownloadPresignRequest,
    _ctx: dict = Depends(verify_runner_token),
):
    if not is_minio_storage():
        raise HTTPException(status_code=400, detail="当前平台存储非 MinIO")

    bucket = (item.bucket or UI_TEST_FILE_BUCKET).strip()
    if bucket not in _ALLOWED_BUCKETS:
        raise HTTPException(status_code=400, detail="不支持的 bucket")

    try:
        object_key = _validate_file_object_key(item.file_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    download_url = minio_client.get_presigned_url(
        object_key,
        expires=PRESIGN_EXPIRES,
        bucket_name=bucket,
    )
    if not download_url:
        raise HTTPException(status_code=500, detail="生成预签名下载 URL 失败")

    return RunnerDownloadPresignResponse(
        download_url=download_url,
        file_key=object_key,
        bucket=bucket,
        expires_in=PRESIGN_EXPIRES,
    )


@router.post(
    "/download/folder-manifest",
    summary="获取文件夹内全部文件的预签名下载清单",
    response_model=RunnerFolderManifestResponse,
    status_code=status.HTTP_200_OK,
)
async def runner_download_folder_manifest(
    item: RunnerFolderManifestRequest,
    _ctx: dict = Depends(verify_runner_token),
):
    if not is_minio_storage():
        raise HTTPException(status_code=400, detail="当前平台存储非 MinIO")

    bucket = (item.bucket or UI_TEST_FILE_BUCKET).strip()
    if bucket not in _ALLOWED_BUCKETS:
        raise HTTPException(status_code=400, detail="不支持的 bucket")

    try:
        folder_key = validate_folder_key(item.folder_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    row = await UiTestFolder.get_or_none(folder_key=folder_key, file_bucket=bucket, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="测试文件夹不存在或已删除")

    files: list[RunnerFolderManifestFile] = []
    for entry in row.entries or []:
        if not isinstance(entry, dict):
            continue
        object_key = (entry.get("object_key") or "").strip()
        relative_path = (entry.get("relative_path") or "").strip()
        if not object_key or not relative_path:
            continue
        try:
            object_key = _validate_file_object_key(object_key)
        except ValueError:
            continue
        download_url = minio_client.get_presigned_url(
            object_key,
            expires=PRESIGN_EXPIRES,
            bucket_name=bucket,
        )
        if not download_url:
            raise HTTPException(status_code=500, detail=f"生成预签名 URL 失败: {relative_path}")
        files.append(RunnerFolderManifestFile(
            relative_path=relative_path,
            object_key=object_key,
            download_url=download_url,
            size=int(entry.get("size") or 0),
        ))

    if not files:
        raise HTTPException(status_code=404, detail="文件夹内没有可下载的文件")

    return RunnerFolderManifestResponse(
        folder_key=folder_key,
        folder_name=row.folder_name or "",
        bucket=bucket,
        files=files,
        expires_in=PRESIGN_EXPIRES,
    )
