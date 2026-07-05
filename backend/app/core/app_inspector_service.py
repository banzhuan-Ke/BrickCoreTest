"""App Inspector 会话（Redis 存储，Runner 回调写入控件树与截图）"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from app.core.redis_client import redis_cli
from app.core.minio_client import is_minio_storage, minio_client

SESSION_PREFIX = "app_inspector:session:"
SESSION_TTL_SECONDS = 1800


def _key(session_id: str) -> str:
    return f"{SESSION_PREFIX}{session_id}"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _presign_minio_object_url(url: str | None) -> str | None:
    """MinIO 私有 bucket 的对象 URL 转为浏览器可读的预签名 GET URL。"""
    if not url or not isinstance(url, str) or not is_minio_storage():
        return url
    bucket = minio_client.bucket_name
    marker = f"/{bucket}/"
    if marker not in url:
        return url
    filename = url.split(marker, 1)[-1]
    signed = minio_client.get_presigned_url(filename, expires=7200)
    return signed or url


def extract_screenshot_object_key(url: str | None) -> str | None:
    """从 Inspector 截图 access_url 解析 MinIO object key。"""
    if not url or not isinstance(url, str) or not is_minio_storage():
        return None
    bucket = minio_client.bucket_name
    marker = f"/{bucket}/"
    if marker not in url:
        return None
    key = url.split(marker, 1)[-1].split("?")[0].strip()
    return key or None


async def load_session_screenshot_bytes(session: Dict[str, Any]) -> tuple[bytes, str]:
    """读取会话截图二进制（优先走 MinIO 内网，避免前端跨域裁剪失败）。"""
    raw_url = session.get("screenshot_url")
    if not raw_url:
        raise ValueError("暂无截图")

    object_key = extract_screenshot_object_key(raw_url)
    if object_key:
        data = minio_client.download_object(object_key)
        if data:
            media = "image/jpeg" if object_key.lower().endswith((".jpg", ".jpeg")) else "image/png"
            return data, media

    import httpx

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(str(raw_url))
        resp.raise_for_status()
        media = (resp.headers.get("content-type") or "image/jpeg").split(";")[0].strip() or "image/jpeg"
        return resp.content, media


def prepare_session_for_client(session: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """返回给前端前处理（截图预签名等）。"""
    if not session:
        return session
    out = dict(session)
    if out.get("screenshot_url"):
        out["screenshot_url"] = _presign_minio_object_url(out["screenshot_url"])
    hierarchy = out.get("hierarchy")
    if isinstance(hierarchy, dict) and "nodes" in hierarchy:
        out["hierarchy"] = {"nodes": hierarchy["nodes"]}
    webview_dom = out.get("webview_dom")
    if isinstance(webview_dom, dict) and "nodes" in webview_dom:
        out["webview_dom"] = dict(webview_dom)
    return out


def slim_hierarchy_for_storage(hierarchy: Any) -> Any:
    """写入 Redis 前去掉冗余 xml / bounds，仅保留 nodes 树。"""
    if not hierarchy or not isinstance(hierarchy, dict):
        return hierarchy
    nodes = hierarchy.get("nodes")
    if nodes is not None:
        return {"nodes": nodes}
    return hierarchy


async def create_session(
    *,
    project_id: int,
    device_id: str,
    app_udid: str,
    username: str,
) -> Dict[str, Any]:
    session_id = uuid.uuid4().hex
    data = {
        "session_id": session_id,
        "project_id": project_id,
        "device_id": device_id,
        "app_udid": app_udid,
        "username": username,
        "status": "ready",
        "hierarchy": None,
        "screenshot_url": None,
        "package": "",
        "activity": "",
        "error": None,
        "webview_nodes": [],
        "webview_contexts": [],
        "webview_hint": "",
        "webview_status": "idle",
        "webview_dom": None,
        "webview_error": None,
        "webview_page_index": 0,
        "devtools_source": "webview",
        "chrome_contexts": [],
        "chrome_hint": "",
        "explore_status": "idle",
        "screenshot_status": "idle",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await redis_cli.setex(_key(session_id), SESSION_TTL_SECONDS, json.dumps(data, ensure_ascii=False))
    return data


async def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    raw = await redis_cli.get(_key(session_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def update_session(session_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    data = await get_session(session_id)
    if not data:
        return None
    data.update(fields)
    data["updated_at"] = _now_iso()
    await redis_cli.setex(_key(session_id), SESSION_TTL_SECONDS, json.dumps(data, ensure_ascii=False))
    return data


async def mark_dumping(session_id: str) -> Optional[Dict[str, Any]]:
    return await update_session(
        session_id,
        status="dumping",
        error=None,
        explore_status="idle",
        screenshot_status="idle",
        webview_status="idle",
        webview_dom=None,
        webview_error=None,
    )


async def apply_dump_result(session_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not payload.get("success"):
        return await update_session(
            session_id,
            status="failed",
            error=payload.get("error") or "dump 失败",
        )
    fields: Dict[str, Any] = {
        "status": "ready",
        "hierarchy": slim_hierarchy_for_storage(payload.get("hierarchy")),
        "screenshot_url": payload.get("screenshot_url"),
        "package": payload.get("package") or "",
        "activity": payload.get("activity") or "",
        "error": None,
        "webview_nodes": payload.get("webview_nodes") or [],
        "webview_contexts": payload.get("webview_contexts") or [],
        "webview_hint": payload.get("webview_hint") or "",
        "chrome_contexts": payload.get("chrome_contexts") or [],
        "chrome_hint": payload.get("chrome_hint") or "",
    }
    return await update_session(session_id, **fields)


async def mark_webview_probing(session_id: str, page_index: int = 0, devtools_source: str = "webview") -> Optional[Dict[str, Any]]:
    return await update_session(
        session_id,
        webview_status="probing",
        webview_error=None,
        webview_page_index=page_index,
        devtools_source=(devtools_source or "webview").strip().lower(),
    )


async def apply_webview_probe_result(session_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if payload.get("contexts") is not None:
        await update_session(session_id, webview_contexts=payload.get("contexts") or [])

    if not payload.get("success"):
        return await update_session(
            session_id,
            webview_status="failed",
            webview_dom=None,
            webview_error=payload.get("error") or "WebView DOM 探测失败",
        )

    dom = payload.get("dom")
    slim_dom = None
    if isinstance(dom, dict):
        slim_dom = {
            "nodes": dom.get("nodes") or [],
            "page_url": dom.get("page_url") or "",
            "page_title": dom.get("page_title") or "",
            "package": dom.get("package") or "",
        }

    return await update_session(
        session_id,
        webview_status="ready",
        webview_dom=slim_dom,
        webview_error=None,
        webview_contexts=payload.get("contexts") or [],
    )


async def close_session(session_id: str) -> None:
    await redis_cli.delete(_key(session_id))


async def mark_exploring(session_id: str) -> Optional[Dict[str, Any]]:
    return await update_session(session_id, explore_status="exploring", error=None)


async def apply_explore_result(session_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not payload.get("success"):
        return await update_session(
            session_id,
            explore_status="idle",
            error=payload.get("error") or "探索操作失败",
        )
    fields: Dict[str, Any] = {
        "explore_status": "ready",
        "error": None,
        "screenshot_url": payload.get("screenshot_url"),
    }
    if payload.get("hierarchy"):
        fields["status"] = "ready"
        fields["hierarchy"] = slim_hierarchy_for_storage(payload.get("hierarchy"))
    if payload.get("package") is not None:
        fields["package"] = payload.get("package") or ""
    if payload.get("activity") is not None:
        fields["activity"] = payload.get("activity") or ""
    if payload.get("webview_nodes") is not None:
        fields["webview_nodes"] = payload.get("webview_nodes") or []
    if payload.get("webview_contexts") is not None:
        fields["webview_contexts"] = payload.get("webview_contexts") or []
    if payload.get("webview_hint") is not None:
        fields["webview_hint"] = payload.get("webview_hint") or ""
    return await update_session(session_id, **fields)


async def mark_screenshot_refreshing(session_id: str) -> Optional[Dict[str, Any]]:
    return await update_session(session_id, screenshot_status="refreshing", error=None)


async def apply_screenshot_result(session_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not payload.get("success"):
        return await update_session(
            session_id,
            screenshot_status="failed",
            error=payload.get("error") or "截图刷新失败",
        )
    fields: Dict[str, Any] = {
        "screenshot_status": "ready",
        "error": None,
        "screenshot_url": payload.get("screenshot_url"),
    }
    if payload.get("package") is not None:
        fields["package"] = payload.get("package") or ""
    if payload.get("activity") is not None:
        fields["activity"] = payload.get("activity") or ""
    return await update_session(session_id, **fields)
