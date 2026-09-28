"""
定位候选统一契约（Backend / Runner 双份 SOT，见 test_locator_candidate_contract_sot）。

形态：
- 字符串 => {locator, source: current}
- {locator|value|selector, source}
- source: current | elevated | neighbor | ai
- alias: rule / params.* / meta.candidates => current

主定位决策与候选排序分离：
- 默认 primary = best(current)；无 current 时返回空（不偷换 elevated/neighbor）
- elevated / neighbor / ai 可作 recommended，不自动成为 primary
- 落盘截断须保住 primary，并尽量各 source 至少一条
- 同 locator 多 source 去重时优先保留 current（忠实命中池）
- locator 字符串形态与前端一致（/html → xpath=/html）
"""
from __future__ import annotations

from typing import Any, Optional

LOCATOR_SOURCES = frozenset({"current", "elevated", "neighbor", "ai"})
SOURCE_ALIASES = {
    "rule": "current",
    "params.locator": "current",
    "params.candidates": "current",
    "meta.candidates": "current",
}
# 稳定性排序参考（Smart Action 等）；同 locator 去重另见 _prefer_source_for_dedup
SOURCE_RANK = {"ai": 4, "elevated": 3, "neighbor": 3, "current": 1}
MAX_LOCATOR_CANDIDATES = 12

SOURCE_LABELS = {
    "current": "当前所选",
    "elevated": "抬升",
    "neighbor": "相邻",
    "ai": "AI 建议",
}

DECISION_FAITHFUL_HIT = "faithful_hit"
DECISION_USER_SELECTED = "user_selected"
DECISION_HEALED = "healed"
DECISION_ASSIST = "assist"
PRIMARY_DECISIONS = frozenset({
    DECISION_FAITHFUL_HIT,
    DECISION_USER_SELECTED,
    DECISION_HEALED,
    DECISION_ASSIST,
})


def normalize_source(src: Any) -> str:
    s = str(src or "current").strip().lower()
    s = SOURCE_ALIASES.get(s, s)
    return s if s in LOCATOR_SOURCES else "current"


def normalize_decision(decision: Any) -> str:
    d = str(decision or DECISION_FAITHFUL_HIT).strip().lower().replace("-", "_")
    return d if d in PRIMARY_DECISIONS else DECISION_FAITHFUL_HIT


def normalize_locator(value: Any) -> str:
    """与前端 normalizeLocatorValue 对齐：绝对路径补 xpath=；frame|| 内段同样规范化。"""
    v = str(value or "").strip()
    if not v:
        return ""
    if "||" in v:
        frame, _, rest = v.partition("||")
        if rest:
            return f"{frame}||{normalize_locator(rest)}"
        return v
    if v.startswith(("xpath=", "css=", "text=")):
        return v
    if v.startswith("/") and not v.startswith("//"):
        return f"xpath={v}"
    return v


def candidate_locator(item: Any) -> str:
    if isinstance(item, dict):
        return normalize_locator(
            item.get("locator") or item.get("value") or item.get("selector") or ""
        )
    return normalize_locator(item)


def candidate_source(item: Any) -> str:
    if isinstance(item, dict):
        return normalize_source(item.get("source") or "current")
    return "current"


def make_candidate(locator: str, source: str = "current") -> dict[str, str]:
    loc = normalize_locator(locator)
    return {"locator": loc, "source": normalize_source(source)}


def normalize_candidate_item(item: Any) -> Optional[dict[str, str]]:
    loc = candidate_locator(item)
    if not loc:
        return None
    return make_candidate(loc, candidate_source(item))


def _prefer_source_for_dedup(old: str, new: str, *, prefer_higher_source: bool) -> str:
    """同 locator 去重：优先 current（主定位池）；否则可选按 SOURCE_RANK。"""
    old_s = normalize_source(old)
    new_s = normalize_source(new)
    if old_s == new_s:
        return old_s
    # 忠实命中池：current 不被 elevated/neighbor/ai 盖掉；后到的 current 可纠正前者
    if old_s == "current" or new_s == "current":
        return "current"
    if prefer_higher_source:
        if SOURCE_RANK.get(new_s, 0) > SOURCE_RANK.get(old_s, 0):
            return new_s
        return old_s
    return old_s


def normalize_candidates(
    items: Any,
    *,
    max_n: Optional[int] = None,
    prefer_higher_source: bool = False,
) -> list[dict[str, str]]:
    """去重为 {locator, source}。max_n=None 表示不截断（内部选择/推荐用）。"""
    out: list[dict[str, str]] = []
    seen: dict[str, int] = {}
    unlimited = max_n is None
    limit = MAX_LOCATOR_CANDIDATES if unlimited else max(1, int(max_n or MAX_LOCATOR_CANDIDATES))
    for item in items or []:
        norm = normalize_candidate_item(item)
        if not norm:
            continue
        loc = norm["locator"]
        if loc in seen:
            idx = seen[loc]
            kept = _prefer_source_for_dedup(
                out[idx]["source"],
                norm["source"],
                prefer_higher_source=prefer_higher_source,
            )
            if kept != out[idx]["source"]:
                out[idx] = make_candidate(loc, kept)
            continue
        seen[loc] = len(out)
        out.append(norm)
        if not unlimited and len(out) >= limit and not prefer_higher_source:
            break
    if unlimited:
        return out
    return out[:limit]


def has_object_candidates(items: Any) -> bool:
    """原始 candidates 是否含对象形态（带 source 语义）；纯字符串走旧评分。"""
    for item in items or []:
        if isinstance(item, dict) and (
            item.get("locator") or item.get("value") or item.get("selector")
        ):
            return True
    return False


def pick_default_from_candidates(
    items: Any,
    *,
    allow_non_current_fallback: bool = False,
) -> str:
    """主定位只从 current 选。默认无 current 时返回空，禁止偷换 elevated/neighbor。"""
    currents: list[str] = []
    any_loc: list[str] = []
    for item in normalize_candidates(items, max_n=None):
        loc = item["locator"]
        any_loc.append(loc)
        if item["source"] == "current":
            currents.append(loc)
    if currents:
        return currents[0]
    if allow_non_current_fallback:
        return any_loc[0] if any_loc else ""
    return ""


def resolve_primary_source(
    primary: str,
    candidates: Any,
    *,
    explicit: Any = None,
) -> str:
    """primary 能在候选中命中则继承其 source；explicit 优先。"""
    if explicit is not None and str(explicit).strip():
        return normalize_source(explicit)
    loc = normalize_locator(primary)
    if not loc:
        return "current"
    for item in normalize_candidates(candidates, max_n=None):
        if item["locator"] == loc:
            return item["source"]
    return "current"


def pick_recommended_candidate(
    items: Any,
    *,
    exclude_locator: str = "",
) -> Optional[dict[str, str]]:
    """从已排序候选中取第一条非 current 且不同于 primary 的，作「更稳推荐」。"""
    exclude = normalize_locator(exclude_locator)
    for item in normalize_candidates(items, max_n=None):
        if item["source"] == "current":
            continue
        if exclude and item["locator"] == exclude:
            continue
        reason = {
            "elevated": "更稳定的抬升宿主",
            "neighbor": "相邻明显文案锚定",
            "ai": "AI 建议定位",
        }.get(item["source"], "备选定位")
        return {
            "locator": item["locator"],
            "source": item["source"],
            "reason": reason,
        }
    return None


def trim_candidates_for_storage(
    items: Any,
    *,
    primary_locator: str = "",
    max_n: int = MAX_LOCATOR_CANDIDATES,
) -> list[dict[str, str]]:
    """落盘截断：先保 primary，再尽量各 source 一条，再按原序填满。"""
    all_cands = normalize_candidates(items, max_n=None)
    limit = max(1, int(max_n or MAX_LOCATOR_CANDIDATES))
    primary = normalize_locator(primary_locator)
    if not all_cands:
        return []

    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def _push(row: dict[str, str]) -> None:
        loc = row["locator"]
        if not loc or loc in seen or len(out) >= limit:
            return
        seen.add(loc)
        out.append(row)

    if primary:
        hit = next((c for c in all_cands if c["locator"] == primary), None)
        _push(hit or make_candidate(primary, "current"))

    for key in ("current", "elevated", "neighbor", "ai"):
        for row in all_cands:
            if row["source"] == key and row["locator"] not in seen:
                _push(row)
                break

    for row in all_cands:
        if len(out) >= limit:
            break
        _push(row)
    return out


def apply_primary_meta(
    meta: Optional[dict],
    candidates: Any,
    primary_locator: str,
    *,
    decision: str = DECISION_FAITHFUL_HIT,
    primary_source: Any = None,
    clear_candidates_if_empty: bool = True,
    max_n: int = MAX_LOCATOR_CANDIDATES,
) -> dict:
    """写入 primarySource / primaryDecision / recommended（薄字段）。

    candidates 传空列表且 clear_candidates_if_empty=True 时清空旧 candidates。
    primary 对应 candidate 的 source 必须与最终 primarySource 一致。
    """
    out = dict(meta or {})
    primary = normalize_locator(primary_locator)
    # 未截断扫描，避免 primary 在第 13+ 条时丢失
    raw = list(candidates) if candidates is not None else None
    if raw is None:
        cands = normalize_candidates(out.get("candidates") or [], max_n=None)
    else:
        cands = normalize_candidates(raw, max_n=None)

    decision_n = normalize_decision(decision)
    src = resolve_primary_source(primary, cands, explicit=primary_source)
    if decision_n == DECISION_FAITHFUL_HIT and primary_source is None:
        src = "current"
    out["primarySource"] = src
    out["primaryDecision"] = decision_n

    if raw is not None and len(raw) == 0 and clear_candidates_if_empty:
        out.pop("candidates", None)
        out.pop("recommended", None)
        return out

    # 确保 primary 在候选中，且 source 与 primarySource 一致（避免悖论）
    if primary:
        synced = False
        for i, c in enumerate(cands):
            if c["locator"] == primary:
                cands[i] = make_candidate(primary, src)
                synced = True
                break
        if not synced:
            cands = [make_candidate(primary, src)] + cands

    trimmed = trim_candidates_for_storage(cands, primary_locator=primary, max_n=max_n)
    if trimmed:
        out["candidates"] = trimmed
    elif clear_candidates_if_empty:
        out.pop("candidates", None)

    rec = pick_recommended_candidate(cands, exclude_locator=primary)
    if rec and rec["locator"] != primary:
        out["recommended"] = rec
    else:
        out.pop("recommended", None)
    return out


def group_candidates_by_source(items: Any) -> dict[str, list[dict[str, str]]]:
    """分组：current → elevated → neighbor → ai（组内保持原序）。"""
    groups = {k: [] for k in ("current", "elevated", "neighbor", "ai")}
    for item in normalize_candidates(items, max_n=None):
        groups[item["source"]].append(item)
    return groups


def flatten_grouped_candidates(items: Any, *, max_n: int = MAX_LOCATOR_CANDIDATES) -> list[dict[str, str]]:
    """分组拼回扁平列表，保证 current 段在前。"""
    return trim_candidates_for_storage(items, max_n=max_n)
