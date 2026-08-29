"""接口套件整包经 Worker：分批回传桥接（内存 + Redis）。"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

_STATE_KEY = "perf:api_suite_state:{suite_run_id}"
_TTL_SECONDS = 3600

_states: dict[str, "SuiteRunState"] = {}
_lock = asyncio.Lock()

_redis_ok: Optional[bool] = None
_redis_checked_at = 0.0
_REDIS_NEG_TTL = 15.0


def new_suite_run_id() -> str:
    return uuid.uuid4().hex


def _key(suite_run_id: str) -> str:
    return _STATE_KEY.format(suite_run_id=suite_run_id)


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
        logger.debug("api_suite_bridge: Redis 不可用: %s", exc)
        return None


@dataclass
class SuiteRunState:
    suite_run_id: str
    total: int
    items: dict[int, dict[str, Any]] = field(default_factory=dict)
    batch_ids: set[str] = field(default_factory=set)
    done: bool = False
    stopped_at: Optional[int] = None
    finished_count: Optional[int] = None
    fatal_error: Optional[str] = None
    event: asyncio.Event = field(default_factory=asyncio.Event)

    def expected_count(self) -> Optional[int]:
        if self.stopped_at is not None:
            return int(self.stopped_at) + 1
        if self.finished_count is not None:
            return int(self.finished_count)
        if self.done:
            return int(self.total)
        return None

    def is_complete(self) -> bool:
        if self.fatal_error and self.done:
            return True
        if not self.done:
            return False
        expected = self.expected_count()
        if expected is None:
            return False
        if expected == 0:
            return True
        for i in range(expected):
            if i not in self.items:
                return False
        return True

    def snapshot(self) -> dict[str, Any]:
        return {
            "suite_run_id": self.suite_run_id,
            "total": self.total,
            "items": {str(k): v for k, v in self.items.items()},
            "batch_ids": list(self.batch_ids),
            "done": self.done,
            "stopped_at": self.stopped_at,
            "finished_count": self.finished_count,
            "fatal_error": self.fatal_error,
        }

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> "SuiteRunState":
        items = {}
        for k, v in (data.get("items") or {}).items():
            try:
                items[int(k)] = v
            except (TypeError, ValueError):
                continue
        return cls(
            suite_run_id=str(data.get("suite_run_id") or ""),
            total=int(data.get("total") or 0),
            items=items,
            batch_ids=set(str(x) for x in (data.get("batch_ids") or [])),
            done=bool(data.get("done")),
            stopped_at=data.get("stopped_at"),
            finished_count=data.get("finished_count"),
            fatal_error=data.get("fatal_error"),
        )

    def merge_from(self, other: "SuiteRunState") -> None:
        self.items.update(other.items)
        self.batch_ids |= other.batch_ids
        self.done = self.done or other.done
        if other.stopped_at is not None:
            self.stopped_at = other.stopped_at
        if other.finished_count is not None:
            self.finished_count = other.finished_count
        if other.fatal_error:
            self.fatal_error = other.fatal_error
        if other.total and self.total <= 0:
            self.total = other.total


async def register_suite(suite_run_id: str, total: int) -> None:
    state = SuiteRunState(suite_run_id=suite_run_id, total=max(0, int(total)))
    async with _lock:
        _states[suite_run_id] = state
    await _persist(state)


async def _persist(state: SuiteRunState) -> None:
    r = await _redis()
    if r is None:
        return
    try:
        payload = json.dumps(state.snapshot(), ensure_ascii=False, default=str)
        await asyncio.wait_for(r.set(_key(state.suite_run_id), payload, ex=_TTL_SECONDS), timeout=1.0)
    except Exception as exc:
        logger.warning("api_suite_bridge: Redis SET 失败: %s", exc)


async def _load_redis(suite_run_id: str) -> Optional[SuiteRunState]:
    r = await _redis()
    if r is None:
        return None
    try:
        raw = await asyncio.wait_for(r.get(_key(suite_run_id)), timeout=1.0)
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return SuiteRunState.from_snapshot(json.loads(raw))
    except Exception as exc:
        logger.warning("api_suite_bridge: Redis GET 失败: %s", exc)
        return None


async def _delete_redis(suite_run_id: str) -> None:
    r = await _redis()
    if r is None:
        return
    try:
        await asyncio.wait_for(r.delete(_key(suite_run_id)), timeout=0.5)
    except Exception:
        pass


async def ingest_batch(
    suite_run_id: str,
    *,
    batch_id: str,
    total: int,
    items: list[dict[str, Any]],
    done: bool = False,
    stopped_at: Optional[int] = None,
    finished_count: Optional[int] = None,
    error: Optional[str] = None,
) -> bool:
    """写入一批结果。同 batch_id 幂等。done 可早于最后一批。"""
    rid = str(suite_run_id or "").strip()
    bid = str(batch_id or "").strip()
    if not rid:
        return False

    loaded = await _load_redis(rid)
    async with _lock:
        state = _states.get(rid)
        if state is None:
            if loaded is None:
                return False
            state = loaded
            state.event = asyncio.Event()
            _states[rid] = state
        elif loaded is not None:
            state.merge_from(loaded)

        if total and state.total <= 0:
            state.total = int(total)

        is_dup = bool(bid and bid in state.batch_ids)
        if bid and not is_dup:
            state.batch_ids.add(bid)
        if not is_dup:
            for raw in items or []:
                if not isinstance(raw, dict):
                    continue
                try:
                    idx = int(raw.get("index"))
                except (TypeError, ValueError):
                    continue
                state.items[idx] = raw

        if done:
            state.done = True
        if stopped_at is not None:
            try:
                state.stopped_at = int(stopped_at)
            except (TypeError, ValueError):
                pass
        if finished_count is not None:
            try:
                state.finished_count = int(finished_count)
            except (TypeError, ValueError):
                pass
        if error:
            state.fatal_error = str(error)
            state.done = True

        if state.done or state.is_complete():
            state.event.set()
        snap = state.snapshot()
        evt_set = state.is_complete()

    await _persist(SuiteRunState.from_snapshot(snap))
    return True


async def wait_suite(suite_run_id: str, timeout: float) -> Optional[SuiteRunState]:
    """等到齐包；超时返回 None（调用方丢弃已收批）。支持 done 早到后继续收晚到批。"""
    rid = str(suite_run_id or "").strip()
    deadline = time.time() + max(1.0, float(timeout))

    while time.time() < deadline:
        loaded = await _load_redis(rid)
        async with _lock:
            state = _states.get(rid)
            if state is None and loaded is not None:
                state = loaded
                state.event = asyncio.Event()
                _states[rid] = state
            elif state is not None and loaded is not None:
                state.merge_from(loaded)

            if state is not None and state.is_complete():
                out = SuiteRunState(
                    suite_run_id=state.suite_run_id,
                    total=state.total,
                    items=dict(state.items),
                    batch_ids=set(state.batch_ids),
                    done=state.done,
                    stopped_at=state.stopped_at,
                    finished_count=state.finished_count,
                    fatal_error=state.fatal_error,
                )
                _states.pop(rid, None)
                await _delete_redis(rid)
                return out
            evt = state.event if state else None
            if state is not None and state.done and not state.is_complete():
                # done 早到：重置 event 等后续 ingest 再 set
                if evt is not None and evt.is_set():
                    state.event = asyncio.Event()
                    evt = state.event

        remain = deadline - time.time()
        if remain <= 0:
            break
        if evt is not None:
            try:
                await asyncio.wait_for(evt.wait(), timeout=min(0.35, remain))
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(min(0.35, remain))

    await cancel_suite(rid)
    return None


async def cancel_suite(suite_run_id: str) -> None:
    rid = str(suite_run_id or "").strip()
    await _delete_redis(rid)
    async with _lock:
        state = _states.pop(rid, None)
        if state:
            state.event.set()
