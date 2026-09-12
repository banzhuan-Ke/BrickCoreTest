"""被测监控采集器路径：限流请求体大小（在 Pydantic 解析之前）。"""
from __future__ import annotations

import ipaddress
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

SUT_AGENT_PREFIX = "/perf/sut-agent"
MAX_BODY_BYTES = 256 * 1024
# 无效 Token 也会打到此层：按「真实客户端 IP」粗限流
IP_MAX_CALLS = 120
IP_WINDOW_SEC = 60.0
# 冷 bucket 清理，避免长期内存增长
_IP_BUCKET_GC_EVERY = 256

_ip_buckets: Dict[str, Deque[float]] = defaultdict(deque)
_ip_bucket_ops = 0


class SutAgentBodyLimitMiddleware:
    """仅拦截 /perf/sut-agent/*：Content-Length 预检 + 流式累计；IP 粗限流。"""

    def __init__(self, app: ASGIApp, *, max_body_bytes: int = MAX_BODY_BYTES):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        if not path.startswith(SUT_AGENT_PREFIX):
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        client_ip = _client_ip(scope, headers)
        if not _allow_ip(client_ip):
            resp = JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"},
            )
            await resp(scope, receive, send)
            return

        cl = headers.get("content-length")
        if cl is not None:
            try:
                size = int(cl)
            except ValueError:
                size = -1
            if size > self.max_body_bytes:
                resp = JSONResponse(
                    status_code=413,
                    content={"detail": f"请求体过大（上限 {self.max_body_bytes} 字节）"},
                )
                await resp(scope, receive, send)
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body") or b""
                received += len(body)
                if received > self.max_body_bytes:
                    raise _BodyTooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            resp = JSONResponse(
                status_code=413,
                content={"detail": f"请求体过大（上限 {self.max_body_bytes} 字节）"},
            )
            await resp(scope, receive, send)


class _BodyTooLarge(Exception):
    pass


def _is_trusted_proxy(peer: str) -> bool:
    """仅当直连 peer 为私网/本机时信任 X-Forwarded-For / X-Real-IP（Docker/nginx）。"""
    try:
        ip = ipaddress.ip_address(peer.split("%")[0])
    except ValueError:
        return False
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local)


def _client_ip(scope: Scope, headers: dict[str, str]) -> str:
    peer = (scope.get("client") or ("unknown", 0))[0]
    peer_s = str(peer or "unknown")
    if not _is_trusted_proxy(peer_s):
        return peer_s
    xri = (headers.get("x-real-ip") or "").strip()
    if xri:
        return xri.split(",")[0].strip() or peer_s
    xff = (headers.get("x-forwarded-for") or "").strip()
    if xff:
        return xff.split(",")[0].strip() or peer_s
    return peer_s


def _allow_ip(ip: str) -> bool:
    global _ip_bucket_ops
    now = time.monotonic()
    cutoff = now - IP_WINDOW_SEC
    q = _ip_buckets[ip]
    while q and q[0] < cutoff:
        q.popleft()
    if len(q) >= IP_MAX_CALLS:
        return False
    q.append(now)
    _ip_bucket_ops += 1
    if _ip_bucket_ops >= _IP_BUCKET_GC_EVERY:
        _ip_bucket_ops = 0
        dead = [k for k, dq in _ip_buckets.items() if not dq or dq[-1] < cutoff]
        for k in dead:
            _ip_buckets.pop(k, None)
    return True


def _reset_ip_buckets_for_tests() -> None:
    _ip_buckets.clear()
