"""性能压测请求诊断信息（不影响 QPS/RT 等聚合指标）。

与 runner/tools/perf_trace.py 保持一致；改动后请同步另一份，并由
tests/test_perf_trace_redact.py / test_perf_sot_sync.py 约束。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MAX_FAILED_SAMPLES = 50
MAX_REQUEST_TRACES = 500
MAX_REQUEST_DETAILS = 5000
REQUEST_DETAIL_BRIEF = "brief"
REQUEST_DETAIL_FULL = "full"

# 完整字段单字段硬上限（失败样本始终存；成功仅 full 模式写入 traces）
FULL_FIELD_MAX_LEN = 32768

REDACTED = "***REDACTED***"

# 请求/响应头名（大小写不敏感）
_SENSITIVE_HEADER_NAMES = frozenset({
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
    "apikey",
    "x-auth-token",
    "x-access-token",
    "x-csrf-token",
    "x-session-token",
    "authentication",
})

# JSON / form 字段名（避免裸匹配 auth，防止误伤 author 等）
_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|secret|access[_-]?token|refresh[_-]?token|(^|[_-])token($|[_-])|"
    r"api[_-]?key|apikey|authorization|credential|session[_-]?(id|key|token)|"
    r"private[_-]?key|(^|[_-])cookie($|[_-]))",
    re.I,
)

_BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+[^\s,;]+")


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


def full_trace_text(val: Any, max_len: int = FULL_FIELD_MAX_LEN) -> str:
    """诊断 trace 用完整文本（不参与 QPS/RT 聚合，仅报告展示）。"""
    if val is None:
        return ""
    if isinstance(val, (dict, list)):
        try:
            text = json.dumps(val, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            text = str(val)
    else:
        text = str(val)
    if max_len > 0 and len(text) > max_len:
        return text[: max_len - 14] + "...[truncated]"
    return text


def headers_to_dict(headers: Any) -> Any:
    if headers is None:
        return None
    if isinstance(headers, dict):
        return dict(headers)
    try:
        return dict(headers)
    except Exception:
        return headers


def _is_sensitive_header_name(name: Any) -> bool:
    return str(name or "").strip().lower() in _SENSITIVE_HEADER_NAMES


def _is_sensitive_field_name(name: Any) -> bool:
    return bool(_SENSITIVE_KEY_RE.search(str(name or "")))


def redact_headers(headers: Any) -> Any:
    """脱敏敏感请求/响应头。"""
    hdr = headers_to_dict(headers)
    if not isinstance(hdr, dict):
        return hdr
    out = {}
    for k, v in hdr.items():
        out[k] = REDACTED if _is_sensitive_header_name(k) else v
    return out


def redact_form_urlencoded_text(text: str) -> Optional[str]:
    """若文本像 x-www-form-urlencoded，则脱敏敏感键；否则返回 None。"""
    if not text or "=" not in text:
        return None
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return None
    try:
        pairs = parse_qsl(text, keep_blank_values=True)
    except Exception:
        return None
    if not pairs:
        return None
    # 至少一个键非空，避免把普通 "a=b 说明文字" 误伤过重仍可处理
    changed = False
    out = []
    for k, v in pairs:
        if _is_sensitive_field_name(k):
            out.append((k, REDACTED))
            changed = True
        else:
            out.append((k, v))
    if not changed:
        return None
    return urlencode(out)


def redact_mapping(value: Any) -> Any:
    """递归脱敏 dict/list 中的敏感键；字符串中的 form / Bearer 凭证一并打码。"""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if _is_sensitive_field_name(k) or _is_sensitive_header_name(k):
                out[k] = REDACTED
            else:
                out[k] = redact_mapping(v)
        return out
    if isinstance(value, list):
        return [redact_mapping(v) for v in value]
    if isinstance(value, str):
        form = redact_form_urlencoded_text(value)
        if form is not None:
            return form
        return _BEARER_RE.sub(r"\1 " + REDACTED, value)
    return value


def redact_url(url: str) -> str:
    """脱敏 URL query 中的敏感参数。"""
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        if not parts.query:
            return url
        pairs = []
        changed = False
        for k, v in parse_qsl(parts.query, keep_blank_values=True):
            if _is_sensitive_field_name(k):
                pairs.append((k, REDACTED))
                changed = True
            else:
                pairs.append((k, v))
        if not changed:
            return url
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), parts.fragment))
    except Exception:
        return url


def _redact_serialized_blob(raw: Any) -> Any:
    """对已序列化的 headers/body 文本尽量脱敏（兼容历史未脱敏数据）。"""
    if raw in (None, ""):
        return raw
    if isinstance(raw, (dict, list)):
        return redact_mapping(raw)
    text = str(raw)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, (dict, list)):
            redacted = redact_mapping(parsed)
            indent = 2 if "\n" in text else None
            return json.dumps(redacted, ensure_ascii=False, indent=indent)
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    form = redact_form_urlencoded_text(text)
    if form is not None:
        return form
    return _BEARER_RE.sub(r"\1 " + REDACTED, text)


def sanitize_trace_item(item: dict) -> dict:
    """展示/导出前脱敏单条 trace（含历史明文数据）。"""
    if not isinstance(item, dict):
        return item
    out = dict(item)
    if out.get("url"):
        out["url"] = redact_url(str(out["url"]))
    for key in (
        "request_headers", "request_headers_preview",
        "response_headers",
        "request_params", "request_params_preview",
        "request_body", "request_body_preview",
        "response_body_preview",
        "csv_row",
    ):
        if key in out and out[key] not in (None, ""):
            out[key] = _redact_serialized_blob(out[key])
    out["trace_redacted"] = True
    return out


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
    response_headers: Any = None,
    csv_row: Optional[dict] = None,
    user_id: str = "",
    worker_id: Optional[int] = None,
) -> dict:
    uid = user_id or (f"User_{worker_id:03d}" if worker_id is not None else "")
    hdr = redact_headers(headers)
    rh = redact_headers(response_headers)
    safe_body = redact_mapping(body)
    safe_params = redact_mapping(params)
    safe_csv = redact_mapping(dict(csv_row)) if isinstance(csv_row, dict) else None
    return {
        "method": method or "",
        "url": redact_url(url or ""),
        "user_id": uid,
        "question": extract_question(body, csv_row),
        "request_headers_preview": preview_text(hdr, 500),
        "request_params_preview": preview_text(safe_params, 300),
        "request_body_preview": preview_text(safe_body, 800),
        "response_body_preview": full_trace_text(redact_mapping(response_body)),
        "request_headers": full_trace_text(hdr),
        "request_params": full_trace_text(safe_params),
        "request_body": full_trace_text(safe_body),
        "response_headers": full_trace_text(rh),
        "csv_row": safe_csv,
        "trace_content_full": True,
        "trace_redacted": True,
    }


def attach_trace_meta(result: dict, **meta_kwargs) -> dict:
    result["_trace_meta"] = build_trace_meta(**meta_kwargs)
    return result


def _pick_field(meta: dict, full_key: str, preview_key: str) -> str:
    full = meta.get(full_key)
    if full not in (None, ""):
        return str(full)
    return str(meta.get(preview_key) or "")


def _trace_row_fields(meta: dict, detail: Optional[dict] = None) -> dict:
    """通用 HTTP/流式诊断字段（报告展示用）。"""
    extras = (detail or {}).get("extras") or {}
    resp = _pick_field(meta, "response_body_preview", "response_body_preview")
    if not resp and extras.get("answer_preview"):
        resp = full_trace_text(extras.get("answer_preview"))
    thinking = str(extras.get("thinking") or "") if extras.get("thinking") else ""
    raw_sse = str((detail or {}).get("raw_sse_preview") or "")
    return {
        "request_headers_preview": meta.get("request_headers_preview", ""),
        "request_params_preview": meta.get("request_params_preview", ""),
        "request_body_preview": meta.get("request_body_preview", ""),
        "response_body_preview": resp,
        "request_headers": _pick_field(meta, "request_headers", "request_headers_preview"),
        "request_params": _pick_field(meta, "request_params", "request_params_preview"),
        "request_body": _pick_field(meta, "request_body", "request_body_preview"),
        "response_headers": meta.get("response_headers") or "",
        "thinking_preview": thinking,
        "raw_sse_preview": raw_sse,
        "trace_content_full": bool(meta.get("trace_content_full")),
        "trace_redacted": bool(meta.get("trace_redacted")),
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
