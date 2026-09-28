"""定位表达式白名单校验与候选合并。"""
from __future__ import annotations

import re
from typing import Any

MAX_CANDIDATES = 8
MAX_LOCATOR_LEN = 500

_FORBIDDEN = re.compile(r"javascript\s*:", re.I)
_DYNAMIC_ID_HINT = re.compile(
    r"el-id-|ember\d+|react-select|cdk-overlay-|el-popper-|el-overlay-",
    re.I,
)
# 只拦 Playwright JS API，勿误杀 CSS 类名如 div.page.content / 文案含括号的 get_by_*=
_PW_JS_API = re.compile(
    r"(?:\bpage\.(?:get_by_\w+|locator|click|fill|check|type)\s*\()|(?:\bget_by_\w+\s*\()",
    re.I,
)

_ALLOWED_SOURCES = frozenset({"current", "elevated", "neighbor", "ai"})
_SOURCE_ALIASES = {"rule": "current"}
_SOURCE_REASON = {
    "current": "当前所选",
    "elevated": "抬升（更稳祖先）",
    "neighbor": "相邻明显文案",
    "ai": "AI 建议",
}


def normalize_locator(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if v.startswith(("xpath=", "css=", "text=")):
        return v
    if v.startswith("/") and not v.startswith("//"):
        return f"xpath={v}"
    return v


def normalize_source(value: Any) -> str:
    src = str(value or "current").strip().lower()
    src = _SOURCE_ALIASES.get(src, src)
    if src in _ALLOWED_SOURCES:
        return src
    return "current"


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
    if "following-sibling::" in loc or "preceding-sibling::" in loc:
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
    currents: list[dict[str, Any]] = []
    elevated: list[dict[str, Any]] = []
    neighbor: list[dict[str, Any]] = []
    ais: list[dict[str, Any]] = []

    def _push(item: dict[str, Any], default_source: str) -> None:
        loc = normalize_locator(str(item.get("locator") or ""))
        if not loc or loc in seen or not is_allowed_locator(loc):
            return
        seen.add(loc)
        source = normalize_source(item.get("source") or default_source)
        reason = (item.get("reason") or "").strip() or _SOURCE_REASON.get(source, "规则生成")
        row = {
            "locator": loc,
            "index": safe_index(item.get("index"), 1),
            "source": source,
            "confidence": item.get("confidence") or confidence_for_locator(loc),
            "reason": reason,
        }
        if source == "elevated":
            elevated.append(row)
        elif source == "neighbor":
            neighbor.append(row)
        elif source == "ai":
            ais.append(row)
        else:
            currents.append(row)

    for it in rule_items or []:
        _push(it, "current")
    for it in ai_items or []:
        _push(it, "ai")

    # 截断时至少保留 1 条 current；再预留 elevated / neighbor
    limit = max(1, int(max_n or MAX_CANDIDATES))
    reserve_c = 1 if currents else 0
    reserve_e = 1 if elevated else 0
    reserve_n = 1 if neighbor else 0
    # limit 过小时优先 current，再 elevated，再 neighbor
    while reserve_c + reserve_e + reserve_n > limit:
        if reserve_n:
            reserve_n = 0
        elif reserve_e:
            reserve_e = 0
        else:
            break
    budget = max(reserve_c, limit - reserve_e - reserve_n) if currents else max(0, limit - reserve_e - reserve_n)

    out: list[dict[str, Any]] = []
    out.extend(currents[: max(budget, reserve_c)])
    if reserve_e:
        out.append(elevated[0])
    if reserve_n:
        out.append(neighbor[0])
    # 剩余额度：其它 elevated/neighbor → ai → 更多 current
    rest: list[dict[str, Any]] = []
    rest.extend(elevated[reserve_e:])
    rest.extend(neighbor[reserve_n:])
    rest.extend(ais)
    rest.extend(currents[max(budget, reserve_c):])
    for row in rest:
        if len(out) >= limit:
            break
        if row["locator"] in {r["locator"] for r in out}:
            continue
        out.append(row)
    return out[:limit]
