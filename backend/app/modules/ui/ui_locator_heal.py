"""
UI 步骤定位器自愈（MCP snapshot + 文本 LLM）
"""
import logging
import re
from typing import Any, Optional

from app.modules.ai.ai_prompts import PromptManager
from app.core.shared.locator_utils import normalize_locator, _strip_role_name_part
from app.modules.ui.page_fetcher import fetch_page_structure, format_elements_for_prompt, MAX_ARIA_SNAPSHOT_CHARS
from app.core.case.step_intent import resolve_step_intent_text

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


def _extract_text_from_locator(locator: str) -> Optional[str]:
    """从定位表达式中提取目标可见文案（用于校验是否缩小了匹配范围）。"""
    locator = (locator or "").strip()
    if not locator:
        return None
    if locator.startswith("get_by_text="):
        return locator[len("get_by_text="):].strip()
    if locator.startswith("get_by_role="):
        parts = locator[len("get_by_role="):].split(",", 1)
        if len(parts) > 1:
            return _strip_role_name_part(parts[1])
    m = re.search(r':has-text\("([^"]+)"\)', locator)
    if m:
        return m.group(1)
    return None


def _extract_target_from_step_desc(step_desc: str) -> Optional[str]:
    """从步骤描述中提取用户意图点击/操作的目标文案。"""
    step_desc = (step_desc or "").strip()
    if not step_desc:
        return None
    for pattern in (
        r"点击['「]([^'」]+)['」]",
        r"悬停到\s*['「]([^'」]+)['」]",
        r"双击['「]([^'」]+)['」]",
        r"点击\s+(.+?)(?:\s*按钮|\s*链接|$)",
        r"点击\s*(\S+)",
    ):
        m = re.search(pattern, step_desc)
        if m:
            target = m.group(1).strip()
            if target:
                return target
    return None


def _reject_shortened_text_match(
    *,
    failed_locator: str,
    new_locator: str,
    step_desc: Optional[str],
) -> Optional[str]:
    """若新定位器把目标文案缩短（如 基础设置→设置），返回拒绝原因。"""
    failed_text = _extract_text_from_locator(failed_locator)
    new_text = _extract_text_from_locator(new_locator)
    if not new_text:
        return None

    desc_target = _extract_target_from_step_desc(step_desc or "")
    for expected in (desc_target, failed_text):
        if not expected or expected == new_text:
            continue
        if expected in new_text or new_text in expected:
            if len(new_text) < len(expected) and new_text != expected:
                return (
                    f"新定位器「{new_locator}」比步骤意图「{expected}」匹配范围更小，"
                    "可能点到页面上其他相似按钮"
                )
    return None


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
    step_intent: Optional[str] = None,
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
        try:
            page_data = await fetch_page_structure(page_url, timeout=15)
        except Exception as exc:
            logger.warning("[ui_locator_heal] fetch_page_structure failed: %s", exc)
            page_data = None
        if page_data:
            snapshot_text = format_elements_for_prompt(page_data.get("elements") or [])
            snap_type = "dom_fetched"

    if not snapshot_text:
        return {
            "success": False,
            "reason": "无法获取页面 snapshot，请提供 page_url 或在 Runner 运行时重试",
        }

    if len(snapshot_text) > MAX_ARIA_SNAPSHOT_CHARS:
        snapshot_text = snapshot_text[:MAX_ARIA_SNAPSHOT_CHARS] + "\n... (truncated)"

    intent_text = resolve_step_intent_text(step_intent=step_intent, step_desc=step_desc)

    try:
        system_prompt, user_prompt = await PromptManager.render("ui_locator_heal", {
            "method": method,
            "failed_locator": failed_locator,
            "step_intent": intent_text,
            "step_desc": (step_desc or "").strip(),
            "error_message": error_message or "",
            "page_url": page_url or "",
            "accessibility_snapshot": snapshot_text,
            "snapshot_type": snap_type,
        })
    except ValueError as exc:
        return {"success": False, "reason": str(exc)}

    try:
        resp = await call_llm(system_prompt, user_prompt)
    except Exception as exc:
        logger.warning("[ui_locator_heal] LLM 调用失败: %s", exc)
        return {"success": False, "reason": f"LLM 调用失败: {exc}"}
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

    shorten_reason = _reject_shortened_text_match(
        failed_locator=failed_locator,
        new_locator=new_locator,
        step_desc=intent_text,
    )
    if shorten_reason:
        return {
            "success": False,
            "reason": shorten_reason,
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
