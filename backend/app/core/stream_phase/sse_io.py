"""SSE 流式请求 I/O（与问答准确性评测 qa_eval_target_client 对齐）"""
from __future__ import annotations

from typing import Any, Optional

import httpx


def clean_stream_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    """去掉空值 Header，避免 token=\"\" 导致网关鉴权失败。"""
    out: dict[str, str] = {}
    for k, v in (headers or {}).items():
        if v is None:
            continue
        s = str(v).strip()
        if s:
            out[str(k)] = s
    return out


def build_stream_timeout(read_seconds: int, *, connect: int = 30) -> httpx.Timeout:
    """长连接读超时单独配置，避免整请求用一个 scalar timeout。"""
    read = max(int(read_seconds or 300), 30)
    return httpx.Timeout(connect=connect, read=read, write=30, pool=30)


def create_isolated_stream_client() -> httpx.AsyncClient:
    """每路 SSE 使用独立连接，不复用 keep-alive（对齐 Locust 每用户独立 session）。"""
    return httpx.AsyncClient(
        follow_redirects=True,
        limits=httpx.Limits(max_keepalive_connections=0, max_connections=100),
    )


def prepare_stream_request_headers(headers: dict[str, Any] | None) -> httpx.Headers:
    """清洗 Header 并补全 SSE Accept。"""
    cleaned = clean_stream_headers(headers)
    if not any(k.lower() == "accept" for k in cleaned):
        cleaned["Accept"] = "text/event-stream"
    return httpx.Headers(cleaned, encoding="utf-8")
