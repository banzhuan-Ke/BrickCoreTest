"""设备实时日志发布（Backend 使用管理员 Redis，供 Runner HTTP 上报）"""
from __future__ import annotations

import logging

from app.core.infra.redis_client import redis_cli

logger = logging.getLogger(__name__)

MAX_HISTORY = 1000


async def publish_device_log_line(device_id: str, line: str) -> None:
    if not device_id or not line:
        return
    channel = f"{device_id}:log"
    history_key = f"{device_id}:history_logs"
    try:
        await redis_cli.publish(channel, line)
        await redis_cli.rpush(history_key, line)
        await redis_cli.ltrim(history_key, -MAX_HISTORY, -1)
    except Exception as exc:
        logger.warning("发布设备日志失败 device=%s: %s", device_id, exc)


async def publish_device_screen(device_id: str, image_base64: str, *, cache: bool = True) -> None:
    """发布设备屏幕帧（JPEG base64），供 WebSocket 实时画面使用。"""
    if not device_id or not image_base64:
        return
    channel = f"{device_id}:screen"
    cache_key = f"{device_id}:cached_image"
    try:
        await redis_cli.publish(channel, image_base64)
        if cache:
            await redis_cli.set(cache_key, image_base64, ex=120)
    except Exception as exc:
        logger.warning("发布设备画面失败 device=%s: %s", device_id, exc)
