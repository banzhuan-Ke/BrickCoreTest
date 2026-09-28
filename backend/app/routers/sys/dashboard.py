"""首页统计看板 API"""
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Query, status
from tortoise import connections

from app.core.platform.auth import is_authenticated
from app.core.ops.dashboard_extra import (
    build_case_proportion,
    build_execution_proportion,
    compute_next_run,
    sort_pending_jobs,
    within_hours,
)
from app.modules.ai.ai_dashboard_stats import (
    collect_generate_trend,
    collect_token_stats,
    collect_user_activity_top,
    enrich_run_by_display,
)
from app.models.ui import Case as UiCase, Suite as UiSuite, UiPlanExecution
from app.models.http import ApiTestCase, ApiTestSuite, ApiSuiteRunRecord, ApiCronJob
from app.models.perf import PerfScene, PerfRecord, PerfCronJob
from app.models.app import AppCase, AppSuite, AppCaseExecution, AppPlanExecution, AppSuiteExecution, AppCronJob
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


def _row_date_key(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    text = str(value)
    return text[:10] if len(text) >= 10 else None


def fold_daily_status_counts(
    rows: List[Dict[str, Any]],
    date_list: List[str],
    success_statuses: set,
    fail_statuses: set,
) -> List[Dict[str, Any]]:
    """把 SQL 的 (日期, 状态, 条数) 折成首页趋势，不把执行明细拉进进程。"""
    trend_map = {d: {"success": 0, "fail": 0} for d in date_list}
    for row in rows:
        day = _row_date_key(row.get("d"))
        if not day or day not in trend_map:
            continue
        status_name = row.get("status")
        count = int(row.get("cnt") or 0)
        if status_name in success_statuses:
            trend_map[day]["success"] += count
        elif status_name in fail_statuses:
            trend_map[day]["fail"] += count
    return [{"date": day, **trend_map[day]} for day in date_list]


async def _sql_rows(sql: str, params: List[Any]) -> List[Dict[str, Any]]:
    conn = connections.get("default")
    return await conn.execute_query_dict(sql, params)


async def _daily_status_rows(
    table: str,
    time_col: str,
    s_dt: datetime,
    e_dt: datetime,
    *,
    join_sql: str = "",
    extra_where: str = "",
    extra_params: Optional[List[Any]] = None,
) -> List[Dict[str, Any]]:
    sql = (
        f"SELECT DATE(t.{time_col}) AS d, t.status AS status, COUNT(*) AS cnt "
        f"FROM {table} t {join_sql} "
        f"WHERE t.{time_col} >= %s AND t.{time_col} <= %s {extra_where} "
        f"GROUP BY DATE(t.{time_col}), t.status"
    )
    params: List[Any] = [s_dt, e_dt, *(extra_params or [])]
    return await _sql_rows(sql, params)


async def _failed_case_counts(
    table: str,
    case_table: str,
    s_dt: datetime,
    e_dt: datetime,
    statuses: List[str],
    *,
    project_id: Optional[int],
    extra_where: str = "",
) -> List[Dict[str, Any]]:
    placeholders = ", ".join(["%s"] * len(statuses))
    join = f"LEFT JOIN {case_table} c ON c.id = t.case_id"
    where = f"AND t.status IN ({placeholders}) {extra_where}"
    params: List[Any] = [s_dt, e_dt, *statuses]
    if project_id:
        where += " AND c.project_id = %s"
        params.append(project_id)
    sql = (
        "SELECT t.case_id AS case_id, MAX(c.name) AS name, COUNT(*) AS cnt "
        f"FROM {table} t {join} "
        f"WHERE t.start_time >= %s AND t.start_time <= %s {where} "
        "GROUP BY t.case_id ORDER BY cnt DESC LIMIT 20"
    )
    return await _sql_rows(sql, params)


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

    app_q = AppCronJob.filter(is_del=False, state=True)
    if project_id:
        app_q = app_q.filter(project_id=project_id)
    for job in await app_q.all():
        nxt = compute_next_run(job.run_type, job.interval, job.run_date, job.crontab, now=now)
        if not within_hours(nxt, 48):
            continue
        target = ""
        if job.plan_id:
            plan = await job.plan
            target = plan.name if plan else "App 计划"
        elif job.suite_id:
            suite = await job.suite
            target = suite.name if suite else "App 套件"
        pending.append({
            "id": job.id,
            "name": job.name,
            "type": "App",
            "target": target or "App 任务",
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

    # ========== 执行趋势（数据库按日聚合，禁止把执行明细/大 JSON 拉进进程） ==========
    ui_join = "INNER JOIN `case` c ON c.id = t.case_id" if project_id else ""
    ui_extra = "AND c.project_id = %s" if project_id else ""
    ui_rows = await _daily_status_rows(
        "ui_case_execution", "start_time", s_dt, e_dt,
        join_sql=ui_join, extra_where=ui_extra, extra_params=[project_id] if project_id else None,
    )
    ui_execution_trend = fold_daily_status_counts(
        ui_rows, date_list, {"success"}, {"fail", "error", "failed"},
    )

    api_extra = "AND t.project_id = %s" if project_id else ""
    api_rows = await _daily_status_rows(
        "api_run_record", "start_time", s_dt, e_dt,
        extra_where=api_extra, extra_params=[project_id] if project_id else None,
    )
    api_execution_trend = fold_daily_status_counts(
        api_rows, date_list, {"success"}, {"failed"},
    )

    app_join = "INNER JOIN app_case c ON c.id = t.case_id" if project_id else ""
    app_extra = "AND t.is_del = 0"
    app_params: List[Any] = []
    if project_id:
        app_extra += " AND c.project_id = %s"
        app_params.append(project_id)
    app_rows = await _daily_status_rows(
        "app_case_execution", "start_time", s_dt, e_dt,
        join_sql=app_join, extra_where=app_extra, extra_params=app_params or None,
    )
    app_execution_trend = fold_daily_status_counts(
        app_rows, date_list, {"success"}, {"fail", "error", "failed"},
    )

    perf_extra = "AND t.project_id = %s" if project_id else ""
    perf_rows = await _daily_status_rows(
        "perf_record", "started_at", s_dt, e_dt,
        extra_where=perf_extra, extra_params=[project_id] if project_id else None,
    )
    perf_execution_trend = fold_daily_status_counts(
        perf_rows, date_list, {"success"}, {"failed", "stopped"},
    )

    # ========== 用例/套件总数统计 ==========
    ui_case_filter = {"is_del": False}
    ui_suite_filter = {"is_del": False}
    app_case_filter = {"is_del": False}
    app_suite_filter = {"is_del": False}
    api_case_filter = {"is_del": False}
    api_suite_filter = {"is_del": False}
    perf_scene_filter = {"is_del": False}
    if project_id:
        ui_case_filter["project_id"] = project_id
        ui_suite_filter["project_id"] = project_id
        app_case_filter["project_id"] = project_id
        app_suite_filter["project_id"] = project_id
        api_case_filter["project_id"] = project_id
        api_suite_filter["project_id"] = project_id
        perf_scene_filter["project_id"] = project_id

    ui_case_total = await UiCase.filter(**ui_case_filter).count()
    ui_suite_total = await UiSuite.filter(**ui_suite_filter).count()
    app_case_total = await AppCase.filter(**app_case_filter).count()
    app_suite_total = await AppSuite.filter(**app_suite_filter).count()
    api_case_total = await ApiTestCase.filter(**api_case_filter).count()
    api_suite_total = await ApiTestSuite.filter(**api_suite_filter).count()
    perf_scene_total = await PerfScene.filter(**perf_scene_filter).count()

    # 性能测试平均指标（只统计有结果的记录；只取数值列，不读时序 JSON）
    perf_avg_sql = (
        "SELECT COUNT(*) AS cnt, COALESCE(AVG(qps), 0) AS avg_qps, "
        "COALESCE(AVG(error_rate), 0) AS avg_err "
        "FROM perf_record WHERE started_at >= %s AND started_at <= %s "
        "AND status IN ('success', 'failed', 'stopped')"
    )
    perf_avg_params: List[Any] = [s_dt, e_dt]
    if project_id:
        perf_avg_sql += " AND project_id = %s"
        perf_avg_params.append(project_id)
    perf_avg_rows = await _sql_rows(perf_avg_sql, perf_avg_params)
    perf_avg = perf_avg_rows[0] if perf_avg_rows else {}
    perf_exec_total = int(perf_avg.get("cnt") or 0)
    perf_avg_qps = round(float(perf_avg.get("avg_qps") or 0), 2) if perf_exec_total else 0
    perf_avg_error_rate = round(float(perf_avg.get("avg_err") or 0), 2) if perf_exec_total else 0

    stats = {
        "ui_case_total": ui_case_total,
        "ui_suite_total": ui_suite_total,
        "app_case_total": app_case_total,
        "app_suite_total": app_suite_total,
        "api_case_total": api_case_total,
        "api_suite_total": api_suite_total,
        "perf_scene_total": perf_scene_total,
        "perf_exec_total": perf_exec_total,
        "perf_avg_qps": perf_avg_qps,
        "perf_avg_error_rate": perf_avg_error_rate,
        "total_case": ui_case_total + app_case_total + api_case_total,
        "total_suite": ui_suite_total + app_suite_total + api_suite_total,
    }

    # ========== Top 5 失败用例（按用例 GROUP BY，不读响应体） ==========
    ui_fail_rows = await _failed_case_counts(
        "ui_case_execution", "`case`", s_dt, e_dt, ["fail", "error", "failed"], project_id=project_id,
    )
    api_fail_where = "AND t.project_id = %s" if project_id else ""
    api_fail_sql_statuses = ["failed"]
    api_fail_params: List[Any] = [s_dt, e_dt, *api_fail_sql_statuses]
    if project_id:
        api_fail_params.append(project_id)
    api_fail_rows = await _sql_rows(
        "SELECT t.case_id AS case_id, MAX(c.name) AS name, COUNT(*) AS cnt "
        "FROM api_run_record t LEFT JOIN api_test_case c ON c.id = t.case_id "
        "WHERE t.start_time >= %s AND t.start_time <= %s AND t.status IN (%s) "
        f"{api_fail_where} GROUP BY t.case_id ORDER BY cnt DESC LIMIT 20",
        api_fail_params,
    )
    app_fail_rows = await _failed_case_counts(
        "app_case_execution", "app_case", s_dt, e_dt, ["fail", "error", "failed"],
        project_id=project_id, extra_where="AND t.is_del = 0",
    )

    def _named_fails(rows: List[Dict[str, Any]], type_label: str) -> List[Dict[str, Any]]:
        return [
            {"case_name": row.get("name") or "未知", "type": type_label, "count": int(row.get("cnt") or 0)}
            for row in rows
        ]

    all_fails = (
        _named_fails(ui_fail_rows, "Web")
        + _named_fails(app_fail_rows, "App")
        + _named_fails(api_fail_rows, "接口")
    )
    all_fails.sort(key=lambda x: x["count"], reverse=True)
    top_failed_cases = all_fails[:5]

    # ========== Top 5 性能测试失败场景（只取数值列，避免大 JSON 进排序）==========
    perf_top_sql = (
        "SELECT scene_id, error_rate, fail_count, total_requests "
        "FROM perf_record WHERE started_at >= %s AND started_at <= %s "
        "AND status IN ('success', 'failed') AND error_rate > 0"
    )
    perf_top_params: List[Any] = [s_dt, e_dt]
    if project_id:
        perf_top_sql += " AND project_id = %s"
        perf_top_params.append(project_id)
    perf_top_sql += " ORDER BY error_rate DESC LIMIT 5"
    perf_top_rows = await _sql_rows(perf_top_sql, perf_top_params)
    scene_ids = [row["scene_id"] for row in perf_top_rows if row.get("scene_id")]
    scene_names = {}
    if scene_ids:
        for scene in await PerfScene.filter(id__in=scene_ids).only("id", "name"):
            scene_names[scene.id] = scene.name
    perf_top_failed_scenes = [
        {
            "scene_name": scene_names.get(row.get("scene_id")) or "未知场景",
            "error_rate": round(float(row.get("error_rate") or 0), 2),
            "fail_count": row.get("fail_count") or 0,
            "total_requests": row.get("total_requests") or 0,
        }
        for row in perf_top_rows
    ]

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

    # App 计划执行记录
    app_exec_q = AppPlanExecution.filter(is_del=False).order_by("-start_time").limit(5)
    if project_id:
        app_exec_q = app_exec_q.filter(project_id=project_id)
    app_exec_records = await app_exec_q.prefetch_related("plan").all()
    for r in app_exec_records:
        plan = await r.plan
        recent_executions.append({
            "id": r.id,
            "name": plan.name if plan else "未知 App 计划",
            "type": "App",
            "record_type": "app_plan",
            "plan_id": plan.id if plan else None,
            "run_by": r.username,
            "start_time": r.start_time.strftime("%Y-%m-%d %H:%M:%S") if r.start_time else None,
            "status": r.status,
            "pass_rate": r.pass_rate,
            "total_cases": r.case_count,
            "report_path": f"/app-record/report/plan/{r.id}",
        })

    # App 套件执行（非计划内）
    app_suite_exec_q = (
        AppSuiteExecution.filter(is_del=False, plan_execution_id=None)
        .order_by("-start_time")
        .limit(5)
    )
    if project_id:
        app_suite_exec_q = app_suite_exec_q.filter(suite__project_id=project_id)
    app_suite_exec_records = await app_suite_exec_q.prefetch_related("suite").all()
    for r in app_suite_exec_records:
        suite = await r.suite
        recent_executions.append({
            "id": r.id,
            "name": suite.name if suite else "未知 App 套件",
            "type": "App",
            "record_type": "app_suite",
            "suite_id": r.suite_id,
            "run_by": r.username,
            "start_time": r.start_time.strftime("%Y-%m-%d %H:%M:%S") if r.start_time else None,
            "status": r.status,
            "pass_rate": r.pass_rate,
            "total_cases": r.case_count,
            "report_path": f"/app-record/report/suite/{r.id}",
        })

    # App 单用例执行
    app_case_exec_q = (
        AppCaseExecution.filter(is_del=False, suite_execution_id=None)
        .order_by("-start_time")
        .limit(5)
    )
    if project_id:
        app_case_exec_q = app_case_exec_q.filter(case__project_id=project_id)
    app_case_exec_records = await app_case_exec_q.prefetch_related("case").all()
    for r in app_case_exec_records:
        case = await r.case
        recent_executions.append({
            "id": r.id,
            "name": case.name if case else "未知 App 用例",
            "type": "App",
            "record_type": "app_case",
            "case_id": r.case_id,
            "run_by": r.username,
            "start_time": r.start_time.strftime("%Y-%m-%d %H:%M:%S") if r.start_time else None,
            "status": r.status,
            "pass_rate": 100.0 if r.status == "success" else 0.0,
            "total_cases": 1,
            "report_path": f"/app-record?record_type=case&case_id={r.case_id}",
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
    recent_executions = await enrich_run_by_display(recent_executions)

    ui_success = sum(i["success"] for i in ui_execution_trend)
    ui_fail = sum(i["fail"] for i in ui_execution_trend)
    app_success = sum(i["success"] for i in app_execution_trend)
    app_fail = sum(i["fail"] for i in app_execution_trend)
    api_success = sum(i["success"] for i in api_execution_trend)
    api_fail = sum(i["fail"] for i in api_execution_trend)
    perf_success = sum(i["success"] for i in perf_execution_trend)
    perf_fail = sum(i["fail"] for i in perf_execution_trend)

    case_proportion = build_case_proportion(ui_case_total, api_case_total, perf_scene_total, app_case_total)
    execution_proportion = build_execution_proportion(
        ui_success, ui_fail, api_success, api_fail, perf_success, perf_fail, app_success, app_fail,
    )
    pending_cron_jobs = await _collect_pending_cron_jobs(project_id)
    ai_summary = await _collect_ai_summary(project_id)
    token_stats = await collect_token_stats(project_id, s_dt, e_dt)
    generate_trend = await collect_generate_trend(project_id, days=len(date_list))
    user_activity_top = await collect_user_activity_top(project_id, s_dt, e_dt)

    return {
        "date_range": date_list,
        "ui_execution_trend": ui_execution_trend,
        "app_execution_trend": app_execution_trend,
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
