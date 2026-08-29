"""平台侧 datetime 归一化（Tortoise timezone=Asia/Shanghai + MySQL naive 墙钟）。"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

APP_TZ = ZoneInfo("Asia/Shanghai")


def now_app() -> datetime:
    """写入 Tortoise / MySQL DATETIME 的 naive 墙钟（Asia/Shanghai）。"""
    return datetime.now(APP_TZ).replace(tzinfo=None)


def as_utc(dt: datetime | None) -> datetime | None:
    """将 DB / Tortoise 读出的时间统一转为 UTC aware。"""
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        # MySQL DATETIME 常见为 Asia/Shanghai 墙钟 naive，勿当作 UTC
        dt = dt.replace(tzinfo=APP_TZ)
    return dt.astimezone(timezone.utc)
