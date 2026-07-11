"""
项目级导出目标：禅道 XLSX / 通用 XLSX
"""
from __future__ import annotations

from typing import Optional

EXPORT_PROFILE_ZENTAO = "zentao"
EXPORT_PROFILE_GENERIC = "generic"
VALID_EXPORT_PROFILES = frozenset({EXPORT_PROFILE_ZENTAO, EXPORT_PROFILE_GENERIC})

EXPORT_PROFILE_LABELS = {
    EXPORT_PROFILE_ZENTAO: "禅道 XLSX",
    EXPORT_PROFILE_GENERIC: "通用 XLSX",
}


def normalize_export_profile(raw: Optional[str]) -> str:
    p = str(raw or "").strip().lower()
    return p if p in VALID_EXPORT_PROFILES else EXPORT_PROFILE_ZENTAO


def get_export_profile_from_bindings(bindings: Optional[dict]) -> str:
    if not bindings or not isinstance(bindings, dict):
        return EXPORT_PROFILE_ZENTAO
    return normalize_export_profile(bindings.get("export_profile"))
