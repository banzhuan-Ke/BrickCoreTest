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
}


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
) -> None:
    udid = (udid or "").strip()
    if not udid:
        return
    holder_type = (holder_type or "").strip().lower()
    holder_id = str(holder_id or "").strip()
    if not holder_type or not holder_id:
        return

    key = _lock_key(udid)
    payload = {
        "app_udid": udid,
        "holder_type": holder_type,
        "holder_id": holder_id,
        "username": username or "",
    }
    payload_json = json.dumps(payload, ensure_ascii=False)

    acquired = await redis_cli.set(key, payload_json, nx=True, ex=LOCK_TTL_SECONDS)
    if acquired:
        return

    existing = await get_device_lock(udid)
    if existing:
        same = existing.get("holder_type") == holder_type and str(existing.get("holder_id")) == holder_id
        if same:
            await redis_cli.setex(key, LOCK_TTL_SECONDS, payload_json)
            return
        label = _HOLDER_LABELS.get(existing.get("holder_type"), existing.get("holder_type"))
        raise HTTPException(
            status_code=409,
            detail=f"设备 {udid} 正被「{label}」占用，请等待其结束或关闭 Inspector 后再试",
        )

    await redis_cli.setex(key, LOCK_TTL_SECONDS, payload_json)


async def refresh_device_lock(udid: str, *, holder_type: str, holder_id: str) -> None:
    udid = (udid or "").strip()
    if not udid:
        return
    existing = await get_device_lock(udid)
    if not existing:
        return
    if existing.get("holder_type") == holder_type and str(existing.get("holder_id")) == str(holder_id):
        await redis_cli.expire(_lock_key(udid), LOCK_TTL_SECONDS)


async def release_device_lock(udid: str, *, holder_type: str, holder_id: str) -> None:
    udid = (udid or "").strip()
    if not udid:
        return
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
