"""
Agent / MCP 探索：通用定位器优选与页面进展判断（与录制器候选优先级一致）
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Optional
from urllib.parse import urlparse

from app.core.locator_utils import normalize_locator

# 与 runner/tools/recorder_engine 一致的短词黑名单（易误匹配页面说明）
_COMMON_SHORT_TEXTS = frozenset({
    "登录", "提交", "确定", "取消", "保存", "删除", "编辑", "新增", "查询", "搜索",
    "OK", "ok", "Yes", "No",
})


def _normalize_url(url: str) -> str:
    try:
        p = urlparse(url or "")
        return f"{p.scheme}://{p.netloc}{p.path}".rstrip("/").lower()
    except Exception:
        return (url or "").strip().lower()


def structural_fingerprint(url: str, snap_text: str) -> str:
    """
    页面结构指纹：URL + snapshot 中导航/按钮/表单等主干节点。
    用于判断 click 后是否真正换屏（忽略仅 Toast/alert 文案变化）。
    """
    lines: list[str] = []
    for line in (snap_text or "").splitlines():
        low = line.lower()
        if any(k in low for k in ("alert", "toast", "role=alert", "错误", "成功提示")):
            if len(line) < 100:
                continue
        if any(
            k in low
            for k in (
                "button", "role=button", "menu", "nav", "link",
                "textbox", "combobox", " id=", "data-testid", "data_testid",
            )
        ):
            lines.append(line.strip()[:120])
    key = _normalize_url(url)
    body = "\n".join(sorted(set(lines))[:40])
    return hashlib.md5(f"{key}\n{body}".encode("utf-8", errors="ignore")).hexdigest()


def action_made_progress(
    *,
    method: str,
    url_before: str,
    url_after: str,
    struct_before: str,
    struct_after: str,
) -> bool:
    """操作后是否有可识别的页面进展（通用，不依赖特定 #id）"""
    if _normalize_url(url_before) != _normalize_url(url_after):
        return True
    if method in ("open_url", "refresh", "go_back", "wait_for_load"):
        return True
    if method == "click_ele" and struct_before != struct_after:
        return True
    if method in ("fill_value", "select_option", "type_value") and struct_before != struct_after:
        return True
    return False


def _infer_role(el: dict) -> str:
    tag = (el.get("tag") or "").lower()
    if tag == "button":
        return "button"
    if tag == "a":
        return "link"
    if tag in ("input", "textarea"):
        t = (el.get("type") or "").lower()
        if t in ("submit", "button"):
            return "button"
        return "textbox"
    if tag == "select":
        return "combobox"
    role = (el.get("role") or "").lower()
    if role in ("button", "link", "textbox", "combobox", "menuitem", "tab"):
        return role
    return ""


def build_candidates_from_element(el: dict) -> list[str]:
    """按录制器优先级生成候选定位器（data-testid > #id > role > text …）"""
    tag = (el.get("tag") or "").lower()
    text = (el.get("text") or "").strip()
    is_short = text in _COMMON_SHORT_TEXTS
    candidates: list[str] = []

    testid = (el.get("data_testid") or el.get("data-testid") or "").strip()
    if testid:
        candidates.append(f'[data-testid="{testid}"]')

    elem_id = (el.get("id") or "").strip()
    if elem_id:
        candidates.append(f"#{elem_id}")
        if tag == "button":
            candidates.append(f"//button[@id='{elem_id}']")

    if text and not is_short and 1 < len(text) < 40:
        role = _infer_role(el)
        if role:
            candidates.append(f"get_by_role={role}, {text}")

    if text and 1 < len(text) < 40 and not is_short:
        candidates.append(f"get_by_text={text}")

    name = (el.get("name") or "").strip()
    if name:
        candidates.append(f'{tag}[name="{name}"]')

    placeholder = (el.get("placeholder") or "").strip()
    if placeholder and tag in ("input", "textarea"):
        candidates.append(f"get_by_placeholder={placeholder}")

    aria = (el.get("aria_label") or "").strip()
    if aria:
        candidates.append(f"get_by_label={aria}")

    selector = (el.get("selector") or "").strip()
    if selector and selector not in candidates:
        candidates.append(selector)

    return candidates


def _hints_from_step(step: dict) -> list[str]:
    """从步骤描述/定位器提取用于匹配 DOM 的文本片段"""
    hints: list[str] = []
    desc = (step.get("desc") or "").strip()
    for m in re.finditer(r"[「『\"']([^」』\"']+)[」』\"']", desc):
        hints.append(m.group(1).strip())
    for m in re.finditer(r"(?:点击|选择|打开|进入)\s*[「『\"]?\s*([^，。；\s]+)", desc):
        t = m.group(1).strip()
        if t and len(t) <= 20:
            hints.append(t)
    loc = normalize_locator((step.get("params") or {}).get("locator"))
    if loc.startswith("get_by_text="):
        hints.append(loc.split("=", 1)[1].strip())
    elif loc.startswith("get_by_role="):
        parts = loc[12:].split(",", 1)
        if len(parts) > 1:
            hints.append(parts[1].strip())
    elif loc.startswith("#"):
        hints.append(loc[1:])
    return [h for h in hints if h]


def _score_element(el: dict, hints: list[str], *, prefer_tags: tuple[str, ...]) -> int:
    tag = (el.get("tag") or "").lower()
    if prefer_tags and tag not in prefer_tags:
        return 0
    text = (el.get("text") or "").strip()
    el_id = (el.get("id") or "").strip()
    score = 0
    if el_id:
        score += 4
    for h in hints:
        if not h:
            continue
        if h == el_id or h == text:
            score += 12
        if h in text or text in h:
            score += 8
        if h.replace(" ", "") in text.replace(" ", ""):
            score += 6
    if tag == "button":
        score += 2
    return score


def find_best_element(
    elements: list[dict],
    hints: list[str],
    *,
    prefer_tags: tuple[str, ...] = ("button", "a", "input"),
) -> Optional[dict]:
    best: Optional[dict] = None
    best_score = 0
    for el in elements:
        if not isinstance(el, dict):
            continue
        s = _score_element(el, hints, prefer_tags=prefer_tags)
        if s > best_score:
            best_score = s
            best = el
    return best if best_score >= 8 else None


def is_weak_locator(loc: str, *, method: str) -> bool:
    loc = normalize_locator(loc)
    if not loc:
        return True
    if method == "click_ele" and loc.startswith("get_by_text="):
        text = loc.split("=", 1)[1].strip()
        if text in _COMMON_SHORT_TEXTS or len(text) <= 4:
            return True
    if method == "fill_value" and loc.startswith("get_by_text="):
        return True
    return False


def pick_stable_locator(step: dict, elements: list[dict]) -> str:
    """为 Agent 规划步骤优选稳定 locator（与录制候选顺序一致）"""
    method = (step.get("method") or "").strip()
    params = step.get("params") or {}
    current = normalize_locator(params.get("locator") if isinstance(params, dict) else "")
    if not elements:
        return current

    hints = _hints_from_step(step)

    if method == "click_ele":
        el = find_best_element(elements, hints, prefer_tags=("button", "a", "input"))
        if el:
            cands = build_candidates_from_element(el)
            if cands:
                return cands[0]
    elif method in ("fill_value", "type_value", "clear_value"):
        el = find_best_element(elements, hints, prefer_tags=("input", "textarea"))
        if el:
            cands = build_candidates_from_element(el)
            for c in cands:
                if c.startswith(("#", "get_by_placeholder=", "get_by_label=", "[")):
                    return c
            if cands:
                return cands[0]

    if is_weak_locator(current, method=method) and hints:
        el = find_best_element(
            elements,
            hints,
            prefer_tags=("button", "a") if method == "click_ele" else ("input", "textarea"),
        )
        if el:
            cands = build_candidates_from_element(el)
            if cands:
                return cands[0]

    return current


def refine_agent_step_locator(step: dict, elements: list[dict]) -> dict:
    """执行前将 LLM 给出的弱定位器替换为 DOM 提取的稳定候选"""
    if not isinstance(step, dict) or not elements:
        return step
    method = (step.get("method") or "").strip()
    if method not in ("click_ele", "fill_value", "type_value", "clear_value", "select_option"):
        return step

    params = step.setdefault("params", {})
    if not isinstance(params, dict):
        return step

    old = normalize_locator(params.get("locator"))
    new = pick_stable_locator(step, elements)
    if new and new != old:
        params["locator"] = new
    return step
