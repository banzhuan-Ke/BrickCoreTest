"""流式阶段解析器注册表"""
from __future__ import annotations

from typing import Any, Callable

from app.modules.stream_phase.parsers import qa_sse_v1, rule_based, http_timing_only
from app.modules.stream_phase.parsers.rule_based import DEFAULT_RULES

ParseFn = Callable[..., dict[str, Any]]

_REGISTRY: dict[str, dict[str, Any]] = {}


def _register(parser_id: str, module) -> None:
    _REGISTRY[parser_id] = {
        "parser_id": parser_id,
        "display_name": module.DISPLAY_NAME,
        "transport": ["sse"],
        "phase_schema": getattr(module, "PHASE_SCHEMA", []),
        "extra_schema": getattr(module, "EXTRA_SCHEMA", []),
        "default_options": {},
        "default_success_rule": {"type": "phase_exists", "phase": "first_char"},
        "parse": module.parse_stream,
    }


_register(qa_sse_v1.PARSER_ID, qa_sse_v1)
_register(rule_based.PARSER_ID, rule_based)
_register(http_timing_only.PARSER_ID, http_timing_only)

_REGISTRY[rule_based.PARSER_ID]["default_options"] = {"rules": DEFAULT_RULES}
_REGISTRY[rule_based.PARSER_ID]["default_success_rule"] = {"type": "phase_exists", "phase": "first_char"}
_REGISTRY[http_timing_only.PARSER_ID]["default_success_rule"] = {"type": "phase_exists", "phase": "total_time"}


def list_parsers() -> list[dict[str, Any]]:
    out = []
    for pid, meta in _REGISTRY.items():
        out.append({
            "parser_id": pid,
            "display_name": meta["display_name"],
            "transport": meta["transport"],
            "phase_schema": meta.get("phase_schema") or [],
            "extra_schema": meta.get("extra_schema") or [],
            "default_options": meta.get("default_options") or {},
            "default_success_rule": meta.get("default_success_rule") or {},
            "supports_rule_builder": pid == rule_based.PARSER_ID,
        })
    return out


def get_parser(parser_id: str) -> dict[str, Any] | None:
    return _REGISTRY.get(parser_id)


def get_parser_preset(parser_id: str) -> dict[str, Any]:
    meta = get_parser(parser_id)
    if not meta:
        return {}
    return {
        "parser_id": parser_id,
        "display_name": meta["display_name"],
        "phase_schema": meta.get("phase_schema") or [],
        "default_options": meta.get("default_options") or {},
        "default_success_rule": meta.get("default_success_rule") or {},
    }


def parse_stream_lines(
    parser_id: str,
    lines: list[str],
    *,
    start_time: float,
    status_code: int = 200,
    options: dict | None = None,
    success_rule: dict | None = None,
    line_elapsed: list[float] | None = None,
) -> dict[str, Any]:
    meta = get_parser(parser_id)
    if not meta:
        raise ValueError(f"未知解析器: {parser_id}")

    opts = dict(meta.get("default_options") or {})
    opts.update(options or {})
    if success_rule and parser_id == rule_based.PARSER_ID:
        opts["success_rule"] = success_rule

    result = meta["parse"](
        lines,
        start_time=start_time,
        status_code=status_code,
        options=opts,
        line_elapsed=line_elapsed,
    )

    if success_rule and parser_id != rule_based.PARSER_ID:
        from app.modules.stream_phase.engine import evaluate_success_rule
        result["success"] = evaluate_success_rule(success_rule, result)

    if not result.get("phase_schema"):
        result["phase_schema"] = meta.get("phase_schema") or []

    return result
