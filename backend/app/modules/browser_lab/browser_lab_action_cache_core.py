"""BL-1 动作缓存纯函数内核：键归一化、动作抽取、终态断言、脱敏。

不依赖 DB / Playwright，便于单测与 Phase 0 独立验收。
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.modules.browser_lab.browser_lab_import import (
    _CLICK_KEYS,
    _INPUT_KEYS,
    _KEYS_KEYS,
    _NAV_KEYS,
    _SCROLL_KEYS,
    _SKIP_ACTION_KEYS,
    _WAIT_KEYS,
    _extract_label,
    _parse_element_index,
    _unwrap_action,
)

SCHEMA_VERSION = 1

_VAR_RE = re.compile(
    r"\$\{\{\s*([A-Za-z_][\w.]*)\s*\}\}|\$\{\s*([A-Za-z_][\w.]*)\s*\}"
)
_NUMERIC_SEG_RE = re.compile(r"^\d+$")
_UUID_SEG_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_HEX_LONG_RE = re.compile(r"^[0-9a-fA-F]{16,}$")
_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|credential|auth|密码|口令)",
    re.I,
)
_SELECT_KEYS = frozenset({"select_dropdown", "select_option", "select", "dropdown"})
ALLOWED_CACHE_OPS = frozenset(
    {"click", "fill", "select", "navigate", "wait", "scroll", "press"}
)


def normalize_task_text(task_text: str) -> str:
    return re.sub(r"\s+", " ", (task_text or "").strip())


def normalize_tags(tags: str | list[str] | None) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, list):
        parts = [str(t).strip() for t in tags]
    else:
        parts = re.split(r"[,，;/|]+", str(tags))
    cleaned = sorted({p.strip().lower() for p in parts if p and p.strip()})
    return cleaned


def _template_path_segment(seg: str) -> str:
    raw = seg.strip()
    if not raw:
        return raw
    if _NUMERIC_SEG_RE.match(raw) or _UUID_SEG_RE.match(raw) or _HEX_LONG_RE.match(raw):
        return ":id"
    return raw


def normalize_start_url(url: str, *, ignore_query: bool = False) -> str:
    """归一化起始 URL：去 fragment；数字/UUID path 段 → :id；可选忽略 query。"""
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "https").lower()
    netloc = (parsed.netloc or "").lower()
    path_parts = [_template_path_segment(p) for p in parsed.path.split("/")]
    path = "/".join(path_parts) or "/"
    if ignore_query:
        query = ""
    else:
        pairs = []
        for k, v in parse_qsl(parsed.query, keep_blank_values=True):
            key = (k or "").strip()
            if not key:
                continue
            val = v or ""
            if _NUMERIC_SEG_RE.match(val) or _UUID_SEG_RE.match(val) or _HEX_LONG_RE.match(val):
                val = ":id"
            pairs.append((key, val))
        pairs.sort(key=lambda x: (x[0], x[1]))
        query = urlencode(pairs)
    return urlunparse((scheme, netloc, path, "", query, ""))


def extract_variable_keys(task_text: str) -> list[str]:
    keys: set[str] = set()
    for m in _VAR_RE.finditer(task_text or ""):
        name = m.group(1) or m.group(2)
        if name:
            keys.add(name)
    return sorted(keys)


def apply_browser_lab_variables(text: str, variables: dict | None) -> str:
    """用项目/环境变量替换 ${{name}} / ${name}，未命中的占位符原样保留。"""
    if not text:
        return ""
    if not variables:
        return text
    from app.core.case.variable_resolver import VariableResolver

    return VariableResolver(variables).replace_in_string(text)


def stringify_runtime_variables(variables: dict | None) -> dict[str, Any]:
    """回放 fill 用：去掉内部键，值转成可填入的标量。"""
    out: dict[str, Any] = {}
    for key, value in (variables or {}).items():
        name = str(key or "").strip()
        if not name or name.startswith("_"):
            continue
        if value is None or isinstance(value, (dict, list)):
            continue
        out[name] = value
    return out


def build_config_fingerprint(
    *,
    ai_config_id: int | None = None,
    use_vision: bool | None = None,
    max_steps: int | None = None,
    model: str | None = None,
) -> str:
    payload = {
        "ai_config_id": ai_config_id,
        "use_vision": bool(use_vision) if use_vision is not None else None,
        "max_steps": max_steps,
        "model": (model or "").strip() or None,
        "schema_version": SCHEMA_VERSION,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_cache_key(
    *,
    project_id: int,
    case_id: int | None,
    start_url: str,
    task_text: str,
    tags: str | list[str] | None = None,
    variable_keys: list[str] | None = None,
    ignore_query: bool = False,
    schema_version: int = SCHEMA_VERSION,
) -> str:
    payload = {
        "project_id": int(project_id),
        "case_id": int(case_id) if case_id is not None else None,
        "tags": normalize_tags(tags),
        "start_url": normalize_start_url(start_url, ignore_query=ignore_query),
        "task_text": normalize_task_text(task_text),
        "variable_keys": sorted(variable_keys or extract_variable_keys(task_text)),
        "schema_version": int(schema_version),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_sensitive_key(name: str) -> bool:
    return bool(_SENSITIVE_KEY_RE.search(name or ""))


def mask_sensitive_value(value: Any, *, key_hint: str = "") -> Any:
    if is_sensitive_key(key_hint):
        return "***"
    if isinstance(value, str):
        if is_sensitive_key(value):
            return "***"
        return value
    if isinstance(value, dict):
        return {k: mask_sensitive_value(v, key_hint=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_sensitive_value(v, key_hint=key_hint) for v in value]
    return value


def _payload_selector(payload: dict) -> str:
    for key in (
        "xpath",
        "selector",
        "css_selector",
        "locator",
        "element",
        "css",
        "query_selector",
    ):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    for key in ("label", "aria_label", "accessible_name", "name", "text", "placeholder"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip() and key != "text":
            safe = val.strip().replace('"', "")
            if key in ("label", "aria_label", "accessible_name", "placeholder"):
                return f'get_by_label={safe}'
            return f'get_by_text={safe}'
    return ""


_ACTION_VERB_RE = re.compile(
    r"^(?:请)?(?:点击|输入|选择|打开|提交|登录|搜索|进入|跳转|切换|关闭|滚动|等待|填写|选中|勾选)"
    r"|^(?:then|click|type|select|open|submit|login|search|enter|go to|navigate)\s*",
    re.I,
)
_ALLOWED_ACTION_KEYS = frozenset(
    {
        "op",
        "selector",
        "value",
        "value_from",
        "url",
        "timeout_ms",
        "strength",
        "option_selector",
        "key",
        "y",
        "new_tab",
        "fallbacks",
        "element_index",
        "repeat_collapsed",
        "sensitive",
    }
)


def _sanitize_goal_label(goal: str, *, max_len: int = 20) -> str:
    """从 next_goal 抽可用文案：去掉动作词前缀，截断到从句，避免整句当 get_by_text。"""
    raw = (goal or "").strip()
    if not raw:
        return ""
    label = _extract_label(raw)
    text = (label or raw).strip()
    text = _ACTION_VERB_RE.sub("", text).strip(" ，,。.;；:：、")
    text = re.split(r"[，,。.;；:：、]|然后|再去|并且|并|且|之后", text, maxsplit=1)[0].strip()
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 2:
        return ""
    return text[:max_len].replace('"', "")


def _resolve_selector(goal: str, payload: dict) -> tuple[str, str]:
    """返回 (selector, strength)。strength: strong | heuristic | weak。"""
    direct = _payload_selector(payload)
    if direct:
        strength = "strong"
        if direct.startswith("get_by_"):
            strength = "heuristic"
        return direct, strength
    short = _sanitize_goal_label(goal, max_len=20)
    if short:
        return f"get_by_text={short}", "heuristic"
    return "", "weak"


def _looks_sensitive_fill(goal: str, payload: dict) -> bool:
    """只看字段自身文案，不因任务里另有 password 变量就把用户名也当敏感。"""
    hints = [
        goal,
        str(payload.get("label") or ""),
        str(payload.get("name") or ""),
        str(payload.get("placeholder") or ""),
        str(payload.get("aria_label") or ""),
    ]
    return any(is_sensitive_key(h) for h in hints if h)


def _value_ref_or_literal(
    text: Any,
    variable_keys: list[str],
    *,
    goal: str = "",
    payload: dict | None = None,
) -> tuple[str | None, Any, bool]:
    """返回 (value_from, literal, sensitive)。

    敏感填值：优先 var:xxx；没有变量引用则不落明文（literal=None, sensitive=True）。
    """
    raw = "" if text is None else str(text)
    for key in variable_keys:
        patterns = (f"${{{{{key}}}}}", f"${{{key}}}")
        if raw in patterns or raw.strip() in patterns:
            return f"var:{key}", None, is_sensitive_key(key)
    payload = payload or {}
    sensitive = _looks_sensitive_fill(goal, payload)
    if sensitive:
        for key in variable_keys:
            if is_sensitive_key(key):
                return f"var:{key}", None, True
        return None, None, True
    return None, raw, False


def _action_dedupe_key(action: dict) -> str:
    return json.dumps(
        {
            "op": action.get("op"),
            "selector": action.get("selector"),
            "url": action.get("url"),
            "value_from": action.get("value_from"),
            "value": action.get("value") if not action.get("value_from") else None,
            "key": action.get("key"),
            "y": action.get("y"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def compress_repeated_actions(actions: list[dict]) -> list[dict]:
    """连续相同动作压缩为一次（SPA 重复点击/输入）。"""
    out: list[dict] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        if out and _action_dedupe_key(out[-1]) == _action_dedupe_key(action):
            out[-1]["repeat_collapsed"] = int(out[-1].get("repeat_collapsed") or 1) + 1
            continue
        item = dict(action)
        item.setdefault("repeat_collapsed", 1)
        out.append(item)
    return out


def _convert_action_to_cache(
    action_key: str,
    payload: dict,
    *,
    goal: str,
    last_url: str,
    variable_keys: list[str],
    include_weak: bool,
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
        return [
            {
                "op": "navigate",
                "url": url,
                "new_tab": bool(payload.get("new_tab")),
                "strength": "strong",
                "timeout_ms": 30000,
            }
        ], url

    if key in _WAIT_KEYS:
        seconds = payload.get("seconds") or payload.get("time") or payload.get("duration") or 2
        try:
            ms = int(float(seconds) * 1000)
        except (TypeError, ValueError):
            ms = 2000
        ms = max(500, min(ms, 60000))
        return [{"op": "wait", "timeout_ms": ms, "strength": "strong"}], last_url

    if key in _SCROLL_KEYS:
        down = payload.get("down")
        y = 400 if down is not False else -400
        if key == "scroll_up":
            y = -400
        return [{"op": "scroll", "y": y, "strength": "strong"}], last_url

    if key in _KEYS_KEYS:
        key_name = payload.get("key") or payload.get("keys") or "Enter"
        return [{"op": "press", "key": str(key_name), "strength": "strong"}], last_url

    if key in _CLICK_KEYS:
        selector, strength = _resolve_selector(goal, payload)
        element_index = _parse_element_index(payload)
        if not selector:
            if not include_weak or element_index is None:
                return [], last_url
            return [
                {
                    "op": "click",
                    "selector": "",
                    "element_index": element_index,
                    "strength": "weak",
                    "timeout_ms": 15000,
                }
            ], last_url
        item: dict[str, Any] = {
            "op": "click",
            "selector": selector,
            "strength": strength,
            "timeout_ms": 15000,
            "fallbacks": [],
        }
        if element_index is not None and strength != "strong":
            item["element_index"] = element_index
        return [item], last_url

    if key in _INPUT_KEYS or key in _SELECT_KEYS:
        text = payload.get("text") or payload.get("value") or payload.get("content") or ""
        selector, strength = _resolve_selector(goal, payload)
        element_index = _parse_element_index(payload)
        value_from, literal, sensitive = _value_ref_or_literal(
            text, variable_keys, goal=goal, payload=payload
        )
        # 敏感且无变量引用：不入缓存（避免明文密码落库）
        if sensitive and not value_from:
            return [], last_url
        if not selector:
            if not include_weak or element_index is None:
                return [], last_url
            item = {
                "op": "fill" if key in _INPUT_KEYS else "select",
                "selector": "",
                "element_index": element_index,
                "strength": "weak",
                "timeout_ms": 15000,
            }
            if value_from:
                item["value_from"] = value_from
            elif literal is not None:
                item["value"] = literal
            if sensitive:
                item["sensitive"] = True
            return [item], last_url
        item = {
            "op": "fill" if key in _INPUT_KEYS else "select",
            "selector": selector,
            "strength": strength,
            "timeout_ms": 15000,
            "fallbacks": [],
        }
        if value_from:
            item["value_from"] = value_from
        elif literal is not None:
            item["value"] = literal
        if sensitive:
            item["sensitive"] = True
        # 自定义下拉：若 payload 带选项定位则一并保存
        for opt_key in ("option_selector", "option_locator", "option_label"):
            opt_val = payload.get(opt_key)
            if isinstance(opt_val, str) and opt_val.strip():
                item["option_selector"] = (
                    opt_val.strip()
                    if opt_key != "option_label"
                    else f"get_by_text={opt_val.strip()[:40]}"
                )
                break
        if element_index is not None and strength != "strong":
            item["element_index"] = element_index
        if key in _SELECT_KEYS and not item.get("option_selector"):
            raw_opt = str(
                payload.get("option_text")
                or payload.get("option")
                or payload.get("text")
                or payload.get("value")
                or payload.get("content")
                or ""
            ).strip()
            if raw_opt and not raw_opt.startswith(("${{", "${")):
                item["option_selector"] = f"get_by_text={raw_opt[:40]}"
        return [item], last_url

    return [], last_url


def extract_cacheable_actions(
    step_log: list | None,
    *,
    include_weak: bool = False,
    compress: bool = True,
    task_text: str = "",
) -> list[dict]:
    """从 step_log 抽取可确定性回放的动作。

    优先 CSS / label / text；索引-only 默认跳过（include_weak=True 才保留）。
    跳过 cache_replay 事件，避免回放失败降级后把回放步骤写进新缓存。
    """
    events = [e for e in (step_log or []) if isinstance(e, dict) and e.get("type") == "step"]
    actions: list[dict] = []
    last_url = ""
    variable_keys = extract_variable_keys(task_text)
    for event in events:
        if event.get("cache_replay"):
            # 只同步 URL，不生成动作：降级 Agent 后的 navigate 去重才不会丢第一步
            url = (event.get("url") or "").strip()
            if url:
                last_url = url
            continue
        idx = event.get("index")
        if idx in (0, None):
            continue
        goal = (event.get("next_goal") or event.get("thinking") or "").strip()
        for raw in event.get("actions") or []:
            if not isinstance(raw, dict):
                continue
            action_key, payload = _unwrap_action(raw)
            converted, last_url = _convert_action_to_cache(
                action_key,
                payload,
                goal=goal,
                last_url=last_url,
                variable_keys=variable_keys,
                include_weak=include_weak,
            )
            # 敏感填值被跳过则整段不缓存，避免「没填密码却点登录」的半截回放
            if not converted and (action_key or "").lower() in _INPUT_KEYS | _SELECT_KEYS:
                value_from, _literal, sensitive = _value_ref_or_literal(
                    (payload or {}).get("text")
                    or (payload or {}).get("value")
                    or (payload or {}).get("content")
                    or "",
                    variable_keys,
                    goal=goal,
                    payload=payload or {},
                )
                if sensitive and not value_from:
                    return []
            actions.extend(converted)
    if compress:
        actions = compress_repeated_actions(actions)
    return actions


def extract_final_assertions(step_log: list | None, *, start_url: str = "") -> dict[str, Any]:
    """终态断言：回放结束必须校验，避免「点成功但业务失败」静默错误。"""
    events = [e for e in (step_log or []) if isinstance(e, dict)]
    steps = [
        e
        for e in events
        if e.get("type") == "step"
        and e.get("index") not in (0, None)
        and not e.get("cache_replay")
    ]
    last = steps[-1] if steps else {}
    final_url = (last.get("url") or "").strip()
    title = (last.get("title") or "").strip()

    assertions: dict[str, Any] = {
        "final_url_template": normalize_start_url(final_url) if final_url else "",
        "title_contains": title[:80] if title else "",
        "text_contains": [],
        "require_final_url": bool(final_url),
        "start_url_template": normalize_start_url(start_url) if start_url else "",
    }
    return assertions


def unresolved_value_from_keys(actions: list | None, variables: dict | None = None) -> list[str]:
    """回放前检查：value_from=var:xxx 在运行时变量表中找不到则不能命中。"""
    variables = variables or {}
    missing: list[str] = []
    seen: set[str] = set()
    for action in actions or []:
        if not isinstance(action, dict):
            continue
        value_from = action.get("value_from")
        if isinstance(value_from, str) and value_from.startswith("var:"):
            key = value_from[4:]
            if key and key not in variables and key not in seen:
                seen.add(key)
                missing.append(key)
    return missing


def assertions_are_usable(assertions: dict | None) -> bool:
    if not isinstance(assertions, dict):
        return False
    if assertions.get("require_final_url") and assertions.get("final_url_template"):
        return True
    if (assertions.get("title_contains") or "").strip():
        return True
    texts = [t for t in (assertions.get("text_contains") or []) if str(t).strip() and not str(t).startswith("_")]
    if texts:
        return True
    return False


def sanitize_assertions_for_api(assertions: dict | None) -> dict:
    if not isinstance(assertions, dict):
        return {}
    return {k: v for k, v in assertions.items() if not str(k).startswith("_")}


def normalize_patch_action(action: dict | None) -> dict:
    """PATCH 缓存动作：只允许白名单 op/字段，避免注入任意 payload。"""
    if not isinstance(action, dict):
        raise ValueError("action 须为对象")
    op = (action.get("op") or "").strip().lower()
    if op not in ALLOWED_CACHE_OPS:
        raise ValueError(f"不支持的 op: {op or '(空)'}")
    cleaned = {k: action[k] for k in _ALLOWED_ACTION_KEYS if k in action}
    cleaned["op"] = op
    if op in ("click", "fill", "select") and not str(cleaned.get("selector") or "").strip():
        raise ValueError(f"{op} 须提供 selector")
    if op == "navigate":
        url = str(cleaned.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError("navigate.url 须以 http:// 或 https:// 开头")
        cleaned["url"] = url
    if cleaned.get("sensitive") and "value" in cleaned and not cleaned.get("value_from"):
        cleaned.pop("value", None)
    return cleaned


def sanitize_actions_for_api(actions: list | None) -> list:
    out = []
    for action in actions or []:
        if not isinstance(action, dict):
            continue
        item = dict(action)
        if "value" in item and "value_from" not in item:
            # 明文 fill/select 值在详情接口一律脱敏
            item["value"] = "***"
        if isinstance(item.get("options"), (list, dict)):
            item["options"] = mask_sensitive_value(item["options"], key_hint="options")
        out.append(item)
    return out


def urls_match_template(actual_url: str, template_url: str) -> bool:
    if not template_url:
        return True
    a = normalize_start_url(actual_url)
    b = normalize_start_url(template_url)
    if a == b:
        return True
    # 模板两侧都按 :id 归一后比较
    return a == b
