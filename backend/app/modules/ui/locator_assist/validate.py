"""定位表达式白名单校验与候选合并。"""
from __future__ import annotations

import re
from typing import Any

MAX_CANDIDATES = 8
MAX_LOCATOR_LEN = 500

_FORBIDDEN = re.compile(r"javascript\s*:", re.I)
_DYNAMIC_ID_HINT = re.compile(r"el-id-|ember\d+|react-select", re.I)
# 只拦 Playwright JS API，勿误杀 CSS 类名如 div.page.content / 文案含括号的 get_by_*=
_PW_JS_API = re.compile(
    r"(?:\bpage\.(?:get_by_\w+|locator|click|fill|check|type)\s*\()|(?:\bget_by_\w+\s*\()",
    re.I,
)


def normalize_locator(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if v.startswith(("xpath=", "css=", "text=")):
        return v
    if v.startswith("/") and not v.startswith("//"):
        return f"xpath={v}"
    return v


def is_allowed_locator(locator: str) -> bool:
    loc = normalize_locator(locator)
    if not loc or len(loc) > MAX_LOCATOR_LEN:
        return False
    if _FORBIDDEN.search(loc):
        return False
    if _PW_JS_API.search(loc):
        return False
    return True


def confidence_for_locator(locator: str) -> str:
    loc = normalize_locator(locator)
    if loc.startswith(("[data-testid=", "#")) and not _DYNAMIC_ID_HINT.search(loc):
        return "high"
    if loc.startswith(("get_by_role=", "get_by_placeholder=", "get_by_label=")):
        return "high"
    if loc.startswith("get_by_text="):
        return "medium"
    if ">>" in loc:
        return "medium"
    if loc.startswith("xpath=/html") or loc.startswith("/html"):
        return "low"
    if _DYNAMIC_ID_HINT.search(loc):
        return "low"
    return "medium"


def safe_index(value: Any, default: int = 1) -> int:
    """AI/规则可能返回非数字 index，避免 int() 抛错。"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        try:
            n = int(default)
        except (TypeError, ValueError):
            return 1
    return max(1, n)


def merge_candidates(
    rule_items: list[dict[str, Any]],
    ai_items: list[dict[str, Any]] | None = None,
    *,
    max_n: int = MAX_CANDIDATES,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    def _push(item: dict[str, Any], default_source: str) -> None:
        loc = normalize_locator(str(item.get("locator") or ""))
        if not loc or loc in seen or not is_allowed_locator(loc):
            return
        seen.add(loc)
        out.append({
            "locator": loc,
            "index": safe_index(item.get("index"), 1),
            "source": item.get("source") or default_source,
            "confidence": item.get("confidence") or confidence_for_locator(loc),
            "reason": (item.get("reason") or "").strip() or (
                "规则生成" if default_source == "rule" else "AI 建议"
            ),
        })

    for it in rule_items or []:
        _push(it, "rule")
    for it in ai_items or []:
        _push(it, "ai")
    return out[:max_n]
