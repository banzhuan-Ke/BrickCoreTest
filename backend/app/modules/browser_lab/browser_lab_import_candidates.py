"""Browser Lab 导入：多定位候选生成（对齐录制 LocatorSelector）。"""
from __future__ import annotations

from typing import Any

from app.modules.browser_lab.browser_lab_import import (
    _CLICK_KEYS,
    _INPUT_KEYS,
    _extract_label,
    _parse_element_index,
)
from app.modules.browser_lab.browser_lab_action_cache_core import _resolve_selector

_ELEMENT_METHODS = frozenset({"click_ele", "fill_value", "select_option", "hover_ele"})


def _dedupe_candidates(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        loc = str(raw or "").strip()
        if not loc or loc in seen:
            continue
        seen.add(loc)
        out.append(loc)
    return out


def _candidates_from_element_meta(meta: dict[str, Any]) -> list[str]:
    if not meta:
        return []
    try:
        from app.modules.ai.recorder_quality import _build_candidates_from_meta

        return list(_build_candidates_from_meta(meta) or [])
    except Exception:
        return []


def _heuristic_candidates(goal: str, payload: dict) -> list[str]:
    out: list[str] = []
    label = _extract_label(goal)
    if label:
        safe = label.replace('"', "")
        out.append(f"get_by_text={safe}")
    for key in ("label", "aria_label", "placeholder", "name"):
        val = (payload.get(key) or "").strip()
        if not val:
            continue
        if key == "placeholder":
            out.append(f"get_by_placeholder={val.replace(chr(34), '')}")
        elif key in ("label", "aria_label"):
            out.append(f"get_by_label={val.replace(chr(34), '')}")
    return out


def build_locator_bundle(
    *,
    goal: str,
    payload: dict | None,
    action_key: str = "",
) -> tuple[str, str, list[dict[str, str]], dict[str, Any]]:
    """返回 (primary_locator, strength, tagged_candidates, element_meta)。"""
    payload = payload or {}
    element_meta = payload.get("element_meta") if isinstance(payload.get("element_meta"), dict) else {}
    primary, strength = _resolve_selector(goal, payload)

    candidates = _candidates_from_element_meta(element_meta)
    candidates.extend(_heuristic_candidates(goal, payload))

    for key in ("xpath", "selector", "css_selector", "locator", "css"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            candidates.insert(0, val.strip())

    fallbacks = payload.get("fallbacks") or payload.get("candidates")
    if isinstance(fallbacks, list):
        for item in fallbacks:
            if isinstance(item, str) and item.strip():
                candidates.append(item.strip())
            elif isinstance(item, dict):
                loc = str(
                    item.get("locator") or item.get("value") or item.get("selector") or ""
                ).strip()
                if loc:
                    candidates.append(loc)

    candidates = _dedupe_candidates(candidates)
    if primary:
        candidates = _dedupe_candidates([primary] + [c for c in candidates if c != primary])
        primary_loc = primary
    elif candidates:
        primary_loc = candidates[0]
        if strength == "weak" and element_meta:
            strength = "heuristic"
    else:
        primary_loc = "body"
        strength = "weak"

    alts = [c for c in candidates if c != primary_loc][:12]
    # 对齐录制：候选带 source；若 meta 含 elevate/neighbor 再补抬升/相邻
    tagged: list[dict[str, str]] = []
    seen: set[str] = set()

    def _push(loc: str, source: str = "current") -> None:
        loc = (loc or "").strip()
        if not loc or loc in seen:
            return
        seen.add(loc)
        tagged.append({"locator": loc, "source": source})

    # 先打标抬升/相邻，再补其余为 current（避免被 current 占坑后无法改标）
    try:
        from app.modules.ui.locator_assist.rules import (
            build_elevated_candidates,
            build_neighbor_candidates,
        )

        for loc in build_elevated_candidates(element_meta or {}):
            if loc != primary_loc:
                _push(loc, "elevated")
        for loc in build_neighbor_candidates(element_meta or {}):
            if loc != primary_loc:
                _push(loc, "neighbor")
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "browser_lab elevated/neighbor candidates failed", exc_info=True
        )

    # 若上游 fallback 已带 source，尽量保留
    if isinstance(fallbacks, list):
        for item in fallbacks:
            if isinstance(item, dict):
                loc = str(
                    item.get("locator") or item.get("value") or item.get("selector") or ""
                ).strip()
                if loc and loc != primary_loc:
                    src = str(item.get("source") or "current").strip().lower()
                    if src == "rule":
                        src = "current"
                    if src not in ("current", "elevated", "neighbor", "ai"):
                        src = "current"
                    _push(loc, src)

    for loc in alts:
        _push(loc, "current")
    return primary_loc, strength, tagged, element_meta


def apply_locator_bundle_to_step(
    step: dict[str, Any],
    *,
    goal: str,
    payload: dict | None,
    action_key: str = "",
) -> dict[str, Any]:
    method = (step.get("method") or "").strip()
    if method not in _ELEMENT_METHODS:
        return step

    primary, strength, alts, element_meta = build_locator_bundle(
        goal=goal,
        payload=payload,
        action_key=action_key,
    )
    params = dict(step.get("params") or {})
    meta = dict(step.get("meta") or {})
    meta["locator_strength"] = strength
    meta["source"] = meta.get("source") or "browser_lab"
    if element_meta:
        meta["element_harvest"] = True
        meta["harvest_source"] = element_meta.get("harvest_source") or "browser_use"
    from app.core.shared.locator_candidate_contract import (
        DECISION_FAITHFUL_HIT,
        apply_primary_meta,
        normalize_locator,
    )

    primary = normalize_locator(primary)
    params["locator"] = primary
    # alts 已带 source；补齐 primarySource / recommended
    meta = apply_primary_meta(
        meta,
        alts or [],
        primary,
        decision=DECISION_FAITHFUL_HIT,
    )
    if strength == "strong":
        meta.pop("needs_manual_locator", None)
    elif element_meta and meta.get("candidates"):
        meta.pop("needs_manual_locator", None)
    elif strength == "weak" or _parse_element_index(payload) is not None:
        meta["needs_manual_locator"] = True
    step = dict(step)
    step["params"] = params
    step["meta"] = meta
    return step


def enrich_ui_steps_with_candidates(steps: list[dict]) -> list[dict]:
    """对已转换步骤补全 meta.candidates（幂等）。"""
    out: list[dict] = []
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        method = step.get("method") or ""
        if method not in _ELEMENT_METHODS:
            out.append(step)
            continue
        meta = step.get("meta") if isinstance(step.get("meta"), dict) else {}
        if meta.get("candidates"):
            out.append(step)
            continue
        params = step.get("params") if isinstance(step.get("params"), dict) else {}
        payload = {"selector": params.get("locator")}
        idx = params.get("index")
        if idx is not None:
            payload["index"] = idx
        enriched = apply_locator_bundle_to_step(
            step,
            goal=(step.get("intent") or step.get("desc") or ""),
            payload=payload,
        )
        out.append(enriched)
    return out
