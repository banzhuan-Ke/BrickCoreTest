"""首页看板扩展计算（定时任务下次执行、占比等）"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger


def compute_next_run(
    run_type: str,
    interval: int = 3600,
    run_date: Optional[datetime] = None,
    crontab: Optional[dict] = None,
    *,
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    """根据定时任务配置计算下次执行时间。"""
    now = now or datetime.now()
    rt = (run_type or "").lower()
    try:
        if rt == "interval":
            trigger = IntervalTrigger(seconds=interval or 3600)
        elif rt == "date":
            if not run_date:
                return None
            if isinstance(run_date, str):
                run_date = datetime.strptime(run_date, "%Y-%m-%d %H:%M:%S")
            return run_date if run_date > now else None
        elif rt == "crontab":
            c = crontab or {}
            trigger = CronTrigger(
                minute=str(c.get("minute", "*")),
                hour=str(c.get("hour", "*")),
                day=str(c.get("day", "*")),
                month=str(c.get("month", "*")),
                day_of_week=str(c.get("day_of_week", "*")),
            )
        else:
            return None
        return trigger.get_next_fire_time(None, now)
    except Exception:
        return None


def build_case_proportion(
    ui_cases: int,
    api_cases: int,
    perf_scenes: int,
) -> list[dict[str, Any]]:
    items = [
        {"name": "Web", "value": ui_cases, "color": "#5470c6"},
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
) -> list[dict[str, Any]]:
    items = [
        {"name": "Web 成功", "value": ui_success, "color": "#5470c6"},
        {"name": "Web 失败", "value": ui_fail, "color": "#ee6666"},
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
    now = datetime.now()
    return now <= dt <= now + timedelta(hours=hours)
