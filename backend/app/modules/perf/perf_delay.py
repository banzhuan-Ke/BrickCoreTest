"""压测请求间隔（think time）：固定或随机区间。

与 runner/tools/perf_delay.py 保持一致；改动后请同步另一份，并由
tests/test_perf_sot_sync.py 约束。
"""
from __future__ import annotations

import random
from typing import Any


def resolve_delay_seconds(item: Any) -> float:
    """
    根据场景项 / 链路步骤配置返回 sleep 秒数。
    - delay_mode=fixed（默认）：使用 delay_ms
    - delay_mode=random：在 [delay_ms_min, delay_ms_max] 上均匀抽样（毫秒）
    """
    if not isinstance(item, dict):
        return 0.0
    mode = str(item.get("delay_mode") or "fixed").strip().lower()
    if mode == "random":
        try:
            lo = max(0, int(item.get("delay_ms_min") or 0))
        except (TypeError, ValueError):
            lo = 0
        try:
            hi = max(0, int(item.get("delay_ms_max") or 0))
        except (TypeError, ValueError):
            hi = 0
        if hi < lo:
            lo, hi = hi, lo
        if hi <= 0:
            return 0.0
        if lo == hi:
            return lo / 1000.0
        return random.uniform(lo, hi) / 1000.0
    try:
        ms = max(0, int(item.get("delay_ms") or 0))
    except (TypeError, ValueError):
        ms = 0
    return ms / 1000.0
