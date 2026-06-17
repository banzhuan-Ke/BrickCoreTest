"""性能压测请求诊断信息（不影响 QPS/RT 等聚合指标）。"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

MAX_FAILED_SAMPLES = 50
MAX_REQUEST_TRACES = 500
MAX_REQUEST_DETAILS = 5000
REQUEST_DETAIL_BRIEF = "brief"
REQUEST_DETAIL_FULL = "full"


def append_request_detail(details: list | None, item: dict) -> None:
    """流式阶段明细上限，避免长跑撑爆内存与 DB JSON。"""
    if details is None:
        return
    if len(details) >= MAX_REQUEST_DETAILS:
        return
    details.append(item)


def preview_text(val: Any, max_len: int = 300) -> str:
    if val is None:
        return ""
    if isinstance(val, (dict, list)):
        try:
            text = json.dumps(val, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(val)
    else:
        text = str(val)
    text = text.replace("\n", " ").replace("\r", " ")
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def full_trace_text(val: Any) -> str:
    """诊断 trace 用完整文本（不参与 QPS/RT 聚合，仅报告展示）。"""
    if val is None:
        return ""
    if isinstance(val, (dict, list)):
        try:
            return json.dumps(val, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(val)
    return str(val)


def extract_question(body: Any, csv_row: Optional[dict] = None) -> str:
    if isinstance(body, dict) and body.get("question") not in (None, ""):
        return str(body["question"])[:500]
    if csv_row and csv_row.get("question") not in (None, ""):
        return str(csv_row["question"])[:500]
    return ""


def build_trace_meta(
    *,
    method: str = "",
    url: str = "",
    body: Any = None,
    headers: Any = None,
    params: Any = None,
    response_body: Any = None,
    csv_row: Optional[dict] = None,
    user_id: str = "",
    worker_id: Optional[int] = None,
) -> dict:
    uid = user_id or (f"User_{worker_id:03d}" if worker_id is not None else "")
    return {
        "method": method or "",
        "url": url or "",
        "user_id": uid,
        "question": extract_question(body, csv_row),
        "request_headers_preview": preview_text(headers, 500),
        "request_params_preview": preview_text(params, 300),
        "request_body_preview": preview_text(body, 800),
        "response_body_preview": full_trace_text(response_body),
        "csv_row": dict(csv_row) if isinstance(csv_row, dict) else None,
    }


def attach_trace_meta(result: dict, **meta_kwargs) -> dict:
    result["_trace_meta"] = build_trace_meta(**meta_kwargs)
    return result


def _trace_row_fields(meta: dict, detail: Optional[dict] = None) -> dict:
    """通用 HTTP/流式诊断字段（报告展示用）。"""
    extras = (detail or {}).get("extras") or {}
    resp = meta.get("response_body_preview", "")
    if not resp and extras.get("answer_preview"):
        resp = full_trace_text(extras.get("answer_preview"))
    thinking = str(extras.get("thinking") or "") if extras.get("thinking") else ""
    return {
        "request_headers_preview": meta.get("request_headers_preview", ""),
        "request_params_preview": meta.get("request_params_preview", ""),
        "request_body_preview": meta.get("request_body_preview", ""),
        "response_body_preview": resp,
        "thinking_preview": thinking,
    }


def build_failed_sample(result: dict) -> dict:
    detail = result.get("_stream_detail") or {}
    meta = result.get("_trace_meta") or {}
    question = detail.get("question") or meta.get("question") or ""
    if not question and isinstance(meta.get("csv_row"), dict):
        question = str(meta["csv_row"].get("question", ""))[:500]
    err = result.get("error_msg") or detail.get("error") or ""
    row = {
        "case_id": result.get("case_id"),
        "case_name": result.get("case_name", "未知"),
        "user_id": detail.get("user_id") or meta.get("user_id", ""),
        "question": question,
        "method": meta.get("method", ""),
        "url": meta.get("url", ""),
        "status_code": result.get("status_code", 0),
        "response_time": round(float(result.get("response_time", 0) or 0), 2),
        "error_msg": str(err)[:500],
        "trace_type": "stream" if detail else "http",
        "success": bool(result.get("success")),
    }
    row.update(_trace_row_fields(meta, detail if detail else None))
    return row


def build_request_trace(result: dict) -> dict:
    row = build_failed_sample(result)
    row["success"] = bool(result.get("success"))
    return row


def collect_result_diagnostics(
    result: dict,
    failed_samples: List[dict],
    request_traces: Optional[List[dict]],
    detail_level: str,
) -> None:
    """收集失败采样（始终）与成功请求明细（仅 full 模式）。"""
    if not result.get("success"):
        if len(failed_samples) < MAX_FAILED_SAMPLES:
            failed_samples.append(build_failed_sample(result))
        return
    if detail_level == REQUEST_DETAIL_FULL and request_traces is not None:
        if len(request_traces) < MAX_REQUEST_TRACES:
            request_traces.append(build_request_trace(result))


def normalize_detail_level(value: Optional[str]) -> str:
    return REQUEST_DETAIL_FULL if value == REQUEST_DETAIL_FULL else REQUEST_DETAIL_BRIEF
