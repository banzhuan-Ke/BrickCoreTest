"""最近执行记录列表（报告向导选用）"""
from __future__ import annotations

from typing import Any

from app.models.app import AppPlanExecution, AppSuiteExecution
from app.models.http import ApiPlanRunRecord, ApiSuiteRunRecord
from app.models.ui import UiPlanExecution, UiSuiteExecution


async def list_recent_exec_records(project_id: int, limit: int = 30) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    api_suites = (
        await ApiSuiteRunRecord.filter(project_id=project_id)
        .order_by("-id")
        .limit(limit)
        .prefetch_related("suite")
    )
    for rec in api_suites:
        suite = rec.suite
        items.append(
            {
                "report_type": "api_suite",
                "record_id": rec.id,
                "name": suite.name if suite else f"API套件#{rec.id}",
                "status": rec.status,
                "pass_rate": round((rec.success_cases or 0) / rec.total_cases * 100, 1)
                if rec.total_cases
                else 0,
                "total_cases": rec.total_cases or 0,
                "run_at": rec.start_time.isoformat() if rec.start_time else None,
                "sort_ts": rec.start_time.timestamp() if rec.start_time else rec.id,
            }
        )

    api_plans = (
        await ApiPlanRunRecord.filter(project_id=project_id)
        .order_by("-id")
        .limit(limit)
        .prefetch_related("plan")
    )
    for rec in api_plans:
        plan = rec.plan
        items.append(
            {
                "report_type": "api_plan",
                "record_id": rec.id,
                "name": plan.name if plan else f"API计划#{rec.id}",
                "status": rec.status,
                "pass_rate": round((rec.success_cases or 0) / rec.total_cases * 100, 1)
                if rec.total_cases
                else 0,
                "total_cases": rec.total_cases or 0,
                "run_at": rec.start_time.isoformat() if rec.start_time else None,
                "sort_ts": rec.start_time.timestamp() if rec.start_time else rec.id,
            }
        )

    ui_suites = (
        await UiSuiteExecution.filter(is_del=False)
        .order_by("-id")
        .limit(limit * 2)
        .prefetch_related("suite")
    )
    for rec in ui_suites:
        if not rec.suite or int(rec.suite.project_id) != project_id:
            continue
        items.append(
            {
                "report_type": "ui_suite",
                "record_id": rec.id,
                "name": rec.suite.name,
                "status": rec.status,
                "pass_rate": float(rec.pass_rate or 0),
                "total_cases": rec.case_count or 0,
                "run_at": rec.start_time.isoformat() if rec.start_time else None,
                "sort_ts": rec.start_time.timestamp() if rec.start_time else rec.id,
            }
        )

    ui_tasks = (
        await UiPlanExecution.filter(project_id=project_id, is_del=False)
        .order_by("-id")
        .limit(limit)
        .prefetch_related("task")
    )
    for rec in ui_tasks:
        items.append(
            {
                "report_type": "ui_task",
                "record_id": rec.id,
                "name": rec.task.name if rec.task else f"UI计划#{rec.id}",
                "status": rec.status,
                "pass_rate": float(rec.pass_rate or 0),
                "total_cases": rec.case_count or 0,
                "run_at": rec.start_time.isoformat() if rec.start_time else None,
                "sort_ts": rec.start_time.timestamp() if rec.start_time else rec.id,
            }
        )

    app_suites = (
        await AppSuiteExecution.filter(is_del=False)
        .order_by("-id")
        .limit(limit * 2)
        .prefetch_related("suite")
    )
    for rec in app_suites:
        if not rec.suite or int(rec.suite.project_id) != project_id:
            continue
        items.append(
            {
                "report_type": "app_suite",
                "record_id": rec.id,
                "name": rec.suite.name,
                "status": rec.status,
                "pass_rate": float(rec.pass_rate or 0),
                "total_cases": rec.case_count or 0,
                "run_at": rec.start_time.isoformat() if rec.start_time else None,
                "sort_ts": rec.start_time.timestamp() if rec.start_time else rec.id,
            }
        )

    app_plans = (
        await AppPlanExecution.filter(project_id=project_id, is_del=False)
        .order_by("-id")
        .limit(limit)
        .prefetch_related("plan")
    )
    for rec in app_plans:
        items.append(
            {
                "report_type": "app_plan",
                "record_id": rec.id,
                "name": rec.plan.name if rec.plan else f"App计划#{rec.id}",
                "status": rec.status,
                "pass_rate": float(rec.pass_rate or 0),
                "total_cases": rec.case_count or 0,
                "run_at": rec.start_time.isoformat() if rec.start_time else None,
                "sort_ts": rec.start_time.timestamp() if rec.start_time else rec.id,
            }
        )

    items.sort(key=lambda x: x.get("sort_ts") or 0, reverse=True)
    for it in items:
        it.pop("sort_ts", None)
    return items[:limit]
