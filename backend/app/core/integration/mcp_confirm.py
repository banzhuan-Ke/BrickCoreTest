"""MCP 危险操作二次确认 Token（Redis）"""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from app.core.infra.redis_client import redis_cli
from app.core.platform.encryption import decrypt_value, encrypt_value

CONFIRM_PREFIX = "mcp_confirm:"
CONFIRM_TTL_SECONDS = 300
_SEALED_KEY = "__sealed__"


def _seal_sensitive(payload: dict[str, Any], seal_keys: Optional[list[str]]) -> dict[str, Any]:
    """将指定字段加密后写入 payload，避免 Redis 明文存密钥。"""
    data = dict(payload or {})
    keys = [k for k in (seal_keys or []) if k in data and data.get(k) is not None]
    if not keys:
        return data
    sealed: dict[str, Any] = {}
    for key in keys:
        sealed[key] = data.pop(key)
    data[_SEALED_KEY] = encrypt_value(json.dumps(sealed, ensure_ascii=False))
    return data


def _unseal_sensitive(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    blob = data.pop(_SEALED_KEY, None)
    if not blob:
        return data
    try:
        sealed = json.loads(decrypt_value(str(blob)))
    except Exception as exc:
        raise ValueError("确认 Token 敏感载荷无法解密，请重新 preview") from exc
    if isinstance(sealed, dict):
        data.update(sealed)
    return data


async def create_confirm_token(
    action: str,
    payload: dict[str, Any],
    username: str,
    ttl: int = CONFIRM_TTL_SECONDS,
    seal_keys: Optional[list[str]] = None,
) -> str:
    token = uuid.uuid4().hex
    data = {
        "action": action,
        "payload": _seal_sensitive(payload, seal_keys),
        "username": username,
    }
    await redis_cli.setex(f"{CONFIRM_PREFIX}{token}", ttl, json.dumps(data, ensure_ascii=False))
    return token


async def _atomic_get_and_delete(key: str) -> Any:
    """原子取出并删除；优先 GETDEL，旧 Redis 回退 Lua。不再使用非原子 GET+DEL。"""
    try:
        return await redis_cli.getdel(key)
    except Exception:
        pass
    try:
        script = "local v=redis.call('GET', KEYS[1]); if v then redis.call('DEL', KEYS[1]) end; return v"
        return await redis_cli.eval(script, 1, key)
    except Exception as exc:
        raise ValueError("确认 Token 消费失败：Redis 不支持原子 GETDEL/Lua，请升级 Redis≥6.2") from exc


async def consume_confirm_token(token: str, action: str, username: Optional[str] = None) -> dict[str, Any]:
    key = f"{CONFIRM_PREFIX}{token}"
    raw = await _atomic_get_and_delete(key)
    if not raw:
        raise ValueError("确认 Token 无效或已过期，请重新执行 preview 操作")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("确认 Token 数据损坏") from exc
    if data.get("action") != action:
        raise ValueError(f"确认 Token 与操作不匹配，期望 {action}")
    if username and data.get("username") and data.get("username") != username:
        raise ValueError("确认 Token 与当前用户不匹配")
    return _unseal_sensitive(data.get("payload") or {})


async def peek_confirm_token(token: str, username: Optional[str] = None) -> dict[str, Any]:
    """只读确认 Token（不删除）；返回完整 data（含 action/payload/username）。"""
    key = f"{CONFIRM_PREFIX}{token}"
    raw = await redis_cli.get(key)
    if not raw:
        raise ValueError("确认 Token 无效或已过期，请重新执行 preview 操作")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("确认 Token 数据损坏") from exc
    if username and data.get("username") and data.get("username") != username:
        raise ValueError("确认 Token 与当前用户不匹配")
    if isinstance(data, dict) and isinstance(data.get("payload"), dict):
        data = dict(data)
        data["payload"] = _unseal_sensitive(data.get("payload") or {})
    return data if isinstance(data, dict) else {}
