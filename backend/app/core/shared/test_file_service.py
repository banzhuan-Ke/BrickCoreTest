"""测试文件预览/下载公共逻辑"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.core.infra.minio_client import is_minio_storage, minio_client
from app.core.shared.test_file_preview import build_preview_payload, preview_content_type


async def get_test_file_preview_payload(
    row,
    *,
    default_bucket: str,
) -> dict[str, Any]:
    if not is_minio_storage():
        raise HTTPException(status_code=400, detail="当前平台存储非 MinIO，无法预览文件")
    filename = getattr(row, "file_name", "") or ""
    if not preview_content_type(filename):
        raise HTTPException(status_code=422, detail="该文件类型不支持在线预览")
    content = minio_client.download_object(
        getattr(row, "file_key"),
        getattr(row, "file_bucket", None) or default_bucket,
    )
    if not content:
        raise HTTPException(status_code=500, detail="读取文件失败")
    try:
        return build_preview_payload(content, filename, getattr(row, "mime_type", "") or "")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


async def get_test_file_download_url(
    row,
    *,
    default_bucket: str,
    expires: int = 7200,
) -> dict[str, Any]:
    if not is_minio_storage():
        raise HTTPException(status_code=400, detail="当前平台存储非 MinIO，无法生成下载链接")
    url = minio_client.get_presigned_url(
        getattr(row, "file_key"),
        expires,
        getattr(row, "file_bucket", None) or default_bucket,
    )
    if not url:
        raise HTTPException(status_code=500, detail="生成下载链接失败")
    return {
        "url": url,
        "file_name": getattr(row, "file_name", ""),
        "mime_type": getattr(row, "mime_type", ""),
        "size": getattr(row, "size", 0),
    }
