"""
UI 执行记录超时清理：长时间处于 running/执行中 的记录自动标记为 error/执行完成。
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Any

from app.models.ui import UiCaseExecution, UiPlanExecution, UiSuiteExecution

logger = logging.getLogger(__name__)

STALE_JOB_ID = "ui_execution_stale_cleanup"
STALE_RUNNING_MINUTES = int(os.getenv("UI_EXECUTION_STALE_MINUTES", "30"))
STALE_MESSAGE = "Runner 未在规定时间内回写结果，系统自动标记为错误"


def _stale_result_patch(existing: Any) -> dict:
    base = existing if isinstance(existing, dict) else {}
    return {
        **base,
        "status": "error",
        "message": STALE_MESSAGE,
        "stale_auto_closed": True,
        "stale_closed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


async def cleanup_stale_ui_executions(minutes: int | None = None) -> dict[str, int]:
    """
    将超过 minutes 仍为进行中的 UI 执行记录标记为终态。
    返回各类清理数量。
    """
    threshold_minutes = minutes if minutes is not None else STALE_RUNNING_MINUTES
    if threshold_minutes <= 0:
        return {"cases": 0, "suites": 0, "plans": 0}

    cutoff = datetime.now() - timedelta(minutes=threshold_minutes)
    case_count = 0
    suite_count = 0
    plan_count = 0

    stale_cases = await UiCaseExecution.filter(
        status="running",
        is_del=False,
        start_time__lt=cutoff,
    ).all()
    for record in stale_cases:
        record.status = "error"
        record.result_data = _stale_result_patch(record.result_data)
        await record.save(update_fields=["status", "result_data"])
        case_count += 1

    stale_suites = await UiSuiteExecution.filter(
        status="执行中",
        is_del=False,
        start_time__lt=cutoff,
    ).all()
    for record in stale_suites:
        pending = max(int(record.no_run or 0), 0)
        record.status = "执行完成"
        record.error = int(record.error or 0) + pending
        record.no_run = 0
        log = list(record.execution_log or [])
        log.append({
            "type": "stale_auto_closed",
            "message": STALE_MESSAGE,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        record.execution_log = log
        await record.save(update_fields=["status", "error", "no_run", "execution_log"])
        suite_count += 1

        child_cases = await UiCaseExecution.filter(
            suite_execution_id=record.id,
            status="running",
            is_del=False,
        ).all()
        for child in child_cases:
            child.status = "error"
            child.result_data = _stale_result_patch(child.result_data)
            await child.save(update_fields=["status", "result_data"])
            case_count += 1

    stale_plans = await UiPlanExecution.filter(
        status="执行中",
        is_del=False,
        start_time__lt=cutoff,
    ).all()
    for record in stale_plans:
        pending = max(int(record.no_run or 0), 0)
        record.status = "执行完成"
        record.error = int(record.error or 0) + pending
        record.no_run = 0
        log = list(record.execution_log or [])
        log.append({
            "type": "stale_auto_closed",
            "message": STALE_MESSAGE,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        record.execution_log = log
        await record.save(update_fields=["status", "error", "no_run", "execution_log"])
        plan_count += 1

    if case_count or suite_count or plan_count:
        logger.info(
            "[ui_execution_stale] 清理超时记录: cases=%s suites=%s plans=%s (>%s min)",
            case_count,
            suite_count,
            plan_count,
            threshold_minutes,
        )

    return {"cases": case_count, "suites": suite_count, "plans": plan_count}


def register_stale_cleanup_job(scheduler) -> None:
    """注册定时清理任务（每 5 分钟扫描一次）"""
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(
        cleanup_stale_ui_executions,
        trigger=IntervalTrigger(minutes=5),
        id=STALE_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
