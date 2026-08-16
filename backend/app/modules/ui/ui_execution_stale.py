"""
UI 执行记录超时清理：长时间处于 running/执行中 的记录自动标记为 error/执行完成。

注意：派发时 start_time=auto_now_add，长排队会超过默认 30 分钟。
因此：
- 父套件/计划仍「执行中|等待执行」时，用例不按派发时间误杀；
- 计划下仍有活套件时，不关闭计划；
- 计划仍活着的套件使用更长排队宽限（默认 180 分钟）再判定僵死。
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Optional

from app.models.ui import UiCaseExecution, UiPlanExecution, UiSuiteExecution

logger = logging.getLogger(__name__)

STALE_JOB_ID = "ui_execution_stale_cleanup"
STALE_RUNNING_MINUTES = int(os.getenv("UI_EXECUTION_STALE_MINUTES", "30"))
# 计划仍在跑时，套件可能在 Runner 槽位排队；宽限需覆盖长排队（默认 180 分钟）
STALE_QUEUED_MINUTES = int(os.getenv("UI_EXECUTION_STALE_QUEUED_MINUTES", "180"))
STALE_MESSAGE = "Runner 未在规定时间内回写结果，系统自动标记为错误"
RUNNER_OFFLINE_MESSAGE = "执行器异常下线，系统已自动结束本次执行"

_LIVE_SUITE_STATUSES = frozenset({"执行中", "等待执行"})
_LIVE_PLAN_STATUSES = frozenset({"执行中", "等待执行"})


def _stale_result_patch(
    existing: Any,
    *,
    case_name: Optional[str] = None,
    case_id: Optional[int] = None,
) -> dict:
    base = existing if isinstance(existing, dict) else {}
    patch = {
        **base,
        "status": "error",
        "message": STALE_MESSAGE,
        "error_msg": STALE_MESSAGE,
        "stale_auto_closed": True,
        "stale_closed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    # 便于报告展开时 hasData 为真，至少能看到超时说明
    if case_name and not patch.get("name") and not patch.get("case_name"):
        patch["name"] = case_name
    if case_id is not None and patch.get("id") is None and patch.get("case_id") is None:
        patch["id"] = case_id
    return patch


def _runner_offline_result_patch(existing: Any) -> dict:
    base = existing if isinstance(existing, dict) else {}
    return {
        **base,
        "status": "error",
        "message": RUNNER_OFFLINE_MESSAGE,
        "error_msg": RUNNER_OFFLINE_MESSAGE,
        "runner_offline": True,
        "runner_offline_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _runner_offline_log_entry() -> dict:
    return {
        "type": "runner_offline",
        "message": RUNNER_OFFLINE_MESSAGE,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _stale_log_entry() -> dict:
    return {
        "type": "stale_auto_closed",
        "message": STALE_MESSAGE,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def suite_log_has_stale_close(execution_log: Any) -> bool:
    if not isinstance(execution_log, list):
        return False
    return any(
        isinstance(item, dict) and item.get("type") == "stale_auto_closed"
        for item in execution_log
    )


def is_substantive_runner_case_result(case_result: Any) -> bool:
    """判断 Runner 回报是否含可展示的实质内容（可覆盖误杀的 stale 空壳）。"""
    if not isinstance(case_result, dict):
        return False
    # 仍是系统收尾空壳，不能用来「覆盖」自己
    if case_result.get("stale_auto_closed") or case_result.get("runner_offline"):
        return False
    steps = case_result.get("steps")
    if isinstance(steps, list) and len(steps) > 0:
        return True
    log_data = case_result.get("log_data")
    if isinstance(log_data, list) and len(log_data) > 0:
        return True
    status = str(case_result.get("status") or "").strip().lower()
    if status in ("success", "fail", "failed", "error", "skip", "no_run"):
        # 有用例身份即视为 Runner 正常回报（含无步骤的 no_run/早期失败）
        if case_result.get("name") or case_result.get("case_name") or case_result.get("id"):
            return True
        if case_result.get("execution_id") is not None:
            return True
    return False


def should_accept_case_result_after_system_close(
    existing: Any,
    incoming: Any,
) -> bool:
    """
    系统收尾后是否仍接受 Runner 迟到回报。
    - runner_offline：设备已判死，默认拒绝（避免脏写）
    - stale_auto_closed：若迟到结果有实质内容则允许覆盖（长排队误杀恢复）
    """
    base = existing if isinstance(existing, dict) else {}
    if base.get("runner_offline"):
        return False
    if base.get("stale_auto_closed"):
        return is_substantive_runner_case_result(incoming)
    return True


def _split_device_ids(raw: str | None) -> set[str]:
    ids: set[str] = set()
    if not raw:
        return ids
    for part in str(raw).split(","):
        part = part.strip()
        if part:
            ids.add(part)
    return ids


async def close_inflight_ui_executions_for_device(device_id: str) -> dict[str, int]:
    """Runner 下线时关闭该设备上仍进行中的 UI 用例/套件/计划执行。"""
    device_id = (device_id or "").strip()
    if not device_id:
        return {"cases": 0, "suites": 0, "plans": 0}

    from app.modules.ui.ui_execution_stop import _collect_plan_device_ids

    case_count = 0
    suite_count = 0
    plan_ids: set[int] = set()

    suite_records = await UiSuiteExecution.filter(
        status__in=["执行中", "等待执行"],
        is_del=False,
    ).all()
    for record in suite_records:
        env = record.env if isinstance(record.env, dict) else {}
        suite_devices = _split_device_ids(record.device_id)
        if env.get("device_id"):
            suite_devices.add(str(env["device_id"]))
        if device_id not in suite_devices:
            continue
        pending = max(int(record.no_run or 0), 0)
        record.status = "执行完成"
        record.error = int(record.error or 0) + pending
        record.no_run = 0
        log = list(record.execution_log or [])
        log.append(_runner_offline_log_entry())
        record.execution_log = log
        await record.save(update_fields=["status", "error", "no_run", "execution_log"])
        suite_count += 1
        if record.plan_execution_id:
            plan_ids.add(int(record.plan_execution_id))

        for child in await UiCaseExecution.filter(
            suite_execution_id=record.id,
            status__in=["running", "no_run"],
            is_del=False,
        ).all():
            child.status = "error"
            child.result_data = _runner_offline_result_patch(child.result_data)
            await child.save(update_fields=["status", "result_data"])
            case_count += 1

    case_records = await UiCaseExecution.filter(
        status="running",
        is_del=False,
        suite_execution_id__isnull=True,
    ).all()
    for record in case_records:
        env = record.env if isinstance(record.env, dict) else {}
        if str(env.get("device_id") or "") != device_id:
            continue
        record.status = "error"
        record.result_data = _runner_offline_result_patch(record.result_data)
        await record.save(update_fields=["status", "result_data"])
        case_count += 1

    plan_records = await UiPlanExecution.filter(
        status__in=["执行中", "等待执行"],
        is_del=False,
    ).all()
    for plan in plan_records:
        if device_id not in await _collect_plan_device_ids(plan):
            continue
        plan_ids.add(plan.id)

    plan_count = 0
    for plan_id in plan_ids:
        suites = await UiSuiteExecution.filter(plan_execution_id=plan_id, is_del=False).all()
        if any(s.status in ("执行中", "等待执行") for s in suites):
            continue
        from app.modules.runner.runner_results import _reaggregate_plan_execution

        await _reaggregate_plan_execution(plan_id)
        plan = await UiPlanExecution.get_or_none(id=plan_id, is_del=False)
        if plan and plan.status in ("执行中", "等待执行"):
            pending = max(int(plan.no_run or 0), 0)
            plan.status = "执行完成"
            plan.error = int(plan.error or 0) + pending
            plan.no_run = 0
            log = list(plan.execution_log or [])
            log.append(_runner_offline_log_entry())
            plan.execution_log = log
            await plan.save(update_fields=["status", "error", "no_run", "execution_log"])
        elif plan:
            log = list(plan.execution_log or [])
            log.append(_runner_offline_log_entry())
            plan.execution_log = log
            await plan.save(update_fields=["execution_log"])
        plan_count += 1

    if case_count or suite_count or plan_count:
        logger.info(
            "[ui_execution_stale] 执行器下线收尾: device=%s cases=%s suites=%s plans=%s",
            device_id,
            case_count,
            suite_count,
            plan_count,
        )
    return {"cases": case_count, "suites": suite_count, "plans": plan_count}


async def _case_parent_suite_live(record: UiCaseExecution) -> bool:
    sid = record.suite_execution_id
    if not sid:
        return False
    suite = await UiSuiteExecution.get_or_none(id=int(sid), is_del=False)
    return bool(suite and suite.status in _LIVE_SUITE_STATUSES)


async def _suite_parent_plan_live(record: UiSuiteExecution) -> bool:
    pid = record.plan_execution_id
    if not pid:
        return False
    plan = await UiPlanExecution.get_or_none(id=int(pid), is_del=False)
    return bool(plan and plan.status in _LIVE_PLAN_STATUSES)


async def _mark_suite_stale(record: UiSuiteExecution) -> int:
    """关闭套件并收口仍 running 的子用例；返回新增关闭的用例数。"""
    pending = max(int(record.no_run or 0), 0)
    record.status = "执行完成"
    record.error = int(record.error or 0) + pending
    record.no_run = 0
    log = list(record.execution_log or [])
    log.append(_stale_log_entry())
    record.execution_log = log
    await record.save(update_fields=["status", "error", "no_run", "execution_log"])

    closed = 0
    child_cases = await UiCaseExecution.filter(
        suite_execution_id=record.id,
        status="running",
        is_del=False,
    ).all()
    for child in child_cases:
        case_name = None
        try:
            if child.case_id:
                from app.models.ui import Case

                case_obj = await Case.get_or_none(id=child.case_id)
                case_name = case_obj.name if case_obj else None
        except Exception:
            case_name = None
        child.status = "error"
        child.result_data = _stale_result_patch(
            child.result_data,
            case_name=case_name,
            case_id=child.case_id,
        )
        await child.save(update_fields=["status", "result_data"])
        closed += 1
    return closed


async def cleanup_stale_ui_executions(minutes: int | None = None) -> dict[str, int]:
    """
    将超过 minutes 仍为进行中的 UI 执行记录标记为终态。
    返回各类清理数量。
    """
    threshold_minutes = minutes if minutes is not None else STALE_RUNNING_MINUTES
    if threshold_minutes <= 0:
        return {"cases": 0, "suites": 0, "plans": 0}

    queued_minutes = max(threshold_minutes, STALE_QUEUED_MINUTES)
    now = datetime.now()
    cutoff = now - timedelta(minutes=threshold_minutes)
    queued_cutoff = now - timedelta(minutes=queued_minutes)
    case_count = 0
    suite_count = 0
    plan_count = 0

    stale_cases = await UiCaseExecution.filter(
        status="running",
        is_del=False,
        start_time__lt=cutoff,
    ).all()
    for record in stale_cases:
        # 父套件仍活着：用例可能只是在套件内排队，不能按派发时间误杀
        if await _case_parent_suite_live(record):
            continue
        case_name = None
        try:
            if record.case_id:
                from app.models.ui import Case

                case_obj = await Case.get_or_none(id=record.case_id)
                case_name = case_obj.name if case_obj else None
        except Exception:
            case_name = None
        record.status = "error"
        record.result_data = _stale_result_patch(
            record.result_data,
            case_name=case_name,
            case_id=record.case_id,
        )
        await record.save(update_fields=["status", "result_data"])
        case_count += 1

    stale_suites = await UiSuiteExecution.filter(
        status="执行中",
        is_del=False,
        start_time__lt=cutoff,
    ).all()
    for record in stale_suites:
        # 计划仍活着：套件可能在 Runner 槽位排队，使用更长宽限
        if await _suite_parent_plan_live(record):
            if not record.start_time or record.start_time >= queued_cutoff:
                continue
        closed_children = await _mark_suite_stale(record)
        suite_count += 1
        case_count += closed_children

    stale_plans = await UiPlanExecution.filter(
        status="执行中",
        is_del=False,
        start_time__lt=cutoff,
    ).all()
    for record in stale_plans:
        live_suites = await UiSuiteExecution.filter(
            plan_execution_id=record.id,
            status__in=list(_LIVE_SUITE_STATUSES),
            is_del=False,
        ).count()
        if live_suites:
            # 仍有套件在跑/排队：不关计划（避免长计划被 30 分钟误杀）
            continue
        pending = max(int(record.no_run or 0), 0)
        record.status = "执行完成"
        record.error = int(record.error or 0) + pending
        record.no_run = 0
        log = list(record.execution_log or [])
        log.append(_stale_log_entry())
        record.execution_log = log
        await record.save(update_fields=["status", "error", "no_run", "execution_log"])
        plan_count += 1

    if case_count or suite_count or plan_count:
        logger.info(
            "[ui_execution_stale] 清理超时记录: cases=%s suites=%s plans=%s "
            "(>%s min, queued_grace=%s min)",
            case_count,
            suite_count,
            plan_count,
            threshold_minutes,
            queued_minutes,
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
