"""交互调试快捷键默认值（与 runner/tools/ui_debug_hotkeys.py 对齐的精简副本）。"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Mapping

HOTKEY_ACTIONS = (
    "page_freeze",
    "pick",
    "highlight",
    "clear_highlight",
    "verify",
    "run_current",
    "run_selected",
    "run_to_end",
    "help",
    "close",
)

HOTKEY_ACTION_LABELS: Dict[str, str] = {
    "page_freeze": "冻结/解冻页面",
    "pick": "拾取开关",
    "highlight": "高亮",
    "clear_highlight": "取消高亮",
    "verify": "验证",
    "run_current": "执行本步",
    "run_selected": "执行勾选",
    "run_to_end": "执行至末尾",
    "help": "快捷键说明",
    "close": "关闭浏览器",
}

DEFAULT_HOTKEYS: Dict[str, str] = {
    "page_freeze": "Ctrl+Shift+F",
    "pick": "Ctrl+Shift+P",
    "highlight": "Ctrl+Shift+H",
    "clear_highlight": "Ctrl+Shift+G",
    "verify": "Ctrl+Shift+V",
    "run_current": "Ctrl+Shift+Enter",
    "run_selected": "Ctrl+Shift+S",
    "run_to_end": "Ctrl+Shift+E",
    "help": "F1",
    "close": "",
}

_MOD_ORDER = ("Ctrl", "Alt", "Shift", "Meta")


def normalize_hotkey_combo(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    parts = re.split(r"[+\s]+", text.replace("-", "+"))
    mods: list[str] = []
    key = ""
    for p in parts:
        t = (p or "").strip()
        if not t:
            continue
        low = t.lower()
        if low in ("ctrl", "control"):
            n = "Ctrl"
        elif low in ("alt", "option"):
            n = "Alt"
        elif low == "shift":
            n = "Shift"
        elif low in ("meta", "cmd", "win"):
            n = "Meta"
        elif low in (" ", "space", "spacebar"):
            n = "Space"
        elif low in ("esc", "escape"):
            n = "Escape"
        elif low in ("enter", "return"):
            n = "Enter"
        elif re.fullmatch(r"[fF]\d{1,2}", t):
            n = t.upper()
        elif len(t) == 1:
            n = t.upper() if t.isalpha() else t
        else:
            n = t
        if n in _MOD_ORDER:
            if n not in mods:
                mods.append(n)
        else:
            key = n
    if not key or key in _MOD_ORDER:
        return ""
    if len(key) == 1 and key.isalnum() and not mods:
        return ""
    return "+".join([m for m in _MOD_ORDER if m in mods] + [key])


def validate_hotkeys_map(raw: Mapping[str, Any] | None) -> Dict[str, str]:
    out = {k: "" for k in HOTKEY_ACTIONS}
    if not isinstance(raw, Mapping):
        return out
    used: Dict[str, str] = {}
    for action in HOTKEY_ACTIONS:
        if action not in raw:
            continue
        combo = normalize_hotkey_combo(raw.get(action))
        if not combo:
            out[action] = ""
            continue
        if combo in used and used[combo] != action:
            out[action] = ""
            continue
        out[action] = combo
        used[combo] = action
    return out


def merge_hotkeys(*layers: Mapping[str, Any] | None) -> Dict[str, str]:
    merged = dict(DEFAULT_HOTKEYS)
    for layer in layers:
        if not isinstance(layer, Mapping):
            continue
        validated = validate_hotkeys_map(layer)
        for action in HOTKEY_ACTIONS:
            if action in layer:
                merged[action] = validated[action]
            elif validated[action]:
                merged[action] = validated[action]
    return validate_hotkeys_map(merged)


def hotkeys_to_json(hotkeys: Mapping[str, str]) -> str:
    merged = merge_hotkeys(DEFAULT_HOTKEYS, hotkeys)
    return json.dumps(merged, ensure_ascii=False)
