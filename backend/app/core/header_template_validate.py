"""Header 模板校验与规范化"""
from typing import Any, List

from app.core.header_merge import normalize_header_items


def normalize_template_headers(raw: Any) -> List[dict]:
    """校验并规范化 Header 模板 headers 字段。"""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("headers 必须是数组")
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
        }
        for item in items
    ]
