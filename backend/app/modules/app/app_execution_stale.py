"""App 执行记录超时清理：长时间处于进行中的记录自动标记为终态并释放设备锁。"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

from app.modules.app.app_device_lock import release_device_lock_by_udid, release_device_locks_for_holder
from app.models.app import AppCaseExecution, AppPlanExecution, AppSuiteExecution

logger = logging.getLogger(__name__)

STALE_JOB_ID = "app_execution_stale_cleanup"
STALE_RUNNING_MINUTES = int(os.getenv("APP_EXECUTION_STALE_MINUTES", "30"))
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


def _stale_log_entry() -> dict:
    return {
        "type": "stale_auto_closed",
        "message": STALE_MESSAGE,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


async def _release_stale_exec_lock(record: AppSuiteExecution | AppCaseExecution) -> None:
    if isinstance(record, AppSuiteExecution) and record.plan_execution_id:
        from app.modules.app.app_runner_results import _reaggregate_app_plan_execution

        await _reaggregate_app_plan_execution(int(record.plan_execution_id))
        return
    await release_device_locks_for_holder("exec", str(record.id))


async def cleanup_stale_app_executions(minutes: int | None = None) -> dict[str, int]:
    """将超过 minutes 仍为进行中的 App 执行记录标记为终态。"""
    threshold_minutes = minutes if minutes is not None else STALE_RUNNING_MINUTES
    if threshold_minutes <= 0:
        return {"cases": 0, "suites": 0, "plans": 0}

    cutoff = datetime.now() - timedelta(minutes=threshold_minutes)
    case_count = 0
    suite_count = 0
    plan_count = 0

    stale_cases = await AppCaseExecution.filter(
        status="running",
        is_del=False,
        start_time__lt=cutoff,
    ).all()
    for record in stale_cases:
        record.status = "error"
        record.result_data = _stale_result_patch(record.result_data)
        await record.save(update_fields=["status", "result_data"])
        if not record.suite_execution_id:
            await _release_stale_exec_lock(record)
        case_count += 1

    stale_suites = await AppSuiteExecution.filter(
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
        log.append(_stale_log_entry())
        record.execution_log = log
        await record.save(update_fields=["status", "error", "no_run", "execution_log"])
        await _release_stale_exec_lock(record)
        suite_count += 1

        child_cases = await AppCaseExecution.filter(
            suite_execution_id=record.id,
            status="running",
            is_del=False,
        ).all()
        for child in child_cases:
            child.status = "error"
            child.result_data = _stale_result_patch(child.result_data)
            await child.save(update_fields=["status", "result_data"])
            case_count += 1

    stale_plans = await AppPlanExecution.filter(
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
        log.append(_stale_log_entry())
        record.execution_log = log
        await record.save(update_fields=["status", "error", "no_run", "execution_log"])
        await release_device_locks_for_holder("exec", str(record.id))
        plan_count += 1

    if case_count or suite_count or plan_count:
        logger.info(
            "[app_execution_stale] 清理超时记录: cases=%s suites=%s plans=%s (>%s min)",
            case_count,
            suite_count,
            plan_count,
            threshold_minutes,
        )

    return {"cases": case_count, "suites": suite_count, "plans": plan_count}


async def close_inflight_executions_for_udid(udid: str) -> dict[str, int]:
    """Runner 下线时关闭该 UDID 上仍在进行中的执行记录并释放锁。"""
    udid = (udid or "").strip()
    if not udid:
        return {"cases": 0, "suites": 0, "plans": 0}

    case_count = 0
    suite_count = 0
    plan_count = 0
    plan_ids: set[int] = set()

    stale_suites = await AppSuiteExecution.filter(status="执行中", is_del=False).all()
    for record in stale_suites:
        env = record.env if isinstance(record.env, dict) else {}
        if (env.get("device_udid") or "").strip() != udid:
            continue
        pending = max(int(record.no_run or 0), 0)
        record.status = "执行完成"
        record.error = int(record.error or 0) + pending
        record.no_run = 0
        log = list(record.execution_log or [])
        log.append({
            "type": "runner_offline",
            "message": "执行器已下线，系统自动结束执行",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        record.execution_log = log
        await record.save(update_fields=["status", "error", "no_run", "execution_log"])
        suite_count += 1
        if record.plan_execution_id:
            plan_ids.add(int(record.plan_execution_id))
        else:
            await release_device_locks_for_holder("exec", str(record.id))

        for child in await AppCaseExecution.filter(suite_execution_id=record.id, status="running", is_del=False).all():
            child.status = "error"
            child.result_data = _stale_result_patch(child.result_data)
            await child.save(update_fields=["status", "result_data"])
            case_count += 1

    stale_cases = await AppCaseExecution.filter(status="running", is_del=False, suite_execution_id__isnull=True).all()
    for record in stale_cases:
        env = record.env if isinstance(record.env, dict) else {}
        if (env.get("device_udid") or "").strip() != udid:
            continue
        record.status = "error"
        record.result_data = _stale_result_patch(record.result_data)
        await record.save(update_fields=["status", "result_data"])
        await release_device_locks_for_holder("exec", str(record.id))
        case_count += 1

    for plan_id in plan_ids:
        suites = await AppSuiteExecution.filter(plan_execution_id=plan_id, is_del=False).all()
        if any(s.status == "执行中" for s in suites):
            continue
        from app.modules.app.app_runner_results import _reaggregate_app_plan_execution

        await _reaggregate_app_plan_execution(plan_id)
        plan_count += 1

    await release_device_lock_by_udid(udid)
    return {"cases": case_count, "suites": suite_count, "plans": plan_count}


def register_stale_cleanup_job(scheduler) -> None:
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(
        cleanup_stale_app_executions,
        trigger=IntervalTrigger(minutes=5),
        id=STALE_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
