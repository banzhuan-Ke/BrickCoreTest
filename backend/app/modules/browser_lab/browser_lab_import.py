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


def _build_step(
    method: str,
    desc: str,
    params: dict[str, Any],
    index: int,
    intent: str = "",
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    if meta:
        step["meta"] = meta
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


def _parse_element_index(payload: dict | None) -> int | None:
    payload = payload or {}
    raw = payload.get("index")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _resolve_page_tab_index(payload: dict | None) -> int:
    payload = payload or {}
    for key in ("index", "tab_id", "page_id", "tab_index", "page_index"):
        raw = payload.get(key)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return 0


def _resolve_locator(goal: str, action_payload: dict | None = None) -> tuple[str, str]:
    """复用 BL-1 缓存同源规则，返回 (locator, strength)。"""
    from app.modules.browser_lab.browser_lab_action_cache_core import _resolve_selector

    payload = action_payload or {}
    locator, strength = _resolve_selector(goal, payload)
    if locator:
        return locator, strength
    label = _extract_label(goal)
    if label:
        safe = label.replace('"', "")
        return f"get_by_text={safe}", "heuristic"
    return "body", "weak"


def _locator_import_meta(strength: str, payload: dict | None) -> dict[str, Any]:
    meta: dict[str, Any] = {"source": "browser_lab", "locator_strength": strength}
    payload = payload or {}
    has_direct = any(
        isinstance(payload.get(k), str) and str(payload.get(k)).strip()
        for k in ("xpath", "selector", "css_selector", "locator", "element")
    )
    if strength == "weak" or (not has_direct and _parse_element_index(payload) is not None):
        meta["needs_manual_locator"] = True
    return meta


def _browser_lab_playwright_index(element_index: int) -> int:
    """Browser Lab 交互元素 index 与 Runner params.index 均为 1-based。"""
    return max(1, int(element_index))


def _build_element_meta(
    action_key: str,
    payload: dict | None,
    *,
    locator_strength: str = "",
) -> dict[str, Any]:
    meta = _locator_import_meta(locator_strength, payload)
    element_index = _parse_element_index(payload)
    if element_index is not None and action_key.lower() in _CLICK_KEYS | _INPUT_KEYS:
        meta["browser_lab_element_index"] = element_index
    return meta


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
) -> tuple[list[dict], str]:
    key = (action_key or "").lower()
    payload = payload or {}

    if key in _SKIP_ACTION_KEYS or key == "compound":
        return [], last_url

    if key in _NAV_KEYS:
        url = (payload.get("url") or payload.get("href") or "").strip()
        if not url:
            return [], last_url
        if url == last_url and not payload.get("new_tab"):
            return [], url
        if payload.get("new_tab"):
            desc = f"新标签页访问 {url[:60]}"
            return [
                _build_step("open_new_page", goal or "新建标签页", {}, step_index, intent=goal),
                _build_step("open_url", desc, {"url": url}, step_index + 1, intent=goal),
            ], url
        desc = f"访问 {url[:60]}"
        return [_build_step("open_url", desc, {"url": url}, step_index, intent=goal)], url

    if key in _BACK_KEYS:
        return [_build_step("go_back", goal or "页面后退", {}, step_index, intent=goal)], last_url

    if key in _WAIT_KEYS:
        seconds = payload.get("seconds") or payload.get("time") or payload.get("duration") or 2
        try:
            ms = int(float(seconds) * 1000)
        except (TypeError, ValueError):
            ms = 2000
        ms = max(500, min(ms, 60000))
        return [_build_step("wait_for_time", goal or "等待", {"timeout": ms}, step_index)], last_url

    if key in _SCROLL_KEYS:
        down = payload.get("down")
        y = 400 if down is not False else -400
        if key == "scroll_up":
            y = -400
        return [
            _build_step(
                "execute_script",
                goal or "滚动页面",
                {"script": f"window.scrollBy(0, {y});"},
                step_index,
                intent=goal,
            )
        ], last_url

    if key in _CLICK_KEYS:
        locator, strength = _resolve_locator(goal, payload)
        label = _extract_label(goal) or "点击元素"
        element_index = _parse_element_index(payload)
        if element_index is not None and key == "click_element_by_index":
            label = f"{label}（Browser Lab 元素 #{element_index}）"[:200]
        meta = _build_element_meta(key, payload, locator_strength=strength)
        click_params: dict[str, Any] = {"locator": locator}
        if element_index is not None:
            click_params["index"] = _browser_lab_playwright_index(element_index)
        from app.modules.browser_lab.browser_lab_import_candidates import apply_locator_bundle_to_step

        return [
            apply_locator_bundle_to_step(
                _build_step(
                    "click_ele",
                    label,
                    click_params,
                    step_index,
                    intent=goal or label,
                    meta=meta,
                ),
                goal=goal,
                payload=payload,
                action_key=key,
            )
        ], last_url

    if key in _INPUT_KEYS:
        text = payload.get("text") or payload.get("value") or payload.get("content") or ""
        locator, strength = _resolve_locator(goal, payload)
        label = _extract_label(goal) or "输入内容"
        element_index = _parse_element_index(payload)
        if element_index is not None:
            label = f"{label}（Browser Lab 元素 #{element_index}）"[:200]
        meta = _build_element_meta(key, payload, locator_strength=strength)
        fill_params: dict[str, Any] = {"locator": locator, "value": str(text)}
        if element_index is not None:
            fill_params["index"] = _browser_lab_playwright_index(element_index)
        from app.modules.browser_lab.browser_lab_import_candidates import apply_locator_bundle_to_step

        return [
            apply_locator_bundle_to_step(
                _build_step(
                    "fill_value",
                    label,
                    fill_params,
                    step_index,
                    intent=goal or label,
                    meta=meta,
                ),
                goal=goal,
                payload=payload,
                action_key=key,
            )
        ], last_url

    if key in _KEYS_KEYS:
        key_name = payload.get("key") or payload.get("keys") or "Enter"
        return [
            _build_step(
                "press_key",
                goal or f"按键 {key_name}",
                {"key": str(key_name)},
                step_index,
                intent=goal,
            )
        ], last_url

    if key == "switch_tab":
        tab_index = _resolve_page_tab_index(payload)
        return [
            _build_step(
                "switch_to_page",
                goal or f"切换到标签页 {tab_index}",
                {"index": tab_index},
                step_index,
                intent=goal,
            )
        ], last_url

    if key == "close_tab":
        return [
            _build_step("close_page", goal or "关闭当前标签页", {}, step_index, intent=goal)
        ], last_url

    return [], last_url


_CLIENT_MUTABLE_PARAM_KEYS = frozenset({"locator", "selector"})


def _import_params_fingerprint(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        return {}
    return {k: v for k, v in sorted(params.items()) if k not in _CLIENT_MUTABLE_PARAM_KEYS}


def _import_element_index(step: dict) -> int | None:
    params = step.get("params") if isinstance(step.get("params"), dict) else {}
    raw_index = params.get("index")
    if raw_index is not None:
        try:
            return int(raw_index)
        except (TypeError, ValueError):
            pass
    meta = step.get("meta") if isinstance(step.get("meta"), dict) else {}
    raw_bl = meta.get("browser_lab_element_index")
    if raw_bl is not None:
        try:
            return _browser_lab_playwright_index(int(raw_bl))
        except (TypeError, ValueError):
            pass
    return None


def _dedup_import_steps(steps: list[dict]) -> list[dict]:
    """相邻相同 method + 语义参数指纹去重（保留翻页等有意重复）。"""
    out: list[dict] = []
    prev_key: tuple[str, str] | None = None
    for step in steps:
        method = str(step.get("method") or "")
        fp_key = (method, str(sorted(_import_params_fingerprint(step.get("params")).items())))
        if fp_key == prev_key:
            continue
        prev_key = fp_key
        out.append(step)
    return out


def steps_match_browser_lab_import(client_steps: list | None, server_steps: list) -> bool:
    """
    校验客户端提交的步骤是否基于本任务服务端转换结果。
    允许微调 locator/selector/desc/intent；禁止篡改 url/value/script/index 等语义参数。
    """
    if not isinstance(client_steps, list) or not client_steps:
        return False
    if len(client_steps) != len(server_steps):
        return False
    for client_step, server_step in zip(client_steps, server_steps):
        if not isinstance(client_step, dict) or not isinstance(server_step, dict):
            return False
        if (client_step.get("method") or "") != (server_step.get("method") or ""):
            return False
        if _import_params_fingerprint(client_step.get("params")) != _import_params_fingerprint(
            server_step.get("params")
        ):
            return False
        if _import_element_index(client_step) != _import_element_index(server_step):
            return False
    return True


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
        if event.get("cache_replay"):
            continue
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
            converted_list, last_url = _convert_single_action(
                action_key,
                payload,
                goal=goal,
                step_index=step_index,
                last_url=last_url,
            )
            for converted in converted_list:
                steps.append(converted)
                step_index += 1

    return _dedup_import_steps(steps)


def convert_cache_actions_to_ui_steps(
    *,
    start_url: str,
    task_text: str,
    actions: list | None,
    include_open_browser: bool = True,
) -> list[dict]:
    """将 BL-1 缓存动作转为 Web UI 步骤（缓存命中任务导入用）。"""
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

    for action in actions or []:
        if not isinstance(action, dict):
            continue
        op = (action.get("op") or "").lower()
        selector = (action.get("selector") or "").strip() or "body"
        if op == "navigate":
            url = (action.get("url") or "").strip()
            if not url or url == last_url:
                continue
            if action.get("new_tab"):
                steps.append(_build_step("open_new_page", "新建标签页", {}, step_index))
                step_index += 1
            steps.append(_build_step("open_url", f"访问 {url[:60]}", {"url": url}, step_index))
            step_index += 1
            last_url = url
            continue
        if op == "click":
            fallbacks = [f for f in (action.get("fallbacks") or []) if isinstance(f, str) and f.strip()]
            meta = {
                "source": "browser_lab_cache",
                "locator_strength": (action.get("strength") or "strong"),
            }
            if fallbacks:
                meta["candidates"] = fallbacks[:12]
            steps.append(
                _build_step(
                    "click_ele",
                    "点击元素",
                    {"locator": selector},
                    step_index,
                    meta=meta,
                )
            )
            step_index += 1
            continue
        if op in ("fill", "select"):
            vf = action.get("value_from")
            if isinstance(vf, str) and vf.startswith("var:"):
                value = "${{" + vf[4:] + "}}"
            else:
                value = "" if vf else (action.get("value") or "")
            fallbacks = [f for f in (action.get("fallbacks") or []) if isinstance(f, str) and f.strip()]
            meta = {
                "source": "browser_lab_cache",
                "locator_strength": (action.get("strength") or "strong"),
            }
            if fallbacks:
                meta["candidates"] = fallbacks[:12]
            steps.append(
                _build_step(
                    "fill_value",
                    "输入内容" if op == "fill" else "选择选项",
                    {"locator": selector, "value": str(value)},
                    step_index,
                    meta=meta,
                )
            )
            step_index += 1
            continue
        if op == "wait":
            ms = int(action.get("timeout_ms") or 1000)
            steps.append(
                _build_step("wait_for_time", "等待", {"timeout": max(500, min(ms, 60000))}, step_index)
            )
            step_index += 1
            continue
        if op == "scroll":
            y = int(action.get("y") or 400)
            steps.append(
                _build_step(
                    "execute_script",
                    "滚动页面",
                    {"script": f"window.scrollBy(0, {y});"},
                    step_index,
                )
            )
            step_index += 1
            continue
        if op == "press":
            key_name = str(action.get("key") or "Enter")
            steps.append(
                _build_step("press_key", f"按键 {key_name}", {"key": key_name}, step_index)
            )
            step_index += 1

    return steps
