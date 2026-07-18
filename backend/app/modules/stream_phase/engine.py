"""流式阶段压测 — Backend 侧仅保留报告/聚合契约；施压循环在 Runner（SOT）。"""
from __future__ import annotations

from typing import Any, Optional

from app.modules.stream_phase.contract import normalize_stream_profile


def evaluate_success_rule(rule: dict, result: dict) -> bool:
    if result.get("error") or (result.get("status_code") or 0) >= 400:
        return False
    rtype = (rule or {}).get("type", "phase_exists")
    phases = result.get("phases") or {}
    extras = result.get("extras") or {}
    if rtype == "phase_exists":
        return phases.get(rule.get("phase")) is not None
    if rtype == "extras_nonempty":
        return bool(extras.get(rule.get("key")))
    if rtype == "status_ok":
        return (result.get("status_code") or 0) < 400
    return phases.get(rule.get("phase", "first_char")) is not None


def build_stream_request_result(
    parse_result: dict,
    *,
    user_id: str = "",
    question: str = "",
    case_id: Any = None,
    case_name: str = "",
    success_rule: dict | None = None,
) -> dict[str, Any]:
    success = parse_result.get("success", False)
    if success_rule:
        success = evaluate_success_rule(success_rule, parse_result)

    return {
        "user_id": user_id,
        "question": question,
        "case_id": case_id,
        "case_name": case_name,
        "parser_id": parse_result.get("parser_id"),
        "success": success,
        "total_time_s": parse_result.get("total_time_s"),
        "status_code": parse_result.get("status_code"),
        "phases": parse_result.get("phases") or {},
        "extras": parse_result.get("extras") or {},
        "error": parse_result.get("error"),
        "phase_schema": parse_result.get("phase_schema") or [],
        "extra_schema": parse_result.get("extra_schema") or [],
    }


async def execute_stream_request(
    method: str,
    url: str,
    headers: dict,
    params: dict,
    body: Any,
    body_type: str,
    timeout: int,
    stream_profile: dict,
    *,
    client: Any = None,
    user_id: str = "",
    question: str = "",
    case_id: Any = None,
    case_name: str = "",
) -> dict[str, Any]:
    """已下沉至 Runner Worker；Backend 不再本机执行流式施压。"""
    _ = (
        method, url, headers, params, body, body_type, timeout, stream_profile,
        client, user_id, question, case_id, case_name,
        normalize_stream_profile,
    )
    raise RuntimeError(
        "流式压测施压已迁至 Runner Worker，请启动并勾选压测 Worker 后重试；"
        "后端不再支持本机直跑施压引擎。"
    )


def stream_result_to_perf_queue_item(result: dict) -> dict:
    """转为压测聚合队列兼容格式。"""
    return {
        "case_id": result.get("case_id"),
        "case_name": result.get("case_name"),
        "status_code": result.get("status_code", 0),
        "response_time": result.get("response_time") or (result.get("total_time_s") or 0) * 1000,
        "success": result.get("success", False),
        "error_msg": result.get("error"),
        "response_size": result.get("response_size", 0),
        "request_size": result.get("request_size", 0),
        "_stream_detail": result,
    }


def extract_stream_detail(queue_item: dict) -> dict:
    detail = queue_item.get("_stream_detail")
    if detail:
        return dict(detail)
    return migrate_legacy_detail(queue_item)


def is_stream_queue_result(queue_item: dict) -> bool:
    """是否为流式/SSE 结果（区别于普通 HTTP 压测结果）。"""
    if queue_item.get("_stream_detail"):
        return True
    if queue_item.get("phases") or queue_item.get("phase_schema"):
        return True
    if "has_answer" in queue_item:
        return True
    return False


def migrate_legacy_detail(d: dict) -> dict:
    """旧扁平字段 → 新 phases 结构。"""
    if d.get("phases"):
        return d
    phases = {}
    mapping = {
        "think_answer_s": "think_answer",
        "intent_complete_time_s": "intent_complete",
        "first_char_time_s": "first_char",
        "total_time_s": "total_time",
        "thinking_duration_s": "thinking_duration",
        "answer_streaming_s": "answer_streaming",
    }
    for old, new in mapping.items():
        if d.get(old) is not None:
            phases[new] = d[old]
    extras = {
        "thread_id": d.get("thread_id"),
        "answer_length": d.get("answer_length"),
        "answer_preview": (d.get("full_answer") or "")[:500],
        "reference_files": d.get("reference_files"),
        "intent_start_at": d.get("intent_start_time"),
        "thinking_start_at": d.get("thinking_start_time"),
    }
    extras = {k: v for k, v in extras.items() if v is not None}
    success = d.get("has_answer") if "has_answer" in d else d.get("success", False)
    return {
        "user_id": d.get("user_id", ""),
        "question": d.get("question", ""),
        "case_id": d.get("case_id"),
        "case_name": d.get("case_name", ""),
        "parser_id": d.get("parser_id", "qa_sse_v1"),
        "success": success,
        "total_time_s": d.get("total_time_s") or (d.get("response_time", 0) / 1000 if d.get("response_time") else None),
        "status_code": d.get("status_code") or d.get("response_status_code"),
        "phases": phases,
        "extras": extras,
        "error": d.get("error") or d.get("error_info"),
        "phase_schema": d.get("phase_schema") or [],
    }
