"""规则驱动 SSE 阶段解析器"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from app.core.stream_phase.timing import line_elapsed_at, stream_end_elapsed

PARSER_ID = "rule_based"
DISPLAY_NAME = "规则配置"

DEFAULT_RULES = {
    "line_prefix": "data:",
    "done_markers": ["[DONE]", "data:[DONE]"],
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
        {"key": "answer_streaming", "label": "答案流式输出(s)", "expr": "total_time - first_char"},
    ],
    "extras_extract": [
        {"key": "thread_id", "from": "json_field", "field": "id", "trigger": "first"},
        {
            "key": "reference_files",
            "from": "eof_references",
            "match": {"type": "eof", "agent": "conventional_summary"},
            "field": "doc_name",
        },
        {"key": "answer_preview", "from": "answer_collect", "agent": "conventional_summary", "max_len": 500},
    ],
}


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


def _match_obj(data: dict, match: dict) -> bool:
    for k, v in (match or {}).items():
        if k == "delta_nonempty":
            delta = data.get("delta", "")
            if v and not (delta and str(delta).strip() and str(delta).strip() != "\n\n"):
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
        # 仅支持 a - b 形式
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
    phases: dict[str, Any] = {}
    extras: dict[str, Any] = {}
    error = None
    done_time = None
    answer_parts: list[str] = []
    triggered_phases = set()
    triggered_extras = set()

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

        for phase_rule in rules.get("phases") or []:
            key = phase_rule.get("key")
            if not key or key in triggered_phases:
                continue
            if _match_obj(data, phase_rule.get("match") or {}):
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
            elif src == "eof_references" and _match_obj(data, extra_rule.get("match") or {}):
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
        extras["answer_preview"] = text[: (rules.get("answer_max_len") or 500)]
        extras["answer_length"] = len(text)

    phase_schema = _build_schema_from_rules(rules)
    success_rule = (options or {}).get("success_rule") or {"type": "phase_exists", "phase": "first_char"}
    success = _evaluate_success(success_rule, phases, extras, status_code, error)

    if status_code >= 400 and not error:
        error = f"HTTP {status_code}"
        success = False

    return {
        "parser_id": PARSER_ID,
        "success": success,
        "total_time_s": total_time,
        "status_code": status_code,
        "phases": phases,
        "extras": extras,
        "error": error,
        "phase_schema": phase_schema,
        "extra_schema": [{"key": k, "label": k} for k in extras.keys()],
    }


def _evaluate_success(rule: dict, phases: dict, extras: dict, status_code: int, error: str | None) -> bool:
    if error or status_code >= 400:
        return False
    rtype = rule.get("type", "phase_exists")
    if rtype == "phase_exists":
        return phases.get(rule.get("phase")) is not None
    if rtype == "extras_nonempty":
        return bool(extras.get(rule.get("key")))
    return phases.get(rule.get("phase", "first_char")) is not None
