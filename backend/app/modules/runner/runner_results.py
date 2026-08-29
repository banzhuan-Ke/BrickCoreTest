"""Runner 执行结果落库（自 mq_consumer 迁移，Backend 统一写入）"""
from __future__ import annotations

import logging
from typing import Any, Optional

from tortoise.transactions import in_transaction

from app.core.ops.notification import NotificationService
from app.modules.ui.ui_case_status import normalize_ui_case_status
from app.modules.ui.plan_reaggregation import aggregate_plan_from_suites
from app.modules.ui.ui_execution_status import (
    is_ui_case_terminal,
    should_apply_case_status_update,
    should_apply_plan_status_update,
    should_apply_suite_status_update,
)
from app.modules.ui.ui_suite_hooks import trigger_ui_suite_hooks_for_execution
from app.models.sys import NotificationConfig
from app.models.ui import Suite, Task, UiCaseExecution, UiPlanExecution, UiSuiteExecution

logger = logging.getLogger(__name__)


async def save_runner_results(run_suite: dict[str, Any], result: dict[str, Any]) -> None:
    """保存自动化执行结果（Web UI / App）"""
    engine_type = (run_suite.get("engine_type") or "").strip().lower()
    if not engine_type and isinstance(result, dict):
        engine_type = (result.get("engine_type") or "").strip().lower()
    if engine_type == "app":
        from app.modules.app.app_runner_results import save_app_runner_results
        await save_app_runner_results(run_suite, result)
        return
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
    new_status = normalize_ui_case_status(case_result.get("status")) or record.status
    existing = record.result_data if isinstance(record.result_data, dict) else {}
    # 系统收尾后：offline 拒绝；stale 误杀若迟到结果有实质内容则允许覆盖
    from app.modules.ui.ui_execution_stale import should_accept_case_result_after_system_close

    if not should_accept_case_result_after_system_close(existing, case_result):
        return
    was_stale = bool(existing.get("stale_auto_closed"))
    if is_ui_case_terminal(record.status) and new_status != record.status:
        if not should_apply_case_status_update(record.status, new_status):
            # 禁止变差覆盖；仍刷新 result_data 便于排查，但不改 status
            # 例外：超时误杀后的实质迟到结果允许连同 status 一并纠正
            if was_stale:
                record.status = new_status
            record.result_data = case_result
            _apply_case_start_time(record, case_result)
            await record.save()
            return
    record.status = new_status
    record.result_data = case_result
    _apply_case_start_time(record, case_result)
    await record.save()


def _apply_case_start_time(record: UiCaseExecution, case_result: dict[str, Any]) -> None:
    """用 Runner 上报的实际开始时间覆盖派发时写入的 auto_now_add。"""
    raw = case_result.get("start_time")
    if not raw:
        return
    parsed = _parse_runner_datetime(raw)
    if parsed is not None:
        record.start_time = parsed


def _parse_runner_datetime(raw: Any):
    """解析 Runner 本地时间字符串。"""
    from datetime import datetime

    if isinstance(raw, datetime):
        return raw
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    return None


async def _save_suite_result(suite_record_id: int, result: dict[str, Any]) -> None:
    suite_data = await UiSuiteExecution.get_or_none(id=suite_record_id, is_del=False)
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

    is_final = result.get("final", True)
    if result.get("cancelled"):
        status = "已停止"
    elif not is_final:
        status = "执行中"
    else:
        status = (
            "执行完成"
            if case_count <= run_all + no_run + result.get("fail", 0) + result.get("error", 0)
            else "执行中"
        )

    apply_status = should_apply_suite_status_update(
        suite_data.status,
        status,
        result_cancelled=bool(result.get("cancelled")),
    )
    # 超时误杀后 Runner 最终回报：允许用真实结果复活套件状态/统计
    from app.modules.ui.ui_execution_stale import suite_log_has_stale_close

    if (
        not apply_status
        and is_final
        and not result.get("cancelled")
        and suite_log_has_stale_close(suite_data.execution_log)
        and status in ("执行完成", "已停止")
    ):
        apply_status = True
    if not apply_status:
        if is_final:
            existing_log = suite_data.execution_log if isinstance(suite_data.execution_log, list) else []
            if not any(
                isinstance(item, dict) and item.get("type") == "runner_offline"
                for item in existing_log
            ):
                suite_data.execution_log = result.get("execution_log", existing_log)
                await suite_data.save()
        for case in result.get("executed_cases", []):
            await _save_case_result(case, case.get("execution_id"))
        for case in result.get("pending_cases", []):
            payload = dict(case)
            payload.setdefault("status", "no_run")
            await _save_case_result(payload, case.get("execution_id"))
        return

    suite_data.status = status
    suite_data.run_all = run_all
    suite_data.no_run = no_run
    suite_data.success = result.get("success", 0)
    suite_data.fail = result.get("fail", 0)
    suite_data.error = result.get("error", 0)
    suite_data.skip = result.get("skip", 0)
    suite_data.quarantine_skip = quarantine_skip
    parsed_start = _parse_runner_datetime(result.get("start_time"))
    if parsed_start is not None:
        suite_data.start_time = parsed_start
    if is_final:
        suite_data.duration = result.get("duration", 0)
        suite_data.execution_log = result.get("execution_log", [])
    suite_data.pass_rate = pass_rate
    await suite_data.save()

    if status == "执行完成" and is_final:
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
            if project_id and not suite_data.plan_execution_id:
                # 计划内套件失败只发计划级告警，避免每个套件各发一封
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
                    alert_scope="ui",
                )

    for case in result.get("executed_cases", []):
        await _save_case_result(case, case.get("execution_id"))
    for case in result.get("pending_cases", []):
        payload = dict(case)
        payload.setdefault("status", "no_run")
        await _save_case_result(payload, case.get("execution_id"))

    if status == "执行完成" and is_final:
        await trigger_ui_suite_hooks_for_execution(suite_record_id)


async def _reaggregate_plan_execution(task_record_id: int) -> None:
    """从各套件执行记录汇总计划统计（并行分设备时避免竞态覆盖）。"""
    async with in_transaction():
        task_data = await UiPlanExecution.select_for_update().get_or_none(
            id=task_record_id, is_del=False
        )
        if not task_data:
            return

        suites = await UiSuiteExecution.filter(plan_execution_id=task_record_id, is_del=False).all()
        if not suites:
            return

        old_status = task_data.status
        case_count = task_data.case_count or 0
        suite_rows = [
            {
                "status": s.status,
                "success": s.success,
                "fail": s.fail,
                "error": s.error,
                "skip": s.skip,
                "quarantine_skip": getattr(s, "quarantine_skip", 0) or 0,
                "run_all": s.run_all,
                "no_run": s.no_run,
                "duration": s.duration,
            }
            for s in suites
        ]
        agg = aggregate_plan_from_suites(suite_rows, case_count=case_count)
        status = agg["status"]
        success = agg["success"]
        fail = agg["fail"]
        error = agg["error"]
        skip = agg["skip"]
        quarantine_skip = agg.get("quarantine_skip", 0)
        run_all = agg["run_all"]
        no_run = agg["no_run"]
        duration = agg["duration"]
        pass_rate = agg["pass_rate"]

        if not should_apply_plan_status_update(old_status, status):
            return

        task_data.status = status
        task_data.run_all = run_all
        task_data.no_run = no_run
        task_data.success = success
        task_data.fail = fail
        task_data.error = error
        task_data.skip = skip
        task_data.quarantine_skip = quarantine_skip
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
            alert_scope="ui",
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
                await NotificationService.send_ui_report(
                    plan_execution_id=task_record_id,
                    auto_push_only=True,
                )
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
