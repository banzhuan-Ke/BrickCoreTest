"""
录制步骤默认质量精简（W-24）

在录制落库前做确定性去冗余，减少对「AI 优化」的依赖。
规则与 ui_record_optimize Prompt 对齐，但仅做安全、可逆的启发式处理。
"""
from __future__ import annotations

import copy
from typing import Any

PROTECTED_PREV_FOR_WAIT = frozenset({
    "open_browser",
    "open_url",
    "hover",
    "wait_for_element",
})

CLICK_METHODS = frozenset({"click_ele", "double_click_ele"})
INPUT_METHODS = frozenset({"fill_value", "select_option"})


def _params(step: dict) -> dict:
    return step.get("params") if isinstance(step.get("params"), dict) else {}


def _method(step: dict) -> str:
    return str(step.get("method") or "")


def _locator(step: dict) -> str:
    return str(_params(step).get("locator") or _params(step).get("selector") or "").strip()


def _same_locator(a: dict, b: dict) -> bool:
    la, lb = _locator(a), _locator(b)
    return bool(la and la == lb)


def _wait_timeout(step: dict) -> int:
    try:
        return int(_params(step).get("timeout") or 0)
    except (TypeError, ValueError):
        return 0


def _step_timestamp(step: dict) -> int | None:
    meta = step.get("meta") if isinstance(step.get("meta"), dict) else {}
    try:
        ts = meta.get("timestamp")
        return int(ts) if ts is not None else None
    except (TypeError, ValueError):
        return None


def _open_url_value(step: dict) -> str:
    return str(_params(step).get("url") or "").strip()


def _is_likely_redirect_open_url(prev: dict, curr: dict) -> bool:
    """仅移除完全相同的连续 open_url（典型重复导航/重定向）。"""
    prev_url = _open_url_value(prev)
    curr_url = _open_url_value(curr)
    return bool(prev_url and curr_url and prev_url == curr_url)


def _should_merge_click_then_fill(click: dict, fill: dict) -> bool:
    # 保守策略：不自动合并 click->fill，避免误删有副作用的点击
    return False


def _is_layout_hover(step: dict) -> bool:
    if _method(step) != "hover":
        return False
    meta = step.get("meta") if isinstance(step.get("meta"), dict) else {}
    tag = str(meta.get("tag") or "").lower()
    return tag in ("body", "html", "main")


def _should_keep_wait(prev: dict | None, wait_step: dict, next_step: dict | None) -> bool:
    prev_method = _method(prev) if prev else ""
    timeout = _wait_timeout(wait_step)
    if prev_method in PROTECTED_PREV_FOR_WAIT:
        return True
    if prev_method == "wait_for_element":
        return True
    if prev_method == "hover" and timeout <= 1200:
        return True
    if next_step and _method(next_step) == "wait_for_element":
        return False
    if next_step and _method(next_step) in CLICK_METHODS | INPUT_METHODS and timeout <= 1500:
        return False
    return timeout <= 1500 and prev_method in CLICK_METHODS | INPUT_METHODS


def _merge_click_then_fill(steps: list[dict]) -> tuple[list[dict], int]:
    if not steps:
        return [], 0
    merged = 0
    out: list[dict] = []
    i = 0
    while i < len(steps):
        cur = steps[i]
        if (
            i + 1 < len(steps)
            and _method(cur) in CLICK_METHODS
            and _method(steps[i + 1]) == "fill_value"
            and _should_merge_click_then_fill(cur, steps[i + 1])
        ):
            out.append(copy.deepcopy(steps[i + 1]))
            merged += 1
            i += 2
            continue
        out.append(copy.deepcopy(cur))
        i += 1
    return out, merged


def _remove_redundant_open_urls(steps: list[dict]) -> tuple[list[dict], int]:
    """仅移除疑似重定向的连续 open_url。"""
    removed = 0
    out: list[dict] = []
    for step in steps:
        if _method(step) != "open_url":
            out.append(step)
            continue
        if out and _method(out[-1]) == "open_url" and _is_likely_redirect_open_url(out[-1], step):
            removed += 1
            continue
        out.append(step)
    return out, removed


def _remove_redundant_waits(steps: list[dict]) -> tuple[list[dict], int]:
    removed = 0
    out: list[dict] = []
    for i, step in enumerate(steps):
        if _method(step) != "wait_for_time":
            out.append(step)
            continue
        prev = out[-1] if out else None
        nxt = steps[i + 1] if i + 1 < len(steps) else None
        if _should_keep_wait(prev, step, nxt):
            out.append(step)
            continue
        timeout = _wait_timeout(step)
        if prev and _method(prev) == "wait_for_time":
            removed += 1
            continue
        if timeout >= 8000:
            removed += 1
            continue
        out.append(step)
    return out, removed


def _dedupe_consecutive_clicks(steps: list[dict]) -> tuple[list[dict], int]:
    removed = 0
    out: list[dict] = []
    for step in steps:
        if (
            out
            and _method(step) in CLICK_METHODS
            and _method(out[-1]) in CLICK_METHODS
            and _same_locator(out[-1], step)
        ):
            removed += 1
            continue
        out.append(step)
    return out, removed


def _trim_redundant_hovers(steps: list[dict]) -> tuple[list[dict], int]:
    removed = 0
    out: list[dict] = []
    i = 0
    while i < len(steps):
        step = steps[i]
        if _method(step) != "hover":
            out.append(step)
            i += 1
            continue
        if _is_layout_hover(step):
            removed += 1
            i += 1
            continue
        if i + 1 < len(steps):
            nxt = steps[i + 1]
            if _method(nxt) in CLICK_METHODS and _same_locator(step, nxt):
                removed += 1
                i += 1
                continue
        out.append(step)
        i += 1
    return out, removed


def sanitize_recorded_steps(steps: list[dict]) -> tuple[list[dict], dict[str, Any]]:
    """
    对录制转换后的步骤做默认精简。
    返回 (精简后步骤, 统计信息)。
    """
    if not steps:
        return [], {"original_count": 0, "final_count": 0, "removed": 0, "merged": 0}

    working = [copy.deepcopy(s) for s in steps if isinstance(s, dict)]
    stats: dict[str, Any] = {
        "original_count": len(working),
        "removed": 0,
        "merged": 0,
        "removed_open_url": 0,
        "removed_wait": 0,
        "removed_hover": 0,
        "removed_duplicate_click": 0,
    }

    working, merged = _merge_click_then_fill(working)
    stats["merged"] = merged

    working, n = _remove_redundant_open_urls(working)
    stats["removed_open_url"] = n
    stats["removed"] += n

    working, n = _remove_redundant_waits(working)
    stats["removed_wait"] = n
    stats["removed"] += n

    working, n = _dedupe_consecutive_clicks(working)
    stats["removed_duplicate_click"] = n
    stats["removed"] += n

    working, n = _trim_redundant_hovers(working)
    stats["removed_hover"] = n
    stats["removed"] += n

    stats["final_count"] = len(working)
    stats["applied"] = stats["removed"] > 0 or stats["merged"] > 0

    if stats["applied"]:
        for step in working:
            meta = step.setdefault("meta", {})
            if isinstance(meta, dict):
                meta["default_sanitized"] = True

    for i, step in enumerate(working):
        step.setdefault("meta", {})["rec_step_index"] = i + 1

    return working, stats
