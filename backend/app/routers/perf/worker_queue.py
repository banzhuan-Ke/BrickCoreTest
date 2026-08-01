"""压测 Worker 任务队列（优先 Redis）。

多进程 / 多副本部署必须共用 Redis。默认 Redis 不可用时拒绝派发（失败关闭），
仅当环境变量 PERF_ALLOW_INMEMORY_WORKER_QUEUE=1 时允许单机内存兜底。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_TASK_KEY = "perf:worker_task:{worker_id}"
_TASK_TTL = 3600

_ALLOW_MEMORY = os.getenv("PERF_ALLOW_INMEMORY_WORKER_QUEUE", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# 进程内兜底（仅 PERF_ALLOW_INMEMORY_WORKER_QUEUE 开启时）
_memory_queue: dict[int, dict] = {}
_memory_events: dict[int, asyncio.Event] = {}


def _key(worker_id: int) -> str:
    return _TASK_KEY.format(worker_id=worker_id)


async def _redis():
    try:
        from app.core.infra.redis_client import redis_cli
        await redis_cli.ping()
        return redis_cli
    except Exception as exc:
        logger.warning("perf worker queue: Redis 不可用: %s", exc)
        return None


async def assign_task(worker_id: int, task: dict) -> bool:
    """为 Worker 写入待领取任务。已有待领取任务时拒绝覆盖，返回 False。"""
    payload = json.dumps(task, ensure_ascii=False, default=str)
    r = await _redis()
    if r is not None:
        try:
            ok = await r.set(_key(worker_id), payload, nx=True, ex=_TASK_TTL)
            if not ok:
                return False
            evt = _memory_events.get(worker_id)
            if evt:
                evt.set()
            return True
        except Exception as exc:
            logger.error("perf worker queue Redis SET 失败: %s", exc)
            if not _ALLOW_MEMORY:
                return False

    if not _ALLOW_MEMORY:
        logger.error(
            "Redis 不可用且未设置 PERF_ALLOW_INMEMORY_WORKER_QUEUE=1，拒绝派发任务 worker_id=%s",
            worker_id,
        )
        return False

    if worker_id in _memory_queue:
        return False
    _memory_queue[worker_id] = task
    evt = _memory_events.get(worker_id)
    if evt:
        evt.set()
    return True


async def clear_task(worker_id: int) -> None:
    """取消尚未领取的任务（部分下发失败时回滚）。"""
    r = await _redis()
    if r is not None:
        try:
            await r.delete(_key(worker_id))
        except Exception as exc:
            logger.warning("perf worker queue Redis DELETE 失败: %s", exc)
    _memory_queue.pop(worker_id, None)
    evt = _memory_events.get(worker_id)
    if evt:
        evt.set()


async def take_task(worker_id: int) -> Optional[dict]:
    """取出并移除 Worker 的待领取任务。"""
    r = await _redis()
    if r is not None:
        try:
            raw = await r.getdel(_key(worker_id))
            if raw is not None:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                return json.loads(raw)
        except Exception as exc:
            try:
                raw = await r.get(_key(worker_id))
                if raw is not None:
                    await r.delete(_key(worker_id))
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    return json.loads(raw)
            except Exception as exc2:
                logger.warning("perf worker queue Redis GET 失败: %s / %s", exc, exc2)

    if _ALLOW_MEMORY:
        return _memory_queue.pop(worker_id, None)
    return None


async def has_pending_task(worker_id: int) -> bool:
    r = await _redis()
    if r is not None:
        try:
            return bool(await r.exists(_key(worker_id)))
        except Exception:
            pass
    if _ALLOW_MEMORY:
        return worker_id in _memory_queue
    return False


def memory_wait_event(worker_id: int) -> asyncio.Event:
    evt = asyncio.Event()
    _memory_events[worker_id] = evt
    return evt


def clear_memory_wait(worker_id: int) -> None:
    _memory_events.pop(worker_id, None)


async def wait_for_task(worker_id: int, timeout: float) -> Optional[dict]:
    """长轮询：优先轮询 Redis，并兼听内存 Event。"""
    task = await take_task(worker_id)
    if task:
        return task

    evt = memory_wait_event(worker_id)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(1.0, float(timeout))
    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            slice_sec = min(0.5, remaining)
            try:
                await asyncio.wait_for(evt.wait(), timeout=slice_sec)
            except asyncio.TimeoutError:
                pass
            task = await take_task(worker_id)
            if task:
                return task
            if evt.is_set():
                evt.clear()
    finally:
        clear_memory_wait(worker_id)

    return await take_task(worker_id)
