"""
UI 步骤 AI Act 兜底：自愈失败后由 LLM 基于页面 snapshot 规划并返回可执行步骤。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from app.modules.ai.ai_prompts import PromptManager
from app.core.shared.locator_utils import normalize_locator
from app.modules.ui.page_fetcher import format_elements_for_prompt, MAX_ARIA_SNAPSHOT_CHARS
from app.core.case.step_intent import resolve_step_intent_text
from app.modules.ui.ui_locator_heal import HEALABLE_METHODS

logger = logging.getLogger(__name__)

AI_ACT_METHODS = frozenset(HEALABLE_METHODS) | frozenset({
    "drag_and_drop",
    "frame_drag_and_drop",
    "press_key",
    "scroll_to_height",
    "mouse_click",
})


def _extract_json_object(text: str) -> dict:
    if not text:
        return {}
    text = text.strip()
    for block in re.findall(r"```(?:json)?\s*([\s\S]*?)```", text):
        try:
            data = json.loads(block.strip())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


def _normalize_act_step(step: dict, *, fallback_method: str) -> Optional[dict]:
    if not isinstance(step, dict):
        return None
    method = (step.get("method") or fallback_method or "").strip()
    if method not in AI_ACT_METHODS:
        return None
    params = step.get("params") if isinstance(step.get("params"), dict) else {}
    params = dict(params)
    for key in ("locator", "selector", "start_selector", "end_selector", "first_locator", "second_locator"):
        if key in params and params[key]:
            params[key] = normalize_locator(str(params[key]))
    return {
        "method": method,
        "keyword": step.get("keyword") or method,
        "desc": step.get("desc") or "",
        "params": params,
        "children": [],
    }


async def plan_ai_act_step(
    *,
    method: str,
    failed_locator: str = "",
    step_desc: Optional[str] = None,
    step_intent: Optional[str] = None,
    original_params: Optional[dict] = None,
    error_message: Optional[str] = None,
    page_url: Optional[str] = None,
    accessibility_snapshot: Optional[str] = None,
    page_elements: Optional[list] = None,
    call_llm,
) -> dict[str, Any]:
    """规划一步 AI Act 并返回可执行 step 对象。"""
    method = (method or "").strip()
    if method and method not in AI_ACT_METHODS:
        return {"success": False, "reason": f"方法 {method} 不支持 AI Act 兜底"}

    intent_text = resolve_step_intent_text(step_intent=step_intent, step_desc=step_desc)
    if not intent_text:
        return {"success": False, "reason": "缺少业务意图（请填写 intent 或操作名称）"}

    snapshot_text = (accessibility_snapshot or "").strip()
    snap_type = "provided"
    if not snapshot_text and page_elements:
        snapshot_text = format_elements_for_prompt(page_elements)
        snap_type = "dom"
    if not snapshot_text:
        return {"success": False, "reason": "无法获取页面 snapshot"}

    if len(snapshot_text) > MAX_ARIA_SNAPSHOT_CHARS:
        snapshot_text = snapshot_text[:MAX_ARIA_SNAPSHOT_CHARS] + "\n... (truncated)"

    orig_params = original_params if isinstance(original_params, dict) else {}
    try:
        system_prompt, user_prompt = await PromptManager.render("ui_ai_act", {
            "method": method or "click_ele",
            "failed_locator": failed_locator or "",
            "step_intent": intent_text,
            "step_desc": (step_desc or "").strip(),
            "error_message": error_message or "",
            "page_url": page_url or "",
            "original_params": json.dumps(orig_params, ensure_ascii=False)[:4000],
            "accessibility_snapshot": snapshot_text,
            "snapshot_type": snap_type,
        })
    except ValueError as exc:
        return {"success": False, "reason": str(exc)}

    try:
        resp = await call_llm(system_prompt, user_prompt)
    except Exception as exc:
        logger.warning("[ui_ai_act] LLM 调用失败: %s", exc)
        return {"success": False, "reason": f"LLM 调用失败: {exc}"}

    raw = resp.get("content", "")
    tokens = resp.get("tokens", 0)
    parsed = _extract_json_object(raw)

    step_raw = parsed.get("step") if isinstance(parsed.get("step"), dict) else parsed
    act_step = _normalize_act_step(step_raw, fallback_method=method)
    if not act_step:
        return {
            "success": False,
            "reason": parsed.get("reason") or "LLM 未能给出可执行步骤",
            "raw_response": raw,
            "tokens_used": tokens,
        }

    locator_keys = ("locator", "selector", "start_selector", "end_selector")
    if not any(act_step["params"].get(k) for k in locator_keys) and method not in ("press_key", "scroll_to_height", "mouse_click"):
        return {
            "success": False,
            "reason": "AI Act 步骤缺少定位器",
            "raw_response": raw,
            "tokens_used": tokens,
        }

    return {
        "success": True,
        "step": act_step,
        "confidence": parsed.get("confidence") or "medium",
        "reason": parsed.get("reason") or "",
        "snapshot_type": snap_type,
        "tokens_used": tokens,
        "raw_response": raw,
    }
