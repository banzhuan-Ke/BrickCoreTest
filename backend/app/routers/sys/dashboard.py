"""首页统计看板 API"""
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Query, status

from app.core.auth import is_authenticated
from app.core.dashboard_extra import (
    build_case_proportion,
    build_execution_proportion,
    compute_next_run,
    sort_pending_jobs,
    within_hours,
)
from app.core.ai_dashboard_stats import (
    collect_generate_trend,
    collect_token_stats,
    collect_user_activity_top,
)
from app.models.ui import Case as UiCase, Suite as UiSuite, UiCaseExecution, UiPlanExecution
from app.models.http import ApiTestCase, ApiTestSuite, ApiRunRecord, ApiSuiteRunRecord, ApiCronJob
from app.models.perf import PerfScene, PerfRecord, PerfCronJob
from app.models.schedule import Cronjob
from app.models.ai import AiGenerateRecord, AiRequirementGenerateJob
from app.models.sys import Device

router = APIRouter(prefix="/dashboard", tags=["首页看板"], dependencies=[Depends(is_authenticated)])


def _parse_date(d: Optional[str]) -> Optional[date]:
    if not d:
        return None
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except Exception:
        return None


def _date_range(days: int = 7) -> tuple:
    end = date.today()
    start = end - timedelta(days=days - 1)
    return start, end


def _generate_date_list(start: date, end: date) -> List[str]:
    res = []
    cur = start
    while cur <= end:
        res.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return res


async def _collect_pending_cron_jobs(project_id: Optional[int], limit: int = 5) -> List[Dict[str, Any]]:
    now = datetime.now()
    pending: List[Dict[str, Any]] = []

    ui_q = Cronjob.filter(is_del=False, state=True)
    if project_id:
        ui_q = ui_q.filter(project_id=project_id)
    for job in await ui_q.all():
        nxt = compute_next_run(job.run_type, job.interval, job.date, job.crontab, now=now)
        if not within_hours(nxt, 48):
            continue
        task = await job.task
        pending.append({
            "id": job.id,
            "name": job.name,
            "type": "Web",
            "target": task.name if task else "测试计划",
            "next_run_time": nxt.strftime("%Y-%m-%d %H:%M:%S") if nxt else "",
            "_sort": nxt or datetime.max,
        })

    api_q = ApiCronJob.filter(is_del=False, state=True)
    if project_id:
        api_q = api_q.filter(project_id=project_id)
    for job in await api_q.all():
        nxt = compute_next_run(job.run_type, job.interval, job.run_date, job.crontab, now=now)
        if not within_hours(nxt, 48):
            continue
        target = ""
        if job.plan_id:
            plan = await job.plan
            target = plan.name if plan else "测试计划"
        elif job.suite_id:
            suite = await job.suite
            target = suite.name if suite else "套件"
        pending.append({
            "id": job.id,
            "name": job.name,
            "type": "接口",
            "target": target or "接口任务",
            "next_run_time": nxt.strftime("%Y-%m-%d %H:%M:%S") if nxt else "",
            "_sort": nxt or datetime.max,
        })

    perf_q = PerfCronJob.filter(is_del=False, state=True)
    if project_id:
        perf_q = perf_q.filter(project_id=project_id)
    for job in await perf_q.all():
        nxt = compute_next_run(job.run_type, job.interval, job.run_date, job.crontab, now=now)
        if not within_hours(nxt, 48):
            continue
        scene = await job.scene
        pending.append({
            "id": job.id,
            "name": job.name,
            "type": "性能",
            "target": scene.name if scene else "压测场景",
            "next_run_time": nxt.strftime("%Y-%m-%d %H:%M:%S") if nxt else "",
            "_sort": nxt or datetime.max,
        })

    return sort_pending_jobs(pending, limit)


async def _collect_ai_summary(project_id: Optional[int]) -> Dict[str, Any]:
    job_q = AiRequirementGenerateJob.filter(status__in=["pending", "running"])
    gen_q = AiGenerateRecord.filter()
    if project_id:
        job_q = job_q.filter(project_id=project_id)
        gen_q = gen_q.filter(project_id=project_id)

    running_jobs = await job_q.count()
    since = datetime.now() - timedelta(days=7)
    recent_generate_count = await gen_q.filter(create_time__gte=since).count()
    recent_requirement_cases = await gen_q.filter(
        create_time__gte=since,
        generate_type="requirement_case",
    ).count()

    online_devices = await Device.filter(is_del=False, status="在线").count()
    total_devices = await Device.filter(is_del=False).count()

    return {
        "running_jobs": running_jobs,
        "recent_generate_count": recent_generate_count,
        "recent_requirement_cases": recent_requirement_cases,
        "device_online": online_devices,
        "device_total": total_devices,
    }


@router.get("", summary="首页统计看板", status_code=status.HTTP_200_OK)
async def get_dashboard(
    start_date: Optional[str] = Query(None, description="开始日期 yyyy-MM-dd"),
    end_date: Optional[str] = Query(None, description="结束日期 yyyy-MM-dd"),
    project_id: Optional[int] = Query(None, description="项目ID（不传则统计全部）")
):
    """获取首页统计看板数据"""
    s = _parse_date(start_date)
    e = _parse_date(end_date)
    if not s or not e:
        s, e = _date_range(7)

    date_list = _generate_date_list(s, e)
    s_dt = datetime.combine(s, datetime.min.time())
    e_dt = datetime.combine(e, datetime.max.time())

    # ========== 执行趋势（按日聚合） ==========
    # UI 用例执行记录
    ui_q = UiCaseExecution.filter(start_time__gte=s_dt, start_time__lte=e_dt)
    if project_id:
        ui_case_ids = await UiCase.filter(project_id=project_id, is_del=False).values_list("id", flat=True)
        ui_q = ui_q.filter(case_id__in=ui_case_ids)
    ui_records = await ui_q.all()

    ui_trend_map = {d: {"success": 0, "fail": 0} for d in date_list}
    for r in ui_records:
        d = r.start_time.strftime("%Y-%m-%d") if r.start_time else None
        if d and d in ui_trend_map:
            if r.status == "success":
                ui_trend_map[d]["success"] += 1
            elif r.status in ("fail", "error", "failed"):
                ui_trend_map[d]["fail"] += 1

    ui_execution_trend = [{"date": d, **ui_trend_map[d]} for d in date_list]

    # API 用例执行记录
    api_q = ApiRunRecord.filter(start_time__gte=s_dt, start_time__lte=e_dt)
    if project_id:
        api_q = api_q.filter(project_id=project_id)
    api_records = await api_q.all()

    api_trend_map = {d: {"success": 0, "fail": 0} for d in date_list}
    for r in api_records:
        d = r.start_time.strftime("%Y-%m-%d") if r.start_time else None
        if d and d in api_trend_map:
            if r.status == "success":
                api_trend_map[d]["success"] += 1
            elif r.status == "failed":
                api_trend_map[d]["fail"] += 1

    api_execution_trend = [{"date": d, **api_trend_map[d]} for d in date_list]

    # 性能测试执行记录
    perf_q = PerfRecord.filter(started_at__gte=s_dt, started_at__lte=e_dt)
    if project_id:
        perf_q = perf_q.filter(project_id=project_id)
    perf_records = await perf_q.only(
        "id", "started_at", "status", "qps", "error_rate",
        "scene_id", "fail_count", "total_requests",
    ).prefetch_related("scene").all()

    perf_trend_map = {d: {"success": 0, "fail": 0} for d in date_list}
    for r in perf_records:
        d = r.started_at.strftime("%Y-%m-%d") if r.started_at else None
        if d and d in perf_trend_map:
            if r.status == "success":
                perf_trend_map[d]["success"] += 1
            elif r.status in ("failed", "stopped"):
                perf_trend_map[d]["fail"] += 1

    perf_execution_trend = [{"date": d, **perf_trend_map[d]} for d in date_list]

    # ========== 用例/套件总数统计 ==========
    ui_case_filter = {"is_del": False}
    ui_suite_filter = {"is_del": False}
    api_case_filter = {"is_del": False}
    api_suite_filter = {"is_del": False}
    perf_scene_filter = {"is_del": False}
    if project_id:
        ui_case_filter["project_id"] = project_id
        ui_suite_filter["project_id"] = project_id
        api_case_filter["project_id"] = project_id
        api_suite_filter["project_id"] = project_id
        perf_scene_filter["project_id"] = project_id

    ui_case_total = await UiCase.filter(**ui_case_filter).count()
    ui_suite_total = await UiSuite.filter(**ui_suite_filter).count()
    api_case_total = await ApiTestCase.filter(**api_case_filter).count()
    api_suite_total = await ApiTestSuite.filter(**api_suite_filter).count()
    perf_scene_total = await PerfScene.filter(**perf_scene_filter).count()

    # 性能测试平均指标（只统计有结果的记录）
    perf_success_records = [r for r in perf_records if r.status in ("success", "failed", "stopped")]
    perf_avg_qps = round(sum(r.qps for r in perf_success_records) / len(perf_success_records), 2) if perf_success_records else 0
    perf_avg_error_rate = round(sum(r.error_rate for r in perf_success_records) / len(perf_success_records), 2) if perf_success_records else 0
    perf_exec_total = len(perf_success_records)

    stats = {
        "ui_case_total": ui_case_total,
        "ui_suite_total": ui_suite_total,
        "api_case_total": api_case_total,
        "api_suite_total": api_suite_total,
        "perf_scene_total": perf_scene_total,
        "perf_exec_total": perf_exec_total,
        "perf_avg_qps": perf_avg_qps,
        "perf_avg_error_rate": perf_avg_error_rate,
        "total_case": ui_case_total + api_case_total,
        "total_suite": ui_suite_total + api_suite_total,
    }

    # ========== Top 5 失败用例（时间范围内） ==========
    top_failed_cases = []

    # UI 失败用例聚合
    ui_failed_q = UiCaseExecution.filter(
        start_time__gte=s_dt, start_time__lte=e_dt, status__in=["fail", "error", "failed"]
    )
    if project_id:
        ui_failed_q = ui_failed_q.filter(case_id__in=ui_case_ids)
    ui_failed_records = await ui_failed_q.prefetch_related("case").all()

    ui_fail_map: Dict[int, Dict] = {}
    for r in ui_failed_records:
        cid = r.case_id
        case = await r.case
        if cid not in ui_fail_map:
            ui_fail_map[cid] = {"case_name": case.name if case else "未知", "type": "Web", "count": 0}
        ui_fail_map[cid]["count"] += 1

    # API 失败用例聚合
    api_failed_q = ApiRunRecord.filter(start_time__gte=s_dt, start_time__lte=e_dt, status="failed")
    if project_id:
        api_failed_q = api_failed_q.filter(project_id=project_id)
    api_failed_records = await api_failed_q.prefetch_related("case").all()

    api_fail_map: Dict[int, Dict] = {}
    for r in api_failed_records:
        cid = r.case_id
        case = await r.case
        if cid not in api_fail_map:
            api_fail_map[cid] = {"case_name": case.name if case else "未知", "type": "接口", "count": 0}
        api_fail_map[cid]["count"] += 1

    all_fails = list(ui_fail_map.values()) + list(api_fail_map.values())
    all_fails.sort(key=lambda x: x["count"], reverse=True)
    top_failed_cases = all_fails[:5]

    # ========== Top 5 性能测试失败场景（按错误率）==========
    # 复用上方已加载的 perf_records，避免 DB 对大表按 error_rate 排序导致 sort buffer 溢出
    perf_top_candidates = sorted(
        (r for r in perf_records if r.status in ("success", "failed") and r.error_rate > 0),
        key=lambda r: r.error_rate,
        reverse=True,
    )[:5]
    perf_top_failed_scenes = []
    for r in perf_top_candidates:
        scene = await r.scene
        perf_top_failed_scenes.append({
            "scene_name": scene.name if scene else "未知场景",
            "error_rate": round(r.error_rate, 2),
            "fail_count": r.fail_count,
            "total_requests": r.total_requests
        })

    # ========== 最近执行记录 ==========
    recent_executions = []

    # UI 计划执行记录
    ui_exec_q = UiPlanExecution.filter(is_del=False).order_by("-start_time").limit(5)
    if project_id:
        ui_exec_q = ui_exec_q.filter(project_id=project_id)
    ui_exec_records = await ui_exec_q.prefetch_related("task").all()
    for r in ui_exec_records:
        task = await r.task
        recent_executions.append({
            "id": r.id,
            "name": task.name if task else "未知计划",
            "type": "Web",
            "record_type": "ui_task",
            "task_id": task.id if task else None,
            "run_by": r.username,
            "start_time": r.start_time.strftime("%Y-%m-%d %H:%M:%S") if r.start_time else None,
            "status": r.status,
            "pass_rate": r.pass_rate,
            "total_cases": r.case_count,
            "report_path": f"/record/report/task/{r.id}",
        })

    # API 套件执行记录
    api_exec_q = ApiSuiteRunRecord.filter().order_by("-start_time").limit(5)
    if project_id:
        api_exec_q = api_exec_q.filter(project_id=project_id)
    api_exec_records = await api_exec_q.prefetch_related("suite").all()
    for r in api_exec_records:
        suite = await r.suite
        recent_executions.append({
            "id": r.id,
            "name": suite.name if suite else "未知套件",
            "type": "接口",
            "record_type": "api_suite",
            "suite_id": r.suite_id,
            "env_id": r.env_id,
            "run_by": r.run_by,
            "start_time": r.start_time.strftime("%Y-%m-%d %H:%M:%S") if r.start_time else None,
            "status": r.status,
            "pass_rate": round((r.success_cases / r.total_cases * 100), 2) if r.total_cases else 0,
            "total_cases": r.total_cases,
            "report_path": f"/api-module/report/{r.id}?type=suite",
        })

    # 性能测试执行记录（按 id 倒序走主键，避免对大表按 started_at 排序导致 sort buffer 溢出）
    perf_exec_filter: Dict[str, Any] = {}
    if project_id:
        perf_exec_filter["project_id"] = project_id
    perf_exec_records = await (
        PerfRecord.filter(**perf_exec_filter)
        .order_by("-id")
        .limit(5)
        .only(
            "id", "scene_id", "run_by", "started_at", "status",
            "qps", "error_rate", "total_requests",
        )
        .prefetch_related("scene")
        .all()
    )
    for r in perf_exec_records:
        scene = await r.scene
        recent_executions.append({
            "id": r.id,
            "name": scene.name if scene else "未知场景",
            "type": "性能",
            "record_type": "perf",
            "run_by": r.run_by,
            "start_time": r.started_at.strftime("%Y-%m-%d %H:%M:%S") if r.started_at else None,
            "status": r.status,
            "qps": r.qps,
            "error_rate": round(r.error_rate, 2),
            "total_requests": r.total_requests,
            "report_path": f"/perf-report/{r.id}",
        })

    recent_executions.sort(key=lambda x: x["start_time"] or "", reverse=True)
    recent_executions = recent_executions[:5]

    ui_success = sum(i["success"] for i in ui_execution_trend)
    ui_fail = sum(i["fail"] for i in ui_execution_trend)
    api_success = sum(i["success"] for i in api_execution_trend)
    api_fail = sum(i["fail"] for i in api_execution_trend)
    perf_success = sum(i["success"] for i in perf_execution_trend)
    perf_fail = sum(i["fail"] for i in perf_execution_trend)

    case_proportion = build_case_proportion(ui_case_total, api_case_total, perf_scene_total)
    execution_proportion = build_execution_proportion(
        ui_success, ui_fail, api_success, api_fail, perf_success, perf_fail,
    )
    pending_cron_jobs = await _collect_pending_cron_jobs(project_id)
    ai_summary = await _collect_ai_summary(project_id)
    token_stats = await collect_token_stats(project_id, s_dt, e_dt)
    generate_trend = await collect_generate_trend(project_id, days=len(date_list))
    user_activity_top = await collect_user_activity_top(project_id, s_dt, e_dt)

    return {
        "date_range": date_list,
        "ui_execution_trend": ui_execution_trend,
        "api_execution_trend": api_execution_trend,
        "perf_execution_trend": perf_execution_trend,
        "stats": stats,
        "case_proportion": case_proportion,
        "execution_proportion": execution_proportion,
        "pending_cron_jobs": pending_cron_jobs,
        "ai_summary": ai_summary,
        "token_stats": token_stats,
        "generate_trend": generate_trend,
        "user_activity_top": user_activity_top,
        "top_failed_cases": top_failed_cases,
        "perf_top_failed_scenes": perf_top_failed_scenes,
        "recent_executions": recent_executions
    }
