"""环境级 Web 启动登录态注入（global_vars 保留键）。

下发给 Runner：ui_auth_inject / ui_storage_state。
变量占位 ${{var}} 由 Runner 在创建 context 时用 env variables 展开。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

UI_AUTH_INJECT_KEY = "__ui_auth_inject"
UI_STORAGE_STATE_KEY = "__ui_storage_state"

UI_AUTH_INJECT_KEYS = frozenset({UI_AUTH_INJECT_KEY, UI_STORAGE_STATE_KEY})

MAX_STORAGE_PAIRS = 30
MAX_COOKIES = 30
MAX_HEADERS = 20
MAX_KEY_LEN = 200
# Pinia / JWT JSON 常见 3～10KB；过小会导致环境「启动登录态」保存失败
MAX_VALUE_LEN = 32000
MAX_HEADER_NAME_LEN = 100
MAX_STORAGE_STATE_CHARS = 500_000


def _extract_plain(raw: Any) -> Any:
    if isinstance(raw, dict) and "value" in raw and len(raw) <= 3:
        # 兼容误存成 {value: ...} 的扩展变量格式；真正的 inject 对象无单一 value
        if set(raw.keys()) <= {"value", "description", "secret"}:
            return raw.get("value")
    return raw


def _as_dict(raw: Any) -> Any:
    val = _extract_plain(raw)
    if val is None or val == "":
        return None
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        text = val.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("启动登录态注入须为 JSON 对象") from exc
        if not isinstance(parsed, dict):
            raise ValueError("启动登录态注入须为 JSON 对象")
        return parsed
    raise ValueError("启动登录态注入须为 JSON 对象")


def _norm_storage_list(raw: Any, *, label: str) -> List[Dict[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{label} 须为数组")
    if len(raw) > MAX_STORAGE_PAIRS:
        raise ValueError(f"{label} 最多 {MAX_STORAGE_PAIRS} 项")
    out: List[Dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"{label} 每项须为对象 {{key, value}}")
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        if len(key) > MAX_KEY_LEN:
            raise ValueError(f"{label} 键长度不能超过 {MAX_KEY_LEN}")
        value = item.get("value")
        if value is None:
            value = ""
        if isinstance(value, (dict, list)):
            raise ValueError(f"{label} 的 value 不能是对象或数组")
        s = str(value)
        if len(s) > MAX_VALUE_LEN:
            raise ValueError(f"{label} 值长度不能超过 {MAX_VALUE_LEN}")
        out.append({"key": key, "value": s})
    return out


def _norm_cookies(raw: Any) -> List[Dict[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("cookies 须为数组")
    if len(raw) > MAX_COOKIES:
        raise ValueError(f"cookies 最多 {MAX_COOKIES} 项")
    out: List[Dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("cookie 项须为对象")
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        if len(name) > MAX_KEY_LEN:
            raise ValueError(f"cookie name 长度不能超过 {MAX_KEY_LEN}")
        value = item.get("value")
        if value is None:
            value = ""
        if isinstance(value, (dict, list)):
            raise ValueError("cookie value 不能是对象或数组")
        s = str(value)
        if len(s) > MAX_VALUE_LEN:
            raise ValueError(f"cookie value 长度不能超过 {MAX_VALUE_LEN}")
        domain = str(item.get("domain") or "").strip()
        path = str(item.get("path") or "/").strip() or "/"
        url = str(item.get("url") or "").strip()
        if not domain and not url:
            raise ValueError(f"cookie「{name}」须提供 domain 或 url")
        if len(domain) > MAX_KEY_LEN:
            raise ValueError("cookie domain 过长")
        if len(path) > MAX_KEY_LEN:
            raise ValueError("cookie path 过长")
        if len(url) > 2000:
            raise ValueError("cookie url 过长")
        entry: Dict[str, str] = {"name": name, "value": s, "path": path}
        if domain:
            entry["domain"] = domain
        if url:
            entry["url"] = url
        out.append(entry)
    return out


def _norm_headers(raw: Any) -> Dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("headers 须为对象")
    if len(raw) > MAX_HEADERS:
        raise ValueError(f"headers 最多 {MAX_HEADERS} 项")
    out: Dict[str, str] = {}
    for k, v in raw.items():
        name = str(k or "").strip()
        if not name:
            continue
        if len(name) > MAX_HEADER_NAME_LEN:
            raise ValueError(f"header 名长度不能超过 {MAX_HEADER_NAME_LEN}")
        if isinstance(v, (dict, list)):
            raise ValueError(f"header「{name}」值不能是对象或数组")
        s = str(v if v is not None else "")
        if len(s) > MAX_VALUE_LEN:
            raise ValueError(f"header「{name}」值过长")
        if s == "":
            continue
        out[name] = s
    return out


def normalize_auth_inject(raw: Any) -> Optional[Dict[str, Any]]:
    """规范化 __ui_auth_inject；空配置返回 None（表示删除键）。"""
    data = _as_dict(raw)
    if data is None:
        return None
    local_storage = _norm_storage_list(data.get("local_storage"), label="local_storage")
    session_storage = _norm_storage_list(data.get("session_storage"), label="session_storage")
    cookies = _norm_cookies(data.get("cookies"))
    headers = _norm_headers(data.get("headers"))
    if not local_storage and not session_storage and not cookies and not headers:
        return None
    return {
        "local_storage": local_storage,
        "session_storage": session_storage,
        "cookies": cookies,
        "headers": headers,
    }


def normalize_storage_state(raw: Any) -> Optional[Any]:
    """
    规范化 __ui_storage_state：
    - 本机路径字符串
    - Playwright storage_state JSON 对象 / JSON 字符串
    空值返回 None。
    """
    val = _extract_plain(raw)
    if val is None or val == "":
        return None
    if isinstance(val, dict):
        text = json.dumps(val, ensure_ascii=False)
        if len(text) > MAX_STORAGE_STATE_CHARS:
            raise ValueError("storage_state JSON 过大")
        # 至少像 Playwright storage state
        if "cookies" not in val and "origins" not in val:
            raise ValueError("storage_state 对象须包含 cookies 或 origins")
        return val
    if isinstance(val, str):
        text = val.strip()
        if not text:
            return None
        if len(text) > MAX_STORAGE_STATE_CHARS:
            raise ValueError("storage_state 内容过大")
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("storage_state JSON 无效") from exc
            if not isinstance(parsed, dict):
                raise ValueError("storage_state JSON 须为对象")
            if "cookies" not in parsed and "origins" not in parsed:
                raise ValueError("storage_state 对象须包含 cookies 或 origins")
            return parsed
        # 路径：禁止明显危险字符
        if "\n" in text or "\r" in text:
            raise ValueError("storage_state 路径不能包含换行")
        if len(text) > 1000:
            raise ValueError("storage_state 路径过长")
        return text
    raise ValueError("storage_state 须为路径字符串或 JSON 对象")


def normalize_ui_auth_inject_value(key: str, raw: Any) -> Any:
    """normalize_global_vars 用：返回应写入的值，或 None 表示删除该键。"""
    if key == UI_AUTH_INJECT_KEY:
        return normalize_auth_inject(raw)
    if key == UI_STORAGE_STATE_KEY:
        return normalize_storage_state(raw)
    raise ValueError(f"未知登录态注入键：{key}")


def parse_ui_auth_inject(global_vars: dict | None) -> Optional[Dict[str, Any]]:
    gv = global_vars if isinstance(global_vars, dict) else {}
    try:
        return normalize_auth_inject(gv.get(UI_AUTH_INJECT_KEY))
    except ValueError:
        return None


def parse_ui_storage_state(global_vars: dict | None) -> Optional[Any]:
    gv = global_vars if isinstance(global_vars, dict) else {}
    try:
        return normalize_storage_state(gv.get(UI_STORAGE_STATE_KEY))
    except ValueError:
        return None


def build_ui_auth_inject_payload(global_vars: dict | None) -> Dict[str, Any]:
    """构建下发给 Runner 的登录态字段（始终带键，便于 Runner 统一处理）。"""
    inject = parse_ui_auth_inject(global_vars)
    storage = parse_ui_storage_state(global_vars)
    return {
        "ui_auth_inject": inject,
        "ui_storage_state": storage,
    }
