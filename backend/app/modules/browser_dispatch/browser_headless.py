"""浏览器有头/无头解析（Browser Lab / UI Agent / page_fetch 共用）。"""
from __future__ import annotations


def resolve_browser_headless(value: bool | None, *, default: bool = True) -> bool:
    """None 时使用 default（默认无头）。"""
    return default if value is None else bool(value)


def read_headless_from_mapping(mapping: dict | None, *, default: bool = True) -> bool:
    if not isinstance(mapping, dict):
        return default
    if "headless" not in mapping or mapping.get("headless") is None:
        return default
    return bool(mapping.get("headless"))
