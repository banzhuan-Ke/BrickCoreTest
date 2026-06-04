"""Runner 中间件账号隔离（Phase 6：按设备 scoped MQ / Redis 凭证）"""
from __future__ import annotations

import asyncio
import logging
import re
import secrets
from typing import Any
from urllib.parse import quote

import httpx
import redis.asyncio as aioredis

from app.core import config as settings

logger = logging.getLogger(__name__)

_RUNNER_MQ_TAG = "runner"
_REDIS_COMMANDS = (
    "+ping",
    "+publish",
    "+rpush",
    "+ltrim",
    "+del",
    "+set",
    "+get",
    "+multi",
    "+exec",
)


def is_middleware_isolation_enabled() -> bool:
    return settings.RUNNER_MIDDLEWARE_ISOLATION


def runner_mq_username(device_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", device_id)
    return f"runner_{safe}"[:255]


def runner_redis_username(device_id: str) -> str:
    return runner_mq_username(device_id)


def _queue_permission_regex(device_id: str) -> str:
    return f"^{re.escape(device_id)}$"


def _management_base_url() -> str:
    host = settings.MQ_MANAGEMENT_HOST
    port = settings.MQ_MANAGEMENT_PORT
    return f"http://{host}:{port}/api"


def _management_auth() -> tuple[str, str]:
    return settings.MQ_CONFIG["username"], settings.MQ_CONFIG["password"]


async def _ensure_mq_queue(device_id: str) -> None:
    """使用管理员账号声明设备队列（Runner 仅有 consume 权限）"""

    def _declare() -> None:
        import pika

        params = pika.ConnectionParameters(
            host=settings.MQ_CONFIG["host"],
            port=int(settings.MQ_CONFIG["port"]),
            credentials=pika.PlainCredentials(
                settings.MQ_CONFIG["username"],
                settings.MQ_CONFIG["password"],
            ),
            heartbeat=60,
        )
        conn = pika.BlockingConnection(params)
        try:
            channel = conn.channel()
            channel.queue_declare(queue=device_id, durable=True, auto_delete=False)
        finally:
            conn.close()

    await asyncio.to_thread(_declare)


async def _upsert_mq_user(device_id: str, username: str, password: str) -> None:
    queue_regex = _queue_permission_regex(device_id)
    vhost = quote(settings.MQ_VHOST, safe="")
    base = _management_base_url()
    auth = _management_auth()
    timeout = httpx.Timeout(15.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        user_resp = await client.put(
            f"{base}/users/{quote(username, safe='')}",
            json={"password": password, "tags": _RUNNER_MQ_TAG},
            auth=auth,
        )
        if user_resp.status_code not in (201, 204):
            raise RuntimeError(f"创建 MQ 用户失败 HTTP {user_resp.status_code}: {user_resp.text[:200]}")

        perm_resp = await client.put(
            f"{base}/permissions/{vhost}/{quote(username, safe='')}",
            json={
                "configure": queue_regex,
                "write": queue_regex,
                "read": queue_regex,
            },
            auth=auth,
        )
        if perm_resp.status_code not in (201, 204):
            raise RuntimeError(f"设置 MQ 权限失败 HTTP {perm_resp.status_code}: {perm_resp.text[:200]}")


async def _delete_mq_user(username: str) -> None:
    if not username:
        return
    base = _management_base_url()
    auth = _management_auth()
    timeout = httpx.Timeout(15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.delete(f"{base}/users/{quote(username, safe='')}", auth=auth)
        if resp.status_code not in (204, 404):
            logger.warning("删除 MQ 用户 %s 失败: HTTP %s %s", username, resp.status_code, resp.text[:200])


def _redis_admin_client() -> aioredis.Redis:
    cfg = settings.REDIS_CONFIG
    return aioredis.Redis(
        host=cfg["host"],
        port=int(cfg["port"]),
        db=int(cfg.get("db", 15)),
        password=cfg.get("password") or None,
        decode_responses=True,
    )


async def _upsert_redis_user(device_id: str, username: str, password: str) -> None:
    client = _redis_admin_client()
    try:
        args: list[Any] = [
            "ACL",
            "SETUSER",
            username,
            "reset",
            "on",
            f">{password}",
            f"~{device_id}:*",
            f"&{device_id}:*",
            *_REDIS_COMMANDS,
        ]
        await client.execute_command(*args)
    finally:
        await client.aclose()


async def _delete_redis_user(username: str) -> None:
    if not username:
        return
    client = _redis_admin_client()
    try:
        await client.execute_command("ACL", "DELUSER", username)
    except Exception as exc:
        logger.warning("删除 Redis ACL 用户 %s 失败: %s", username, exc)
    finally:
        await client.aclose()


async def provision_device_middleware(device_id: str) -> dict[str, Any]:
    """
    为设备创建/轮换 scoped 中间件凭证。
    返回 mq / redis 连接片段（不含 host/port/db）。
    """
    if not is_middleware_isolation_enabled():
        mq = settings.MQ_CONFIG
        redis = settings.REDIS_CONFIG
        return {
            "mq_username": mq["username"],
            "mq_password": mq["password"],
            "redis_username": "",
            "redis_password": redis.get("password") or "",
        }

    mq_user = runner_mq_username(device_id)
    redis_user = runner_redis_username(device_id)
    password = secrets.token_urlsafe(24)

    await _ensure_mq_queue(device_id)
    await _upsert_mq_user(device_id, mq_user, password)
    await _upsert_redis_user(device_id, redis_user, password)

    logger.info("已为设备 %s 轮换中间件凭证 (mq_user=%s)", device_id, mq_user)
    return {
        "mq_username": mq_user,
        "mq_password": password,
        "redis_username": redis_user,
        "redis_password": password,
    }


async def revoke_device_middleware(
    device_id: str,
    *,
    mq_username: str = "",
    redis_username: str = "",
) -> None:
    """下线或删除设备时吊销 scoped 凭证"""
    if not is_middleware_isolation_enabled():
        return

    mq_user = mq_username or runner_mq_username(device_id)
    redis_user = redis_username or runner_redis_username(device_id)
    await _delete_mq_user(mq_user)
    await _delete_redis_user(redis_user)
    logger.info("已吊销设备 %s 中间件凭证", device_id)
