"""环境级 Web 启动登录态注入（global_vars 保留键）。

下发给 Runner：ui_auth_inject / ui_storage_state。
变量占位 ${{var}} 由 Runner 在创建 context 时用 env variables 展开。

多站点：`__ui_auth_profiles` 为命名登录态列表（类似 Token 授权多条配置），
启用项在下发前合并为单一 `ui_storage_state` 对象，任意执行机可用（不必本机路径）。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

UI_AUTH_INJECT_KEY = "__ui_auth_inject"
UI_STORAGE_STATE_KEY = "__ui_storage_state"
UI_AUTH_PROFILES_KEY = "__ui_auth_profiles"
# 总开关：false 时保留配置但不下发给 Runner（停用不清数据）
UI_AUTH_ENABLED_KEY = "__ui_auth_enabled"

UI_AUTH_INJECT_KEYS = frozenset(
    {
        UI_AUTH_INJECT_KEY,
        UI_STORAGE_STATE_KEY,
        UI_AUTH_PROFILES_KEY,
        UI_AUTH_ENABLED_KEY,
    }
)

MAX_STORAGE_PAIRS = 30
MAX_COOKIES = 30
MAX_HEADERS = 20
MAX_KEY_LEN = 200
# Pinia / JWT JSON 常见 3～10KB；过小会导致环境「启动登录态」保存失败
MAX_VALUE_LEN = 32000
MAX_HEADER_NAME_LEN = 100
MAX_STORAGE_STATE_CHARS = 500_000
MAX_AUTH_PROFILES = 12
MAX_PROFILE_NAME_LEN = 80
MAX_HOST_HINT_LEN = 200


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


def _has_storage_payload(doc: dict) -> bool:
    if not isinstance(doc, dict):
        return False
    if isinstance(doc.get("cookies"), list) and doc.get("cookies"):
        return True
    if isinstance(doc.get("origins"), list) and doc.get("origins"):
        return True
    for key in ("sessionStorageOrigins", "session_storage_origins"):
        if isinstance(doc.get(key), list) and doc.get(key):
            return True
    # 允许空壳对象（cookies/origins 键存在），便于占位后再编辑
    return "cookies" in doc or "origins" in doc or "sessionStorageOrigins" in doc


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
    - 本机路径字符串（兼容旧用法；推荐改为 profiles 内嵌 JSON）
    - Playwright storage_state JSON 对象 / JSON 字符串（可含 sessionStorageOrigins）
    空值返回 None。
    """
    val = _extract_plain(raw)
    if val is None or val == "":
        return None
    if isinstance(val, dict):
        text = json.dumps(val, ensure_ascii=False)
        if len(text) > MAX_STORAGE_STATE_CHARS:
            raise ValueError("storage_state JSON 过大")
        if not _has_storage_payload(val) and not (
            "cookies" in val or "origins" in val or "sessionStorageOrigins" in val
        ):
            raise ValueError("storage_state 对象须包含 cookies、origins 或 sessionStorageOrigins")
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
            if not (
                "cookies" in parsed
                or "origins" in parsed
                or "sessionStorageOrigins" in parsed
            ):
                raise ValueError("storage_state 对象须包含 cookies、origins 或 sessionStorageOrigins")
            return parsed
        # 路径：禁止明显危险字符
        if "\n" in text or "\r" in text:
            raise ValueError("storage_state 路径不能包含换行")
        if len(text) > 1000:
            raise ValueError("storage_state 路径过长")
        return text
    raise ValueError("storage_state 须为路径字符串或 JSON 对象")


def merge_storage_state_documents(docs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """合并多份 storage_state（多站点 Cookie / LS / SS 可共存于同一 BrowserContext）。"""
    cookies: List[Any] = []
    origins_map: Dict[str, Dict[str, str]] = {}
    ss_map: Dict[str, Dict[str, str]] = {}

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        for c in doc.get("cookies") or []:
            if isinstance(c, dict) and str(c.get("name") or "").strip():
                cookies.append(dict(c))
        for o in doc.get("origins") or []:
            if not isinstance(o, dict):
                continue
            origin = str(o.get("origin") or "").strip()
            if not origin:
                continue
            bag = origins_map.setdefault(origin, {})
            items = o.get("localStorage")
            if items is None:
                items = o.get("local_storage")
            if isinstance(items, list):
                for ent in items:
                    if isinstance(ent, dict):
                        name = str(ent.get("name") or ent.get("key") or "").strip()
                        if name:
                            bag[name] = "" if ent.get("value") is None else str(ent.get("value"))
            elif isinstance(items, dict):
                for k, v in items.items():
                    name = str(k or "").strip()
                    if name:
                        bag[name] = "" if v is None else str(v)
        ss_raw = doc.get("sessionStorageOrigins")
        if ss_raw is None:
            ss_raw = doc.get("session_storage_origins")
        if isinstance(ss_raw, list):
            for item in ss_raw:
                if not isinstance(item, dict):
                    continue
                origin = str(item.get("origin") or "").strip()
                if not origin:
                    continue
                bag = ss_map.setdefault(origin, {})
                entries = item.get("sessionStorage")
                if entries is None:
                    entries = item.get("session_storage")
                if isinstance(entries, list):
                    for ent in entries:
                        if isinstance(ent, dict):
                            name = str(ent.get("name") or ent.get("key") or "").strip()
                            if name:
                                bag[name] = (
                                    "" if ent.get("value") is None else str(ent.get("value"))
                                )
                elif isinstance(entries, dict):
                    for k, v in entries.items():
                        name = str(k or "").strip()
                        if name:
                            bag[name] = "" if v is None else str(v)

    if not cookies and not origins_map and not ss_map:
        return None

    out: Dict[str, Any] = {
        "cookies": cookies,
        "origins": [
            {
                "origin": origin,
                "localStorage": [{"name": k, "value": v} for k, v in bag.items()],
            }
            for origin, bag in origins_map.items()
            if bag
        ],
    }
    if ss_map:
        out["sessionStorageOrigins"] = [
            {
                "origin": origin,
                "sessionStorage": [{"name": k, "value": v} for k, v in bag.items()],
            }
            for origin, bag in ss_map.items()
            if bag
        ]
    text = json.dumps(out, ensure_ascii=False)
    if len(text) > MAX_STORAGE_STATE_CHARS:
        raise ValueError(
            f"合并后的登录态过大（>{MAX_STORAGE_STATE_CHARS} 字符），请减少启用的站点配置"
        )
    return out


def normalize_auth_profiles(raw: Any) -> Optional[List[Dict[str, Any]]]:
    """规范化 __ui_auth_profiles；空列表返回 None。"""
    val = _extract_plain(raw)
    if val is None or val == "":
        return None
    if isinstance(val, str):
        text = val.strip()
        if not text:
            return None
        try:
            val = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("登录态配置列表须为 JSON 数组") from exc
    if not isinstance(val, list):
        raise ValueError("登录态配置列表须为数组")
    if len(val) > MAX_AUTH_PROFILES:
        raise ValueError(f"登录态配置最多 {MAX_AUTH_PROFILES} 条")

    out: List[Dict[str, Any]] = []
    for item in val:
        if not isinstance(item, dict):
            raise ValueError("登录态配置每项须为对象")
        name = str(item.get("name") or "").strip() or "未命名"
        if len(name) > MAX_PROFILE_NAME_LEN:
            raise ValueError(f"登录态名称过长（≤{MAX_PROFILE_NAME_LEN}）")
        enabled = bool(item.get("enabled", True))
        host_hint = str(item.get("host_hint") or item.get("match_host") or "").strip()
        if len(host_hint) > MAX_HOST_HINT_LEN:
            raise ValueError("站点提示过长")
        note = str(item.get("note") or "").strip()
        if len(note) > 500:
            raise ValueError("备注过长")
        state = normalize_storage_state(item.get("storage_state"))
        if state is None:
            # 允许暂存空配置（仅名称），保存时仍占位；下发时跳过
            state = {"cookies": [], "origins": []}
        if isinstance(state, str):
            raise ValueError(
                f"登录态「{name}」请导入 JSON 内容，不要填执行机本机路径（换机器无法使用）"
            )
        entry: Dict[str, Any] = {
            "name": name,
            "enabled": enabled,
            "storage_state": state,
        }
        if host_hint:
            entry["host_hint"] = host_hint
        if note:
            entry["note"] = note
        out.append(entry)

    return out or None


def normalize_auth_enabled(raw: Any) -> Optional[bool]:
    """规范化 __ui_auth_enabled；None 表示未显式配置（兼容旧数据按「有配置即启用」）。"""
    val = _extract_plain(raw)
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        text = val.strip().lower()
        if text in ("1", "true", "yes", "on"):
            return True
        if text in ("0", "false", "no", "off"):
            return False
        raise ValueError("启动登录态总开关须为布尔值")
    raise ValueError("启动登录态总开关须为布尔值")


def is_ui_auth_master_enabled(global_vars: dict | None) -> bool:
    """总开关是否开启：显式 false 为关；未配置时有任意登录态数据则视为开。"""
    gv = global_vars if isinstance(global_vars, dict) else {}
    try:
        flag = normalize_auth_enabled(gv.get(UI_AUTH_ENABLED_KEY))
    except ValueError:
        flag = None
    if flag is False:
        return False
    if flag is True:
        return True
    # 兼容：无总开关键时，有配置即启用
    if parse_ui_auth_inject(gv):
        return True
    if parse_ui_auth_profiles(gv):
        return True
    if parse_ui_storage_state(gv) not in (None, ""):
        return True
    return False


def normalize_ui_auth_inject_value(key: str, raw: Any) -> Any:
    """normalize_global_vars 用：返回应写入的值，或 None 表示删除该键。"""
    if key == UI_AUTH_INJECT_KEY:
        return normalize_auth_inject(raw)
    if key == UI_STORAGE_STATE_KEY:
        return normalize_storage_state(raw)
    if key == UI_AUTH_PROFILES_KEY:
        return normalize_auth_profiles(raw)
    if key == UI_AUTH_ENABLED_KEY:
        return normalize_auth_enabled(raw)
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


def parse_ui_auth_profiles(global_vars: dict | None) -> Optional[List[Dict[str, Any]]]:
    gv = global_vars if isinstance(global_vars, dict) else {}
    try:
        return normalize_auth_profiles(gv.get(UI_AUTH_PROFILES_KEY))
    except ValueError:
        return None


def resolve_effective_storage_state(global_vars: dict | None) -> Optional[Any]:
    """
    下发给 Runner 的有效 storage_state：
    - 优先合并启用的 __ui_auth_profiles（内嵌 JSON）
    - 再合并旧版 __ui_storage_state 对象
    - 若仅剩本机路径字符串且无 profiles 对象，则保留路径（兼容）
    """
    docs: List[Dict[str, Any]] = []
    path_fallback: Optional[str] = None

    profiles = parse_ui_auth_profiles(global_vars) or []
    for p in profiles:
        if not p.get("enabled", True):
            continue
        state = p.get("storage_state")
        if isinstance(state, dict) and _has_storage_payload(state):
            # 跳过完全空的 cookies/origins/ss
            has_data = bool(state.get("cookies")) or bool(state.get("origins"))
            ss = state.get("sessionStorageOrigins") or state.get("session_storage_origins")
            has_data = has_data or bool(ss)
            if has_data:
                docs.append(state)

    legacy = parse_ui_storage_state(global_vars)
    if isinstance(legacy, dict):
        # 已有启用 profile 数据时不再合并旧对象，避免双份 Cookie
        if not docs:
            docs.append(legacy)
    elif isinstance(legacy, str):
        path_fallback = legacy

    if docs:
        return merge_storage_state_documents(docs)
    return path_fallback


def build_ui_auth_inject_payload(global_vars: dict | None) -> Dict[str, Any]:
    """构建下发给 Runner 的登录态字段（始终带键，便于 Runner 统一处理）。

    总开关关闭时仍保留环境内配置，但下发为 None（不注入）。
    """
    if not is_ui_auth_master_enabled(global_vars):
        return {
            "ui_auth_inject": None,
            "ui_storage_state": None,
        }
    inject = parse_ui_auth_inject(global_vars)
    storage = resolve_effective_storage_state(global_vars)
    return {
        "ui_auth_inject": inject,
        "ui_storage_state": storage,
    }
