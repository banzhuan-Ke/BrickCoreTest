"""从压测时序推断真实施压窗（相对时间轴对齐用）。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.core.platform.datetime_utils import app_dt_to_epoch_ms, as_utc


def _to_epoch_ms(value: Any) -> Optional[int]:
    """
    将时间转为 Unix epoch ms。

    平台 Tortoise/MySQL 的 naive datetime 是 Asia/Shanghai 墙钟，
    必须走 as_utc / app_dt_to_epoch_ms，禁止当作 UTC。
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = int(value)
        # 秒级时间戳兜底
        if v < 10_000_000_000:
            return v * 1000
        return v
    if isinstance(value, datetime):
        return app_dt_to_epoch_ms(value)
    if isinstance(value, str) and value.strip():
        try:
            s = value.strip().replace("Z", "+00:00")
            if "T" in s or "+" in s[-6:] or s.endswith("+00:00"):
                dt = datetime.fromisoformat(s)
            else:
                # "YYYY-MM-DD HH:MM:SS" → 平台墙钟
                dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
            if dt.tzinfo is None:
                return app_dt_to_epoch_ms(dt)
            utc = as_utc(dt)
            return int(utc.timestamp() * 1000) if utc else None
        except (TypeError, ValueError):
            return None
    return None


def _point_qps(item: dict[str, Any]) -> float:
    # 只用吞吐类字段，避免 cumulative total_req 误判施压窗
    for key in ("qps", "success_qps"):
        try:
            v = float(item.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if v > 0:
            return v
    return 0.0


def infer_pressure_window(
    time_series: Optional[list],
    *,
    started_at: Any = None,
    ended_at: Any = None,
    duration_sec: Optional[float] = None,
    load_started_ms: Any = None,
    load_stopped_ms: Any = None,
    drain_until_ms: Any = None,
) -> dict[str, Any]:
    """
    优先用 Runner 上报的真实负载窗（load_started_ms / load_stopped_ms）；
    其次用 time_series 中首尾非零 QPS；最后回退记录开始/结束。

    注意：QPS 是完成吞吐而非请求发起时间，高 RT 下可能晚于真实负载起点，
    故仅作 fallback。

    返回:
      start_ms, end_ms, source: load|qps|record|unknown,
      note: 给人看的提示；若有 drain_until_ms 另附观察窗提示
    """
    started_ms = _to_epoch_ms(started_at)
    ended_ms = _to_epoch_ms(ended_at)
    if ended_ms is None and started_ms is not None and duration_sec:
        try:
            ended_ms = started_ms + int(float(duration_sec) * 1000)
        except (TypeError, ValueError):
            pass

    load_start = _to_epoch_ms(load_started_ms)
    load_stop = _to_epoch_ms(load_stopped_ms)
    drain_ms = _to_epoch_ms(drain_until_ms)
    if load_stop is None and drain_ms is not None:
        load_stop = drain_ms
    if load_start is not None and load_stop is not None and load_stop >= load_start:
        note = "施压窗由执行机上报的真实负载起止时间确定"
        if drain_ms is not None and drain_ms > load_stop:
            note += f"；drain 观察至 {drain_ms}"
        return {
            "start_ms": load_start,
            "end_ms": load_stop if drain_ms is None else max(load_stop, drain_ms),
            "source": "load",
            "note": note,
            "load_started_ms": load_start,
            "load_stopped_ms": load_stop,
            "drain_until_ms": drain_ms,
        }

    series = [p for p in (time_series or []) if isinstance(p, dict)]
    if series:
        first_idx = None
        last_idx = None
        for i, p in enumerate(series):
            if _point_qps(p) > 0:
                if first_idx is None:
                    first_idx = i
                last_idx = i
        if first_idx is not None and last_idx is not None:
            def _abs_ms(p: dict[str, Any], fallback_offset_sec: float) -> Optional[int]:
                for key in ("absolute_ts_ms", "ts_ms", "epoch_ms"):
                    ms = _to_epoch_ms(p.get(key))
                    if ms is not None:
                        return ms
                if started_ms is not None:
                    try:
                        offset = float(p.get("timestamp") if p.get("timestamp") is not None else fallback_offset_sec)
                    except (TypeError, ValueError):
                        offset = fallback_offset_sec
                    return started_ms + int(offset * 1000)
                return None

            start_ms = _abs_ms(series[first_idx], float(first_idx))
            end_ms = _abs_ms(series[last_idx], float(last_idx))
            if start_ms is not None and end_ms is not None and end_ms >= start_ms:
                # 末点再扩 1s，覆盖该秒内采样
                return {
                    "start_ms": start_ms,
                    "end_ms": end_ms + 1000,
                    "source": "qps",
                    "note": (
                        "施压窗由 QPS 时序首尾非零点推断（完成吞吐，非请求发起；"
                        "高 RT 时起点可能偏晚，基线可能略被污染）"
                    ),
                }

    if started_ms is not None and ended_ms is not None and ended_ms >= started_ms:
        return {
            "start_ms": started_ms,
            "end_ms": ended_ms,
            "source": "record",
            "note": "未能从 QPS 推断施压窗，已回退到记录开始/结束时间（可能含排队等待段）",
        }

    if started_ms is not None:
        end = ended_ms or (started_ms + int(float(duration_sec or 0) * 1000) or started_ms)
        return {
            "start_ms": started_ms,
            "end_ms": max(started_ms, end),
            "source": "record",
            "note": "施压窗信息不完整，已尽量用记录时间回退",
        }

    return {
        "start_ms": None,
        "end_ms": None,
        "source": "unknown",
        "note": "无法确定施压时间窗",
    }
