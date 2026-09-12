"""被测监控采集器简易内存限流（单进程；多副本各自计数，仍可挡住单机滥用）。"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException

_lock = threading.Lock()
_buckets: Dict[str, Deque[float]] = defaultdict(deque)


def check_rate_limit(key: str, *, max_calls: int, window_sec: float) -> None:
    """超限抛 429。"""
    if max_calls <= 0 or window_sec <= 0:
        return
    now = time.monotonic()
    cutoff = now - window_sec
    with _lock:
        q = _buckets[key]
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= max_calls:
            raise HTTPException(
                status_code=429,
                detail=f"请求过于频繁，请稍后再试（{int(window_sec)}s 内最多 {max_calls} 次）",
            )
        q.append(now)
