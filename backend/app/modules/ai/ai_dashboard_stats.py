"""AI 工作台与看板共用的 AI 统计计算"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, date
from typing import Any, Optional

import re

from app.models.ai import (
    AiFunctionalCase,
    AiGenerateRecord,
    AiRequirementCase,
    AiRequirementGenerateJob,
    AiRequirementTestPoint,
    AiUsageLog,
)
from app.modules.ai.ai_scene_config import AI_SCENE_DEFINITIONS
from app.models.http import ApiRunRecord, ApiSuiteRunRecord
from app.models.perf import PerfRecord
from app.models.sys import Device, OperationLog, User
from app.models.ui import UiPlanExecution
from app.models.app import AppCaseExecution, AppPlanExecution, AppSuiteExecution


def _to_naive_local(dt: datetime) -> datetime:
    """ORM 可能返回带时区的 datetime，统一转为本地 naive 再比较。"""
    if dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


def _local_today_start() -> datetime:
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def _default_period_range(days: int = 30) -> tuple[datetime, datetime]:
    end_dt = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
    start_dt = _local_today_start() - timedelta(days=days - 1)
    return start_dt, end_dt


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
            "path": "/ai-testing/requirements/" + str(req_id) if req_id else "/ai-testing",
            "query": {"tab": "points"} if req_id else {"tab": "points"},
            "hint": "进入测试分析确认测试点",
            "level": "warning",
        })
    if draft_cases:
        req_id = await _latest_requirement_id_for_draft_cases(project_id)
        todos.append({
            "type": "draft_cases",
            "title": "工作区草稿用例",
            "count": draft_cases,
            "path": "/ai-testing/requirements/" + str(req_id) if req_id else "/ai-testing",
            "query": {"tab": "cases"} if req_id else {},
            "hint": "打开需求工作区继续编辑用例",
            "level": "warning",
        })
    if not_in_library:
        req_id = await _latest_requirement_id_not_in_library(project_id)
        todos.append({
            "type": "not_in_library",
            "title": "未入库功能用例",
            "count": not_in_library,
            "path": "/ai-testing/requirements/" + str(req_id) if req_id else "/ai-testing",
            "query": {"tab": "cases"} if req_id else {},
            "hint": "将工作区用例复制到功能用例库",
            "level": "info",
        })
    if pending_ui:
        todos.append({
            "type": "pending_ui",
            "title": "待转 Web 自动化",
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
            "path": "/ai-testing/requirements/" + str(req_id) if req_id else "/ai-testing",
            "query": {"tab": "cases"} if req_id else {},
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
    """统计 Token 消耗；优先 ai_usage_log，无记录时回退历史 generate_record / job 表。"""
    if start_dt is None or end_dt is None:
        start_dt, end_dt = _default_period_range(30)

    log_q = AiUsageLog.filter(create_time__gte=start_dt, create_time__lte=end_dt)
    rec_q = AiGenerateRecord.filter(create_time__gte=start_dt, create_time__lte=end_dt)
    job_q = AiRequirementGenerateJob.filter(create_time__gte=start_dt, create_time__lte=end_dt)
    if project_id:
        log_q = log_q.filter(project_id=project_id)
        rec_q = rec_q.filter(project_id=project_id)
        job_q = job_q.filter(project_id=project_id)

    logs = await log_q.all()
    records = await rec_q.all()
    jobs = await job_q.all()
    log_tokens = sum(l.tokens_used or 0 for l in logs)
    record_tokens = sum(r.tokens_used or 0 for r in records)
    job_tokens = sum(j.tokens_used or 0 for j in jobs)
    legacy_tokens = record_tokens + job_tokens
    return {
        "month_generate_count": len(records),
        "month_job_count": len(jobs),
        "month_usage_log_count": len(logs),
        "month_usage_log_tokens": log_tokens,
        "month_record_tokens": record_tokens,
        "month_job_tokens": job_tokens,
        "month_tokens_used": log_tokens if logs else legacy_tokens,
    }


async def collect_usage_summary(
    project_id: Optional[int],
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
) -> dict[str, Any]:
    """本月 AI 调用汇总：今日 Token、Top 场景。"""
    if start_dt is None or end_dt is None:
        start_dt, end_dt = _default_period_range(30)
    today_start = _local_today_start()

    qs = AiUsageLog.filter(create_time__gte=start_dt, create_time__lte=end_dt)
    if project_id:
        qs = qs.filter(project_id=project_id)
    logs = await qs.all()

    today_tokens = 0
    scene_tokens: dict[str, int] = defaultdict(int)
    scene_labels: dict[str, str] = {}
    for row in logs:
        ct = _to_naive_local(row.create_time) if row.create_time else None
        if ct and ct >= today_start:
            today_tokens += row.tokens_used or 0
        scene = row.scene or "unknown"
        scene_tokens[scene] += row.tokens_used or 0
        if row.scene_label:
            scene_labels[scene] = row.scene_label

    top_scenes: list[dict[str, Any]] = []
    for scene, tokens in sorted(scene_tokens.items(), key=lambda x: x[1], reverse=True)[:5]:
        if tokens <= 0:
            continue
        label = scene_labels.get(scene) or AI_SCENE_DEFINITIONS.get(scene, (scene, ""))[0]
        top_scenes.append({"scene": scene, "label": label, "tokens": tokens})

    month_tokens = sum(l.tokens_used or 0 for l in logs)
    return {
        "today_tokens": today_tokens,
        "month_tokens": month_tokens,
        "month_count": len(logs),
        "top_scenes": top_scenes,
    }


async def collect_generate_trend(project_id: Optional[int], days: int = 7) -> list[dict[str, Any]]:
    """近 N 日 AI 调用趋势（基于 ai_usage_log）。"""
    end_dt = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
    start_dt = _local_today_start() - timedelta(days=days - 1)
    end = end_dt.date()
    start = start_dt.date()

    qs = AiUsageLog.filter(create_time__gte=start_dt, create_time__lte=end_dt)
    if project_id:
        qs = qs.filter(project_id=project_id)
    logs = await qs.all()

    day_map: dict[str, dict[str, int]] = {}
    cur = start
    while cur <= end:
        day_map[cur.strftime("%Y-%m-%d")] = {"total": 0, "success": 0, "failed": 0, "tokens": 0}
        cur += timedelta(days=1)

    for row in logs:
        ct = _to_naive_local(row.create_time) if row.create_time else None
        d = ct.strftime("%Y-%m-%d") if ct else None
        if not d or d not in day_map:
            continue
        day_map[d]["total"] += 1
        if row.status == "failed":
            day_map[d]["failed"] += 1
        else:
            day_map[d]["success"] += 1
        day_map[d]["tokens"] += row.tokens_used or 0

    return [{"date": d, **day_map[d]} for d in sorted(day_map.keys())]


_RUNNER_USERNAME_RE = re.compile(r"^(.+)\(([^)]+)\)$")


def _normalize_activity_username(raw: str, device_ids: set[str], runner_mq_users: set[str]) -> str | None:
    name = (raw or "").strip()
    if not name:
        return None
    if name.startswith("runner_") or name in runner_mq_users:
        return None
    match = _RUNNER_USERNAME_RE.match(name)
    if match:
        base, suffix = match.group(1).strip(), match.group(2).strip()
        if suffix in device_ids or (suffix.isdigit() and len(suffix) >= 8):
            return base or None
    return name


async def _load_runner_identity_sets() -> tuple[set[str], set[str]]:
    device_ids: set[str] = set()
    runner_mq_users: set[str] = set()
    for row in await Device.filter(is_del=False).values("id", "runner_mq_username"):
        did = (row.get("id") or "").strip()
        if did:
            device_ids.add(did)
        mq_user = (row.get("runner_mq_username") or "").strip()
        if mq_user:
            runner_mq_users.add(mq_user)
    return device_ids, runner_mq_users


async def _format_activity_display(usernames: list[str]) -> list[dict[str, Any]]:
    users = await User.filter(username__in=usernames, is_del=False).values("username", "nickname")
    nick_map = {u["username"]: (u.get("nickname") or u["username"]) for u in users}
    rows = []
    for username in usernames:
        nick = nick_map.get(username) or username
        if nick == username:
            display_name = username
        else:
            display_name = f"{nick}（{username}）"
        rows.append({"username": display_name, "activity_score": 0})
    return rows


async def collect_user_activity_top(
    project_id: Optional[int],
    start_dt: datetime,
    end_dt: datetime,
    limit: int = 5,
) -> list[dict[str, Any]]:
    device_ids, runner_mq_users = await _load_runner_identity_sets()
    counts: dict[str, int] = defaultdict(int)

    def bump(raw: str, weight: int = 1) -> None:
        key = _normalize_activity_username(raw, device_ids, runner_mq_users)
        if key:
            counts[key] += weight

    log_q = OperationLog.filter(create_time__gte=start_dt, create_time__lte=end_dt).exclude(
        path__startswith="/runner/"
    )
    for row in await log_q.values("username"):
        bump(row.get("username") or "", 1)

    ui_q = UiPlanExecution.filter(start_time__gte=start_dt, start_time__lte=end_dt, is_del=False)
    if project_id:
        ui_q = ui_q.filter(project_id=project_id)
    for row in await ui_q.values("username"):
        bump(row.get("username") or "", 2)

    api_q = ApiRunRecord.filter(start_time__gte=start_dt, start_time__lte=end_dt)
    if project_id:
        api_q = api_q.filter(project_id=project_id)
    for row in await api_q.values("run_by"):
        bump(row.get("run_by") or "", 2)

    suite_q = ApiSuiteRunRecord.filter(start_time__gte=start_dt, start_time__lte=end_dt)
    if project_id:
        suite_q = suite_q.filter(project_id=project_id)
    for row in await suite_q.values("run_by"):
        bump(row.get("run_by") or "", 2)

    perf_q = PerfRecord.filter(started_at__gte=start_dt, started_at__lte=end_dt)
    if project_id:
        perf_q = perf_q.filter(project_id=project_id)
    for row in await perf_q.values("run_by"):
        bump(row.get("run_by") or "", 2)

    app_plan_q = AppPlanExecution.filter(start_time__gte=start_dt, start_time__lte=end_dt, is_del=False)
    app_suite_q = AppSuiteExecution.filter(start_time__gte=start_dt, start_time__lte=end_dt, is_del=False)
    app_case_q = AppCaseExecution.filter(start_time__gte=start_dt, start_time__lte=end_dt, is_del=False)
    if project_id:
        app_plan_q = app_plan_q.filter(project_id=project_id)
        app_suite_q = app_suite_q.filter(suite__project_id=project_id)
        app_case_q = app_case_q.filter(case__project_id=project_id)
    for row in await app_plan_q.values("username"):
        bump(row.get("username") or "", 2)
    for row in await app_suite_q.values("username"):
        bump(row.get("username") or "", 2)
    for row in await app_case_q.values("username"):
        bump(row.get("username") or "", 2)

    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    if not ranked:
        return []
    display_rows = await _format_activity_display([u for u, _ in ranked])
    for i, (_, score) in enumerate(ranked):
        display_rows[i]["activity_score"] = score
    return display_rows
