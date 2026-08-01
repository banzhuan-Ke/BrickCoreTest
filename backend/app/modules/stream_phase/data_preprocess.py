"""SSE 规则解析 — 通用数据预处理（解包嵌套 JSON / Patch 累积）。

与 runner/tools/stream_phase/data_preprocess.py 保持同步（仅允许模块 docstring 差异）。

不绑定任何厂商协议：通过 rules.preprocess[] 配置步骤，公司改输出规范时只改规则即可。
"""
from __future__ import annotations

import copy
import json
from typing import Any, Optional

try:
    from jsonpath_ng import parse as jsonpath_parse
except ImportError:  # pragma: no cover
    jsonpath_parse = None  # type: ignore


def jsonpath_get(obj: Any, path: str) -> Any:
    """取 JSONPath 第一个匹配值；失败返回 None。"""
    p = (path or "").strip()
    if not p or obj is None:
        return None
    if jsonpath_parse is None:
        return None
    try:
        matches = jsonpath_parse(p).find(obj)
    except Exception:
        return None
    if not matches:
        return None
    return matches[0].value


def jsonpath_get_str(obj: Any, path: str) -> str:
    v = jsonpath_get(obj, path)
    if v is None:
        return ""
    return v if isinstance(v, str) else str(v)


class PreprocessState:
    """跨帧预处理状态（Patch 文档、游标、path 文本快照）。"""

    def __init__(self) -> None:
        self.doc: dict[str, Any] = {}
        self.cursor_path: Optional[str] = None
        self.cursor_op: Optional[str] = None
        self.path_text_prev: dict[str, str] = {}
        self.last_views: list[dict[str, Any]] = []


def _resolve_index(seq: list, idx: int) -> int:
    if idx < 0:
        return len(seq) + idx
    return idx


def _ensure_container(parent: Any, key: str, *, prefer_list: bool = False) -> Any:
    if isinstance(parent, dict):
        if key not in parent or parent[key] is None:
            parent[key] = [] if prefer_list else {}
        return parent[key]
    return parent


def _navigate_to_parent(doc: dict[str, Any], path: str) -> tuple[Any, Any]:
    """沿 path 导航到父节点与最终 key/index。path 形如 response/fragments/-1/content。"""
    parts = [p for p in str(path or "").split("/") if p != ""]
    if not parts:
        return doc, None
    cur: Any = doc
    for i, part in enumerate(parts[:-1]):
        is_last_mid = i == len(parts) - 2
        next_part = parts[i + 1]
        next_is_index = next_part.lstrip("-").isdigit()
        if part.lstrip("-").isdigit():
            if not isinstance(cur, list):
                return None, None
            idx = _resolve_index(cur, int(part))
            if idx < 0 or idx >= len(cur):
                return None, None
            cur = cur[idx]
        else:
            prefer_list = next_is_index
            if not isinstance(cur, dict):
                return None, None
            if part not in cur or cur[part] is None:
                cur[part] = [] if prefer_list else {}
            elif prefer_list and not isinstance(cur[part], list):
                cur[part] = []
            elif not prefer_list and not isinstance(cur[part], (dict, list)):
                cur[part] = {}
            cur = cur[part]
        # silence unused
        _ = is_last_mid
    return cur, parts[-1]


def _get_at_path(doc: dict[str, Any], path: str) -> Any:
    parent, last = _navigate_to_parent(doc, path)
    if parent is None or last is None:
        return None
    if last.lstrip("-").isdigit():
        if not isinstance(parent, list):
            return None
        idx = _resolve_index(parent, int(last))
        if idx < 0 or idx >= len(parent):
            return None
        return parent[idx]
    if not isinstance(parent, dict):
        return None
    return parent.get(last)


def _set_at_path(doc: dict[str, Any], path: str, value: Any) -> None:
    parent, last = _navigate_to_parent(doc, path)
    if parent is None or last is None:
        if not path:
            if isinstance(value, dict):
                doc.clear()
                doc.update(value)
        return
    if last.lstrip("-").isdigit():
        if not isinstance(parent, list):
            return
        idx = _resolve_index(parent, int(last))
        if idx < 0:
            return
        while len(parent) <= idx:
            parent.append(None)
        parent[idx] = value
        return
    if isinstance(parent, dict):
        parent[last] = value


def _append_at_path(doc: dict[str, Any], path: str, value: Any) -> str:
    """APPEND：字符串拼接或数组 append。返回本帧 text_delta（仅字符串时有值）。"""
    parent, last = _navigate_to_parent(doc, path)
    if parent is None or last is None:
        return ""
    if last.lstrip("-").isdigit():
        if not isinstance(parent, list):
            return ""
        idx = _resolve_index(parent, int(last))
        if idx < 0 or idx >= len(parent):
            return ""
        cur = parent[idx]
        if isinstance(cur, str) or cur is None:
            delta = "" if value is None else str(value)
            parent[idx] = (cur or "") + delta
            return delta
        if isinstance(cur, list):
            cur.append(value)
            return ""
        return ""
    if not isinstance(parent, dict):
        return ""
    cur = parent.get(last)
    if isinstance(value, list) and (cur is None or isinstance(cur, list)):
        if cur is None:
            parent[last] = []
            cur = parent[last]
        if isinstance(cur, list):
            cur.extend(value)
        return ""
    if isinstance(cur, list):
        cur.append(value)
        return ""
    delta = "" if value is None else str(value)
    parent[last] = ("" if cur is None else str(cur)) + delta
    return delta


def _apply_one_patch(doc: dict[str, Any], patch: dict[str, Any], state: PreprocessState) -> str:
    """应用单条 patch，返回 text_delta。"""
    p = patch.get("p")
    o = (patch.get("o") or "").strip().upper() if patch.get("o") is not None else ""
    v = patch.get("v")

    # 仅 {"v": ...}：续写上一游标，或无 p 时合并对象进 doc
    if p is None or str(p).strip() == "":
        if isinstance(v, dict) and not o:
            # 无 path 的对象：合并到根（常见整包 response）
            for k, val in v.items():
                doc[k] = copy.deepcopy(val)
            state.cursor_path = None
            state.cursor_op = None
            return ""
        if state.cursor_path and (state.cursor_op or "APPEND") == "APPEND":
            return _append_at_path(doc, state.cursor_path, v)
        return ""

    path = str(p).strip()
    op = o or "SET"
    state.cursor_path = path
    state.cursor_op = op

    if op == "BATCH" and isinstance(v, list):
        delta_parts = []
        for item in v:
            if isinstance(item, dict):
                # BATCH 子项可带相对 p
                sub = dict(item)
                if sub.get("p") and not str(sub.get("p")).startswith("response"):
                    # 相对当前 path 前缀
                    sub_p = str(sub["p"]).lstrip("/")
                    if path:
                        sub["p"] = f"{path}/{sub_p}" if sub_p else path
                d = _apply_one_patch(doc, sub, state)
                if d:
                    delta_parts.append(d)
        # 恢复 BATCH 游标
        state.cursor_path = path
        state.cursor_op = "BATCH"
        return "".join(delta_parts)

    if op == "APPEND":
        return _append_at_path(doc, path, v)

    # SET 及默认
    _set_at_path(doc, path, copy.deepcopy(v))
    if isinstance(v, str):
        return v
    return ""


def _current_fragment_type(doc: dict[str, Any]) -> str:
    frags = None
    resp = doc.get("response")
    if isinstance(resp, dict):
        frags = resp.get("fragments")
    if not isinstance(frags, list) or not frags:
        return ""
    last = frags[-1]
    if isinstance(last, dict):
        return str(last.get("type") or "")
    return ""


def _response_status(doc: dict[str, Any]) -> str:
    resp = doc.get("response")
    if isinstance(resp, dict):
        return str(resp.get("status") or "")
    return ""


def apply_json_patch_step(
    raw: dict[str, Any],
    state: PreprocessState,
    *,
    sse_event: str = "",
) -> dict[str, Any]:
    """通用 p/o/v Patch 步骤 → 合成匹配视图。"""
    text_delta = _apply_one_patch(state.doc, raw, state)
    # 无显式 patch 字段时，整包对象也可能是首次状态
    if not any(k in raw for k in ("p", "o", "v")) and raw:
        for k, val in raw.items():
            if k.startswith("_"):
                continue
            state.doc[k] = copy.deepcopy(val)

    frag_type = _current_fragment_type(state.doc)
    status = _response_status(state.doc)
    view: dict[str, Any] = {
        "sse_event": sse_event or "",
        "fragment_type": frag_type,
        "response_status": status,
        "patch_path": state.cursor_path or "",
        "patch_op": state.cursor_op or "",
        "text_delta": text_delta,
        "delta": text_delta,  # 兼容既有 delta_nonempty
        "_doc": state.doc,
    }
    # 透传本帧原始顶层（便于偶发顶层匹配）
    for k, val in raw.items():
        if k not in view and not str(k).startswith("_"):
            view[k] = val
    return view


def apply_unwrap_json_text(
    raw: dict[str, Any],
    step: dict[str, Any],
    *,
    sse_event: str = "",
) -> dict[str, Any]:
    """按 path 取出嵌套 JSON 字符串并 loads，作为后续匹配上下文。"""
    path = str(step.get("path") or "").strip()
    when_path = str(step.get("when_path") or "").strip()
    when_eq = step.get("when_eq")
    keep_outer = bool(step.get("keep_outer"))

    if when_path:
        actual = jsonpath_get(raw, when_path)
        if when_eq is not None and str(actual) != str(when_eq):
            view = dict(raw)
            view["sse_event"] = sse_event or view.get("sse_event") or ""
            return view

    payload = jsonpath_get(raw, path) if path else None
    inner: Any = None
    if isinstance(payload, str) and payload.strip():
        try:
            inner = json.loads(payload)
        except json.JSONDecodeError:
            inner = None
    elif isinstance(payload, dict):
        inner = payload

    if not isinstance(inner, dict):
        view = dict(raw)
        view["sse_event"] = sse_event or view.get("sse_event") or ""
        return view

    view = dict(inner)
    view["sse_event"] = sse_event or ""
    if keep_outer:
        view["_outer"] = raw
    view["_doc"] = inner
    return view


def _merge_text_grew(view: dict[str, Any], state: PreprocessState) -> None:
    """为视图补充 _path_text 快照，供 text_grew 匹配使用。"""
    # 不在这里自动扫全部 path；text_grew 在 match 时读 state.path_text_prev
    view["_preprocess_state"] = state


def run_preprocess(
    raw: dict[str, Any],
    steps: list[dict[str, Any]] | None,
    state: PreprocessState,
    *,
    sse_event: str = "",
) -> dict[str, Any]:
    """按序执行 preprocess 步骤，返回 match_view。"""
    view: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    view["sse_event"] = sse_event if sse_event is not None else view.get("sse_event") or ""

    for step in steps or []:
        if not isinstance(step, dict):
            continue
        op = str(step.get("op") or step.get("type") or "").strip().lower()
        if op in ("unwrap_json_text", "unwrap"):
            view = apply_unwrap_json_text(view, step, sse_event=view.get("sse_event") or "")
        elif op in ("json_patch", "patch"):
            # Patch 以「当前 view 中的原始 patch 字段」为准；若刚 unwrap 过则用 _doc
            patch_src = raw if any(k in raw for k in ("p", "o", "v")) else view
            if not any(k in patch_src for k in ("p", "o", "v")) and isinstance(view.get("_doc"), dict):
                patch_src = view
            view = apply_json_patch_step(
                patch_src if isinstance(patch_src, dict) else raw,
                state,
                sse_event=view.get("sse_event") or "",
            )
        else:
            continue

    _merge_text_grew(view, state)
    state.last_views.append({k: v for k, v in view.items() if k not in ("_preprocess_state", "_doc", "_outer")})
    if len(state.last_views) > 5:
        state.last_views = state.last_views[-5:]
    return view


# —— 匿名示例模板（可套用后随意改，不绑定厂商）——

EXAMPLE_TEMPLATE_NESTED_JSON = {
    "id": "nested_json",
    "name": "示例：嵌套 JSON 解包",
    "description": "外层 data[].value 为 JSON 字符串时，先解包再按内层字段/文本变长计阶段。",
    "parser_id": "custom_sse",
    "rules": {
        "frame_mode": True,
        "data_prefix": "data:",
        "event_prefix": "event:",
        "id_prefix": "id:",
        "done_markers": ["[DONE]"],
        "done_events": ["done", "close"],
        "preprocess": [
            {
                "op": "unwrap_json_text",
                "path": "$.data[0].value",
                "when_path": "$.data[0].type",
                "when_eq": "JSON_TEXT",
            }
        ],
        "phases": [
            {
                "key": "first_char",
                "label": "首字时间(s)",
                "trigger": "first",
                "match": {
                    "text_grew": {
                        "path": "$.data.messageList[0].contentList[1].content",
                        "min_chars": 1,
                    }
                },
            },
            {
                "key": "answer_done",
                "label": "回答完成(s)",
                "trigger": "first",
                "match": {
                    "path_eq": {
                        "path": "$.data.messageList[0].status",
                        "value": "FINISHED",
                    }
                },
            },
        ],
        "derived": [
            {"key": "answer_streaming", "label": "回答耗时(s)", "expr": "total_time - first_char"},
        ],
        "extras_extract": [
            {
                "key": "answer_preview",
                "label": "答案预览",
                "from": "json_path",
                "path": "$.data.messageList[0].contentList[1].content",
                "trigger": "last",
                "max_len": 500,
            }
        ],
    },
    "success_rule": {"type": "phase_exists", "phase": "first_char"},
}

EXAMPLE_TEMPLATE_JSON_PATCH = {
    "id": "json_patch_stream",
    "name": "示例：JSON Patch 流",
    "description": "data 行为 p/o/v（及仅 v 续写）时，先累积文档再按 fragment_type / 增量文本计阶段。",
    "parser_id": "custom_sse",
    "rules": {
        "frame_mode": True,
        "data_prefix": "data:",
        "event_prefix": "event:",
        "id_prefix": "id:",
        "done_markers": ["[DONE]"],
        "done_events": ["close", "done"],
        "preprocess": [{"op": "json_patch"}],
        "phases": [
            {
                "key": "think_start",
                "label": "思考开始(s)",
                "trigger": "first",
                "match": {"fragment_type": "THINK", "delta_nonempty": True},
            },
            {
                "key": "first_char",
                "label": "首字时间(s)",
                "trigger": "first",
                "match": {"fragment_type": "RESPONSE", "delta_nonempty": True},
            },
            {
                "key": "answer_done",
                "label": "回答完成(s)",
                "trigger": "first",
                "match": {"response_status": "FINISHED"},
            },
        ],
        "derived": [
            {"key": "thinking_duration", "label": "思考耗时(s)", "expr": "first_char - think_start"},
            {"key": "answer_streaming", "label": "回答耗时(s)", "expr": "total_time - first_char"},
        ],
        "extras_extract": [
            {
                "key": "answer_preview",
                "label": "答案预览",
                "from": "text_collect_path",
                "match": {"fragment_type": "RESPONSE"},
                "max_len": 500,
            }
        ],
    },
    "success_rule": {"type": "phase_exists", "phase": "first_char"},
}


def list_example_rule_templates() -> list[dict[str, Any]]:
    return [
        {
            "id": EXAMPLE_TEMPLATE_NESTED_JSON["id"],
            "name": EXAMPLE_TEMPLATE_NESTED_JSON["name"],
            "description": EXAMPLE_TEMPLATE_NESTED_JSON["description"],
            "parser_id": EXAMPLE_TEMPLATE_NESTED_JSON["parser_id"],
            "success_rule": EXAMPLE_TEMPLATE_NESTED_JSON["success_rule"],
            "rules": EXAMPLE_TEMPLATE_NESTED_JSON["rules"],
        },
        {
            "id": EXAMPLE_TEMPLATE_JSON_PATCH["id"],
            "name": EXAMPLE_TEMPLATE_JSON_PATCH["name"],
            "description": EXAMPLE_TEMPLATE_JSON_PATCH["description"],
            "parser_id": EXAMPLE_TEMPLATE_JSON_PATCH["parser_id"],
            "success_rule": EXAMPLE_TEMPLATE_JSON_PATCH["success_rule"],
            "rules": EXAMPLE_TEMPLATE_JSON_PATCH["rules"],
        },
    ]
