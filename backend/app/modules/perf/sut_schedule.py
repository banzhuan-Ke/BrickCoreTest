"""被测监控日程：当前是否允许采样。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo


def _parse_hm(s: str) -> Optional[int]:
    try:
        parts = str(s).split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (TypeError, ValueError, IndexError):
        return None


def _day_matches(configured_days: Any, python_weekday: int) -> bool:
    """days 约定：Python weekday，周一=0 … 周日=6（与 datetime.weekday 一致）。"""
    if configured_days is None:
        return True
    if not isinstance(configured_days, (list, tuple)):
        return True
    raw: set[int] = set()
    for d in configured_days:
        try:
            raw.add(int(d))
        except (TypeError, ValueError):
            continue
    if not raw:
        return True
    return python_weekday in raw


def _in_time_windows(windows: list, local: datetime) -> bool:
    """
    days 表示窗口**起始日**。
    若 start > end（跨午夜），则延续到次日凌晨，次日后半夜仍归属起始日的 days。
    """
    if not windows:
        return False
    hm = local.hour * 60 + local.minute
    weekday = local.weekday()
    prev_weekday = (weekday - 1) % 7
    for w in windows:
        if not isinstance(w, dict):
            continue
        start_m = _parse_hm(w.get("start") or "00:00")
        end_m = _parse_hm(w.get("end") or "23:59")
        if start_m is None or end_m is None:
            continue
        days = w.get("days")
        if start_m <= end_m:
            # 同日窗口：当前星期 ∩ [start, end)
            if not _day_matches(days, weekday):
                continue
            if start_m <= hm < end_m:
                return True
        else:
            # 跨午夜：起始日 [start, 24:00) 或 次日 [00:00, end)
            if hm >= start_m and _day_matches(days, weekday):
                return True
            if hm < end_m and _day_matches(days, prev_weekday):
                return True
    return False


def is_monitoring_allowed(
    *,
    monitoring_enabled: bool,
    schedule: Optional[dict[str, Any]] = None,
    force_until_ms: Optional[int] = None,
    force_from_ms: Optional[int] = None,
    now: Optional[datetime] = None,
) -> bool:
    """
    1. monitoring_enabled=False → 不采
    2. force 窗口覆盖 now → 强制采（历史点用 from/until；仅 until 时表示未过期才强制）
    3. schedule.mode: always | windows | pause_windows
    """
    if not monitoring_enabled:
        return False

    tz_default = ZoneInfo("Asia/Shanghai")
    now = now or datetime.now(tz=tz_default)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz_default)

    now_ms = int(now.timestamp() * 1000)
    if force_until_ms is not None:
        try:
            until = int(force_until_ms)
            if force_from_ms is not None:
                if int(force_from_ms) <= now_ms <= until:
                    return True
            elif until > now_ms:
                return True
        except (TypeError, ValueError):
            pass

    if not schedule or not isinstance(schedule, dict):
        return True

    mode = (schedule.get("mode") or "always").strip().lower()
    tz_name = schedule.get("timezone") or "Asia/Shanghai"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = tz_default
    local = now.astimezone(tz)

    if mode == "always":
        return True
    if mode == "windows":
        return _in_time_windows(list(schedule.get("windows") or []), local)
    if mode == "pause_windows":
        if _in_time_windows(list(schedule.get("pause_windows") or []), local):
            return False
        return True
    return True


def epoch_ms_to_aware(ts_ms: int, *, tz_name: str = "Asia/Shanghai") -> datetime:
    """将 epoch ms 转为指定时区 aware datetime（用于按点过滤日程）。"""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    return datetime.fromtimestamp(int(ts_ms) / 1000.0, tz=tz)
