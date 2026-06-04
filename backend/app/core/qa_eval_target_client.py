"""被测问答 API 调用：JSON / SSE 流式与调试"""
from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime
from typing import Any, Optional

import httpx

from app.routers.http.utils import get_json_path_value

QA_SSE_PARSER_V1 = "qa_sse_v1"
# 历史配置兼容（不再对外暴露）
_LEGACY_SSE_PARSER_V1 = "kbs_qa_v1"

QA_SSE_DEFAULT_BODY: dict[str, Any] = {
    "fileNo": "",
    "fileType": "",
    "rootDirectory": 5,
    "oneDirectory": "",
    "twoDirectory": "",
    "threeDirectory": "",
    "directoryType": 1,
    "quoteText": [],
    "thinkingEnabled": False,
    "language": "zh-CN",
}

QA_QUESTION_TYPES = (
    "事实性问答类",
    "归纳总结类",
    "对比分析类",
    "逻辑推理类",
    "多轮对话类",
)


def clean_headers(headers: dict[str, Any]) -> dict[str, str]:
    """去掉空值 Header，避免发送 token: \"\" 导致网关鉴权失败"""
    out: dict[str, str] = {}
    for k, v in (headers or {}).items():
        if v is None:
            continue
        s = str(v).strip()
        if s:
            out[str(k)] = s
    return out


def auth_header_hint(url: str, raw_headers: dict[str, Any]) -> Optional[str]:
    u = (url or "").lower()
    if "digiwin" not in u and "/api/v1/qa" not in u:
        return None
    missing = []
    for key in ("token", "digi-middleware-auth-app"):
        val = raw_headers.get(key) if isinstance(raw_headers, dict) else None
        if not val or not str(val).strip():
            missing.append(key)
    if not missing:
        return None
    return (
        f"Headers 缺少鉴权字段：{', '.join(missing)}。"
        "请从浏览器开发者工具复制 token、digi-middleware-auth-app（及 signature 等）到配置中"
    )


def _template_replace(text: str, ctx: dict[str, Any]) -> str:
    out = text or ""
    for key, val in ctx.items():
        if isinstance(val, (list, dict)):
            rep = json.dumps(val, ensure_ascii=False)
        elif isinstance(val, bool):
            rep = "true" if val else "false"
        elif val is None:
            rep = ""
        else:
            rep = str(val)
        out = out.replace(f"{{{{{key}}}}}", rep)
        out = out.replace(f"{{{{ {key} }}}}", rep)
    return out


def build_request_context(question: str, extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    extra = extra if isinstance(extra, dict) else {}
    chat_path = extra.get("chatPath")
    if chat_path is None:
        chat_path = extra.get("chat_path")
    if chat_path is None:
        chat_path = []
    if isinstance(chat_path, str):
        chat_path = chat_path.strip()
        if chat_path:
            try:
                chat_path = json.loads(chat_path)
            except json.JSONDecodeError:
                chat_path = []
        else:
            chat_path = []
    session_id = extra.get("sessionId")
    if session_id is None:
        session_id = extra.get("session_id")
    if session_id is None:
        session_id = ""
    if not str(session_id).strip():
        session_id = uuid.uuid4().hex
    history = extra.get("historyFlag")
    if history is None:
        history = extra.get("history_flag")
    return {
        "question": (question or "").strip(),
        "chatPath": chat_path if isinstance(chat_path, list) else [],
        "sessionId": str(session_id or ""),
        "historyFlag": bool(history),
        "questionTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def build_request_body(cfg: dict[str, Any], ctx: dict[str, Any]) -> Any:
    default_body = cfg.get("default_body")
    template = (cfg.get("body_template") or "").strip()

    if isinstance(default_body, dict) and default_body:
        body = dict(default_body)
        body["question"] = ctx["question"]
        body["chatPath"] = ctx["chatPath"]
        body["sessionId"] = ctx["sessionId"]
        body["historyFlag"] = ctx["historyFlag"]
        body["questionTime"] = ctx["questionTime"]
        return body

    body_raw = template or '{"question":"{{question}}"}'
    body_raw = _template_replace(body_raw, ctx)
    try:
        return json.loads(body_raw)
    except json.JSONDecodeError:
        return {"question": ctx["question"]}


def normalize_sse_parser(parser: Optional[str]) -> str:
    p = (parser or QA_SSE_PARSER_V1).lower()
    if p == _LEGACY_SSE_PARSER_V1:
        return QA_SSE_PARSER_V1
    return p


def is_qa_sse_v1_parser(parser: Optional[str]) -> bool:
    return normalize_sse_parser(parser) == QA_SSE_PARSER_V1


def parse_qa_sse_v1(lines: list[str]) -> dict[str, Any]:
    """解析问答 SSE 流（think / output_text / eof references）"""
    thinking: list[str] = []
    answer: list[str] = []
    refs: list[tuple[str, float]] = []

    for line in lines:
        if not line:
            continue
        txt = line.strip()
        if not txt.startswith("data:"):
            continue
        data = txt[5:].strip()
        if data == "[DONE]":
            break
        if '"errorMessage"' in data or '"duration"' in data:
            continue
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        t = obj.get("type")
        if t in ("think", "think_answer"):
            delta = obj.get("delta", "{}")
            try:
                d = json.loads(delta) if isinstance(delta, str) else delta
                if isinstance(d, dict) and d.get("message_type") == "text":
                    text = (d.get("content") or {}).get("text", "")
                    if text:
                        thinking.append(str(text))
            except (json.JSONDecodeError, TypeError):
                pass
        elif t == "output_text":
            delta = obj.get("delta", "")
            if delta:
                answer.append(str(delta))
        elif t == "eof":
            for ref in obj.get("references") or []:
                if not isinstance(ref, dict):
                    continue
                name = ref.get("doc_name")
                score_raw = ref.get("chunk_score", 0)
                if not name:
                    continue
                try:
                    score_val = float(score_raw) if score_raw else 0.0
                except (TypeError, ValueError):
                    score_val = 0.0
                refs.append((str(name), score_val))

    answer_str = re.sub(r"\[ref:\d+\]", "", "".join(answer)).strip()
    thinking_str = "".join(thinking).strip()

    seen: set[str] = set()
    unique_refs: list[tuple[str, float]] = []
    for name, score in refs:
        if name not in seen:
            seen.add(name)
            unique_refs.append((name, score))

    refs_all = "；".join(f"{n} ({s:.2f})" for n, s in unique_refs) if unique_refs else ""
    high_refs = [(n, s) for n, s in unique_refs if s > 80]
    refs_high = "；".join(f"{n} ({s:.2f})" for n, s in high_refs) if high_refs else ""

    status = "success" if answer_str and not answer_str.startswith("请求") else "fail"
    return {
        "actual_answer": answer_str[:16000],
        "thinking": thinking_str[:8000],
        "references_all": refs_all[:4000],
        "references_high": refs_high[:4000],
        "status": status,
    }


async def invoke_target_api(
    cfg: dict[str, Any],
    question: str,
    *,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """调用被测 API，返回统一结构（含调试字段）"""
    url = (cfg.get("url") or "").strip()
    if not url:
        return {
            "success": False,
            "actual_answer": None,
            "api_error": "被测 API 未配置 url",
            "api_latency_ms": 0,
            "raw_preview": "",
            "parsed_fields": {},
        }

    method = (cfg.get("method") or "POST").upper()
    raw_headers = cfg.get("headers") or {}
    if not isinstance(raw_headers, dict):
        raw_headers = {}
    auth_hint = auth_header_hint(url, raw_headers)
    headers = clean_headers(raw_headers)
    response_type = (cfg.get("response_type") or "json").lower()
    ctx = build_request_context(question, extra)
    body = build_request_body(cfg, ctx)
    connect_timeout = int(cfg.get("connect_timeout_sec") or 30)
    read_timeout = int(cfg.get("read_timeout_sec") or cfg.get("timeout_sec") or 300)
    timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=30, pool=30)
    started = time.perf_counter()

    if auth_hint:
        return {
            "success": False,
            "actual_answer": None,
            "api_error": auth_hint,
            "api_latency_ms": 0,
            "raw_preview": "",
            "parsed_fields": {},
            "request_body": body,
            "request_headers_keys": list(headers.keys()),
        }

    try:
        async with httpx.AsyncClient(timeout=timeout, verify=cfg.get("verify_ssl", True)) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers, params={"question": ctx["question"]})
                latency_ms = int((time.perf_counter() - started) * 1000)
                raw_text = resp.text or ""
                if resp.status_code >= 400:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    return _fail(resp.status_code, raw_text, latency_ms, auth_hint=auth_hint)
                return _parse_json_response(cfg, raw_text, latency_ms)

            if response_type == "sse":
                raw_lines: list[str] = []
                async with client.stream(method, url, headers=headers, json=body) as resp:
                    if resp.status_code >= 400:
                        raw_text = (await resp.aread()).decode("utf-8", errors="replace")
                        latency_ms = int((time.perf_counter() - started) * 1000)
                        return _fail(resp.status_code, raw_text, latency_ms, auth_hint=auth_hint)
                    async for line in resp.aiter_lines():
                        if line is not None:
                            raw_lines.append(line)
                latency_ms = int((time.perf_counter() - started) * 1000)
                parser = normalize_sse_parser(cfg.get("sse_parser"))
                if not is_qa_sse_v1_parser(parser):
                    joined = "\n".join(raw_lines)
                    return {
                        "success": bool(joined.strip()),
                        "actual_answer": joined[:16000],
                        "api_error": None,
                        "api_latency_ms": latency_ms,
                        "raw_preview": "\n".join(raw_lines[-50:])[:12000],
                        "parsed_fields": {},
                        "request_body": body,
                    }
                parsed = parse_qa_sse_v1(raw_lines)
                api_error = None if parsed["status"] == "success" else "SSE 解析未得到有效回答"
                return {
                    "success": parsed["status"] == "success",
                    "actual_answer": parsed["actual_answer"] or None,
                    "api_error": api_error,
                    "api_latency_ms": latency_ms,
                    "raw_preview": "\n".join(raw_lines[-50:])[:12000],
                    "parsed_fields": {
                        "thinking": parsed["thinking"],
                        "references_all": parsed["references_all"],
                        "references_high": parsed["references_high"],
                        "status": parsed["status"],
                    },
                    "request_body": body,
                }

            resp = await client.request(method, url, headers=headers, json=body)
            latency_ms = int((time.perf_counter() - started) * 1000)
            raw_text = resp.text or ""
            if resp.status_code >= 400:
                return _fail(resp.status_code, raw_text, latency_ms, auth_hint=auth_hint)
            return _parse_json_response(cfg, raw_text, latency_ms, json_body=body)

    except Exception as e:
        latency_ms = int((time.perf_counter() - started) * 1000)
        err = str(e)[:1000]
        if auth_hint:
            err = f"{auth_hint}；{err}" if err else auth_hint
        return {
            "success": False,
            "actual_answer": None,
            "api_error": err,
            "api_latency_ms": latency_ms,
            "raw_preview": "",
            "parsed_fields": {},
            "request_body": body,
            "request_headers_keys": list(headers.keys()),
        }

def _fail(
    status_code: int,
    raw_text: str,
    latency_ms: int,
    *,
    auth_hint: Optional[str] = None,
) -> dict[str, Any]:
    err = f"HTTP {status_code}: {(raw_text or '')[:500]}"
    if auth_hint:
        err = f"{auth_hint}；{err}"
    return {
        "success": False,
        "actual_answer": None,
        "api_error": err,
        "api_latency_ms": latency_ms,
        "raw_preview": (raw_text or "")[:12000],
        "parsed_fields": {},
    }


def _parse_json_response(
    cfg: dict[str, Any],
    raw_text: str,
    latency_ms: int,
    *,
    json_body: Any = None,
) -> dict[str, Any]:
    try:
        data = json.loads(raw_text) if raw_text else {}
    except json.JSONDecodeError:
        return {
            "success": bool(raw_text.strip()),
            "actual_answer": raw_text[:16000] if raw_text else "",
            "api_error": None,
            "api_latency_ms": latency_ms,
            "raw_preview": raw_text[:12000],
            "parsed_fields": {},
            "request_body": json_body,
        }

    jsonpath = (cfg.get("answer_jsonpath") or "").strip()
    if jsonpath:
        val = get_json_path_value(data, jsonpath)
        if val is None:
            return {
                "success": False,
                "actual_answer": None,
                "api_error": f"JSONPath 未匹配: {jsonpath}",
                "api_latency_ms": latency_ms,
                "raw_preview": raw_text[:12000],
                "parsed_fields": {},
                "request_body": json_body,
            }
        actual = json.dumps(val, ensure_ascii=False) if isinstance(val, (dict, list)) else str(val)
    elif isinstance(data, dict):
        actual = None
        for key in ("answer", "data", "content", "message", "result"):
            if key in data and data[key] is not None:
                v = data[key]
                actual = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
                break
        if actual is None:
            actual = json.dumps(data, ensure_ascii=False)
    else:
        actual = str(data)

    return {
        "success": bool(actual),
        "actual_answer": (actual or "")[:16000],
        "api_error": None,
        "api_latency_ms": latency_ms,
        "raw_preview": raw_text[:12000],
        "parsed_fields": {},
        "request_body": json_body,
    }


def new_session_id() -> str:
    return uuid.uuid4().hex
