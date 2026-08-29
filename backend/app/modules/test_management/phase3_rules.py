"""测试管理 Phase 3 — 派发权限、外部链接校验"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import HTTPException

from app.core.platform.permissions import (
    API_CASE_EXECUTE,
    APP_CASE_EXECUTE,
    PERF_SCENE_EXECUTE,
    UI_CASE_EXECUTE,
)

AUTOMATION_ITEM_EXECUTE_PERM: dict[str, str] = {
    "api_case": API_CASE_EXECUTE,
    "ui_case": UI_CASE_EXECUTE,
    "app_case": APP_CASE_EXECUTE,
    "perf_scene": PERF_SCENE_EXECUTE,
}

DEFECT_KEY_PREFIX = "BC-DEF-"
DEFECT_KEY_PATTERN = re.compile(r"^BC-DEF-(\d+)$", re.IGNORECASE)
LEGACY_DEFECT_KEY_PATTERN = re.compile(r"^DEF-(\d+)$", re.IGNORECASE)


def parse_defect_key_seq(defect_key: str) -> Optional[int]:
    key = (defect_key or "").strip()
    m = DEFECT_KEY_PATTERN.match(key) or LEGACY_DEFECT_KEY_PATTERN.match(key)
    if not m:
        return None
    return int(m.group(1))


def format_defect_key(seq: int) -> str:
    return f"{DEFECT_KEY_PREFIX}{int(seq)}"


def assert_can_dispatch_automation(
    item_type: str,
    user_permissions: set[str],
    *,
    is_superuser: bool = False,
) -> None:
    if is_superuser:
        return
    it = (item_type or "").strip()
    perm = AUTOMATION_ITEM_EXECUTE_PERM.get(it)
    if perm and perm not in user_permissions:
        raise HTTPException(
            status_code=403,
            detail=f"缺少模块执行权限 {perm}，无法派发 {it}",
        )


def validate_external_url(url: Optional[str]) -> Optional[str]:
    if url is None:
        return None
    u = str(url).strip()
    if not u:
        return None
    from urllib.parse import urlparse

    parsed = urlparse(u)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="external_url 须为 http(s) 链接")
    if not (parsed.netloc or "").strip():
        raise HTTPException(status_code=400, detail="external_url 缺少有效主机名")
    # 拒绝 javascript: 等嵌在 host 的畸形写法
    host = parsed.netloc.lower()
    if "javascript:" in host or "data:" in host:
        raise HTTPException(status_code=400, detail="external_url 非法")
    return u
