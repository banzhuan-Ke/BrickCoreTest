"""压测秒级上报共享存储（优先 Redis，保证多 Backend 副本可见）。

默认 Redis 不可用时拒绝写入（失败关闭），与任务队列一致；
仅当环境变量 PERF_ALLOW_INMEMORY_WORKER_REPORTS=1 时允许单机内存兜底。
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_REPORT_KEY = "perf:worker_report:{record_id}:{worker_id}"
_INDEX_KEY = "perf:worker_report_index:{record_id}"
_TTL = 7200

_ALLOW_MEMORY = os.getenv("PERF_ALLOW_INMEMORY_WORKER_REPORTS", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# 单机兜底（仅 PERF_ALLOW_INMEMORY_WORKER_REPORTS 开启时）
_memory_reports: dict[int, dict[int, list]] = {}


async def _redis():
    try:
        from app.core.infra.redis_client import redis_cli
        await redis_cli.ping()
        return redis_cli
    except Exception as exc:
        logger.warning("perf worker reports: Redis 不可用: %s", exc)
        return None


def _report_key(record_id: int, worker_id: int) -> str:
    return _REPORT_KEY.format(record_id=record_id, worker_id=worker_id)


def _index_key(record_id: int) -> str:
    return _INDEX_KEY.format(record_id=record_id)


def _mem_bucket(record_id: int) -> dict[int, list]:
    if record_id not in _memory_reports:
        _memory_reports[record_id] = {}
    return _memory_reports[record_id]


def memory_fallback_enabled() -> bool:
    return _ALLOW_MEMORY


async def append_report(record_id: int, worker_id: int, point: dict) -> bool:
    """追加一条秒级上报点。成功返回 True；Redis 不可用且未开内存兜底时返回 False。"""
    payload = json.dumps(point, ensure_ascii=False, default=str)
    r = await _redis()
    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.rpush(_report_key(record_id, worker_id), payload)
            pipe.expire(_report_key(record_id, worker_id), _TTL)
            pipe.sadd(_index_key(record_id), worker_id)
            pipe.expire(_index_key(record_id), _TTL)
            await pipe.execute()
            return True
        except Exception as exc:
            logger.error("perf worker reports Redis 写入失败: %s", exc)
            if not _ALLOW_MEMORY:
                return False

    if not _ALLOW_MEMORY:
        logger.error(
            "Redis 不可用且未设置 PERF_ALLOW_INMEMORY_WORKER_REPORTS=1，拒绝秒级上报 record=%s worker=%s",
            record_id,
            worker_id,
        )
        return False

    bucket = _mem_bucket(record_id)
    bucket.setdefault(worker_id, []).append(point)
    return True


async def load_all_reports(record_id: int) -> dict[int, list]:
    """加载某 record 下全部 Worker 的秒级点列。"""
    result: dict[int, list] = {}
    r = await _redis()
    if r is not None:
        try:
            raw_ids = await r.smembers(_index_key(record_id))
            worker_ids: list[int] = []
            for x in raw_ids or []:
                if isinstance(x, bytes):
                    x = x.decode("utf-8")
                try:
                    worker_ids.append(int(x))
                except (TypeError, ValueError):
                    continue
            for wid in worker_ids:
                rows = await r.lrange(_report_key(record_id, wid), 0, -1)
                points = []
                for row in rows or []:
                    if isinstance(row, bytes):
                        row = row.decode("utf-8")
                    try:
                        points.append(json.loads(row))
                    except Exception:
                        continue
                if points:
                    result[wid] = points
            if result:
                return result
        except Exception as exc:
            logger.error("perf worker reports Redis 读取失败: %s", exc)
            if not _ALLOW_MEMORY:
                return {}

    if not _ALLOW_MEMORY:
        return {}

    mem = _memory_reports.get(record_id) or {}
    return {wid: list(pts) for wid, pts in mem.items()}


async def clear_reports(record_id: int) -> None:
    r = await _redis()
    if r is not None:
        try:
            raw_ids = await r.smembers(_index_key(record_id))
            keys = [_index_key(record_id)]
            for x in raw_ids or []:
                if isinstance(x, bytes):
                    x = x.decode("utf-8")
                try:
                    wid = int(x)
                except (TypeError, ValueError):
                    continue
                keys.append(_report_key(record_id, wid))
            if keys:
                await r.delete(*keys)
        except Exception as exc:
            logger.warning("perf worker reports Redis 清理失败: %s", exc)
    _memory_reports.pop(record_id, None)
