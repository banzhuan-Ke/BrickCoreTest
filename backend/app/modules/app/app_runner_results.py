"""App 自动化执行结果落库"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.modules.app.app_suite_hooks import trigger_app_suite_hooks_for_execution
from app.modules.app.app_device_lock import release_device_locks_for_holder
from app.core.ops.notification import NotificationService
from app.models.sys import NotificationConfig
from app.modules.ui.ui_case_status import normalize_ui_case_status
from app.models.app import (
    AppCaseExecution,
    AppPlanExecution,
    AppSuiteExecution,
)

logger = logging.getLogger(__name__)


async def _maybe_notify_app_suite_complete(suite_record: AppSuiteExecution) -> None:
    suite = await suite_record.suite
    if not suite:
        return
    project_id = suite.project_id
    total_fail = int(suite_record.fail or 0) + int(suite_record.error or 0)
    suite_name = suite.name

    if total_fail > 0:
        await NotificationService.send_alert(
            project_id=project_id,
            title=f"App套件执行失败：{suite_name}",
            content={
                "execution_type": "App套件",
                "name": suite_name,
                "status": "failed",
                "total": suite_record.case_count or 0,
                "success": suite_record.success or 0,
                "failed": total_fail,
                "pass_rate": suite_record.pass_rate or 0,
                "duration": suite_record.duration or 0,
                "run_by": suite_record.username,
                "link": "",
            },
            related_id=suite_record.id,
            related_type="app_suite_execution",
            alert_scope="app",
        )

    push_cfg = await NotificationConfig.filter(
        project_id=project_id,
        channel_type="email",
        enabled=True,
        app_auto_push_report=True,
    ).first()
    if push_cfg:
        try:
            await NotificationService.send_app_suite_report(
                suite_record.id,
                auto_push_only=True,
            )
        except Exception as exc:
            logger.error("自动推送 App 套件报告失败 suite=%s: %s", suite_record.id, exc)


async def _maybe_notify_app_plan_complete(plan_record: AppPlanExecution) -> None:
    plan = await plan_record.plan
    project_id = plan_record.project_id
    total_fail = int(plan_record.fail or 0) + int(plan_record.error or 0)
    plan_name = plan.name if plan else "未知计划"

    if total_fail > 0:
        await NotificationService.send_alert(
            project_id=project_id,
            title=f"App计划执行失败：{plan_name}",
            content={
                "execution_type": "App计划",
                "name": plan_name,
                "status": "failed",
                "total": plan_record.case_count or 0,
                "success": plan_record.success or 0,
                "failed": total_fail,
                "pass_rate": plan_record.pass_rate or 0,
                "duration": plan_record.duration or 0,
                "run_by": plan_record.username,
                "link": "",
            },
            related_id=plan_record.id,
            related_type="app_plan_execution",
            alert_scope="app",
        )

    push_cfg = await NotificationConfig.filter(
        project_id=project_id,
        channel_type="email",
        enabled=True,
        app_auto_push_report=True,
    ).first()
    if push_cfg:
        try:
            await NotificationService.send_app_plan_report(
                plan_record.id,
                auto_push_only=True,
            )
        except Exception as exc:
            logger.error("自动推送 App 计划报告失败 plan=%s: %s", plan_record.id, exc)


async def _release_exec_device_lock(suite_record: AppSuiteExecution) -> None:
    """独立套件执行完成时释放；计划内套件由计划聚合完成后统一释放。"""
    if suite_record.plan_execution_id:
        return
    await release_device_locks_for_holder("exec", str(suite_record.id))


async def _release_case_exec_device_lock(record: AppCaseExecution) -> None:
    await release_device_locks_for_holder("exec", str(record.id))


async def save_app_runner_results(run_suite: dict[str, Any], result: dict[str, Any]) -> None:
    if run_suite.get("plan_execution_id"):
        await _save_app_plan_result(
            int(run_suite["plan_execution_id"]),
            int(run_suite["suite_execution_id"]) if run_suite.get("suite_execution_id") else None,
            result,
        )
    elif run_suite.get("suite_execution_id"):
        await _save_app_suite_result(int(run_suite["suite_execution_id"]), result)
    else:
        if result.get("executed_cases"):
            case_data = result["executed_cases"][0]
            await _save_app_case_result(case_data, case_data.get("execution_id"))
        elif result.get("pending_cases"):
            case_data = result["pending_cases"][0]
            await _save_app_case_result(case_data, case_data.get("execution_id"))


async def _save_app_case_result(case_result: dict[str, Any], case_execution_id: Optional[int]) -> None:
    if not case_execution_id:
        logger.error("缺少 execution_id，无法保存 App 用例结果")
        return
    record = await AppCaseExecution.get_or_none(id=case_execution_id, is_del=False)
    if not record:
        logger.error("App 用例执行记录不存在: %s", case_execution_id)
        return
    record.status = normalize_ui_case_status(case_result.get("status")) or record.status
    record.result_data = case_result
    await record.save()
    status = str(record.status or "").lower()
    if status not in ("running", "pending") and not record.suite_execution_id:
        await _release_case_exec_device_lock(record)


async def _save_app_suite_result(suite_record_id: int, result: dict[str, Any]) -> None:
    suite_data = await AppSuiteExecution.get_or_none(id=suite_record_id, is_del=False)
    if not suite_data:
        return

    case_count = suite_data.case_count or 0
    total_cases = result.get("case_count", 0)
    success = result.get("success", 0)
    skip = result.get("skip", 0)
    from app.modules.stability.metrics import compute_suite_pass_rate, count_quarantine_skips

    quarantine_skip = count_quarantine_skips(result.get("executed_cases"))
    pass_rate = compute_suite_pass_rate(
        success=success,
        skip=skip,
        quarantine_skip=quarantine_skip,
        case_count=total_cases or case_count,
    )
    run_all = len(result.get("executed_cases", []))
    no_run = result.get("no_run", 0)
    if run_all == 0 and case_count > 0 and not result.get("fail") and not result.get("error"):
        no_run = max(no_run, case_count)

    status = "执行完成" if case_count <= run_all + no_run + result.get("fail", 0) + result.get("error", 0) else "执行中"
    if result.get("cancelled"):
        status = "已停止"

    suite_data.status = status
    suite_data.run_all = run_all
    suite_data.no_run = no_run
    suite_data.success = result.get("success", 0)
    suite_data.fail = result.get("fail", 0)
    suite_data.error = result.get("error", 0)
    suite_data.skip = result.get("skip", 0)
    suite_data.quarantine_skip = quarantine_skip
    suite_data.duration = result.get("duration", 0)
    suite_data.execution_log = result.get("execution_log", [])
    suite_data.pass_rate = pass_rate
    await suite_data.save()

    for case in result.get("executed_cases", []):
        await _save_app_case_result(case, case.get("execution_id"))
    for case in result.get("pending_cases", []):
        payload = dict(case)
        payload.setdefault("status", "no_run")
        await _save_app_case_result(payload, case.get("execution_id"))

    if status == "执行完成":
        await trigger_app_suite_hooks_for_execution(suite_record_id)
        await _release_exec_device_lock(suite_data)
        if not suite_data.plan_execution_id:
            await _maybe_notify_app_suite_complete(suite_data)
    elif status == "已停止" or result.get("cancelled"):
        await _release_exec_device_lock(suite_data)


async def _reaggregate_app_plan_execution(plan_record_id: int) -> None:
    plan_data = await AppPlanExecution.get_or_none(id=plan_record_id, is_del=False)
    if not plan_data:
        return
    suites = await AppSuiteExecution.filter(plan_execution_id=plan_record_id, is_del=False).all()
    if not suites:
        return

    case_count = plan_data.case_count or 0
    from app.modules.ui.plan_reaggregation import aggregate_plan_from_suites

    suite_rows = [
        {
            "status": s.status,
            "success": s.success or 0,
            "fail": s.fail or 0,
            "error": s.error or 0,
            "skip": s.skip or 0,
            "quarantine_skip": getattr(s, "quarantine_skip", 0) or 0,
            "run_all": s.run_all or 0,
            "no_run": s.no_run or 0,
            "duration": s.duration or 0,
        }
        for s in suites
    ]
    agg = aggregate_plan_from_suites(suite_rows, case_count=case_count)

    plan_data.status = agg["status"]
    plan_data.run_all = agg["run_all"]
    plan_data.no_run = agg["no_run"]
    plan_data.success = agg["success"]
    plan_data.fail = agg["fail"]
    plan_data.error = agg["error"]
    plan_data.skip = agg["skip"]
    plan_data.quarantine_skip = agg.get("quarantine_skip", 0)
    plan_data.duration = agg["duration"]
    plan_data.pass_rate = agg["pass_rate"]
    await plan_data.save()

    if agg["status"] in ("执行完成", "已停止"):
        await release_device_locks_for_holder("exec", str(plan_record_id))
        if agg["status"] == "执行完成":
            await _maybe_notify_app_plan_complete(plan_data)


async def _save_app_plan_result(
    plan_record_id: int,
    suite_record_id: Optional[int],
    result: dict[str, Any],
) -> None:
    if suite_record_id:
        await _save_app_suite_result(suite_record_id, result)
    await _reaggregate_app_plan_execution(plan_record_id)
