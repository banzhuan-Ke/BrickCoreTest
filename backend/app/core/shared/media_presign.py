"""将结果数据中的 MinIO 对象 URL 替换为浏览器可访问的预签名 URL。"""
from __future__ import annotations

import json
from typing import Any

from app.core.infra.minio_client import is_minio_storage, minio_client


def presign_media_urls_in_result(result_data: Any) -> Any:
    """将 result_data 中的 MinIO 静态 URL 替换为预签名 URL。"""
    if not result_data or not is_minio_storage():
        return result_data

    if isinstance(result_data, str):
        try:
            result_data = json.loads(result_data)
        except json.JSONDecodeError:
            return result_data

    if not isinstance(result_data, dict):
        return result_data

    def presign(url: str | None) -> str | None:
        if not url or not isinstance(url, str):
            return url
        bucket = minio_client.bucket_name
        marker = f"/{bucket}/"
        if marker not in url:
            return url
        filename = url.split(marker, 1)[-1]
        signed = minio_client.get_presigned_url(filename, expires=7200)
        return signed or url

    data = dict(result_data)
    for key in ("img", "video_url", "screenshot", "image"):
        if key in data:
            data[key] = presign(data[key])
    for step in data.get("steps", []):
        if isinstance(step, dict):
            if "screenshot" in step:
                step["screenshot"] = presign(step["screenshot"])
            if "image" in step:
                step["image"] = presign(step["image"])
    return data
