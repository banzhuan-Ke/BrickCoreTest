"""连接探测（TCP 可达性）"""
from __future__ import annotations

import socket
from typing import Any


def tcp_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    if not host or not port:
        return False
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def probe_connect_bundle(connect_data: dict[str, Any] | None) -> dict[str, bool]:
    if not connect_data:
        return {"mq": False, "redis": False}
    mq = connect_data.get("mq") or {}
    redis = connect_data.get("redis") or {}
    return {
        "mq": tcp_reachable(str(mq.get("host", "")), int(mq.get("port") or 0)),
        "redis": tcp_reachable(str(redis.get("host", "")), int(redis.get("port") or 0)),
    }
