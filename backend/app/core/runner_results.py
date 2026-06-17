"""Runner 执行结果落库（自 mq_consumer 迁移，Backend 统一写入）"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.notification import NotificationService
from app.core.ui_suite_hooks import trigger_ui_suite_hooks_for_execution
from app.models.sys import NotificationConfig
from app.models.ui import Suite, Task, UiCaseExecution, UiPlanExecution, UiSuiteExecution

logger = logging.getLogger(__name__)


async def save_runner_results(run_suite: dict[str, Any], result: dict[str, Any]) -> None:
    """保存 UI 自动化执行结果（计划 / 套件 / 单用例）"""
    if run_suite.get("plan_execution_id"):
        await _save_task_result(
            int(run_suite["plan_execution_id"]),
            int(run_suite["suite_execution_id"]) if run_suite.get("suite_execution_id") else None,
            result,
        )
    elif run_suite.get("suite_execution_id"):
        await _save_suite_result(int(run_suite["suite_execution_id"]), result)
    else:
        if result.get("executed_cases"):
            case_data = result["executed_cases"][0]
            await _save_case_result(case_data, case_data.get("execution_id"))
        elif result.get("pending_cases"):
            case_data = result["pending_cases"][0]
            await _save_case_result(case_data, case_data.get("execution_id"))


async def _save_case_result(case_result: dict[str, Any], case_execution_id: Optional[int]) -> None:
    if not case_execution_id:
        logger.error("缺少 execution_id，无法保存用例结果: %s", case_result)
        return
    record = await UiCaseExecution.get_or_none(id=case_execution_id, is_del=False)
    if not record:
        logger.error("用例执行记录不存在: %s", case_execution_id)
        return
    record.status = case_result.get("status") or record.status
    record.result_data = case_result
    await record.save()


async def _save_suite_result(suite_record_id: int, result: dict[str, Any]) -> None:
    suite_data = await UiSuiteExecution.get_or_none(id=suite_record_id, is_del=False)
    if not suite_data:
        return

    case_count = suite_data.case_count or 0
    total_cases = result.get("case_count", 0)
    success = result.get("success", 0)
    skip = result.get("skip", 0)
    pass_rate = round((success + skip) / total_cases * 100, 2) if total_cases > 0 else 0

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
    suite_data.duration = result.get("duration", 0)
    suite_data.execution_log = result.get("execution_log", [])
    suite_data.pass_rate = pass_rate
    await suite_data.save()

    if status == "执行完成":
        total_fail = result.get("fail", 0) + result.get("error", 0)
        if total_fail > 0:
            project_id = None
            suite_name = "未知套件"
            if suite_data.suite_id:
                suite = await Suite.get_or_none(id=suite_data.suite_id)
                if suite:
                    suite_name = suite.name
                    project_id = suite.project_id
            if not project_id and suite_data.plan_execution_id:
                plan = await UiPlanExecution.get_or_none(id=suite_data.plan_execution_id)
                if plan:
                    project_id = plan.project_id
            if project_id:
                await NotificationService.send_alert(
                    project_id=project_id,
                    title=f"UI套件执行失败：{suite_name}",
                    content={
                        "execution_type": "UI套件",
                        "name": suite_name,
                        "status": "failed",
                        "total": case_count,
                        "success": result.get("success", 0),
                        "failed": total_fail,
                        "pass_rate": pass_rate,
                        "duration": result.get("duration", 0),
                        "run_by": suite_data.username,
                        "link": "",
                    },
                    related_id=suite_record_id,
                    related_type="ui_suite_execution",
                )

    for case in result.get("executed_cases", []):
        await _save_case_result(case, case.get("execution_id"))
    for case in result.get("pending_cases", []):
        await _save_case_result(case, case.get("execution_id"))

    if status == "执行完成":
        await trigger_ui_suite_hooks_for_execution(suite_record_id)


async def _reaggregate_plan_execution(task_record_id: int) -> None:
    """从各套件执行记录汇总计划统计（并行分设备时避免竞态覆盖）。"""
    task_data = await UiPlanExecution.get_or_none(id=task_record_id, is_del=False)
    if not task_data:
        return

    suites = await UiSuiteExecution.filter(plan_execution_id=task_record_id, is_del=False).all()
    if not suites:
        return

    old_status = task_data.status
    case_count = task_data.case_count or 0
    success = sum(s.success or 0 for s in suites)
    fail = sum(s.fail or 0 for s in suites)
    error = sum(s.error or 0 for s in suites)
    skip = sum(s.skip or 0 for s in suites)
    run_all = sum(s.run_all or 0 for s in suites)
    no_run = sum(s.no_run or 0 for s in suites)
    duration = max((s.duration or 0) for s in suites)
    pass_rate = round((success + skip) / case_count * 100, 2) if case_count > 0 else 0

    statuses = [s.status for s in suites]
    terminal = {"执行完成", "已停止"}
    if any(s not in terminal for s in statuses):
        status = "已停止" if any(s == "已停止" for s in statuses) else "执行中"
    elif all(s == "执行完成" for s in statuses):
        status = "执行完成"
    else:
        status = "执行中"

    task_data.status = status
    task_data.run_all = run_all
    task_data.no_run = no_run
    task_data.success = success
    task_data.fail = fail
    task_data.error = error
    task_data.skip = skip
    task_data.duration = duration
    task_data.pass_rate = pass_rate
    await task_data.save()

    if old_status == status or status not in ("执行完成", "已停止"):
        return

    project_id = task_data.project_id
    total_fail = fail + error

    if status == "执行完成" and total_fail > 0 and project_id:
        task_name = "未知计划"
        if task_data.task_id:
            task = await Task.get_or_none(id=task_data.task_id)
            if task:
                task_name = task.name
        await NotificationService.send_alert(
            project_id=project_id,
            title=f"UI计划执行失败：{task_name}",
            content={
                "execution_type": "UI计划",
                "name": task_name,
                "status": "failed",
                "total": case_count,
                "success": success,
                "failed": total_fail,
                "pass_rate": pass_rate,
                "duration": duration,
                "run_by": task_data.username,
                "link": "",
            },
            related_id=task_record_id,
            related_type="ui_plan_execution",
        )

    if status == "执行完成" and project_id:
        push_cfg = await NotificationConfig.filter(
            project_id=project_id,
            channel_type="email",
            enabled=True,
            ui_auto_push_report=True,
        ).first()
        if push_cfg:
            try:
                await NotificationService.send_ui_report(plan_execution_id=task_record_id)
            except Exception as exc:
                logger.error("自动推送 UI 报告失败 plan=%s: %s", task_record_id, exc)


async def _save_task_result(
    task_record_id: int,
    suite_record_id: Optional[int],
    result: dict[str, Any],
) -> None:
    if suite_record_id:
        await _save_suite_result(suite_record_id, result)
    await _reaggregate_plan_execution(task_record_id)
