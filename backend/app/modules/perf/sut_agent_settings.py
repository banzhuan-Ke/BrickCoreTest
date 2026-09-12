"""被测监控采集器运行参数（平台下发，经 activate/heartbeat）。"""
from __future__ import annotations

from typing import Any, Optional

DEFAULT_INTERVAL_SEC = 5
DEFAULT_UPLOAD_EVERY_SEC = 15
DEFAULT_BUFFER_HOURS = 48
MIN_INTERVAL_SEC = 2
MAX_INTERVAL_SEC = 60
MIN_BUFFER_HOURS = 1
MAX_BUFFER_HOURS = 168


def default_agent_settings() -> dict[str, int]:
    return {
        "interval_sec": DEFAULT_INTERVAL_SEC,
        "upload_every_sec": DEFAULT_UPLOAD_EVERY_SEC,
        "buffer_hours": DEFAULT_BUFFER_HOURS,
    }


def validate_agent_settings(raw: Any) -> Optional[dict[str, int]]:
    """规范化采集参数；None 表示清除平台覆盖。非法值抛 ValueError。"""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("agent_settings 须为对象或 null")
    if not raw:
        return None

    base = default_agent_settings()
    out = dict(base)
    for key in ("interval_sec", "upload_every_sec", "buffer_hours"):
        if key not in raw or raw[key] is None:
            continue
        try:
            out[key] = int(raw[key])
        except (TypeError, ValueError) as e:
            raise ValueError(f"{key} 须为整数") from e

    interval = out["interval_sec"]
    upload_every = out["upload_every_sec"]
    buffer_hours = out["buffer_hours"]
    if interval < MIN_INTERVAL_SEC or interval > MAX_INTERVAL_SEC:
        raise ValueError(f"interval_sec 须在 {MIN_INTERVAL_SEC}～{MAX_INTERVAL_SEC}")
    if upload_every < interval:
        raise ValueError("upload_every_sec 不能小于 interval_sec")
    if upload_every > 3600:
        raise ValueError("upload_every_sec 过大（最多 3600）")
    if buffer_hours < MIN_BUFFER_HOURS or buffer_hours > MAX_BUFFER_HOURS:
        raise ValueError(f"buffer_hours 须在 {MIN_BUFFER_HOURS}～{MAX_BUFFER_HOURS}")
    return {
        "interval_sec": interval,
        "upload_every_sec": upload_every,
        "buffer_hours": buffer_hours,
    }


def agent_settings_from_row(row) -> Optional[dict[str, int]]:
    raw = getattr(row, "agent_settings_json", None)
    if raw is None:
        return None
    try:
        return validate_agent_settings(raw)
    except ValueError:
        return None
