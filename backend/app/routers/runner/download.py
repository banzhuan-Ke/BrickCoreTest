"""Runner 下载预签名 API（UI 测试文件等）"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import verify_runner_token
from app.core.config import UI_TEST_FILE_BUCKET
from app.core.minio_client import is_minio_storage, minio_client
from app.schemas.runner import RunnerDownloadPresignRequest, RunnerDownloadPresignResponse

router = APIRouter(prefix="/runner", tags=["Runner 客户端"])

PRESIGN_EXPIRES = 3600

_ALLOWED_BUCKETS = frozenset({UI_TEST_FILE_BUCKET})


def _validate_object_key(value: str) -> str:
    name = value.replace("\\", "/").lstrip("/")
    if not name or ".." in name:
        raise ValueError("非法 object key")
    if not re.match(r"^[0-9]+/[A-Fa-f0-9]{32}/[^/]+$", name):
        raise ValueError("object key 格式不正确")
    return name


@router.post(
    "/download/presign",
    summary="获取 MinIO 预签名下载 URL",
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
        object_key = _validate_object_key(item.file_key)
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
