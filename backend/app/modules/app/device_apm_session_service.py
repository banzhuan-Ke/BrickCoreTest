"""独立设备性能监控会话（Redis 状态 + 秒级点；停后可落库）。"""

from __future__ import annotations

import json
import logging
import math
import time
import uuid
from typing import Any, Dict, List, Optional, Set

from app.core.infra.redis_client import redis_cli
from app.modules.app.device_apm import (
    DEFAULT_THRESHOLDS,
    downsample_series,
    normalize_thresholds,
)

logger = logging.getLogger(__name__)

SESSION_PREFIX = "app_device_apm:session:"
POINTS_PREFIX = "app_device_apm:points:"
UDID_INDEX_PREFIX = "app_device_apm:udid:"
ACTIVE_SET_KEY = "app_device_apm:active"
BATCH_SEEN_PREFIX = "app_device_apm:batch:"
PERSIST_PENDING_SET = "app_device_apm:persist_pending"
HEARTBEAT_PREFIX = "app_device_apm:hb:"
DEFAULT_SESSION_TTL_SECONDS = 7200
MAX_SESSION_TTL_SECONDS = 90000  # ~25h，覆盖 24h duration + grace
STOPPING_STALE_MS = 90_000
STARTING_STALE_MS = 180_000
BATCH_SEEN_TTL_SECONDS = 7200
FINAL_REDIS_TTL_SECONDS = 3600  # 终态后缩短保留，仅留手动补写窗口
PERSIST_FAIL_TTL_SECONDS = 86400  # 落库失败延长保留，供后台轻量补偿
PERSIST_RETRY_BATCH = 20  # 每次扫描最多补偿条数，控制服务器压力
# 手动会话：无 points 心跳超过该时间才算僵死（默认与 session TTL 对齐）
RUNNING_IDLE_STALE_MS = DEFAULT_SESSION_TTL_SECONDS * 1000

_ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    "starting": {"running", "stopping", "failed", "finished"},
    "running": {"stopping", "finished", "failed"},
    "stopping": {"finished", "failed"},
    "finished": set(),
    "failed": set(),
}

# 仅当 value 与期望完全一致时写入，避免连接池下 WATCH 跨连接失效
_CAS_SET_LUA = """
local cur = redis.call('GET', KEYS[1])
if not cur then return -1 end
if tostring(cur) ~= tostring(ARGV[1]) then return 0 end
redis.call('SETEX', KEYS[1], tonumber(ARGV[2]), ARGV[3])
return 1
"""

_BIND_UDID_LUA = """
local cur = redis.call('GET', KEYS[1])
if not cur then
  redis.call('SETEX', KEYS[1], tonumber(ARGV[2]), ARGV[1])
  return 1
end
if tostring(cur) == tostring(ARGV[1]) then
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
  return 1
end
return 0
"""

# KEYS[1]=points KEYS[2]=batch(optional empty key unused)
# ARGV: batch_id, n, cap, points_ttl, batch_ttl, point_json...
# 先检查 batch，再 RPUSH+LTRIM+EXPIRE，最后标记 batch —— 同脚本原子
_APPEND_POINTS_LUA = """
local batch_id = tostring(ARGV[1] or '')
local batch_key = KEYS[2]
if batch_id ~= '' then
  if redis.call('EXISTS', batch_key) == 1 then
    return 0
  end
end
local n = tonumber(ARGV[2]) or 0
local cap = tonumber(ARGV[3]) or 600
local points_ttl = tonumber(ARGV[4]) or 7200
local batch_ttl = tonumber(ARGV[5]) or 7200
local accepted = 0
for i = 1, n do
  redis.call('RPUSH', KEYS[1], ARGV[5 + i])
  accepted = accepted + 1
end
if accepted > 0 then
  redis.call('LTRIM', KEYS[1], -cap, -1)
  redis.call('EXPIRE', KEYS[1], points_ttl)
end
if batch_id ~= '' then
  redis.call('SET', batch_key, '1', 'EX', batch_ttl)
end
return accepted
"""


def _as_str(raw: Any) -> str:
    if isinstance(raw, (bytes, bytearray)):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def session_ttl_seconds(duration_sec: float = 0) -> int:
    """session / points / lock TTL：基于 duration + grace，至少 2h。"""
    try:
        dur = float(duration_sec or 0)
    except (TypeError, ValueError):
        dur = 0.0
    if dur <= 0:
        return DEFAULT_SESSION_TTL_SECONDS
    return int(min(MAX_SESSION_TTL_SECONDS, max(DEFAULT_SESSION_TTL_SECONDS, dur + 900)))


def starting_lock_ttl_seconds(duration_sec: float = 0) -> int:
    """启动阶段用较短锁；首批 points 后再按 duration 续期。"""
    full = session_ttl_seconds(duration_sec)
    boot = int(STARTING_STALE_MS / 1000) + 60
    return int(min(full, max(120, boot)))


def max_live_points(*, interval_ms: int = 1000, duration_sec: float = 0) -> int:
    """live 点上限：按 interval/duration 估算，封顶避免 Redis 暴涨。"""
    try:
        interval = max(200, int(interval_ms or 1000))
    except (TypeError, ValueError):
        interval = 1000
    try:
        dur = float(duration_sec or 0)
    except (TypeError, ValueError):
        dur = 0.0
    window_sec = dur if dur > 0 else float(DEFAULT_SESSION_TTL_SECONDS)
    n = int(math.ceil(window_sec * 1000.0 / interval)) + 50
    return int(min(max(n, 600), 18000))


def _session_key(session_id: str) -> str:
    return f"{SESSION_PREFIX}{session_id}"


def _points_key(session_id: str) -> str:
    return f"{POINTS_PREFIX}{session_id}"


def _udid_index_key(udid: str) -> str:
    return f"{UDID_INDEX_PREFIX}{(udid or '').strip()}"


def _batch_key(session_id: str, batch_id: str) -> str:
    return f"{BATCH_SEEN_PREFIX}{session_id}:{batch_id}"


def _ttl_of(data: Dict[str, Any]) -> int:
    status = str(data.get("status") or "")
    if status in ("finished", "failed"):
        return FINAL_REDIS_TTL_SECONDS
    return session_ttl_seconds(float(data.get("duration_sec") or 0))


async def _track_active(session_id: str) -> None:
    if session_id:
        await redis_cli.sadd(ACTIVE_SET_KEY, session_id)


async def _untrack_active(session_id: str) -> None:
    if session_id:
        await redis_cli.srem(ACTIVE_SET_KEY, session_id)


async def list_active_session_ids() -> List[str]:
    raw = await redis_cli.smembers(ACTIVE_SET_KEY)
    out: List[str] = []
    for item in raw or []:
        sid = item.decode() if isinstance(item, (bytes, bytearray)) else str(item)
        if sid:
            out.append(sid)
    return out


async def _track_persist_pending(session_id: str) -> None:
    if not session_id:
        return
    await redis_cli.sadd(PERSIST_PENDING_SET, session_id)
    # 落库失败时延长 session/points 保留，避免 1h 后无法补偿
    try:
        await redis_cli.expire(_session_key(session_id), PERSIST_FAIL_TTL_SECONDS)
        await redis_cli.expire(_points_key(session_id), PERSIST_FAIL_TTL_SECONDS)
    except Exception:
        pass


async def _clear_persist_pending(session_id: str) -> None:
    if session_id:
        await redis_cli.srem(PERSIST_PENDING_SET, session_id)


async def clear_persist_pending(session_id: str) -> None:
    await _clear_persist_pending(session_id)


async def list_persist_pending_session_ids(*, limit: int = PERSIST_RETRY_BATCH) -> List[str]:
    """轻量读取待落库补偿会话，限制条数避免扫描打满 Redis。"""
    cap = max(1, min(int(limit or PERSIST_RETRY_BATCH), 50))
    raw = await redis_cli.srandmember(PERSIST_PENDING_SET, cap)
    if not raw:
        return []
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    out: List[str] = []
    for item in raw:
        sid = item.decode() if isinstance(item, (bytes, bytearray)) else str(item)
        if sid:
            out.append(sid)
    return out

async def bind_udid_session(udid: str, session_id: str, *, ttl: int) -> bool:
    """绑定 UDID→session；已绑定其他会话时返回 False。"""
    udid = (udid or "").strip()
    if not udid or not session_id:
        return False
    try:
        rc = await redis_cli.eval(
            _BIND_UDID_LUA,
            1,
            _udid_index_key(udid),
            str(session_id),
            str(int(ttl)),
        )
        return int(rc or 0) == 1
    except Exception:
        # 回退：仅空键可写
        key = _udid_index_key(udid)
        ok = await redis_cli.set(key, session_id, nx=True, ex=int(ttl))
        if ok:
            return True
        cur = await redis_cli.get(key)
        if cur and _as_str(cur) == str(session_id):
            await redis_cli.expire(key, int(ttl))
            return True
        return False


async def clear_udid_session(udid: str, session_id: str | None = None) -> None:
    udid = (udid or "").strip()
    if not udid:
        return
    key = _udid_index_key(udid)
    if session_id:
        script = """
        local cur = redis.call('GET', KEYS[1])
        if not cur then return 0 end
        if tostring(cur) == tostring(ARGV[1]) then
          return redis.call('DEL', KEYS[1])
        end
        return 0
        """
        try:
            await redis_cli.eval(script, 1, key, str(session_id))
            return
        except Exception:
            cur = await redis_cli.get(key)
            if cur and str(cur) != str(session_id):
                return
    await redis_cli.delete(key)


async def get_session_id_by_udid(udid: str) -> Optional[str]:
    raw = await redis_cli.get(_udid_index_key((udid or "").strip()))
    if not raw:
        return None
    return str(raw)


async def create_session(
    *,
    project_id: int,
    device_id: str,
    app_udid: str,
    pkg_name: str,
    username: str = "",
    interval_ms: int = 1000,
    metrics: Optional[List[str]] = None,
    thresholds: Optional[Dict[str, Any]] = None,
    duration_sec: float = 0,
) -> Dict[str, Any]:
    session_id = uuid.uuid4().hex
    ttl = session_ttl_seconds(duration_sec)
    data: Dict[str, Any] = {
        "session_id": session_id,
        "project_id": project_id,
        "device_id": device_id,
        "app_udid": app_udid,
        "pkg_name": pkg_name,
        "username": username or "",
        "interval_ms": interval_ms,
        "metrics": list(metrics or []),
        "thresholds": normalize_thresholds(thresholds),
        "duration_sec": float(duration_sec or 0),
        "status": "starting",
        "error": None,
        "summary": None,
        "series": None,
        "created_at_ms": int(time.time() * 1000),
        "updated_at_ms": int(time.time() * 1000),
        "stop_requested_at_ms": None,
    }
    await redis_cli.setex(_session_key(session_id), ttl, json.dumps(data, ensure_ascii=False))
    await redis_cli.delete(_points_key(session_id))
    bound = await bind_udid_session(app_udid, session_id, ttl=ttl)
    if not bound:
        await redis_cli.delete(_session_key(session_id))
        await redis_cli.delete(_points_key(session_id))
        raise ValueError(f"设备 {app_udid} 已有活跃性能监控会话")
    await _track_active(session_id)
    return data


async def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    raw = await redis_cli.get(_session_key(session_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _apply_session_patch(data: Dict[str, Any], fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """应用字段补丁；非法状态迁移时丢弃 status。无有效变更返回 None。"""
    patch = dict(fields)
    new_status = patch.get("status")
    if new_status is not None:
        cur = str(data.get("status") or "")
        nxt = str(new_status)
        if nxt != cur and nxt not in _ALLOWED_TRANSITIONS.get(cur, set()):
            patch = {k: v for k, v in patch.items() if k != "status"}
            if not patch:
                return None
    out = dict(data)
    out.update(patch)
    out["updated_at_ms"] = int(time.time() * 1000)
    return out


async def update_session(session_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    """CAS 更新：比较整包 JSON，避免 touch/final 互相覆盖。"""
    key = _session_key(session_id)
    for _ in range(8):
        raw = await redis_cli.get(key)
        if not raw:
            return None
        try:
            data = json.loads(_as_str(raw))
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        patched = _apply_session_patch(data, fields)
        if patched is None:
            return data
        new_raw = json.dumps(patched, ensure_ascii=False)
        ttl = _ttl_of(patched)
        try:
            rc = await redis_cli.eval(_CAS_SET_LUA, 1, key, _as_str(raw), str(ttl), new_raw)
        except Exception:
            logger.exception("update_session CAS eval failed session=%s", session_id)
            break
        code = int(rc if rc is not None else 0)
        if code == 1:
            if str(patched.get("status") or "") in ("finished", "failed"):
                await _untrack_active(session_id)
            return patched
        if code == -1:
            return None
        # code == 0：并发写入，重试
    # CAS 耗尽后禁止非原子 SETEX，避免用过期快照覆盖 finished/failed
    logger.warning("update_session CAS exhausted session=%s fields=%s", session_id, list(fields.keys()))
    return None


async def mark_running(session_id: str) -> Optional[Dict[str, Any]]:
    data = await get_session(session_id)
    if not data:
        return None
    if str(data.get("status") or "") in ("stopping", "finished", "failed"):
        return data
    return await update_session(session_id, status="running", error=None)


async def mark_stopping(session_id: str) -> Optional[Dict[str, Any]]:
    data = await get_session(session_id)
    if not data:
        return None
    # 已在 stopping：勿重置 stop_requested_at_ms，否则推迟 stale finalize
    if str(data.get("status") or "") == "stopping":
        return data
    return await update_session(
        session_id,
        status="stopping",
        stop_requested_at_ms=int(time.time() * 1000),
    )


def _heartbeat_key(session_id: str) -> str:
    return f"{HEARTBEAT_PREFIX}{session_id}"


async def touch_session_ttl(session_id: str) -> Optional[Dict[str, Any]]:
    """points 上报时只刷新 TTL + 心跳，禁止重写 session value（避免覆盖 final）。"""
    data = await get_session(session_id)
    if not data:
        return None
    ttl = _ttl_of(data)
    await redis_cli.expire(_session_key(session_id), ttl)
    await redis_cli.expire(_points_key(session_id), ttl)
    # 独立心跳：手动监控 duration=0 时 touch 不改 updated_at，靠此判断活跃
    try:
        await redis_cli.setex(_heartbeat_key(session_id), ttl, str(int(time.time() * 1000)))
    except Exception:
        pass
    return data


async def _last_activity_ms(session_id: str, data: Dict[str, Any]) -> int:
    updated = int(data.get("updated_at_ms") or data.get("created_at_ms") or 0)
    try:
        raw = await redis_cli.get(_heartbeat_key(session_id))
        if raw:
            hb = int(_as_str(raw))
            if hb > updated:
                return hb
    except Exception:
        pass
    return updated


async def append_points(
    session_id: str,
    points: List[Dict[str, Any]],
    *,
    batch_id: str | None = None,
) -> int:
    if not points:
        return 0
    data = await get_session(session_id)
    if not data:
        return 0
    status = str(data.get("status") or "")
    if status in ("finished", "failed"):
        return 0

    bid = str(batch_id or "").strip()
    key = _points_key(session_id)
    batch_key = _batch_key(session_id, bid) if bid else f"{BATCH_SEEN_PREFIX}_unused"
    ttl = _ttl_of(data)
    # batch 标记与 session 同寿，避免 24h 会话中 2h 后幂等失效
    batch_ttl = max(BATCH_SEEN_TTL_SECONDS, ttl)
    cap = max_live_points(
        interval_ms=int(data.get("interval_ms") or 1000),
        duration_sec=float(data.get("duration_sec") or 0),
    )
    seen_ts: set[int] = set()
    try:
        tail = await redis_cli.lrange(key, -80, -1)
        for raw in tail or []:
            try:
                item = json.loads(raw)
                if isinstance(item, dict) and item.get("ts_ms") is not None:
                    seen_ts.add(int(item["ts_ms"]))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
    except Exception:
        pass

    payloads: List[str] = []
    for p in points:
        if not isinstance(p, dict):
            continue
        try:
            ts = int(p.get("ts_ms") or 0)
        except (TypeError, ValueError):
            ts = 0
        if ts and ts in seen_ts:
            continue
        if ts:
            seen_ts.add(ts)
        payloads.append(json.dumps(p, ensure_ascii=False))
    if not payloads and not bid:
        return 0

    try:
        accepted = await redis_cli.eval(
            _APPEND_POINTS_LUA,
            2,
            key,
            batch_key,
            bid,
            str(len(payloads)),
            str(cap),
            str(ttl),
            str(batch_ttl),
            *payloads,
        )
        accepted = int(accepted or 0)
    except Exception:
        logger.exception("append_points Lua failed session=%s; fallback without pre-mark", session_id)
        # 回退：先抢 batch NX，成功再写点；抢不到说明并发已处理
        if bid:
            claimed = await redis_cli.set(batch_key, "1", nx=True, ex=batch_ttl)
            if not claimed:
                return 0
        accepted = 0
        try:
            for raw_p in payloads:
                await redis_cli.rpush(key, raw_p)
                accepted += 1
            if accepted:
                await redis_cli.ltrim(key, -cap, -1)
                await redis_cli.expire(key, ttl)
        except Exception:
            # 写失败则删掉 batch 标记，允许重试
            if bid:
                try:
                    await redis_cli.delete(batch_key)
                except Exception:
                    pass
            raise
    if accepted:
        await touch_session_ttl(session_id)
    return accepted


async def get_points(
    session_id: str,
    *,
    after_ts_ms: int | None = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    key = _points_key(session_id)
    # after_ts 时也只扫尾部窗口，避免每次 LRANGE 全量
    if after_ts_ms is not None:
        lookback = 800
        if limit and limit > 0:
            lookback = max(lookback, int(limit) * 2)
        raw_list = await redis_cli.lrange(key, -lookback, -1)
    elif limit and limit > 0:
        raw_list = await redis_cli.lrange(key, -int(limit), -1)
    else:
        raw_list = await redis_cli.lrange(key, 0, -1)
    out: List[Dict[str, Any]] = []
    for raw in raw_list or []:
        try:
            item = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(item, dict):
            continue
        ts = int(item.get("ts_ms") or 0)
        if after_ts_ms is not None and ts <= int(after_ts_ms):
            continue
        out.append(item)
    if limit and limit > 0 and len(out) > limit:
        out = out[-limit:]
    return out


async def apply_final(
    session_id: str,
    *,
    summary: Optional[Dict[str, Any]],
    series: Optional[List[Dict[str, Any]]],
    thresholds: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    data = await get_session(session_id)
    if not data:
        return None
    cur = str(data.get("status") or "")
    if cur in ("finished", "failed"):
        return data
    summary_out = dict(summary or {})
    thr = normalize_thresholds(thresholds or data.get("thresholds") or summary_out.get("thresholds"))
    summary_out["thresholds"] = thr
    series_list = list(series or [])
    if not series_list:
        # 限流：stale/空 series 时最多回填 300 点（与 downsample 上限一致），避免全量 LRANGE
        series_list = await get_points(session_id, limit=300)
        if series_list:
            summary_out.setdefault("partial_data", True)
            notes = summary_out.get("quality_notes")
            if not isinstance(notes, dict):
                notes = {}
            notes = dict(notes)
            notes["series_fallback"] = "rebuilt from redis live points (capped)"
            summary_out["quality_notes"] = notes
    series_out = downsample_series(series_list)
    status = "failed" if error else "finished"
    err = (str(error)[:500] if error else None)
    updated = await update_session(
        session_id,
        status=status,
        error=err,
        summary=summary_out,
        series=series_out,
        thresholds=thr,
    )
    if updated is None:
        # CAS 失败：仅当并发已写入终态时做清理；否则不释锁/不拆索引
        cur2 = await get_session(session_id)
        if cur2 and str(cur2.get("status") or "") in ("finished", "failed"):
            try:
                await redis_cli.expire(_points_key(session_id), FINAL_REDIS_TTL_SECONDS)
            except Exception:
                pass
            await clear_udid_session(str(cur2.get("app_udid") or data.get("app_udid") or ""), session_id)
            await _untrack_active(session_id)
            try:
                await redis_cli.delete(_heartbeat_key(session_id))
            except Exception:
                pass
            return cur2
        logger.warning("apply_final CAS failed and session not terminal session=%s", session_id)
        return None

    try:
        await redis_cli.expire(_points_key(session_id), FINAL_REDIS_TTL_SECONDS)
    except Exception:
        pass
    await clear_udid_session(str(data.get("app_udid") or ""), session_id)
    await _untrack_active(session_id)
    try:
        await redis_cli.delete(_heartbeat_key(session_id))
    except Exception:
        pass
    return updated


async def persist_session_to_db(session: Dict[str, Any]) -> str:
    """将终态会话写入 DB。返回 ok|already|error:..."""
    from app.models.app import AppDeviceApmSession

    session_id = str(session.get("session_id") or "").strip()
    if not session_id:
        return "error: missing session_id"
    status = str(session.get("status") or "")
    if status not in ("finished", "failed"):
        return "error: not terminal"
    try:
        await AppDeviceApmSession.update_or_create(
            defaults={
                "project_id": int(session.get("project_id") or 0),
                "device_id": str(session.get("device_id") or ""),
                "app_udid": str(session.get("app_udid") or ""),
                "pkg_name": str(session.get("pkg_name") or "")[:255],
                "status": status,
                "interval_ms": int(session.get("interval_ms") or 1000),
                "metrics": session.get("metrics") or [],
                "thresholds": session.get("thresholds"),
                "summary": session.get("summary"),
                "series": session.get("series"),
                "error": (str(session.get("error") or "")[:500] or None),
                "username": str(session.get("username") or ""),
                "is_del": False,
            },
            id=session_id,
        )
        # 落库成功清 persist_error
        if session.get("persist_error"):
            await update_session(session_id, persist_error=None)
        await _clear_persist_pending(session_id)
        return "ok"
    except Exception as exc:
        msg = str(exc)[:200]
        await update_session(session_id, persist_error=msg)
        await _track_persist_pending(session_id)
        logger.exception("APM persist_session_to_db failed session=%s", session_id)
        return f"error:{msg}"

async def fail_if_stale(session_id: str) -> Optional[Dict[str, Any]]:
    """stopping/starting/running 过久无 final → failed。"""
    data = await get_session(session_id)
    if not data:
        await _untrack_active(session_id)
        return None
    status = str(data.get("status") or "")
    now = int(time.time() * 1000)
    updated = int(data.get("updated_at_ms") or data.get("created_at_ms") or 0)
    stop_at = int(data.get("stop_requested_at_ms") or updated)

    async def _finalize_stale(error: str) -> Optional[Dict[str, Any]]:
        live_points = await get_points(session_id, limit=300)
        existing_series = data.get("series") if isinstance(data.get("series"), list) else []
        series = existing_series or live_points or []
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        if not summary:
            summary = {
                "partial_data": True,
                "sample_count": len(series),
                "first_ts_ms": (series[0] or {}).get("ts_ms") if series else None,
                "last_ts_ms": (series[-1] or {}).get("ts_ms") if series else None,
            }
        return await apply_final(
            session_id,
            summary=summary,
            series=series,
            thresholds=data.get("thresholds") if isinstance(data.get("thresholds"), dict) else None,
            error=error,
        )

    if status == "stopping" and now - stop_at > STOPPING_STALE_MS:
        return await _finalize_stale("stale: no final after stop")
    if status == "starting" and now - updated > STARTING_STALE_MS:
        return await _finalize_stale("stale: runner never started")
    if status == "running":
        dur = float(data.get("duration_sec") or 0)
        last_active = await _last_activity_ms(session_id, data)
        # 核心：有 points 心跳则不杀（修复手动会话 touch 不刷新 updated_at 的误杀）
        if now - last_active > RUNNING_IDLE_STALE_MS:
            return await _finalize_stale("stale: session idle without points")
        if dur > 0:
            created = int(data.get("created_at_ms") or updated or 0)
            grace_ms = int((dur + 900) * 1000)
            # 已超过计划时长，且短时间无心跳 → Runner 可能已挂
            if created and now - created > grace_ms and now - last_active > STOPPING_STALE_MS:
                return await _finalize_stale("stale: session expired without final")
    return data


async def close_session(session_id: str) -> None:
    data = await get_session(session_id)
    await redis_cli.delete(_session_key(session_id))
    await redis_cli.delete(_points_key(session_id))
    try:
        await redis_cli.delete(_heartbeat_key(session_id))
    except Exception:
        pass
    await _untrack_active(session_id)
    if data:
        await clear_udid_session(str(data.get("app_udid") or ""), session_id)


async def prepare_udid_for_new_session(udid: str, *, project_id: int, username: str = "") -> Optional[Dict[str, Any]]:
    """若该 UDID 已有活跃会话：同项目则返回可恢复会话；已 stale 则清理并返回 None。"""
    sid = await get_session_id_by_udid(udid)
    if not sid:
        return None
    data = await fail_if_stale(sid)
    if not data:
        data = await get_session(sid)
    if not data:
        await clear_udid_session(udid, sid)
        return None
    status = str(data.get("status") or "")
    if status in ("finished", "failed"):
        await clear_udid_session(udid, sid)
        return None
    if int(data.get("project_id") or 0) == int(project_id):
        return data
    return {"_conflict": True, "session": data}


def public_session_view(session: Dict[str, Any], *, points: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    return {
        "session_id": session.get("session_id"),
        "project_id": session.get("project_id"),
        "device_id": session.get("device_id"),
        "app_udid": session.get("app_udid"),
        "pkg_name": session.get("pkg_name"),
        "interval_ms": session.get("interval_ms"),
        "metrics": session.get("metrics") or [],
        "thresholds": session.get("thresholds") or dict(DEFAULT_THRESHOLDS),
        "duration_sec": session.get("duration_sec") or 0,
        "status": session.get("status"),
        "error": session.get("error"),
        "persist_error": session.get("persist_error"),
        "summary": session.get("summary"),
        "series": session.get("series"),
        "points": points if points is not None else [],
        "created_at_ms": session.get("created_at_ms"),
        "updated_at_ms": session.get("updated_at_ms"),
    }
