"""Browser Lab 媒体 URL 解析（MinIO 对象 key / 本地 static）。"""
from __future__ import annotations

from typing import Any

from app.core.infra.minio_client import is_minio_storage, minio_client

_BROWSER_LAB_PREFIX = "browser_lab/"


def is_browser_lab_object_key(path: str | None) -> bool:
    raw = (path or "").strip().lstrip("/")
    return raw.startswith(_BROWSER_LAB_PREFIX) and ".." not in raw


def presign_browser_lab_object(object_key: str | None, *, expires: int = 7200) -> str | None:
    key = (object_key or "").strip().lstrip("/")
    if not key or not is_browser_lab_object_key(key):
        return None
    if not is_minio_storage():
        return None
    try:
        return minio_client.get_presigned_url(key, expires=expires)
    except Exception:
        return None


def resolve_browser_lab_gif_url(gif_path: str | None) -> str | None:
    if not gif_path:
        return None
    signed = presign_browser_lab_object(gif_path)
    if signed:
        return signed
    if is_browser_lab_object_key(gif_path):
        return None
    return f"/static/{gif_path.lstrip('/')}"


def resolve_browser_lab_screenshot_url(screenshot_file: str | None) -> str | None:
    """MinIO 对象 key → 预签名 URL；本地文件名返回 None（走原有 /screenshots/ 接口）。"""
    if not screenshot_file:
        return None
    return presign_browser_lab_object(screenshot_file)


def enrich_step_log_media(step_log: list | None) -> list:
    """为 step 事件补充 screenshot_url（MinIO 直传场景）。"""
    if not step_log:
        return []
    out: list[Any] = []
    for evt in step_log:
        if not isinstance(evt, dict):
            out.append(evt)
            continue
        item = dict(evt)
        if item.get("type") == "step":
            shot = item.get("screenshot_file")
            url = resolve_browser_lab_screenshot_url(shot)
            if url:
                item["screenshot_url"] = url
        out.append(item)
    return out
