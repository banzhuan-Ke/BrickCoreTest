"""规则驱动 SSE 阶段解析器

与 runner/tools/stream_phase/parsers/rule_based.py 保持同步（仅允许 import 路径与模块 docstring 差异）。
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from app.modules.stream_phase.data_preprocess import (
    PreprocessState,
    jsonpath_get,
    jsonpath_get_str,
    run_preprocess,
)
from app.modules.stream_phase.sse_frames import coalesce_sse_frames, frame_match_context
from app.modules.stream_phase.timing import line_elapsed_at, stream_end_elapsed

PARSER_ID = "rule_based"
DISPLAY_NAME = "规则配置"

DEFAULT_RULES = {
    "line_prefix": "data:",
    "done_markers": ["[DONE]", "data:[DONE]"],
    # 默认按 SSE 帧拼包（event/id/data）；false 时退回逐 data 行
    "frame_mode": True,
    # sse_event 命中这些值时记为流结束时刻
    "done_events": ["done"],
    # 可选预处理：unwrap_json_text / json_patch（见 data_preprocess）
    "preprocess": [],
    "phases": [
        {
            "key": "intent_complete",
            "label": "意图完成(s)",
            "match": {"type": "think", "agent": "think", "action": "intent", "status": "success"},
            "trigger": "first",
        },
        {
            "key": "first_char",
            "label": "首字时间(s)",
            "match": {"type": "output_text", "agent": "conventional_summary", "delta_nonempty": True},
            "trigger": "first",
        },
    ],
    "derived": [
        {"key": "thinking_duration", "label": "思考耗时(s)", "expr": "first_char - intent_complete"},
        {"key": "answer_streaming", "label": "回答耗时(s)", "expr": "total_time - first_char"},
    ],
    "extras_extract": [
        {"key": "thread_id", "label": "thread_id", "from": "json_field", "field": "id", "trigger": "first"},
        {
            "key": "reference_files",
            "label": "引用文件",
            "from": "eof_references",
            "match": {"type": "eof", "agent": "conventional_summary"},
            "field": "doc_name",
        },
        {
            "key": "answer_preview",
            "label": "答案预览",
            "from": "answer_collect",
            "agent": "conventional_summary",
            "max_len": 500,
        },
    ],
}

_SPECIAL_MATCH_KEYS = frozenset({
    "delta_nonempty",
    "path_eq",
    "path_nonempty",
    "text_grew",
})


def _build_schema_from_rules(rules: dict) -> list[dict]:
    schema = []
    for p in rules.get("phases") or []:
        schema.append({
            "key": p.get("key"),
            "label": p.get("label") or p.get("key"),
            "unit": "s",
            "aggregate": p.get("aggregate", True),
        })
    for d in rules.get("derived") or []:
        schema.append({
            "key": d.get("key"),
            "label": d.get("label") or d.get("key"),
            "unit": "s",
            "aggregate": d.get("aggregate", True),
        })
    schema.append({"key": "total_time", "label": "整体耗时(s)", "unit": "s", "aggregate": True})
    return [s for s in schema if s.get("key")]


def _doc_root(data: dict[str, Any]) -> Any:
    if isinstance(data.get("_doc"), (dict, list)):
        return data["_doc"]
    return data


def _delta_text(data: dict) -> str:
    for key in ("delta", "text_delta"):
        v = data.get(key, "")
        if v is None:
            continue
        s = str(v)
        if s.strip() and s.strip() != "\n\n":
            return s
    return ""


def _match_path_eq(data: dict, spec: Any) -> bool:
    if not isinstance(spec, dict):
        return False
    path = str(spec.get("path") or "").strip()
    if not path:
        return False
    actual = jsonpath_get(_doc_root(data), path)
    if actual is None:
        actual = jsonpath_get(data, path)
    return str(actual) == str(spec.get("value"))


def _match_path_nonempty(data: dict, spec: Any) -> bool:
    path = ""
    if isinstance(spec, dict):
        path = str(spec.get("path") or "").strip()
    elif isinstance(spec, str):
        path = spec.strip()
    if not path:
        return False
    text = jsonpath_get_str(_doc_root(data), path) or jsonpath_get_str(data, path)
    return bool(text.strip())


def _match_text_grew(data: dict, spec: Any, state: PreprocessState | None) -> bool:
    if not isinstance(spec, dict):
        return False
    path = str(spec.get("path") or "").strip()
    if not path:
        return False
    try:
        min_chars = int(spec.get("min_chars") or 1)
    except (TypeError, ValueError):
        min_chars = 1
    cur = jsonpath_get_str(_doc_root(data), path)
    if cur == "" and path:
        cur = jsonpath_get_str(data, path)
    prev = ""
    if state is not None:
        prev = state.path_text_prev.get(path, "")
    grew = len(cur) - len(prev)
    return grew >= min_chars or (not prev.strip() and len(cur.strip()) >= min_chars)


def _snapshot_text_paths(data: dict, rules: dict, state: PreprocessState | None) -> None:
    """帧处理结束后更新 text_grew / text_collect 相关 path 快照。"""
    if state is None:
        return
    paths: set[str] = set()
    for phase_rule in rules.get("phases") or []:
        m = phase_rule.get("match") or {}
        tg = m.get("text_grew")
        if isinstance(tg, dict) and tg.get("path"):
            paths.add(str(tg["path"]).strip())
    for er in rules.get("extras_extract") or []:
        if er.get("from") == "text_collect_path" and er.get("path"):
            paths.add(str(er["path"]).strip())
    for path in paths:
        if not path:
            continue
        cur = jsonpath_get_str(_doc_root(data), path) or jsonpath_get_str(data, path)
        state.path_text_prev[path] = cur
        state.path_text_prev[f"__collect::{path}"] = cur


def _match_obj(data: dict, match: dict, *, state: PreprocessState | None = None) -> bool:
    for k, v in (match or {}).items():
        if k == "delta_nonempty":
            if v and not _delta_text(data):
                return False
            continue
        if k == "path_eq":
            if not _match_path_eq(data, v):
                return False
            continue
        if k == "path_nonempty":
            if not _match_path_nonempty(data, v):
                return False
            continue
        if k == "text_grew":
            if not _match_text_grew(data, v, state):
                return False
            continue
        if str(data.get(k, "")) != str(v):
            return False
    return True


def _eval_derived(expr: str, phases: dict, total_time: float) -> float | None:
    expr = (expr or "").strip()
    if not expr:
        return None
    ctx = {**phases, "total_time": total_time}
    try:
        if " - " in expr:
            left, right = [p.strip() for p in expr.split(" - ", 1)]
            lv = ctx.get(left)
            rv = ctx.get(right)
            if lv is not None and rv is not None:
                return round(float(lv) - float(rv), 3)
        if expr in ctx and ctx[expr] is not None:
            return round(float(ctx[expr]), 3)
    except (TypeError, ValueError):
        return None
    return None


def _apply_phases_and_extras(
    *,
    data: dict[str, Any],
    elapsed: float,
    rules: dict,
    phases: dict[str, Any],
    extras: dict[str, Any],
    answer_parts: list[str],
    triggered_phases: set,
    triggered_extras: set,
    state: PreprocessState | None = None,
) -> None:
    for phase_rule in rules.get("phases") or []:
        key = phase_rule.get("key")
        if not key:
            continue
        if not _match_obj(data, phase_rule.get("match") or {}, state=state):
            continue
        trigger = str(phase_rule.get("trigger") or "first").strip() or "first"
        if trigger == "last":
            phases[key] = round(elapsed, 3)
            continue
        if key in triggered_phases:
            continue
        phases[key] = round(elapsed, 3)
        triggered_phases.add(key)

    for extra_rule in rules.get("extras_extract") or []:
        key = extra_rule.get("key")
        if not key:
            continue
        src = extra_rule.get("from")
        if src == "json_field" and key not in triggered_extras:
            field = extra_rule.get("field", "id")
            if data.get(field):
                extras[key] = data.get(field)
                triggered_extras.add(key)
        elif src == "eof_references" and _match_obj(data, extra_rule.get("match") or {}, state=state):
            refs = data.get("references") or []
            names = [r.get(extra_rule.get("field", "doc_name")) for r in refs if isinstance(r, dict)]
            names = [n for n in names if n]
            if names:
                extras[key] = "; ".join(set(names))
        elif src == "answer_collect":
            agent = extra_rule.get("agent")
            if agent and data.get("agent") == agent and data.get("type") == "output_text":
                delta = data.get("delta", "")
                if delta and str(delta).strip():
                    answer_parts.append(re.sub(r"\[ref:\d+\]", "", str(delta)))
        elif src == "json_path":
            path = str(extra_rule.get("path") or "").strip()
            if not path:
                continue
            val = jsonpath_get(_doc_root(data), path)
            if val is None:
                val = jsonpath_get(data, path)
            if val is None or val == "":
                continue
            trigger = str(extra_rule.get("trigger") or "first").strip() or "first"
            if trigger == "last":
                extras[key] = val
            elif key not in triggered_extras:
                extras[key] = val
                triggered_extras.add(key)
        elif src == "text_collect_path":
            m = extra_rule.get("match") or {}
            if m and not _match_obj(data, m, state=state):
                continue
            path = str(extra_rule.get("path") or "").strip()
            piece = _delta_text(data)
            if not piece and path:
                cur = jsonpath_get_str(_doc_root(data), path) or jsonpath_get_str(data, path)
                prev_key = f"__collect::{path}"
                prev = state.path_text_prev.get(prev_key, "") if state is not None else ""
                if len(cur) > len(prev):
                    piece = cur[len(prev):]
                elif cur and not prev:
                    piece = cur
            if piece and str(piece).strip():
                answer_parts.append(str(piece))


def _sanitize_view_for_debug(view: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in (view or {}).items():
        if k in ("_preprocess_state",):
            continue
        if k in ("_doc", "_outer"):
            continue
        out[k] = v
    # 附带精简 _doc 键名，便于试解析排错
    doc = view.get("_doc")
    if isinstance(doc, dict):
        out["_doc_keys"] = list(doc.keys())[:40]
        if isinstance(doc.get("response"), dict):
            out["response_status"] = out.get("response_status") or doc["response"].get("status")
    return out


def parse_stream(
    lines: list[str],
    *,
    start_time: float,
    status_code: int = 200,
    options: dict | None = None,
    line_elapsed: list[float] | None = None,
) -> dict[str, Any]:
    rules = dict(DEFAULT_RULES)
    user_rules = (options or {}).get("rules") or {}
    for k, v in user_rules.items():
        rules[k] = v

    line_prefix = rules.get("line_prefix") or "data:"
    done_markers = set(rules.get("done_markers") or ["[DONE]"])
    done_events = {
        str(x).strip().lower()
        for x in (rules.get("done_events") or ["done"])
        if str(x).strip()
    }
    frame_mode = rules.get("frame_mode", True)
    if isinstance(frame_mode, str):
        frame_mode = frame_mode.strip().lower() not in ("0", "false", "no", "off")
    preprocess_steps = rules.get("preprocess") or []
    if not isinstance(preprocess_steps, list):
        preprocess_steps = []
    debug_views = bool((options or {}).get("debug_match_views"))

    phases: dict[str, Any] = {}
    extras: dict[str, Any] = {}
    error = None
    done_time = None
    answer_parts: list[str] = []
    triggered_phases = set()
    triggered_extras = set()
    pp_state = PreprocessState()
    match_view_samples: list[dict[str, Any]] = []

    def _handle_ctx(raw_ctx: dict[str, Any], elapsed: float) -> None:
        nonlocal match_view_samples
        sse_event = raw_ctx.get("sse_event") or ""
        if preprocess_steps:
            view = run_preprocess(
                {k: v for k, v in raw_ctx.items() if k != "sse_event"},
                preprocess_steps,
                pp_state,
                sse_event=str(sse_event),
            )
            # 保留帧级 sse_event / sse_id
            if "sse_id" in raw_ctx:
                view["sse_id"] = raw_ctx["sse_id"]
            view["sse_event"] = str(sse_event)
        else:
            view = raw_ctx
        if debug_views and len(match_view_samples) < 12:
            sample = _sanitize_view_for_debug(view)
            sample["_elapsed"] = round(elapsed, 3)
            match_view_samples.append(sample)
        _apply_phases_and_extras(
            data=view,
            elapsed=elapsed,
            rules=rules,
            phases=phases,
            extras=extras,
            answer_parts=answer_parts,
            triggered_phases=triggered_phases,
            triggered_extras=triggered_extras,
            state=pp_state,
        )
        _snapshot_text_paths(view, rules, pp_state)

    if frame_mode:
        frames = coalesce_sse_frames(
            lines,
            line_elapsed=line_elapsed,
            start_time=start_time,
            data_prefix=rules.get("data_prefix") or "data:",
            event_prefix=rules.get("event_prefix") or "event:",
            id_prefix=rules.get("id_prefix") or "id:",
        )
        data_pfx = str(rules.get("data_prefix") or "data:")
        for frame in frames:
            elapsed = float(frame.get("elapsed") or 0.0)
            data_raw = (frame.get("data_raw") or "").strip()
            if (
                data_raw in done_markers
                or f"{data_pfx}{data_raw}" in done_markers
                or f"data:{data_raw}" in done_markers
            ):
                done_time = elapsed
                continue
            sse_event = frame.get("event")
            if sse_event is not None and str(sse_event).strip().lower() in done_events:
                done_time = elapsed
            data_obj = frame.get("data_obj")
            if data_obj is None and data_raw and data_raw[0] not in ("{", "["):
                error = f"服务器返回错误: {data_raw}"
                continue
            if not isinstance(data_obj, dict):
                # 有 data 但 JSON 解析失败：勿当成空对象，避免仅 sse_event 误命中
                if data_raw:
                    continue
                # 无 data 的纯 event 帧（如 close）也参与匹配
                if sse_event is None:
                    continue
                data_obj = {}
            ctx = frame_match_context({**frame, "data_obj": data_obj})
            _handle_ctx(ctx, elapsed)
    else:
        for idx, line in enumerate(lines):
            if not line:
                continue
            elapsed = line_elapsed_at(idx, line_elapsed, start_time)
            line_str = line.decode("utf-8") if isinstance(line, bytes) else line
            if not line_str or line_str.startswith("event:"):
                continue
            stripped = line_str.strip()
            if stripped in done_markers:
                done_time = elapsed
                continue
            if not line_str.startswith(line_prefix):
                continue
            data_str = line_str[len(line_prefix):].strip()
            if data_str in done_markers:
                done_time = elapsed
                continue
            if data_str and data_str[0] not in ("{", "["):
                error = f"服务器返回错误: {data_str}"
                continue
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            _handle_ctx(data, elapsed)

    total_time = round(stream_end_elapsed(line_elapsed, start_time, done_at=done_time), 3)
    phases["total_time"] = total_time

    for derived in rules.get("derived") or []:
        key = derived.get("key")
        if not key:
            continue
        val = _eval_derived(derived.get("expr", ""), phases, total_time)
        if val is not None:
            phases[key] = val

    if answer_parts:
        text = "".join(answer_parts)
        preview_len = 500
        for er in rules.get("extras_extract") or []:
            if er.get("from") in ("answer_collect", "text_collect_path", "json_path") and er.get("max_len"):
                try:
                    preview_len = max(50, min(16000, int(er.get("max_len"))))
                except (TypeError, ValueError):
                    preview_len = 500
                break
        extras["answer"] = text[:16000] if not extras.get("answer") else extras["answer"]
        # json_path last 可能已写入 answer_preview；仅在收集到增量时覆盖/补齐
        if "answer_preview" not in extras or answer_parts:
            if any(
                (er.get("from") in ("answer_collect", "text_collect_path"))
                for er in (rules.get("extras_extract") or [])
            ):
                extras["answer"] = text[:16000]
                extras["answer_preview"] = text[:preview_len]
                extras["answer_length"] = len(text)

    # json_path 字符串截断预览（不依赖 answer_parts）
    for er in rules.get("extras_extract") or []:
        if er.get("from") == "json_path" and er.get("key") == "answer_preview":
            val = extras.get("answer_preview")
            if isinstance(val, str) and er.get("max_len"):
                try:
                    ml = max(50, min(16000, int(er.get("max_len"))))
                except (TypeError, ValueError):
                    ml = 500
                extras["answer_preview"] = val[:ml]
                extras.setdefault("answer_length", len(val))

    phase_schema = _build_schema_from_rules(rules)
    success_rule = (options or {}).get("success_rule") or {"type": "phase_exists", "phase": "first_char"}
    success = _evaluate_success(success_rule, phases, extras, status_code, error)

    if status_code >= 400 and not error:
        error = f"HTTP {status_code}"
        success = False

    label_map = {
        str(er.get("key")): (er.get("label") or er.get("key"))
        for er in (rules.get("extras_extract") or [])
        if er.get("key")
    }
    label_map.setdefault("answer_length", "答案长度")
    label_map.setdefault("answer", "完整回答")
    label_map.setdefault("answer_preview", "答案预览")

    out = {
        "parser_id": PARSER_ID,
        "success": success,
        "total_time_s": total_time,
        "status_code": status_code,
        "phases": phases,
        "extras": extras,
        "error": error,
        "phase_schema": phase_schema,
        "extra_schema": [
            {"key": k, "label": label_map.get(k) or k} for k in extras.keys()
        ],
    }
    if debug_views:
        out["match_view_samples"] = match_view_samples
    return out


def _evaluate_success(rule: dict, phases: dict, extras: dict, status_code: int, error: str | None) -> bool:
    if error or status_code >= 400:
        return False
    rtype = rule.get("type", "phase_exists")
    if rtype == "phase_exists":
        return phases.get(rule.get("phase")) is not None
    if rtype == "extras_nonempty":
        return bool(extras.get(rule.get("key")))
    return phases.get(rule.get("phase", "first_char")) is not None
