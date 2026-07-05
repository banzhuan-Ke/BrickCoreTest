"""App 元素库 locator_ref 展开（执行前将引用替换为 Locator DSL）"""
from __future__ import annotations

import copy
import re
import urllib.parse
from typing import Any, Dict, Iterable, List, Set

from fastapi import HTTPException

from app.models.app import AppElement

_APP_ELEMENT_KEY_RE = re.compile(r"^app-elements/\d+/[a-f0-9]{12}\.(png|jpe?g|webp)$", re.I)

LOCATOR_PARAM_METHODS = frozenset({
    "click_element",
    "double_click_element",
    "long_press_element",
    "input_text",
    "clear_text",
    "get_text",
    "wait_element",
    "wait_gone",
    "scroll_to",
    "assert_exists",
    "assert_not_exists",
    "assert_text",
    "assert_text_contains",
    "extract_text",
})


def _normalize_image_locator_value(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return raw
    if raw.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(raw)
        path = urllib.parse.unquote(parsed.path or "").lstrip("/")
        if path.startswith("app-elements/"):
            return path
        parts = path.split("/", 1)
        if len(parts) == 2 and parts[1].startswith("app-elements/"):
            return parts[1]
    return raw


def _normalize_image_locator(locator: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(locator, dict):
        return locator
    if str(locator.get("by") or "").strip().lower() != "image":
        return locator
    out = copy.deepcopy(locator)
    value = _normalize_image_locator_value(out.get("value"))
    if value and _APP_ELEMENT_KEY_RE.match(value):
        out["value"] = value
    return out


def _collect_locator_refs(steps: Iterable[Dict[str, Any]], refs: Set[str]) -> None:
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        method = (step.get("method") or "").strip()
        params = step.get("params") or {}
        if method in LOCATOR_PARAM_METHODS:
            ref = (params.get("locator_ref") or "").strip()
            if ref:
                refs.add(ref)
        if method == "condition_branch":
            params = step.get("params") or {}
            branches = step.get("branches") or (params.get("branches") if isinstance(params, dict) else None) or []
            for branch in branches:
                if not isinstance(branch, dict):
                    continue
                cond = branch.get("condition") or {}
                ref = (cond.get("locator_ref") or "").strip()
                if ref:
                    refs.add(ref)
                _collect_locator_refs(branch.get("steps") or [], refs)


def _expand_step_params(params: Dict[str, Any], mapping: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    ref = (params.get("locator_ref") or "").strip()
    if not ref:
        return params
    locator = mapping.get(ref)
    if not locator:
        raise HTTPException(status_code=422, detail=f"元素库引用不存在: {ref}")
    out = dict(params)
    out["locator"] = _normalize_image_locator(copy.deepcopy(locator))
    return out


def _expand_steps(steps: List[Dict[str, Any]], mapping: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for step in steps or []:
        if not isinstance(step, dict):
            result.append(step)
            continue
        item = copy.deepcopy(step)
        method = (item.get("method") or "").strip()
        if method in LOCATOR_PARAM_METHODS and isinstance(item.get("params"), dict):
            item["params"] = _expand_step_params(item["params"], mapping)
        if method == "condition_branch":
            branches = []
            for branch in item.get("branches") or []:
                if not isinstance(branch, dict):
                    branches.append(branch)
                    continue
                b = copy.deepcopy(branch)
                cond = b.get("condition") or {}
                ref = (cond.get("locator_ref") or "").strip()
                if ref:
                    locator = mapping.get(ref)
                    if not locator:
                        raise HTTPException(status_code=422, detail=f"元素库引用不存在: {ref}")
                    cond = dict(cond)
                    cond["locator"] = copy.deepcopy(locator)
                    b["condition"] = cond
                b["steps"] = _expand_steps(b.get("steps") or [], mapping)
                branches.append(b)
            item["branches"] = branches
        result.append(item)
    return result


async def expand_locator_refs_in_steps(steps: List[Dict[str, Any]], project_id: int) -> List[Dict[str, Any]]:
    """将步骤中的 locator_ref 展开为元素库 locator。"""
    if not steps:
        return steps
    refs: Set[str] = set()
    _collect_locator_refs(steps, refs)
    if not refs:
        return steps
    rows = await AppElement.filter(project_id=project_id, name__in=list(refs), is_del=False)
    mapping = {row.name: _normalize_image_locator(row.locator) for row in rows if row.name and isinstance(row.locator, dict)}
    missing = sorted(refs - set(mapping.keys()))
    if missing:
        raise HTTPException(status_code=422, detail=f"元素库引用不存在: {', '.join(missing)}")
    return _expand_steps(steps, mapping)
