"""AI 工作台与看板共用的 AI 统计计算"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, date
from typing import Any, Optional

from app.models.ai import (
    AiFunctionalCase,
    AiGenerateRecord,
    AiRequirementCase,
    AiRequirementGenerateJob,
    AiRequirementTestPoint,
)
from app.models.http import ApiRunRecord, ApiSuiteRunRecord
from app.models.perf import PerfRecord
from app.models.sys import OperationLog
from app.models.ui import UiPlanExecution


def build_workbench_funnel(stats: dict[str, int]) -> list[dict[str, Any]]:
    """AI 转化链路：按业务流程顺序排列，转化率相对上一环节计算。"""
    raw = [
        {"stage": "需求文档", "key": "requirement", "count": stats.get("requirement_total", 0)},
        {"stage": "测试点", "key": "test_point", "count": stats.get("test_point_total", 0)},
        {"stage": "工作区用例", "key": "case", "count": stats.get("case_total", 0)},
        {"stage": "功能用例库", "key": "library", "count": stats.get("functional_case_total", 0)},
        {"stage": "已转 UI", "key": "ui", "count": stats.get("ui_automated_count", 0)},
    ]
    prev_count: Optional[int] = None
    for item in raw:
        count = item["count"]
        if prev_count is not None and prev_count > 0:
            # 相对上一环节转化率（可大于 100%，表示中间环节有扩充/合并）
            item["rate_from_prev"] = round(min(count / prev_count * 100, 999.9), 1)
        else:
            item["rate_from_prev"] = None
        prev_count = count
    return raw


async def _latest_requirement_id_for_draft_points(project_id: int) -> Optional[int]:
    row = await AiRequirementTestPoint.filter(
        project_id=project_id, is_del=False, status="draft",
    ).order_by("-update_time", "-id").first()
    return row.requirement_id if row else None


async def _latest_requirement_id_for_draft_cases(project_id: int) -> Optional[int]:
    row = await AiRequirementCase.filter(
        project_id=project_id, is_del=False, status="draft",
    ).order_by("-update_time", "-id").first()
    return row.requirement_id if row else None


async def _latest_requirement_id_not_in_library(project_id: int) -> Optional[int]:
    imported_ids = await AiFunctionalCase.filter(
        project_id=project_id,
        is_del=False,
        source_requirement_case_id__not_isnull=True,
    ).values_list("source_requirement_case_id", flat=True)
    row = await AiRequirementCase.filter(
        project_id=project_id, is_del=False,
    ).exclude(id__in=list(imported_ids)).order_by("-update_time", "-id").first()
    return row.requirement_id if row else None


async def _latest_failed_job_requirement_id(project_id: int) -> Optional[int]:
    row = await AiRequirementGenerateJob.filter(
        project_id=project_id, status="failed",
    ).order_by("-update_time", "-id").first()
    return row.requirement_id if row else None


async def build_workbench_todos(project_id: int) -> list[dict[str, Any]]:
    draft_points = await AiRequirementTestPoint.filter(
        project_id=project_id, is_del=False, status="draft",
    ).count()
    draft_cases = await AiRequirementCase.filter(
        project_id=project_id, is_del=False, status="draft",
    ).count()

    imported_ids = await AiFunctionalCase.filter(
        project_id=project_id,
        is_del=False,
        source_requirement_case_id__not_isnull=True,
    ).values_list("source_requirement_case_id", flat=True)
    not_in_library = await AiRequirementCase.filter(
        project_id=project_id, is_del=False,
    ).exclude(id__in=list(imported_ids)).count()

    failed_jobs = await AiRequirementGenerateJob.filter(
        project_id=project_id, status="failed",
    ).count()
    rejected_records = await AiGenerateRecord.filter(
        project_id=project_id, status="rejected",
    ).count()

    functional_total = await AiFunctionalCase.filter(project_id=project_id, is_del=False).count()
    from app.models.ui import Case as UiCase
    ui_linked = await UiCase.filter(
        project_id=project_id,
        is_del=False,
        source_functional_case_id__not_isnull=True,
    ).count()
    pending_ui = max(0, functional_total - ui_linked)

    todos: list[dict[str, Any]] = []
    if draft_points:
        req_id = await _latest_requirement_id_for_draft_points(project_id)
        todos.append({
            "type": "draft_test_points",
            "title": "未确认测试点",
            "count": draft_points,
            "path": "/ai-test-analysis",
            "query": {"reqId": str(req_id)} if req_id else {},
            "hint": "进入测试分析确认测试点",
            "level": "warning",
        })
    if draft_cases:
        req_id = await _latest_requirement_id_for_draft_cases(project_id)
        todos.append({
            "type": "draft_cases",
            "title": "工作区草稿用例",
            "count": draft_cases,
            "path": "/ai-requirements",
            "query": {"reqId": str(req_id)} if req_id else {},
            "hint": "打开需求工作区继续编辑用例",
            "level": "warning",
        })
    if not_in_library:
        req_id = await _latest_requirement_id_not_in_library(project_id)
        todos.append({
            "type": "not_in_library",
            "title": "未入库功能用例",
            "count": not_in_library,
            "path": "/ai-requirements",
            "query": {"reqId": str(req_id)} if req_id else {},
            "hint": "将工作区用例复制到功能用例库",
            "level": "info",
        })
    if pending_ui:
        todos.append({
            "type": "pending_ui",
            "title": "待转 UI 自动化",
            "count": pending_ui,
            "path": "/ai-functional-cases",
            "query": {},
            "hint": "在功能用例库勾选并生成 UI 步骤",
            "level": "info",
        })
    if failed_jobs:
        req_id = await _latest_failed_job_requirement_id(project_id)
        todos.append({
            "type": "failed_jobs",
            "title": "生成任务失败",
            "count": failed_jobs,
            "path": "/ai-requirements",
            "query": {"reqId": str(req_id)} if req_id else {},
            "hint": "查看失败任务并重试",
            "level": "danger",
        })
    if rejected_records:
        todos.append({
            "type": "rejected_records",
            "title": "AI 生成失败记录",
            "count": rejected_records,
            "path": "/ai-test",
            "query": {},
            "hint": "在工作台查看最近生成失败项",
            "level": "danger",
        })
    return todos


async def collect_token_stats(
    project_id: Optional[int],
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
) -> dict[str, Any]:
    """统计 Token 消耗；未传时间范围时默认近 30 日（与看板日期筛选一致时可传入 start/end）。"""
    if start_dt is None or end_dt is None:
        end_dt = datetime.combine(date.today(), datetime.max.time())
        start_dt = datetime.combine(date.today() - timedelta(days=29), datetime.min.time())

    rec_q = AiGenerateRecord.filter(create_time__gte=start_dt, create_time__lte=end_dt)
    job_q = AiRequirementGenerateJob.filter(create_time__gte=start_dt, create_time__lte=end_dt)
    if project_id:
        rec_q = rec_q.filter(project_id=project_id)
        job_q = job_q.filter(project_id=project_id)

    records = await rec_q.all()
    jobs = await job_q.all()
    record_tokens = sum(r.tokens_used or 0 for r in records)
    job_tokens = sum(j.tokens_used or 0 for j in jobs)
    return {
        "month_generate_count": len(records),
        "month_job_count": len(jobs),
        "month_tokens_used": record_tokens + job_tokens,
        "month_record_tokens": record_tokens,
        "month_job_tokens": job_tokens,
    }


async def collect_generate_trend(project_id: Optional[int], days: int = 7) -> list[dict[str, Any]]:
    end = date.today()
    start = end - timedelta(days=days - 1)
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())

    qs = AiGenerateRecord.filter(create_time__gte=start_dt, create_time__lte=end_dt)
    if project_id:
        qs = qs.filter(project_id=project_id)
    records = await qs.all()

    day_map: dict[str, dict[str, int]] = {}
    cur = start
    while cur <= end:
        day_map[cur.strftime("%Y-%m-%d")] = {"total": 0, "success": 0, "failed": 0}
        cur += timedelta(days=1)

    for r in records:
        d = r.create_time.strftime("%Y-%m-%d") if r.create_time else None
        if not d or d not in day_map:
            continue
        day_map[d]["total"] += 1
        if r.status in ("imported", "accepted", "pending"):
            day_map[d]["success"] += 1
        elif r.status == "rejected":
            day_map[d]["failed"] += 1

    return [{"date": d, **day_map[d]} for d in sorted(day_map.keys())]


async def collect_user_activity_top(
    project_id: Optional[int],
    start_dt: datetime,
    end_dt: datetime,
    limit: int = 5,
) -> list[dict[str, Any]]:
    counts: dict[str, int] = defaultdict(int)

    log_q = OperationLog.filter(create_time__gte=start_dt, create_time__lte=end_dt)
    for row in await log_q.values("username"):
        name = (row.get("username") or "").strip()
        if name:
            counts[name] += 1

    ui_q = UiPlanExecution.filter(start_time__gte=start_dt, start_time__lte=end_dt, is_del=False)
    if project_id:
        ui_q = ui_q.filter(project_id=project_id)
    for row in await ui_q.values("username"):
        name = (row.get("username") or "").strip()
        if name:
            counts[name] += 2

    api_q = ApiRunRecord.filter(start_time__gte=start_dt, start_time__lte=end_dt)
    if project_id:
        api_q = api_q.filter(project_id=project_id)
    for row in await api_q.values("run_by"):
        name = (row.get("run_by") or "").strip()
        if name:
            counts[name] += 2

    suite_q = ApiSuiteRunRecord.filter(start_time__gte=start_dt, start_time__lte=end_dt)
    if project_id:
        suite_q = suite_q.filter(project_id=project_id)
    for row in await suite_q.values("run_by"):
        name = (row.get("run_by") or "").strip()
        if name:
            counts[name] += 2

    perf_q = PerfRecord.filter(started_at__gte=start_dt, started_at__lte=end_dt)
    if project_id:
        perf_q = perf_q.filter(project_id=project_id)
    for row in await perf_q.values("run_by"):
        name = (row.get("run_by") or "").strip()
        if name:
            counts[name] += 2

    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [{"username": u, "activity_score": c} for u, c in ranked]
