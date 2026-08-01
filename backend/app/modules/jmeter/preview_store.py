"""Redis-backed preview token store for JMeter import."""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from app.core.infra.redis_client import redis_cli

PREVIEW_PREFIX = "jmeter_import_preview:"
PREVIEW_TTL_SECONDS = 30 * 60


async def save_preview(
    *,
    project_id: int,
    username: str,
    catalog_id: Optional[int],
    ir: dict[str, Any],
    preview: dict[str, Any],
    ttl: int = PREVIEW_TTL_SECONDS,
) -> str:
    token = uuid.uuid4().hex
    payload = {
        "project_id": project_id,
        "username": username,
        "catalog_id": catalog_id,
        "ir": ir,
        "preview": preview,
    }
    await redis_cli.setex(
        f"{PREVIEW_PREFIX}{token}",
        ttl,
        json.dumps(payload, ensure_ascii=False),
    )
    return token


async def consume_preview(
    token: str,
    *,
    project_id: int,
    username: str,
) -> dict[str, Any]:
    key = f"{PREVIEW_PREFIX}{token}"
    raw = await redis_cli.get(key)
    if not raw:
        raise ValueError("预览 Token 无效或已过期，请重新上传解析")
    await redis_cli.delete(key)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("预览 Token 数据损坏") from exc
    if int(data.get("project_id") or 0) != int(project_id):
        raise ValueError("预览 Token 与项目不匹配")
    if data.get("username") and data.get("username") != username:
        raise ValueError("预览 Token 与当前用户不匹配")
    return data
