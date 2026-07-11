"""请求 Header 合并与规范化工具"""
from __future__ import annotations

from typing import Any, Dict, List


def normalize_header_items(raw: Any) -> List[Dict[str, Any]]:
    """将 list / dict 格式的 Header 统一为 [{key, value, description, enabled?, source?}, ...]"""
    if not raw:
        return []
    if isinstance(raw, list):
        items = []
        for h in raw:
            if not isinstance(h, dict):
                continue
            key = (h.get("key") or "").strip()
            if not key:
                continue
            items.append({
                "key": key,
                "value": h.get("value", ""),
                "description": h.get("description") or "",
                "enabled": h.get("enabled", True) is not False,
                "source": h.get("source"),
            })
        return items
    if isinstance(raw, dict):
        return [
            {
                "key": k,
                "value": v if v is not None else "",
                "description": "",
                "enabled": True,
            }
            for k, v in raw.items()
            if k
        ]
    return []


def headers_list_to_dict(headers: Any) -> Dict[str, str]:
    """Header 列表/字典 → {key: value}"""
    result: Dict[str, str] = {}
    for item in normalize_header_items(headers):
        result[item["key"]] = str(item.get("value", ""))
    return result


def merge_request_headers(
    *,
    api_headers: Any = None,
    case_headers: Any = None,
    **_legacy,
) -> Dict[str, str]:
    """
    合并接口/用例本地 Header（低→高：接口 → 用例）。
    不再自动合并项目/环境全局 Header；模板仅在编辑页手动导入。
    """
    result = headers_list_to_dict(api_headers)
    case_dict = headers_list_to_dict(case_headers)
    if case_dict:
        result.update(case_dict)
    return result
