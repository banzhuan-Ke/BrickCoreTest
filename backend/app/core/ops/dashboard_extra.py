"""首页看板扩展计算（定时任务下次执行、占比等）"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

import pytz
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

_LOCAL_TZ = pytz.timezone("Asia/Shanghai")


def _to_naive_local(dt: datetime) -> datetime:
    """ORM / APScheduler 可能返回带时区时间，统一为上海本地 naive 再比较。"""
    if dt.tzinfo is not None:
        return dt.astimezone(_LOCAL_TZ).replace(tzinfo=None)
    return dt


def _to_aware_local(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(_LOCAL_TZ)
    return _LOCAL_TZ.localize(dt)


def compute_next_run(
    run_type: str,
    interval: int = 3600,
    run_date: Optional[datetime] = None,
    crontab: Optional[dict] = None,
    *,
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    """根据定时任务配置计算下次执行时间。"""
    now = _to_naive_local(now or datetime.now())
    rt = (run_type or "").lower()
    try:
        if rt == "interval":
            trigger = IntervalTrigger(seconds=interval or 3600, timezone=_LOCAL_TZ)
            nxt = trigger.get_next_fire_time(None, _to_aware_local(now))
            return _to_naive_local(nxt) if nxt else None
        if rt == "date":
            if not run_date:
                return None
            if isinstance(run_date, str):
                run_date = datetime.strptime(run_date, "%Y-%m-%d %H:%M:%S")
            else:
                run_date = _to_naive_local(run_date)
            return run_date if run_date > now else None
        if rt == "crontab":
            c = crontab or {}
            trigger = CronTrigger(
                minute=str(c.get("minute", "*")),
                hour=str(c.get("hour", "*")),
                day=str(c.get("day", "*")),
                month=str(c.get("month", "*")),
                day_of_week=str(c.get("day_of_week", "*")),
                timezone=_LOCAL_TZ,
            )
            nxt = trigger.get_next_fire_time(None, _to_aware_local(now))
            return _to_naive_local(nxt) if nxt else None
        return None
    except Exception:
        return None


def build_case_proportion(
    ui_cases: int,
    api_cases: int,
    perf_scenes: int,
    app_cases: int = 0,
) -> list[dict[str, Any]]:
    items = [
        {"name": "Web", "value": ui_cases, "color": "#5470c6"},
        {"name": "App", "value": app_cases, "color": "#9a60b4"},
        {"name": "接口", "value": api_cases, "color": "#91cc75"},
        {"name": "性能", "value": perf_scenes, "color": "#73c0de"},
    ]
    return [i for i in items if i["value"] > 0]


def build_execution_proportion(
    ui_success: int,
    ui_fail: int,
    api_success: int,
    api_fail: int,
    perf_success: int,
    perf_fail: int,
    app_success: int = 0,
    app_fail: int = 0,
) -> list[dict[str, Any]]:
    items = [
        {"name": "Web 成功", "value": ui_success, "color": "#5470c6"},
        {"name": "Web 失败", "value": ui_fail, "color": "#ee6666"},
        {"name": "App 成功", "value": app_success, "color": "#9a60b4"},
        {"name": "App 失败", "value": app_fail, "color": "#ea7ccc"},
        {"name": "接口 成功", "value": api_success, "color": "#91cc75"},
        {"name": "接口 失败", "value": api_fail, "color": "#fac858"},
        {"name": "性能 成功", "value": perf_success, "color": "#73c0de"},
        {"name": "性能 失败", "value": perf_fail, "color": "#fc8452"},
    ]
    return [i for i in items if i["value"] > 0]


def sort_pending_jobs(jobs: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    jobs.sort(key=lambda x: x.get("_sort") or datetime.max)
    result = []
    for job in jobs[:limit]:
        row = {k: v for k, v in job.items() if k != "_sort"}
        result.append(row)
    return result


def within_hours(dt: Optional[datetime], hours: int = 48) -> bool:
    if not dt:
        return False
    now = _to_naive_local(datetime.now())
    dt = _to_naive_local(dt)
    return now <= dt <= now + timedelta(hours=hours)
