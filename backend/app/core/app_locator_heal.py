"""
App 步骤定位器自愈（控件树 + 可选截图 Vision）
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional

from app.core.ai_prompts import PromptManager
from app.core.app_keywords import METHOD_TO_KEYWORD

logger = logging.getLogger(__name__)

APP_HEALABLE_METHODS = frozenset({
    "click_element", "double_click_element", "long_press_element",
    "input_text", "clear_text", "get_text",
    "wait_element", "wait_gone", "scroll_to",
    "assert_exists", "assert_not_exists", "assert_text", "assert_text_contains",
    "extract_text",
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
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


def _format_locator(locator: Any) -> str:
    if isinstance(locator, dict):
        by = locator.get("by") or ""
        val = locator.get("value") or ""
        return f'{{"by":"{by}","value":"{val}"}}'
    return str(locator or "")


_LOCATOR_META_KEYS = (
    "context",
    "page_index",
    "devtools_source",
    "index",
    "threshold",
    "rgb",
    "record_pos",
    "resolution",
    "target_pos",
)


def _merge_locator_metadata(out: dict, raw: dict, failed: dict) -> dict:
    """保留 H5/WebView/图像定位元数据；LLM 未返回时继承失败定位器。"""
    for key in _LOCATOR_META_KEYS:
        if key in raw and raw[key] is not None:
            out[key] = raw[key]
        elif key in failed and failed[key] is not None:
            out[key] = failed[key]
    if str(out.get("by") or "").lower() == "image" and out.get("threshold") is None:
        out["threshold"] = failed.get("threshold") if failed.get("threshold") is not None else 0.8
    return out


def _normalize_healed_locator(raw: Any, failed: dict) -> Optional[dict]:
    if isinstance(raw, dict) and raw.get("by"):
        out = {"by": str(raw["by"]).strip(), "value": str(raw.get("value") or "").strip()}
        return _merge_locator_metadata(out, raw, failed)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and parsed.get("by"):
                return _normalize_healed_locator(parsed, failed)
        except json.JSONDecodeError:
            pass
        by = failed.get("by") or "text"
        return _merge_locator_metadata({"by": by, "value": raw.strip()}, {}, failed)
    return None


async def heal_app_locator(
    *,
    method: str,
    failed_locator: dict,
    step_desc: Optional[str] = None,
    error_message: Optional[str] = None,
    match_score: Optional[float] = None,
    control_tree_excerpt: Optional[str] = None,
    screenshot_base64: Optional[str] = None,
    call_llm: Callable,
    call_vision: Optional[Callable] = None,
) -> dict[str, Any]:
    """为 App 失败步骤推荐新 locator（对象格式）。"""
    method = (method or "").strip()
    if method and method not in APP_HEALABLE_METHODS:
        return {"success": False, "reason": f"方法 {method} 不支持自愈"}

    failed = failed_locator if isinstance(failed_locator, dict) else {}
    if not failed.get("by"):
        return {"success": False, "reason": "缺少失败定位器"}

    vision_hint = ""
    tokens = 0
    if screenshot_base64 and call_vision:
        try:
            vresp = await call_vision(
                "请简要描述截图中与步骤相关的可点击控件位置与文案（中文，3～5 句）。",
                screenshot_base64,
            )
            vision_hint = (vresp.get("content") or "").strip()
            tokens += int(vresp.get("tokens") or 0)
        except Exception as exc:
            logger.warning("[app_locator_heal] Vision 读图失败: %s", exc)

    try:
        system_prompt, user_prompt = await PromptManager.render(
            "app_locator_heal",
            {
                "method": method,
                "failed_locator": _format_locator(failed),
                "step_desc": step_desc or "",
                "error_message": error_message or "",
                "match_score": match_score if match_score is not None else "",
                "control_tree_excerpt": control_tree_excerpt or "（未提供控件树）",
                "vision_hint": vision_hint or "（未使用 Vision）",
            },
        )
    except Exception as exc:
        return {"success": False, "reason": f"Prompt 渲染失败: {exc}"}

    resp = await call_llm(system_prompt, user_prompt)
    raw = resp.get("content", "")
    tokens += int(resp.get("tokens") or 0)
    parsed = _extract_json_object(raw)
    new_loc = _normalize_healed_locator(
        parsed.get("locator") or parsed.get("new_locator"),
        failed,
    )
    if not new_loc:
        return {
            "success": False,
            "reason": parsed.get("reason") or "LLM 未能给出新定位器",
            "tokens_used": tokens,
            "raw_response": raw,
        }
    by_value = str(new_loc.get("by") or "").strip().lower()
    if by_value != "coordinates" and not str(new_loc.get("value") or "").strip():
        return {
            "success": False,
            "reason": "LLM 返回的定位值为空",
            "tokens_used": tokens,
            "raw_response": raw,
        }
    if new_loc.get("by") == failed.get("by") and new_loc.get("value") == failed.get("value"):
        return {
            "success": False,
            "reason": "建议定位器与原定位器相同",
            "locator": new_loc,
            "tokens_used": tokens,
        }
    return {
        "success": True,
        "locator": new_loc,
        "confidence": parsed.get("confidence") or "medium",
        "reason": parsed.get("reason") or "",
        "tokens_used": tokens,
        "raw_response": raw,
    }


def format_control_tree_excerpt(nodes: list, *, limit: int = 40) -> str:
    """从控件树节点列表截取可见文本摘要。"""
    lines: list[str] = []
    for i, node in enumerate(nodes[:limit]):
        if not isinstance(node, dict):
            continue
        attrs = node.get("attributes") or node.get("attrib") or node
        if not isinstance(attrs, dict):
            attrs = {}
        text = (
            attrs.get("text")
            or attrs.get("content-desc")
            or attrs.get("contentDescription")
            or attrs.get("resource-id")
            or attrs.get("resourceId")
            or ""
        )
        cls = attrs.get("class") or attrs.get("className") or ""
        if text or cls:
            lines.append(f"{i}. class={cls} text={text}")
    return "\n".join(lines) if lines else "（控件树为空）"
