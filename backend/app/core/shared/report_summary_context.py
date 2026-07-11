"""
测试报告摘要 / 失败目标采集（API 套件·计划、UI 套件·任务）
"""
from __future__ import annotations

import json
from typing import Any, Literal, Optional

from fastapi import HTTPException

from app.modules.ui.ui_result_extract import extract_ui_case_failure_summary
from app.models.app import AppCaseExecution, AppPlanExecution, AppSuiteExecution
from app.models.http import ApiPlanRunRecord, ApiRunRecord, ApiSuiteRunRecord
from app.models.ui import UiCaseExecution, UiPlanExecution, UiSuiteExecution

ReportType = Literal["api_suite", "api_plan", "ui_suite", "ui_task", "app_suite", "app_plan"]

API_FAIL_STATUSES = frozenset({"failed", "error"})
UI_FAIL_STATUSES = frozenset({"fail", "failed", "error"})
APP_FAIL_STATUSES = UI_FAIL_STATUSES


def _truncate_json(data: Any, max_len: int = 12000) -> str:
    text = json.dumps(data, ensure_ascii=False, default=str)
    if len(text) <= max_len:
        return text
    return text[: max_len - 20] + "…（已截断）"


async def build_report_execution_data(
    report_type: ReportType,
    record_id: int,
    project_id: int,
) -> dict[str, Any]:
    """构建 report_summary Prompt 用的 execution_data 结构"""
    if report_type == "api_suite":
        rec = await ApiSuiteRunRecord.get_or_none(id=record_id, project_id=project_id)
        if not rec:
            raise HTTPException(status_code=404, detail="接口套件执行记录不存在")
        suite = await rec.suite
        case_records = await ApiRunRecord.filter(suite_run_record_id=record_id).order_by("id").all()
        failed_cases = []
        for cr in case_records:
            if cr.status not in API_FAIL_STATUSES:
                continue
            case = await cr.case
            failed_cases.append(
                {
                    "case_name": case.name if case else "未知",
                    "status": cr.status,
                    "http_status": cr.response_status,
                    "error_msg": (cr.error_msg or "")[:300],
                    "record_id": cr.id,
                }
            )
        total = rec.total_cases or len(case_records)
        success = rec.success_cases or 0
        failed = rec.failed_cases or len(failed_cases)
        pass_rate = round(success / total * 100, 1) if total else 0
        return {
            "report_type": "api_suite",
            "name": suite.name if suite else "未知套件",
            "status": rec.status,
            "total_cases": total,
            "success_cases": success,
            "failed_cases": failed,
            "skipped_cases": rec.skipped_cases or 0,
            "pass_rate_percent": pass_rate,
            "duration_ms": rec.duration,
            "env_name": rec.env_name,
            "run_by": rec.run_by,
            "failed_case_samples": failed_cases[:15],
        }

    if report_type == "api_plan":
        rec = await ApiPlanRunRecord.get_or_none(id=record_id, project_id=project_id)
        if not rec:
            raise HTTPException(status_code=404, detail="接口计划执行记录不存在")
        plan = await rec.plan
        items = rec.item_results if isinstance(rec.item_results, list) else []
        failed_items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("status") not in API_FAIL_STATUSES and item.get("status") != "failed":
                continue
            failed_items.append(
                {
                    "name": item.get("name") or "未知",
                    "item_type": item.get("item_type"),
                    "status": item.get("status"),
                    "failed": item.get("failed"),
                    "error": (item.get("error") or "")[:300],
                }
            )
        total = rec.total_cases or 0
        success = rec.success_cases or 0
        failed = rec.failed_cases or 0
        pass_rate = round(success / total * 100, 1) if total else 0
        return {
            "report_type": "api_plan",
            "name": plan.name if plan else "未知计划",
            "status": rec.status,
            "total_cases": total,
            "success_cases": success,
            "failed_cases": failed,
            "pass_rate_percent": pass_rate,
            "duration_ms": rec.duration,
            "env_name": rec.env_name,
            "run_by": rec.run_by,
            "failed_item_samples": failed_items[:15],
        }

    if report_type == "ui_suite":
        rec = await UiSuiteExecution.get_or_none(id=record_id, is_del=False).prefetch_related("suite")
        if not rec:
            raise HTTPException(status_code=404, detail="UI 套件执行记录不存在")
        if rec.suite and int(rec.suite.project_id) != project_id:
            raise HTTPException(status_code=403, detail="无权访问该记录")
        case_execs = await UiCaseExecution.filter(suite_execution_id=record_id, is_del=False).prefetch_related("case")
        failed_cases = []
        for ce in case_execs:
            if ce.status not in UI_FAIL_STATUSES:
                continue
            summary = extract_ui_case_failure_summary(ce.result_data)
            failed_cases.append(
                {
                    "case_name": summary.get("case_name") or (ce.case.name if ce.case else "未知"),
                    "status": ce.status,
                    "execution_id": ce.id,
                    "error_hint": summary.get("error_hint") or "",
                    "failed_step_index": summary.get("failed_step_index"),
                    "failed_step_keyword": summary.get("failed_step_keyword") or "",
                    "log_error_excerpt": summary.get("log_error_excerpt") or "",
                    "has_screenshot": summary.get("has_screenshot"),
                    "data_complete": summary.get("data_complete"),
                }
            )
        total = rec.case_count or len(case_execs)
        success = rec.success or 0
        failed = (rec.fail or 0) + (rec.error or 0)
        pass_rate = float(rec.pass_rate or (round(success / total * 100, 2) if total else 0))
        return {
            "report_type": "ui_suite",
            "name": rec.suite.name if rec.suite else "未知套件",
            "status": rec.status,
            "total_cases": total,
            "success_cases": success,
            "failed_cases": failed,
            "pass_rate_percent": pass_rate,
            "duration_sec": rec.duration,
            "failed_case_samples": failed_cases[:15],
        }

    if report_type == "ui_task":
        rec = await UiPlanExecution.get_or_none(id=record_id, project_id=project_id, is_del=False).prefetch_related("task")
        if not rec:
            raise HTTPException(status_code=404, detail="UI 计划执行记录不存在")
        suite_execs = await UiSuiteExecution.filter(plan_execution_id=record_id, is_del=False).prefetch_related("suite")
        failed_suites = []
        for se in suite_execs:
            if (se.fail or 0) + (se.error or 0) <= 0:
                continue
            suite_failed_cases = []
            case_execs = await UiCaseExecution.filter(
                suite_execution_id=se.id, is_del=False, status__in=list(UI_FAIL_STATUSES)
            ).prefetch_related("case").order_by("id").limit(5)
            for ce in case_execs:
                summary = extract_ui_case_failure_summary(ce.result_data)
                suite_failed_cases.append(
                    {
                        "case_name": summary.get("case_name") or (ce.case.name if ce.case else "未知"),
                        "execution_id": ce.id,
                        "status": ce.status,
                        "error_hint": summary.get("error_hint") or "",
                        "failed_step_keyword": summary.get("failed_step_keyword") or "",
                    }
                )
            failed_suites.append(
                {
                    "suite_name": se.suite.name if se.suite else "未知",
                    "fail": se.fail,
                    "error": se.error,
                    "pass_rate": se.pass_rate,
                    "suite_execution_id": se.id,
                    "failed_case_samples": suite_failed_cases,
                }
            )
        total = rec.case_count or 0
        success = rec.success or 0
        failed = (rec.fail or 0) + (rec.error or 0)
        return {
            "report_type": "ui_task",
            "name": rec.task.name if rec.task else "未知计划",
            "status": rec.status,
            "total_cases": total,
            "success_cases": success,
            "failed_cases": failed,
            "pass_rate_percent": rec.pass_rate,
            "duration_sec": rec.duration,
            "failed_suite_samples": failed_suites[:15],
        }

    if report_type == "app_suite":
        rec = await AppSuiteExecution.get_or_none(id=record_id, is_del=False).prefetch_related("suite")
        if not rec:
            raise HTTPException(status_code=404, detail="App 套件执行记录不存在")
        if rec.suite and int(rec.suite.project_id) != project_id:
            raise HTTPException(status_code=403, detail="无权访问该记录")
        case_execs = await AppCaseExecution.filter(suite_execution_id=record_id, is_del=False).prefetch_related("case")
        failed_cases = []
        for ce in case_execs:
            if ce.status not in APP_FAIL_STATUSES:
                continue
            summary = extract_ui_case_failure_summary(ce.result_data)
            failed_cases.append(
                {
                    "case_name": summary.get("case_name") or (ce.case.name if ce.case else "未知"),
                    "status": ce.status,
                    "execution_id": ce.id,
                    "error_hint": summary.get("error_hint") or "",
                    "failed_step_index": summary.get("failed_step_index"),
                    "failed_step_keyword": summary.get("failed_step_keyword") or "",
                    "log_error_excerpt": summary.get("log_error_excerpt") or "",
                    "has_screenshot": summary.get("has_screenshot"),
                    "data_complete": summary.get("data_complete"),
                }
            )
        total = rec.case_count or len(case_execs)
        success = rec.success or 0
        failed = (rec.fail or 0) + (rec.error or 0)
        pass_rate = float(rec.pass_rate or (round(success / total * 100, 2) if total else 0))
        return {
            "report_type": "app_suite",
            "name": rec.suite.name if rec.suite else "未知套件",
            "status": rec.status,
            "total_cases": total,
            "success_cases": success,
            "failed_cases": failed,
            "pass_rate_percent": pass_rate,
            "duration_sec": rec.duration,
            "failed_case_samples": failed_cases[:15],
        }

    if report_type == "app_plan":
        rec = await AppPlanExecution.get_or_none(id=record_id, project_id=project_id, is_del=False).prefetch_related("plan")
        if not rec:
            raise HTTPException(status_code=404, detail="App 计划执行记录不存在")
        suite_execs = await AppSuiteExecution.filter(plan_execution_id=record_id, is_del=False).prefetch_related("suite")
        failed_suites = []
        for se in suite_execs:
            if (se.fail or 0) + (se.error or 0) <= 0:
                continue
            suite_failed_cases = []
            case_execs = await AppCaseExecution.filter(
                suite_execution_id=se.id, is_del=False, status__in=list(APP_FAIL_STATUSES)
            ).prefetch_related("case").order_by("id").limit(5)
            for ce in case_execs:
                summary = extract_ui_case_failure_summary(ce.result_data)
                suite_failed_cases.append(
                    {
                        "case_name": summary.get("case_name") or (ce.case.name if ce.case else "未知"),
                        "execution_id": ce.id,
                        "status": ce.status,
                        "error_hint": summary.get("error_hint") or "",
                        "failed_step_keyword": summary.get("failed_step_keyword") or "",
                    }
                )
            failed_suites.append(
                {
                    "suite_name": se.suite.name if se.suite else "未知",
                    "fail": se.fail,
                    "error": se.error,
                    "pass_rate": se.pass_rate,
                    "suite_execution_id": se.id,
                    "failed_case_samples": suite_failed_cases,
                }
            )
        total = rec.case_count or 0
        success = rec.success or 0
        failed = (rec.fail or 0) + (rec.error or 0)
        return {
            "report_type": "app_plan",
            "name": rec.plan.name if rec.plan else "未知计划",
            "status": rec.status,
            "total_cases": total,
            "success_cases": success,
            "failed_cases": failed,
            "pass_rate_percent": rec.pass_rate,
            "duration_sec": rec.duration,
            "failed_suite_samples": failed_suites[:15],
        }

    raise HTTPException(status_code=400, detail="不支持的报告类型")


async def collect_failure_targets(
    report_type: ReportType,
    record_id: int,
    project_id: int,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """从一次套件/计划执行中收集失败用例，供批量 AI 分析"""
    targets: list[dict[str, Any]] = []

    if report_type == "api_suite":
        rec = await ApiSuiteRunRecord.get_or_none(id=record_id, project_id=project_id)
        if not rec:
            raise HTTPException(status_code=404, detail="接口套件执行记录不存在")
        case_records = await ApiRunRecord.filter(
            suite_run_record_id=record_id,
            status__in=list(API_FAIL_STATUSES),
        ).order_by("id").limit(limit * 2)
        for cr in case_records:
            if len(targets) >= limit:
                break
            case = await cr.case
            targets.append(
                {
                    "target_type": "api",
                    "target_id": cr.id,
                    "case_name": case.name if case else "未知用例",
                    "error_msg": (cr.error_msg or "")[:200],
                }
            )
        return targets

    if report_type == "api_plan":
        rec = await ApiPlanRunRecord.get_or_none(id=record_id, project_id=project_id)
        if not rec:
            raise HTTPException(status_code=404, detail="接口计划执行记录不存在")
        items = rec.item_results if isinstance(rec.item_results, list) else []
        for item in items:
            if len(targets) >= limit:
                break
            if not isinstance(item, dict):
                continue
            for cr in item.get("case_results") or []:
                if len(targets) >= limit:
                    break
                if not isinstance(cr, dict):
                    continue
                if cr.get("status") not in API_FAIL_STATUSES:
                    continue
                rid = cr.get("record_id")
                if not rid:
                    continue
                targets.append(
                    {
                        "target_type": "api",
                        "target_id": int(rid),
                        "case_name": cr.get("case_name") or "未知用例",
                        "error_msg": (cr.get("error_msg") or "")[:200],
                    }
                )
        return targets

    if report_type == "ui_suite":
        rec = await UiSuiteExecution.get_or_none(id=record_id, is_del=False).prefetch_related("suite")
        if not rec:
            raise HTTPException(status_code=404, detail="UI 套件执行记录不存在")
        if rec.suite and int(rec.suite.project_id) != project_id:
            raise HTTPException(status_code=403, detail="无权访问该记录")
        case_execs = await UiCaseExecution.filter(
            suite_execution_id=record_id,
            is_del=False,
            status__in=list(UI_FAIL_STATUSES),
        ).order_by("id").limit(limit)
        for ce in case_execs:
            summary = extract_ui_case_failure_summary(ce.result_data)
            targets.append(
                {
                    "target_type": "ui",
                    "target_id": ce.id,
                    "case_name": summary.get("case_name") or (ce.case.name if ce.case else "未知用例"),
                    "error_msg": (summary.get("error_hint") or summary.get("log_error_excerpt") or "")[:200],
                }
            )
        return targets

    if report_type == "ui_task":
        rec = await UiPlanExecution.get_or_none(id=record_id, project_id=project_id, is_del=False)
        if not rec:
            raise HTTPException(status_code=404, detail="UI 计划执行记录不存在")
        suite_execs = await UiSuiteExecution.filter(plan_execution_id=record_id, is_del=False).order_by("id")
        for se in suite_execs:
            if len(targets) >= limit:
                break
            case_execs = await UiCaseExecution.filter(
                suite_execution_id=se.id,
                is_del=False,
                status__in=list(UI_FAIL_STATUSES),
            ).order_by("id")
            for ce in case_execs:
                if len(targets) >= limit:
                    break
                summary = extract_ui_case_failure_summary(ce.result_data)
                targets.append(
                    {
                        "target_type": "ui",
                        "target_id": ce.id,
                        "case_name": summary.get("case_name") or (ce.case.name if ce.case else "未知用例"),
                        "error_msg": (summary.get("error_hint") or summary.get("log_error_excerpt") or "")[:200],
                    }
                )
        return targets

    if report_type == "app_suite":
        rec = await AppSuiteExecution.get_or_none(id=record_id, is_del=False).prefetch_related("suite")
        if not rec:
            raise HTTPException(status_code=404, detail="App 套件执行记录不存在")
        if rec.suite and int(rec.suite.project_id) != project_id:
            raise HTTPException(status_code=403, detail="无权访问该记录")
        case_execs = await AppCaseExecution.filter(
            suite_execution_id=record_id,
            is_del=False,
            status__in=list(APP_FAIL_STATUSES),
        ).order_by("id").limit(limit)
        for ce in case_execs:
            summary = extract_ui_case_failure_summary(ce.result_data)
            targets.append(
                {
                    "target_type": "app",
                    "target_id": ce.id,
                    "case_name": summary.get("case_name") or (ce.case.name if ce.case else "未知用例"),
                    "error_msg": (summary.get("error_hint") or summary.get("log_error_excerpt") or "")[:200],
                }
            )
        return targets

    if report_type == "app_plan":
        rec = await AppPlanExecution.get_or_none(id=record_id, project_id=project_id, is_del=False)
        if not rec:
            raise HTTPException(status_code=404, detail="App 计划执行记录不存在")
        suite_execs = await AppSuiteExecution.filter(plan_execution_id=record_id, is_del=False).order_by("id")
        for se in suite_execs:
            if len(targets) >= limit:
                break
            case_execs = await AppCaseExecution.filter(
                suite_execution_id=se.id,
                is_del=False,
                status__in=list(APP_FAIL_STATUSES),
            ).order_by("id")
            for ce in case_execs:
                if len(targets) >= limit:
                    break
                summary = extract_ui_case_failure_summary(ce.result_data)
                targets.append(
                    {
                        "target_type": "app",
                        "target_id": ce.id,
                        "case_name": summary.get("case_name") or (ce.case.name if ce.case else "未知用例"),
                        "error_msg": (summary.get("error_hint") or summary.get("log_error_excerpt") or "")[:200],
                    }
                )
        return targets

    raise HTTPException(status_code=400, detail="不支持的报告类型")


async def fetch_recent_failures(project_id: int, limit: int = 8) -> list[dict[str, Any]]:
    """工作台：最近失败执行记录（接口 + UI 混合）"""
    rows: list[dict[str, Any]] = []

    api_records = (
        await ApiRunRecord.filter(project_id=project_id, status__in=list(API_FAIL_STATUSES))
        .order_by("-id")
        .limit(limit)
    )
    for cr in api_records:
        case = await cr.case
        rows.append(
            {
                "target_type": "api",
                "target_id": cr.id,
                "case_name": case.name if case else "未知用例",
                "error_msg": (cr.error_msg or "")[:120],
                "status": cr.status,
                "run_at": cr.start_time.strftime("%Y-%m-%d %H:%M:%S") if cr.start_time else "",
                "sort_ts": cr.start_time.timestamp() if cr.start_time else 0,
                "report_path": f"/api-run-records?recordId={cr.suite_run_record_id or cr.id}",
            }
        )

    ui_records = (
        await UiCaseExecution.filter(is_del=False, status__in=list(UI_FAIL_STATUSES))
        .prefetch_related("case")
        .order_by("-id")
        .limit(limit * 2)
    )
    for ce in ui_records:
        if not ce.case or int(ce.case.project_id) != project_id:
            continue
        summary = extract_ui_case_failure_summary(ce.result_data)
        rows.append(
            {
                "target_type": "ui",
                "target_id": ce.id,
                "case_name": summary.get("case_name") or ce.case.name,
                "error_msg": (summary.get("error_hint") or summary.get("log_error_excerpt") or "")[:120],
                "status": ce.status,
                "run_at": ce.start_time.strftime("%Y-%m-%d %H:%M:%S") if ce.start_time else "",
                "sort_ts": ce.start_time.timestamp() if ce.start_time else 0,
                "report_path": f"/record/report/suite/{ce.suite_execution_id}"
                if ce.suite_execution_id
                else "/record",
            }
        )
        if len([r for r in rows if r["target_type"] == "ui"]) >= limit:
            break

    rows.sort(key=lambda x: x.get("sort_ts") or 0, reverse=True)
    for r in rows:
        r.pop("sort_ts", None)
    return rows[:limit]
