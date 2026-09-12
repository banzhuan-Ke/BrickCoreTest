"""App 设备 UDID 互斥锁：Inspector 与用例执行不可同时使用同一真机"""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import HTTPException

from app.core.infra.redis_client import redis_cli

LOCK_PREFIX = "app_device_lock:"
LOCK_TTL_SECONDS = 7200

_HOLDER_LABELS = {
    "inspector": "Inspector 调试",
    "exec": "用例执行",
    "apm": "设备性能监控",
}

# Lua：仅当 holder 匹配时 expire / delete，避免误操作他人锁
_REFRESH_LUA = """
local v = redis.call('GET', KEYS[1])
if not v then return 0 end
if string.find(v, ARGV[1], 1, true) and string.find(v, ARGV[2], 1, true) then
  return redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
end
return 0
"""

_RELEASE_LUA = """
local v = redis.call('GET', KEYS[1])
if not v then return 0 end
if string.find(v, ARGV[1], 1, true) and string.find(v, ARGV[2], 1, true) then
  return redis.call('DEL', KEYS[1])
end
return 0
"""

_RENEW_LUA = """
local v = redis.call('GET', KEYS[1])
if not v then return 0 end
if string.find(v, ARGV[1], 1, true) and string.find(v, ARGV[2], 1, true) then
  redis.call('SET', KEYS[1], ARGV[4])
  return redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
end
return 0
"""


def _holder_markers(holder_type: str, holder_id: str) -> tuple[str, str]:
    # 与 json.dumps 默认分隔符对齐：': '
    return f'"holder_type": "{holder_type}"', f'"holder_id": "{holder_id}"'


def _lock_key(udid: str) -> str:
    return f"{LOCK_PREFIX}{(udid or '').strip()}"


def resolve_exec_lock_holder_id(suite_payload: dict[str, Any]) -> str:
    """计划级执行共用 plan_execution_id 锁，避免同设备多套件 dispatch 409。"""
    if suite_payload.get("plan_execution_id"):
        return str(suite_payload["plan_execution_id"])
    if suite_payload.get("suite_execution_id"):
        return str(suite_payload["suite_execution_id"])
    cases = suite_payload.get("cases") or []
    if cases and cases[0].get("execution_id"):
        return str(cases[0]["execution_id"])
    return str(suite_payload.get("case_execution_id") or "")


async def get_device_lock(udid: str) -> Optional[dict[str, Any]]:
    udid = (udid or "").strip()
    if not udid:
        return None
    raw = await redis_cli.get(_lock_key(udid))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def acquire_device_lock(
    udid: str,
    *,
    holder_type: str,
    holder_id: str,
    username: str = "",
    ttl_seconds: int | None = None,
) -> None:
    udid = (udid or "").strip()
    if not udid:
        return
    holder_type = (holder_type or "").strip().lower()
    holder_id = str(holder_id or "").strip()
    if not holder_type or not holder_id:
        return

    ttl = int(ttl_seconds or LOCK_TTL_SECONDS)
    if ttl < 60:
        ttl = LOCK_TTL_SECONDS

    key = _lock_key(udid)
    payload = {
        "app_udid": udid,
        "holder_type": holder_type,
        "holder_id": holder_id,
        "username": username or "",
    }
    payload_json = json.dumps(payload, ensure_ascii=False)

    # 最多两轮 NX：禁止在「键刚好过期」窗口用无 NX 的 SETEX 抢锁
    for _ in range(2):
        acquired = await redis_cli.set(key, payload_json, nx=True, ex=ttl)
        if acquired:
            return

        existing = await get_device_lock(udid)
        if not existing:
            # 竞态：读到空后再试一次 NX，仍失败则交给外层 409
            continue

        same = existing.get("holder_type") == holder_type and str(existing.get("holder_id")) == holder_id
        if same:
            ht, hid = _holder_markers(holder_type, holder_id)
            try:
                ok = await redis_cli.eval(_RENEW_LUA, 1, key, ht, hid, str(ttl), payload_json)
                if ok:
                    return
            except Exception:
                # 回退也必须 NX：仅当仍是自己或键已空时续写
                reacquired = await redis_cli.set(key, payload_json, nx=True, ex=ttl)
                if reacquired:
                    return
                existing2 = await get_device_lock(udid)
                if (
                    existing2
                    and existing2.get("holder_type") == holder_type
                    and str(existing2.get("holder_id")) == holder_id
                ):
                    await redis_cli.expire(key, ttl)
                    return
            existing = await get_device_lock(udid) or existing
            if (
                existing
                and existing.get("holder_type") == holder_type
                and str(existing.get("holder_id")) == holder_id
            ):
                return

        label = _HOLDER_LABELS.get((existing or {}).get("holder_type"), (existing or {}).get("holder_type"))
        raise HTTPException(
            status_code=409,
            detail=f"设备 {udid} 正被「{label}」占用，请等待其结束或关闭 Inspector 后再试",
        )

    raise HTTPException(
        status_code=409,
        detail=f"设备 {udid} 正被占用，请稍后重试",
    )


async def refresh_device_lock(
    udid: str,
    *,
    holder_type: str,
    holder_id: str,
    ttl_seconds: int | None = None,
) -> None:
    udid = (udid or "").strip()
    if not udid:
        return
    holder_type = (holder_type or "").strip().lower()
    holder_id = str(holder_id or "").strip()
    ttl = int(ttl_seconds or LOCK_TTL_SECONDS)
    ht, hid = _holder_markers(holder_type, holder_id)
    try:
        await redis_cli.eval(_REFRESH_LUA, 1, _lock_key(udid), ht, hid, str(ttl))
    except Exception:
        existing = await get_device_lock(udid)
        if not existing:
            return
        if existing.get("holder_type") == holder_type and str(existing.get("holder_id")) == str(holder_id):
            await redis_cli.expire(_lock_key(udid), ttl)


async def release_device_lock(udid: str, *, holder_type: str, holder_id: str) -> None:
    udid = (udid or "").strip()
    if not udid:
        return
    holder_type = (holder_type or "").strip().lower()
    holder_id = str(holder_id or "").strip()
    ht, hid = _holder_markers(holder_type, holder_id)
    try:
        await redis_cli.eval(_RELEASE_LUA, 1, _lock_key(udid), ht, hid)
    except Exception:
        existing = await get_device_lock(udid)
        if not existing:
            return
        if existing.get("holder_type") == holder_type and str(existing.get("holder_id")) == str(holder_id):
            await redis_cli.delete(_lock_key(udid))


async def release_device_lock_by_holder(holder_type: str, holder_id: str) -> None:
    """按持有者释放锁（会话过期时 Inspector 仍须释放）。"""
    holder_type = (holder_type or "").strip().lower()
    holder_id = str(holder_id or "").strip()
    if not holder_type or not holder_id:
        return
    # 扫描代价可接受：单设备通常仅一把锁
    async for key in redis_cli.scan_iter(match=f"{LOCK_PREFIX}*"):
        raw = await redis_cli.get(key)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if data.get("holder_type") == holder_type and str(data.get("holder_id")) == holder_id:
            await redis_cli.delete(key)
            return


async def release_device_lock_by_udid(udid: str) -> None:
    udid = (udid or "").strip()
    if udid:
        await redis_cli.delete(_lock_key(udid))


async def release_device_locks_for_holder(holder_type: str, holder_id: str) -> int:
    """按持有者释放所有设备锁（计划并行多 UDID 场景）。"""
    holder_type = (holder_type or "").strip().lower()
    holder_id = str(holder_id or "").strip()
    if not holder_type or not holder_id:
        return 0
    released = 0
    async for key in redis_cli.scan_iter(match=f"{LOCK_PREFIX}*"):
        raw = await redis_cli.get(key)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if data.get("holder_type") == holder_type and str(data.get("holder_id")) == holder_id:
            await redis_cli.delete(key)
            released += 1
    return released
