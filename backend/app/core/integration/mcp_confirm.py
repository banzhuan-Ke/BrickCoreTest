"""MCP 危险操作二次确认 Token（Redis）"""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from app.core.infra.redis_client import redis_cli

CONFIRM_PREFIX = "mcp_confirm:"
CONFIRM_TTL_SECONDS = 300


async def create_confirm_token(
    action: str,
    payload: dict[str, Any],
    username: str,
    ttl: int = CONFIRM_TTL_SECONDS,
) -> str:
    token = uuid.uuid4().hex
    data = {
        "action": action,
        "payload": payload,
        "username": username,
    }
    await redis_cli.setex(f"{CONFIRM_PREFIX}{token}", ttl, json.dumps(data, ensure_ascii=False))
    return token


async def consume_confirm_token(token: str, action: str, username: Optional[str] = None) -> dict[str, Any]:
    key = f"{CONFIRM_PREFIX}{token}"
    raw = await redis_cli.get(key)
    if not raw:
        raise ValueError("确认 Token 无效或已过期，请重新执行 preview 操作")
    await redis_cli.delete(key)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("确认 Token 数据损坏") from exc
    if data.get("action") != action:
        raise ValueError(f"确认 Token 与操作不匹配，期望 {action}")
    if username and data.get("username") and data.get("username") != username:
        raise ValueError("确认 Token 与当前用户不匹配")
    return data.get("payload") or {}
