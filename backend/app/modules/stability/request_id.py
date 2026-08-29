"""X-Request-Id 注入（OBS lite）。"""
from __future__ import annotations

import uuid
from typing import Any

REQUEST_ID_HEADER = "X-Request-Id"


def _header_key_ci(headers: dict[str, Any], name: str) -> str | None:
    target = name.lower()
    for key in headers:
        if str(key).lower() == target:
            return str(key)
    return None


def get_request_id(headers: Any) -> str:
    if not isinstance(headers, dict):
        return ""
    key = _header_key_ci(headers, REQUEST_ID_HEADER)
    if not key:
        return ""
    return str(headers.get(key) or "").strip()


def set_request_id(headers: Any, request_id: str) -> dict[str, Any]:
    """写入规范键 X-Request-Id，并移除大小写不同的同义键，避免双键并存。"""
    out = dict(headers) if isinstance(headers, dict) else {}
    rid = str(request_id or "").strip()
    if not rid:
        return out
    while True:
        key = _header_key_ci(out, REQUEST_ID_HEADER)
        if not key:
            break
        out.pop(key, None)
    out[REQUEST_ID_HEADER] = rid
    return out


def ensure_request_id(headers: Any) -> tuple[dict[str, Any], str]:
    """若无 X-Request-Id 则生成 UUID，返回 (headers, request_id)。"""
    out = dict(headers) if isinstance(headers, dict) else {}
    existing = get_request_id(out)
    if existing:
        return set_request_id(out, existing), existing
    rid = str(uuid.uuid4())
    return set_request_id(out, rid), rid


def extract_request_id_from_detail(request_detail: Any, headers: Any = None) -> str:
    if isinstance(request_detail, dict):
        rid = str(request_detail.get("request_id") or "").strip()
        if rid:
            return rid
        nested = request_detail.get("headers")
        if isinstance(nested, dict):
            for key in ("final", "original"):
                part = nested.get(key)
                if isinstance(part, dict):
                    rid = get_request_id(part)
                    if rid:
                        return rid
            rid = get_request_id(nested)
            if rid:
                return rid
    return get_request_id(headers)
