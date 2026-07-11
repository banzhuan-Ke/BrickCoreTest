"""全局 Header 配置校验与规范化"""
from typing import Any, List

from app.core.shared.header_merge import normalize_header_items


def normalize_default_headers(raw: Any) -> List[dict]:
    """校验并规范化项目/环境级 default_headers。"""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("default_headers 必须是数组")
    items = normalize_header_items(raw)
    seen = set()
    for item in items:
        key = item["key"]
        if key in seen:
            raise ValueError(f"Header key 重复: {key}")
        seen.add(key)
    return [
        {
            "key": item["key"],
            "value": item.get("value", ""),
            "description": item.get("description") or "",
            "enabled": item.get("enabled", True) is not False,
        }
        for item in items
    ]
