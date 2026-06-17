"""流式阶段压测引擎"""
from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from app.core.stream_phase.registry import parse_stream_lines
from app.core.stream_phase.contract import normalize_stream_profile
from app.core.stream_phase.sse_io import (
    build_stream_timeout,
    create_isolated_stream_client,
    prepare_stream_request_headers,
)


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
    client: httpx.AsyncClient | None = None,
    user_id: str = "",
    question: str = "",
    case_id: Any = None,
    case_name: str = "",
) -> dict[str, Any]:
    """执行流式请求并返回 StreamRequestResult。"""
    profile = normalize_stream_profile({"stream_profile": stream_profile})
    parser_id = profile["parser_id"]
    parser_options = profile.get("parser_options") or {}
    success_rule = profile.get("success_rule") or {}
    timeout = profile.get("timeout_seconds") or timeout

    start_time = time.time()
    request_size = len(str(body).encode("utf-8")) if body else 0

    async def _do_stream(req_client: httpx.AsyncClient):
        req_timeout = build_stream_timeout(timeout)
        stream_headers = prepare_stream_request_headers(headers)
        kwargs = {"headers": stream_headers, "params": params, "timeout": req_timeout}
        if method in ("POST", "PUT", "PATCH") and body:
            if body_type == "json":
                kwargs["json"] = body
            else:
                kwargs["data"] = body

        raw_lines: list[str] = []
        line_elapsed: list[float] = []
        status_code = 0
        response_size = 0

        async with req_client.stream(method, url, **kwargs) as response:
            status_code = response.status_code
            if status_code >= 400:
                error_text = (await response.aread()).decode("utf-8", errors="replace")
                parsed = parse_stream_lines(parser_id, [], start_time=start_time, status_code=status_code, options=parser_options, success_rule=success_rule)
                parsed["error"] = f"HTTP {status_code}: {error_text[:200]}"
                parsed["success"] = False
                return parsed, response_size, request_size

            stream_err = None
            try:
                async for line in response.aiter_lines():
                    if line is not None:
                        raw_lines.append(line)
                        line_elapsed.append(time.time() - start_time)
                        response_size += len(line.encode("utf-8")) if isinstance(line, str) else len(line)
            except (httpx.ReadError, httpx.RemoteProtocolError, httpx.StreamError) as exc:
                stream_err = str(exc)

        parsed = parse_stream_lines(
            parser_id, raw_lines, start_time=start_time, status_code=status_code,
            options=parser_options, success_rule=success_rule, line_elapsed=line_elapsed,
        )
        if stream_err:
            if success_rule and evaluate_success_rule(success_rule, {**parsed, "error": None}):
                parsed["success"] = True
                extras = parsed.setdefault("extras", {})
                extras["stream_interrupted"] = stream_err
            elif not parsed.get("success"):
                parsed["error"] = stream_err
                parsed["success"] = False
        return parsed, response_size, request_size

    try:
        # 并发 SSE 必须独立连接；传入的共享 client 仅作兼容，实际不使用
        _ = client
        async with create_isolated_stream_client() as stream_client:
            parsed, response_size, request_size = await _do_stream(stream_client)

        result = build_stream_request_result(
            parsed, user_id=user_id, question=question,
            case_id=case_id, case_name=case_name, success_rule=success_rule,
        )
        result["response_time"] = round((result.get("total_time_s") or 0) * 1000, 2)
        result["response_size"] = response_size
        result["request_size"] = request_size
        if not result.get("success") and not result.get("error"):
            result["error"] = "未满足成功判定规则"
        return result

    except httpx.TimeoutException:
        elapsed = round(time.time() - start_time, 3)
        return {
            "user_id": user_id, "question": question, "case_id": case_id, "case_name": case_name,
            "parser_id": parser_id, "success": False, "total_time_s": elapsed, "status_code": 0,
            "phases": {}, "extras": {}, "error": "timeout",
            "phase_schema": [], "response_time": elapsed * 1000,
            "response_size": 0, "request_size": request_size,
        }
    except Exception as e:
        elapsed = round(time.time() - start_time, 3)
        return {
            "user_id": user_id, "question": question, "case_id": case_id, "case_name": case_name,
            "parser_id": parser_id, "success": False, "total_time_s": elapsed, "status_code": 0,
            "phases": {}, "extras": {}, "error": str(e),
            "phase_schema": [], "response_time": elapsed * 1000,
            "response_size": 0, "request_size": request_size,
        }


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
