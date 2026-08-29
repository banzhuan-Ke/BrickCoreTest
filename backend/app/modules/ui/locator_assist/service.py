"""定位助手编排：解析 → 规则 → 可选 AI → 合并校验。"""
from __future__ import annotations

from typing import Any, Optional

from app.modules.ui.locator_assist.ai_enhance import enhance_candidates_with_ai
from app.modules.ui.locator_assist.parse import apply_frame_prefix, parse_raw_element
from app.modules.ui.locator_assist.rules import build_rule_candidates, extract_suggested_index
from app.modules.ui.locator_assist.validate import (
    MAX_CANDIDATES,
    confidence_for_locator,
    merge_candidates,
    normalize_locator,
)


def _element_summary(element: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "tag", "text", "accessibleName", "id", "class", "name", "title",
        "placeholder", "role", "ariaLabel", "dataTestid", "inputType",
        "region", "popupRoot", "parseWeak", "framePrefix", "frameChain",
    )
    return {k: element.get(k) for k in keys if element.get(k) not in (None, "", [])}


async def suggest_locators(
    *,
    raw_element: str,
    intent: str = "",
    ai_enabled: bool = True,
    ai_config_id: Optional[int] = None,
    step_method: str = "",
    max_candidates: int = MAX_CANDIDATES,
    project_id: Optional[int] = None,
    username: str = "",
) -> dict[str, Any]:
    element = parse_raw_element(raw_element)
    summary = _element_summary(element)
    suggested_index = extract_suggested_index(intent) or 1
    frame_prefix = (element.get("framePrefix") or "").strip()
    frame_chain = element.get("frameChain") or []

    rule_locs = build_rule_candidates(element)
    if frame_prefix:
        rule_locs = [apply_frame_prefix(loc, frame_prefix) for loc in rule_locs]
    rule_items = [
        {
            "locator": normalize_locator(loc),
            "index": suggested_index,
            "source": "rule",
            "confidence": confidence_for_locator(loc),
            "reason": "规则生成（含 iframe 前缀）" if frame_prefix else "规则生成",
        }
        for loc in rule_locs
        if normalize_locator(loc)
    ]

    warnings: list[str] = []
    ai_used = False
    ai_items: list[dict[str, Any]] = []

    if element.get("parseWeak"):
        warnings.append("未能结构化解析元素，建议粘贴 outerHTML 或属性；已尽量用全文辅助")

    if frame_chain:
        warnings.append(f"已识别 {len(frame_chain)} 层 iframe，候选已加前缀：{' || '.join(frame_chain)}")
        if len(frame_chain) == 1:
            warnings.append(
                "若按钮还在更内层 iframe（常见：业务壳套编辑器），请把内层 <iframe> 的 outerHTML 也一并粘贴"
            )

    if ai_enabled:
        ai_items, ai_used, warn = await enhance_candidates_with_ai(
            project_id=project_id,
            username=username,
            raw_element=raw_element,
            intent=intent,
            element_summary=summary,
            rule_candidates=rule_items,
            step_method=step_method,
            ai_config_id=ai_config_id,
            suggested_index=suggested_index,
        )
        if warn:
            warnings.append(warn)
        if frame_prefix and ai_items:
            for item in ai_items:
                item["locator"] = apply_frame_prefix(str(item.get("locator") or ""), frame_prefix)
    else:
        warnings.append("未启用 AI，仅返回规则候选")

    candidates = merge_candidates(rule_items, ai_items, max_n=max(1, min(int(max_candidates or 8), 12)))
    if not candidates and raw_element.strip():
        warnings.append("未生成可用定位，请补充更完整的元素信息或改用交互调试拾取")

    return {
        "element_summary": summary,
        "suggested_index": suggested_index,
        "candidates": candidates,
        "ai_used": ai_used,
        "warnings": warnings,
    }
