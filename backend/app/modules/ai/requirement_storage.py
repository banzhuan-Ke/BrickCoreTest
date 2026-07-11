"""
AI 需求文档与读图资源存储（MinIO 为主，本地磁盘为回退）
"""
from __future__ import annotations

import logging
import mimetypes
import os
from typing import Any, Optional

from app.core.platform.config import AI_REQUIREMENT_BUCKET, STATIC_DIR
from app.core.infra.minio_client import is_minio_storage, minio_client

logger = logging.getLogger(__name__)

# 本地回退目录（STORAGE_TYPE != minio 或 MinIO 不可用时）
LOCAL_REQ_DIR = os.path.join(STATIC_DIR, "ai_requirements")
os.makedirs(LOCAL_REQ_DIR, exist_ok=True)


def source_object_key(req_id: int, ext: str) -> str:
    ext = ext if ext.startswith(".") else f".{ext}" if ext else ".bin"
    return f"requirements/{req_id}/source{ext}"


def image_object_key(req_id: int, index: int, ext: str) -> str:
    ext = ext if ext.startswith(".") else f".{ext}"
    return f"requirements/{req_id}/images/{index}{ext}"


def _guess_content_type(file_name: str, fallback: str = "application/octet-stream") -> str:
    ct, _ = mimetypes.guess_type(file_name or "")
    return ct or fallback


def save_requirement_source(req_id: int, file_name: str, content: bytes) -> dict[str, Any]:
    """
    保存需求源文件，返回 storage 元数据：
    { storage: {type, bucket?, source_key?, file_path?}, file_path }
    """
    ext = os.path.splitext(file_name or "")[1].lower() or ".bin"
    if is_minio_storage():
        key = source_object_key(req_id, ext)
        ok = minio_client.upload_bytes(
            key,
            content,
            _guess_content_type(file_name),
            bucket_name=AI_REQUIREMENT_BUCKET,
        )
        if not ok:
            raise RuntimeError(f"需求文档上传 MinIO 失败: {key}")
        return {
            "storage": {
                "type": "minio",
                "bucket": AI_REQUIREMENT_BUCKET,
                "source_key": key,
            },
            "file_path": key,
        }

    rel_dir = os.path.join(LOCAL_REQ_DIR, str(req_id))
    os.makedirs(rel_dir, exist_ok=True)
    path = os.path.join(rel_dir, f"source{ext}")
    with open(path, "wb") as f:
        f.write(content)
    return {
        "storage": {"type": "local", "file_path": path},
        "file_path": path,
    }


def load_requirement_source(meta: dict) -> tuple[bytes, str]:
    """从 MinIO 或本地路径读取源文件字节。"""
    file_name = meta.get("file_name") or "requirement.docx"
    storage = meta.get("storage") if isinstance(meta.get("storage"), dict) else {}

    if storage.get("type") == "minio" and storage.get("source_key"):
        bucket = storage.get("bucket") or AI_REQUIREMENT_BUCKET
        data = minio_client.download_object(storage["source_key"], bucket)
        if data:
            return data, file_name
        raise FileNotFoundError(f"MinIO 源文件不存在: {storage['source_key']}")

    for path in (
        storage.get("file_path"),
        meta.get("file_path"),
    ):
        if path and os.path.isfile(path):
            with open(path, "rb") as f:
                return f.read(), file_name

    raise FileNotFoundError("源文件不存在，请重新上传需求文档")


def save_requirement_images(req_id: int, images: list) -> list[dict]:
    saved: list[dict] = []
    for img in images:
        ext = ".png" if getattr(img, "mime", None) == "image/png" else ".jpg"
        mime = getattr(img, "mime", None) or ("image/png" if ext == ".png" else "image/jpeg")
        idx = img.index
        item: dict[str, Any] = {
            "index": idx,
            "mime": mime,
            "source": getattr(img, "source", None),
            "page": getattr(img, "page", None),
        }

        if is_minio_storage():
            key = image_object_key(req_id, idx, ext)
            ok = minio_client.upload_bytes(
                key,
                img.data,
                mime,
                bucket_name=AI_REQUIREMENT_BUCKET,
            )
            if not ok:
                logger.warning("[requirement_storage] 图片上传 MinIO 失败: %s", key)
                continue
            item["object_key"] = key
            item["bucket"] = AI_REQUIREMENT_BUCKET
            item["path"] = key
            item["storage"] = {"type": "minio", "bucket": AI_REQUIREMENT_BUCKET, "object_key": key}
        else:
            rel_dir = os.path.join(LOCAL_REQ_DIR, str(req_id), "images")
            os.makedirs(rel_dir, exist_ok=True)
            fname = f"{idx}{ext}"
            path = os.path.join(rel_dir, fname)
            with open(path, "wb") as f:
                f.write(img.data)
            item["path"] = path
            item["storage"] = {"type": "local", "file_path": path}

        saved.append(item)
    return saved


def load_images_from_meta(meta: dict) -> list[dict]:
    """加载图片二进制，兼容旧数据（仅 path 本地）与新数据（MinIO object_key）。"""
    images = meta.get("images") or []
    result: list[dict] = []
    for item in images:
        if not isinstance(item, dict):
            continue
        data: Optional[bytes] = None
        storage = item.get("storage") if isinstance(item.get("storage"), dict) else {}
        object_key = item.get("object_key") or storage.get("object_key")
        bucket = item.get("bucket") or storage.get("bucket") or AI_REQUIREMENT_BUCKET

        if object_key or (storage.get("type") == "minio" and storage.get("object_key")):
            key = object_key or storage.get("object_key")
            data = minio_client.download_object(key, bucket)
            if not data:
                logger.warning(
                    "[requirement_storage] MinIO 读图失败 bucket=%s key=%s index=%s",
                    bucket,
                    key,
                    item.get("index"),
                )
        else:
            path = item.get("path") or storage.get("file_path")
            if path and os.path.isfile(path):
                with open(path, "rb") as f:
                    data = f.read()
            elif path:
                logger.warning(
                    "[requirement_storage] 本地图片不存在 path=%s index=%s",
                    path,
                    item.get("index"),
                )

        if data:
            result.append({**item, "data": data})
    return result


def get_storage_summary(meta: dict) -> dict:
    """供 API 返回存储位置摘要。"""
    storage = meta.get("storage") if isinstance(meta.get("storage"), dict) else {}
    stype = storage.get("type") or ("minio" if is_minio_storage() else "local")
    out = {"type": stype}
    if stype == "minio":
        out["bucket"] = storage.get("bucket") or AI_REQUIREMENT_BUCKET
        out["source_key"] = storage.get("source_key") or meta.get("file_path")
    else:
        out["file_path"] = storage.get("file_path") or meta.get("file_path")
    return out
