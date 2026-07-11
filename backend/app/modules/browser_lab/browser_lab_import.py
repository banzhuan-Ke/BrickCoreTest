"""Browser Lab 执行记录 → Web UI 自动化步骤转换。"""
from __future__ import annotations

import re
import time
from typing import Any

from app.core.shared.ui_keywords import METHOD_TO_KEYWORD, UI_DEFAULT_PARAMS

_SKIP_ACTION_KEYS = frozenset({
    "done",
    "extract_content",
    "extract_structured_data",
    "search_google",
    "write_file",
    "read_file",
})

_NAV_KEYS = frozenset({"navigate", "go_to_url", "go_to", "open_url"})
_CLICK_KEYS = frozenset({"click_element", "click", "click_element_by_index"})
_INPUT_KEYS = frozenset({"input_text", "input", "type_text"})
_SCROLL_KEYS = frozenset({"scroll", "scroll_down", "scroll_up", "scroll_page"})
_WAIT_KEYS = frozenset({"wait", "wait_for", "wait_seconds"})
_BACK_KEYS = frozenset({"go_back", "back"})
_KEYS_KEYS = frozenset({"send_keys", "press_key"})


def _new_step_id(index: int) -> str:
    return f"step_{int(time.time() * 1000)}_{index}"


def _build_step(method: str, desc: str, params: dict[str, Any], index: int, intent: str = "") -> dict[str, Any]:
    merged = dict(UI_DEFAULT_PARAMS.get(method, {}))
    merged.update(params or {})
    step: dict[str, Any] = {
        "id": _new_step_id(index),
        "keyword": METHOD_TO_KEYWORD.get(method, method),
        "desc": (desc or METHOD_TO_KEYWORD.get(method, method))[:200],
        "method": method,
        "params": merged,
        "children": [],
    }
    if intent.strip():
        step["intent"] = intent.strip()[:500]
    return step


def _extract_label(text: str) -> str:
    if not text:
        return ""
    for pattern in (
        r"[「『\"']([^「」『』\"']{1,40})[」』\"']",
        r"(?:点击|输入|选择|打开|提交|登录|搜索)(.{1,20})",
    ):
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip()
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:40] if cleaned else ""


def _guess_locator(goal: str, action_payload: dict | None = None) -> str:
    payload = action_payload or {}
    for key in ("xpath", "selector", "css_selector", "locator", "element"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    label = _extract_label(goal)
    if label:
        safe = label.replace('"', "")
        return f'get_by_text={safe}'
    if goal:
        short = goal.strip()[:30].replace('"', "")
        return f'get_by_text={short}'
    return "body"


def _unwrap_action(action: dict) -> tuple[str, dict]:
    if not isinstance(action, dict) or not action:
        return "", {}
    if len(action) == 1:
        key, val = next(iter(action.items()))
        if isinstance(val, dict):
            return str(key), val
        return str(key), {}
    return "compound", action


def _convert_single_action(
    action_key: str,
    payload: dict,
    *,
    goal: str,
    step_index: int,
    last_url: str,
) -> tuple[dict | None, str]:
    key = (action_key or "").lower()
    payload = payload or {}

    if key in _SKIP_ACTION_KEYS or key == "compound":
        return None, last_url

    if key in _NAV_KEYS:
        url = (payload.get("url") or payload.get("href") or "").strip()
        if not url:
            return None, last_url
        if url == last_url:
            return None, url
        desc = f"访问 {url[:60]}"
        return _build_step("open_url", desc, {"url": url}, step_index, intent=goal), url

    if key in _BACK_KEYS:
        return _build_step("go_back", goal or "页面后退", {}, step_index, intent=goal), last_url

    if key in _WAIT_KEYS:
        seconds = payload.get("seconds") or payload.get("time") or payload.get("duration") or 2
        try:
            ms = int(float(seconds) * 1000)
        except (TypeError, ValueError):
            ms = 2000
        ms = max(500, min(ms, 60000))
        return _build_step("wait_for_time", goal or "等待", {"timeout": ms}, step_index), last_url

    if key in _SCROLL_KEYS:
        down = payload.get("down")
        y = 400 if down is not False else -400
        if key == "scroll_up":
            y = -400
        return _build_step(
            "execute_script",
            goal or "滚动页面",
            {"script": f"window.scrollBy(0, {y});"},
            step_index,
            intent=goal,
        ), last_url

    if key in _CLICK_KEYS:
        locator = _guess_locator(goal, payload)
        label = _extract_label(goal) or "点击元素"
        return _build_step(
            "click_ele",
            label,
            {"locator": locator},
            step_index,
            intent=goal or label,
        ), last_url

    if key in _INPUT_KEYS:
        text = payload.get("text") or payload.get("value") or payload.get("content") or ""
        locator = _guess_locator(goal, payload)
        label = _extract_label(goal) or "输入内容"
        return _build_step(
            "fill_value",
            label,
            {"locator": locator, "value": str(text)},
            step_index,
            intent=goal or label,
        ), last_url

    if key in _KEYS_KEYS:
        key_name = payload.get("key") or payload.get("keys") or "Enter"
        return _build_step(
            "press_key",
            goal or f"按键 {key_name}",
            {"key": str(key_name)},
            step_index,
            intent=goal,
        ), last_url

    if key in {"switch_tab", "close_tab"}:
        return None, last_url

    return None, last_url


def convert_browser_lab_to_ui_steps(
    *,
    start_url: str,
    task_text: str,
    step_log: list | None,
    include_open_browser: bool = True,
) -> list[dict]:
    """
    将 Browser Lab step_log 转为 Web UI 步骤列表。
    定位器多为启发式生成，导入后需人工核对。
    """
    events = [e for e in (step_log or []) if isinstance(e, dict) and e.get("type") == "step"]
    steps: list[dict] = []
    step_index = 0
    last_url = ""

    if include_open_browser:
        steps.append(_build_step("open_browser", "打开浏览器", {"browser_type": "chromium"}, step_index))
        step_index += 1

    normalized_start = (start_url or "").strip()
    if normalized_start:
        steps.append(
            _build_step(
                "open_url",
                f"访问 {normalized_start[:60]}",
                {"url": normalized_start},
                step_index,
                intent=(task_text or "")[:500],
            )
        )
        step_index += 1
        last_url = normalized_start

    for event in events:
        idx = event.get("index")
        if idx in (0, None):
            continue
        goal = (event.get("next_goal") or event.get("thinking") or "").strip()
        actions = event.get("actions") or []
        if not actions:
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            action_key, payload = _unwrap_action(action)
            converted, last_url = _convert_single_action(
                action_key,
                payload,
                goal=goal,
                step_index=step_index,
                last_url=last_url,
            )
            if converted:
                steps.append(converted)
                step_index += 1

    return steps
