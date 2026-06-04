"""
UI 步骤定位器自愈（MCP snapshot + 文本 LLM）
"""
import logging
from typing import Any, Optional

from app.core.ai_prompts import PromptManager
from app.core.locator_utils import normalize_locator
from app.core.page_fetcher import fetch_page_structure, format_elements_for_prompt

logger = logging.getLogger(__name__)

HEALABLE_METHODS = frozenset({
    "click_ele", "fill_value", "double_click_ele", "clear_value", "set_checked",
    "hover", "focus_element", "select_option", "type_value", "long_click_element",
    "upload_file", "wait_for_element",
    "frame_fill_value", "frame_click_element", "frame_hover", "frame_focus_element",
    "frame_select_option", "frame_type_value", "frame_long_click_element",
    "kw_assert_visible", "kw_assert_hidden", "kw_assert_element_text", "kw_assert_value",
    "kw_assert_attribute", "kw_assert_enabled", "kw_assert_disabled",
    "kw_assert_checked", "kw_assert_empty", "kw_assert_editable", "kw_assert_focused",
    "extract_text", "extract_attribute",
})


def _extract_json_object(text: str) -> dict:
    import json
    import re

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
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


async def heal_locator(
    *,
    method: str,
    failed_locator: str,
    step_desc: Optional[str] = None,
    error_message: Optional[str] = None,
    page_url: Optional[str] = None,
    accessibility_snapshot: Optional[str] = None,
    page_elements: Optional[list] = None,
    call_llm,
    ai_config_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    基于页面 snapshot 为失败步骤推荐新 locator。
    call_llm: async (system, user) -> {content, tokens}
    """
    method = (method or "").strip()
    failed_locator = (failed_locator or "").strip()
    if method not in HEALABLE_METHODS:
        return {
            "success": False,
            "reason": f"方法 {method} 不支持 AI 自愈",
        }
    if not failed_locator:
        return {"success": False, "reason": "缺少 failed_locator"}

    snap_type = "provided"
    snapshot_text = (accessibility_snapshot or "").strip()

    if not snapshot_text and page_elements:
        snapshot_text = format_elements_for_prompt(page_elements)
        snap_type = "dom"

    if not snapshot_text and page_url:
        page_data = await fetch_page_structure(page_url, timeout=15)
        if page_data:
            snapshot_text = format_elements_for_prompt(page_data.get("elements") or [])
            snap_type = "dom_fetched"

    if not snapshot_text:
        return {
            "success": False,
            "reason": "无法获取页面 snapshot，请提供 page_url 或在 Runner 运行时重试",
        }

    system_prompt, user_prompt = await PromptManager.render("ui_locator_heal", {
        "method": method,
        "failed_locator": failed_locator,
        "step_desc": step_desc or "",
        "error_message": error_message or "",
        "page_url": page_url or "",
        "accessibility_snapshot": snapshot_text,
        "snapshot_type": snap_type,
    })

    resp = await call_llm(system_prompt, user_prompt)
    raw = resp.get("content", "")
    tokens = resp.get("tokens", 0)
    parsed = _extract_json_object(raw)

    new_locator = normalize_locator(parsed.get("locator") or parsed.get("new_locator") or "")
    if not new_locator:
        return {
            "success": False,
            "reason": parsed.get("reason") or "LLM 未能给出新定位器",
            "raw_response": raw,
            "tokens_used": tokens,
        }

    if new_locator == failed_locator:
        return {
            "success": False,
            "reason": "建议定位器与原定位器相同",
            "locator": new_locator,
            "raw_response": raw,
            "tokens_used": tokens,
        }

    return {
        "success": True,
        "locator": new_locator,
        "confidence": parsed.get("confidence") or "medium",
        "reason": parsed.get("reason") or "",
        "snapshot_type": snap_type,
        "tokens_used": tokens,
        "raw_response": raw,
    }
