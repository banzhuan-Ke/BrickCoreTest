"""
定位器字符串规范化（与 Runner tools.locator_normalize 逻辑一致）
"""
import re
from typing import Any


def normalize_locator(locator: Any) -> str:
    if locator is None:
        return ""
    if isinstance(locator, dict):
        role = locator.get("get_by_role") or locator.get("role")
        if role:
            name = (locator.get("name") or locator.get("label") or "").strip()
            return f"get_by_role={role}, {name}" if name else f"get_by_role={role}"
        text = locator.get("get_by_text") or locator.get("text")
        if text:
            return f"get_by_text={text}"
        ph = locator.get("get_by_placeholder") or locator.get("placeholder")
        if ph:
            return f"get_by_placeholder={ph}"
        for key in ("selector", "css", "locator", "value"):
            val = locator.get(key)
            if val and isinstance(val, str):
                return val.strip()
        return str(locator).strip()

    s = str(locator).strip()
    if not s:
        return ""

    m = re.match(r"^get_by_placeholder\s*\(\s*['\"](.+?)['\"]\s*\)$", s)
    if m:
        return f"get_by_placeholder={m.group(1)}"

    m = re.match(r"^get_by_text\s*\(\s*['\"](.+?)['\"]\s*\)$", s)
    if m:
        return f"get_by_text={m.group(1)}"

    m = re.match(r"^get_by_label\s*\(\s*['\"](.+?)['\"]\s*\)$", s)
    if m:
        return f"get_by_label={m.group(1)}"

    m = re.match(r"^get_by_title\s*\(\s*['\"](.+?)['\"]\s*\)$", s)
    if m:
        return f"get_by_title={m.group(1)}"

    m = re.match(
        r"^get_by_role\s*\(\s*['\"]([^'\"]+)['\"]\s*(?:,\s*name\s*=\s*['\"](.+?)['\"]\s*)?\)$",
        s,
    )
    if m:
        role, name = m.group(1), m.group(2)
        return f"get_by_role={role}, {name}" if name else f"get_by_role={role}"

    return s
