"""单页 DOM 抓取：平台同步等待 Runner 回传（仿 api_debug_bridge）。"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)

_RESULT_KEY = "ui:page_fetch_result:{request_id}"
_TTL_SECONDS = 180

_events: dict[str, asyncio.Event] = {}
_results: dict[str, dict[str, Any]] = {}
_lock = asyncio.Lock()

_redis_ok: Optional[bool] = None
_redis_checked_at = 0.0
_REDIS_NEG_TTL = 15.0


def new_request_id() -> str:
    return uuid.uuid4().hex


def _key(request_id: str) -> str:
    return _RESULT_KEY.format(request_id=request_id)


async def _redis():
    global _redis_ok, _redis_checked_at
    now = time.time()
    if _redis_ok is False and (now - _redis_checked_at) < _REDIS_NEG_TTL:
        return None
    try:
        from app.core.infra.redis_client import redis_cli

        await asyncio.wait_for(redis_cli.ping(), timeout=0.4)
        _redis_ok = True
        _redis_checked_at = now
        return redis_cli
    except Exception as exc:
        _redis_ok = False
        _redis_checked_at = now
        logger.debug("page_fetch_bridge: Redis 不可用: %s", exc)
        return None


async def register_wait(request_id: str) -> None:
    async with _lock:
        _events[request_id] = asyncio.Event()
        _results.pop(request_id, None)


async def complete(request_id: str, result: dict[str, Any]) -> bool:
    payload = json.dumps(result, ensure_ascii=False, default=str)
    wrote_redis = False
    r = await _redis()
    if r is not None:
        try:
            await asyncio.wait_for(r.set(_key(request_id), payload, ex=_TTL_SECONDS), timeout=1.0)
            wrote_redis = True
        except Exception as exc:
            logger.error("page_fetch_bridge: Redis SET 失败: %s", exc)

    async with _lock:
        _results[request_id] = result
        evt = _events.get(request_id)
        if evt:
            evt.set()
            return True
    return wrote_redis


async def _read_redis(request_id: str) -> Optional[dict[str, Any]]:
    r = await _redis()
    if r is None:
        return None
    try:
        raw = await asyncio.wait_for(r.get(_key(request_id)), timeout=1.0)
        if not raw:
            return None
        await asyncio.wait_for(r.delete(_key(request_id)), timeout=1.0)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)
    except Exception as exc:
        logger.warning("page_fetch_bridge: Redis GET 失败: %s", exc)
        return None


async def wait_result(request_id: str, timeout: float) -> Optional[dict[str, Any]]:
    deadline = time.time() + max(1.0, timeout)

    while time.time() < deadline:
        cached = await _read_redis(request_id)
        if cached is not None:
            async with _lock:
                _events.pop(request_id, None)
                _results.pop(request_id, None)
            return cached

        async with _lock:
            if request_id in _results:
                result = _results.pop(request_id)
                _events.pop(request_id, None)
                return result
            evt = _events.get(request_id)

        remain = deadline - time.time()
        if remain <= 0:
            break
        if evt is not None:
            try:
                await asyncio.wait_for(evt.wait(), timeout=min(0.2, remain))
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(min(0.2, remain))

    await cancel(request_id)
    return None


async def cancel(request_id: str) -> None:
    r = await _redis()
    if r is not None:
        try:
            await asyncio.wait_for(r.delete(_key(request_id)), timeout=0.5)
        except Exception:
            pass
    async with _lock:
        _results.pop(request_id, None)
        evt = _events.pop(request_id, None)
        if evt:
            evt.set()
