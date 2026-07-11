"""压测执行进度计算（本地聚合与分布式秒级上报共用）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.modules.stream_phase import normalize_perf_mode, STREAM_BURST_MODE
from app.modules.perf.perf_journey import JOURNEY_FIXED_MODE, JOURNEY_LOOP_MODE, normalize_journey_config


def normalize_distribution_mode(mode: Optional[str]) -> str:
    m = (mode or "weighted_random").strip()
    if m in ("random_weight", "weighted_random"):
        return "weighted_random"
    if m == "fixed_ratio":
        return "fixed_ratio"
    return "weighted_random"


def compute_running_progress(config: dict, time_series: List[dict]) -> Optional[Dict[str, Any]]:
    """根据配置与（合并后的）秒级时序计算进度。"""
    if not time_series:
        return None
    mode = normalize_perf_mode(config.get("mode", "fixed"))
    latest = time_series[-1]
    elapsed = float(latest.get("timestamp") or 0)

    if mode == "loop":
        loop_total = int(config.get("loop_count") or 100) * int(config.get("concurrent_users") or 1)
        current = sum(int(p.get("qps") or 0) for p in time_series)
        return {
            "mode": mode,
            "current": current,
            "total": loop_total,
            "percentage": round(min(100, current / loop_total * 100), 1) if loop_total > 0 else 0,
        }

    if mode == JOURNEY_LOOP_MODE:
        loop_total = int(config.get("loop_count") or 100) * int(config.get("concurrent_users") or 1)
        journey = normalize_journey_config(config)
        steps_per_journey = max(
            1,
            sum(len(p.get("steps") or []) for p in journey.get("phases") or []),
        )
        total_req = sum(int(p.get("qps") or 0) for p in time_series)
        current = min(loop_total, total_req // steps_per_journey)
        return {
            "mode": mode,
            "current": current,
            "total": loop_total,
            "percentage": round(min(100, current / loop_total * 100), 1) if loop_total > 0 else 0,
        }

    if mode in (STREAM_BURST_MODE, "sse_burst"):
        burst_total = int(config.get("concurrent_users") or 1)
        current = sum(int(p.get("qps") or 0) for p in time_series)
        return {
            "mode": STREAM_BURST_MODE,
            "current": current,
            "total": burst_total,
            "percentage": round(min(100, current / burst_total * 100), 1) if burst_total > 0 else 0,
        }

    if mode == "stepping":
        steps = config.get("steps") or []
        total_d = sum(int(s.get("duration") or 30) for s in steps) or 60
        pct = min(100, round(elapsed / total_d * 100, 1))
        return {
            "mode": "stepping",
            "current": round(elapsed, 1),
            "total": total_d,
            "percentage": pct,
        }

    if mode == JOURNEY_FIXED_MODE:
        duration = int(config.get("duration_seconds") or 60)
        pct = min(100, round(elapsed / duration * 100, 1))
        return {
            "mode": mode,
            "current": round(elapsed, 1),
            "total": duration,
            "percentage": pct,
        }

    duration = int(config.get("duration_seconds") or 60)
    pct = min(100, round(elapsed / duration * 100, 1))
    return {
        "mode": mode if mode == "fixed" else "fixed",
        "current": round(elapsed, 1),
        "total": duration,
        "percentage": pct,
    }
