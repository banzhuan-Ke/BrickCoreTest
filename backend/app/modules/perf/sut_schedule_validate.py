"""日程配置校验（写入 schedule_json 前）。"""
from __future__ import annotations

import re
from typing import Any, Optional
from zoneinfo import ZoneInfo

ALLOWED_MODES = {"always", "windows", "pause_windows"}
_HM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _validate_hm(s: str, *, field: str) -> str:
    raw = str(s or "").strip()
    m = _HM_RE.match(raw)
    if not m:
        raise ValueError(f"{field} 须为 HH:MM（0–23 时），收到: {raw!r}")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def validate_schedule(schedule: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """
    规范化 schedule；非法则抛 ValueError。
    null / 空 → None（表示始终，与 monitoring_enabled 配合）。
    """
    if schedule is None:
        return None
    if not isinstance(schedule, dict):
        raise ValueError("schedule 必须是对象")
    if not schedule:
        return None

    mode = str(schedule.get("mode") or "always").strip().lower()
    if mode not in ALLOWED_MODES:
        raise ValueError(f"schedule.mode 须为 {', '.join(sorted(ALLOWED_MODES))}")

    tz = str(schedule.get("timezone") or "Asia/Shanghai").strip() or "Asia/Shanghai"
    try:
        ZoneInfo(tz)
    except Exception as e:
        raise ValueError(f"无效时区: {tz}") from e

    out: dict[str, Any] = {"mode": mode, "timezone": tz}

    def _windows(key: str) -> list[dict[str, Any]]:
        raw = schedule.get(key) or []
        if not isinstance(raw, list):
            raise ValueError(f"schedule.{key} 必须是数组")
        cleaned: list[dict[str, Any]] = []
        for w in raw:
            if not isinstance(w, dict):
                continue
            start = _validate_hm(w.get("start") or "00:00", field=f"{key}[].start")
            end = _validate_hm(w.get("end") or "23:59", field=f"{key}[].end")
            days = w.get("days")
            item: dict[str, Any] = {"start": start, "end": end}
            if days is None:
                # 未指定 → 全周；显式空数组不允许（易误配成「永不匹配」直觉）
                item["days"] = [0, 1, 2, 3, 4, 5, 6]
            elif isinstance(days, list):
                if len(days) == 0:
                    raise ValueError(f"{key}[].days 不能为空，请至少选一天或省略表示全周")
                d_out = []
                for d in days:
                    try:
                        di = int(d)
                    except (TypeError, ValueError):
                        continue
                    if 0 <= di <= 6:
                        d_out.append(di)
                if not d_out:
                    raise ValueError(f"{key}[].days 无效")
                item["days"] = sorted(set(d_out))
            else:
                raise ValueError(f"{key}[].days 必须是数组")
            cleaned.append(item)
        return cleaned

    if mode == "windows":
        wins = _windows("windows")
        if not wins:
            raise ValueError("mode=windows 时至少配置一个 windows 时段")
        out["windows"] = wins
    elif mode == "pause_windows":
        wins = _windows("pause_windows")
        if not wins:
            raise ValueError("mode=pause_windows 时至少配置一个 pause_windows 时段")
        out["pause_windows"] = wins

    return out
