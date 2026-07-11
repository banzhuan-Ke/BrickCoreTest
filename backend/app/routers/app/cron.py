"""App 自动化定时任务 API"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

import pytz
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.platform import config as settings
from app.core.platform.auth import get_current_username, is_authenticated, require_permissions
from app.core.platform.permissions import APP_PLAN_EDIT, APP_PLAN_EXECUTE, APP_PLAN_VIEW
from app.core.infra.scheduler_lock import with_scheduler_lock
from app.modules.ui.ui_project_guard import assert_user_project_member, assert_user_project_viewer
from app.models.app import AppCronJob, AppPlan, AppPlanExecution, AppSuite
from app.models.sys import Device, Environment
from app.schemas.app import AppCronJobCreate, AppCronJobUpdate, AppRunForm

job_stores = {
    "default": RedisJobStore(
        host=settings.APSCHEDULER_CONFIG["host"],
        port=settings.APSCHEDULER_CONFIG["port"],
        db=settings.APSCHEDULER_CONFIG["db"],
        password=settings.APSCHEDULER_CONFIG["password"],
    )
}
job_defaults = {"coalesce": False, "max_instances": 10}
local_timezone = pytz.timezone("Asia/Shanghai")
scheduler = AsyncIOScheduler(jobstores=job_stores, job_defaults=job_defaults, timezone=local_timezone)

router = APIRouter(
    prefix="/cron",
    tags=["App定时任务"],
    dependencies=[Depends(is_authenticated), Depends(require_permissions(APP_PLAN_VIEW))],
)


async def _cron_job_to_out(job: AppCronJob) -> dict:
    suite = await AppSuite.get_or_none(id=job.suite_id) if job.suite_id else None
    plan = await AppPlan.get_or_none(id=job.plan_id) if job.plan_id else None
    run_date_str = None
    if job.run_date:
        run_date_str = job.run_date.isoformat() if isinstance(job.run_date, datetime) else str(job.run_date)
    return {
        "id": job.id,
        "name": job.name,
        "project_id": job.project_id,
        "suite_id": job.suite_id,
        "suite_name": suite.name if suite else None,
        "plan_id": job.plan_id,
        "plan_name": plan.name if plan else None,
        "target_type": "plan" if job.plan_id else "suite",
        "env_id": job.env_id,
        "device_id": job.device_id,
        "app_udid": job.app_udid or "",
        "app_id": job.app_id or "",
        "run_type": job.run_type,
        "interval": job.interval,
        "run_date": run_date_str,
        "crontab": job.crontab or {},
        "state": job.state,
        "last_run_record_id": job.last_run_record_id,
        "last_run_time": job.last_run_time,
        "last_run_status": job.last_run_status,
        "create_by": job.create_by,
        "update_by": job.update_by,
        "create_time": job.create_time,
        "update_time": job.update_time,
    }


async def _create_real_cron_job(job: AppCronJob) -> None:
    try:
        if job.run_type == "Interval":
            trigger = IntervalTrigger(seconds=job.interval, timezone=local_timezone)
        elif job.run_type == "date":
            if not job.run_date:
                return
            trigger = DateTrigger(run_date=job.run_date, timezone=local_timezone)
        elif job.run_type == "crontab":
            crontab = job.crontab or {}
            trigger = CronTrigger(
                minute=crontab.get("minute", "*"),
                hour=crontab.get("hour", "*"),
                day=crontab.get("day", "*"),
                month=crontab.get("month", "*"),
                day_of_week=crontab.get("day_of_week", "*"),
                timezone=local_timezone,
            )
        else:
            return
        scheduler.add_job(
            func=execute_app_cron_job,
            trigger=trigger,
            id=job.id,
            args=[job.id],
            replace_existing=True,
            misfire_grace_time=3600,
        )
    except Exception as exc:
        print(f"[App调度器] 创建定时任务失败: {exc}")


async def _remove_real_cron_job(job_id: str) -> None:
    try:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
    except Exception as exc:
        print(f"[App调度器] 移除定时任务失败: {exc}")


async def _online_app_devices() -> list[Device]:
    rows = await Device.filter(status="在线", is_del=False).all()
    out: list[Device] = []
    for d in rows:
        types = d.runner_engine_types or ["web"]
        if "app" in types and (d.app_udid or "").strip():
            out.append(d)
    return out


def _build_run_form(job: AppCronJob, device_id: str) -> AppRunForm:
    return AppRunForm(
        env_id=job.env_id,
        device_id=device_id,
        username=job.create_by,
        app_udid=job.app_udid or "",
        app_id=job.app_id or "",
        trigger_source="cron",
    )


@with_scheduler_lock(lock_prefix="scheduler:app", expire_seconds=300)
async def execute_app_cron_job(job_id: str) -> None:
    record_id: int | None = None
    exec_status = "failed"
    try:
        job = await AppCronJob.get_or_none(id=job_id, is_del=False, state=True)
        if not job:
            return
        env = await Environment.get_or_none(id=job.env_id, is_del=False)
        if not env:
            return

        if job.plan_id:
            exec_status, record_id = await _execute_plan_cron(job)
        elif job.suite_id:
            exec_status, record_id = await _execute_suite_cron(job)
    except Exception as exc:
        print(f"[App定时任务] 执行异常: {exc}")
        exec_status = "failed"
        record_id = None

    job = await AppCronJob.get_or_none(id=job_id)
    if job:
        job.last_run_record_id = record_id
        job.last_run_time = datetime.now()
        job.last_run_status = exec_status
        await job.save()


async def _execute_suite_cron(job: AppCronJob) -> tuple[str, int | None]:
    from app.routers.app.exec import execute_app_suite_internal

    suite = await AppSuite.get_or_none(id=job.suite_id, is_del=False)
    if not suite:
        return "failed", None

    device_id = (job.device_id or "").strip()
    if not device_id:
        online = await _online_app_devices()
        if not online:
            return "failed", None
        device_id = online[0].id

    form = _build_run_form(job, device_id)
    result = await execute_app_suite_internal(job.suite_id, form, job.create_by, cronjob_id=job.id)
    return ("success" if result.get("dispatched") else "failed"), result.get("execution_id")


async def _execute_plan_cron(job: AppCronJob) -> tuple[str, int | None]:
    from app.modules.app.app_plan_runner import execute_app_plan

    plan = await AppPlan.get_or_none(id=job.plan_id, is_del=False)
    if not plan:
        return "failed", None

    device_id: str | None = (job.device_id or "").strip() or None
    devices: list[dict] | None = None
    if plan.parallel:
        online = await _online_app_devices()
        if len(online) > 1:
            devices = [{"device_id": d.id, "weight": 1} for d in online]
            device_id = None
        elif online:
            device_id = online[0].id
        else:
            return "failed", None
    elif not device_id:
        online = await _online_app_devices()
        if not online:
            return "failed", None
        device_id = online[0].id

    form = _build_run_form(job, device_id or "")
    if devices:
        form = form.model_copy(update={"devices": devices})

    result = await execute_app_plan(
        plan,
        env_id=job.env_id,
        username=job.create_by,
        run_form=form,
        device_id=device_id,
        devices=devices,
        trigger_source="cron",
        cronjob_id=job.id,
    )
    exec_id = result.get("execution_id")
    if exec_id:
        rec = await AppPlanExecution.get_or_none(id=exec_id)
        if rec:
            env_payload = rec.env if isinstance(rec.env, dict) else {}
            env_payload["trigger_source"] = "cron"
            rec.env = env_payload
            await rec.save()
    status = "success" if result.get("dispatched") else "failed"
    return status, exec_id


@router.post("", summary="创建 App 定时任务", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(APP_PLAN_EDIT))])
async def create_cron_job(
    item: AppCronJobCreate,
    user_info: dict = Depends(require_permissions(APP_PLAN_EDIT)),
    username: str = Depends(get_current_username),
):
    await assert_user_project_member(user_info, item.project_id)
    if not item.suite_id and not item.plan_id:
        raise HTTPException(status_code=422, detail="suite_id 和 plan_id 必须填写一个")
    if item.suite_id and item.plan_id:
        raise HTTPException(status_code=422, detail="suite_id 和 plan_id 只能填写一个")
    env = await Environment.get_or_none(id=item.env_id, is_del=False)
    if not env or env.project_id != item.project_id:
        raise HTTPException(status_code=422, detail="环境不存在或与项目不匹配")
    if item.suite_id:
        suite = await AppSuite.get_or_none(id=item.suite_id, is_del=False, project_id=item.project_id)
        if not suite:
            raise HTTPException(status_code=404, detail="套件不存在")
    if item.plan_id:
        plan = await AppPlan.get_or_none(id=item.plan_id, is_del=False, project_id=item.project_id)
        if not plan:
            raise HTTPException(status_code=404, detail="计划不存在")

    run_date = None
    if item.run_date and str(item.run_date).strip():
        try:
            run_date = datetime.fromisoformat(str(item.run_date).replace("Z", "+00:00"))
        except ValueError:
            run_date = None

    job_id = f"app_cron_{item.project_id}_{int(time.time() * 1000)}"
    job = await AppCronJob.create(
        id=job_id,
        name=item.name,
        project_id=item.project_id,
        suite_id=item.suite_id,
        plan_id=item.plan_id,
        run_type=item.run_type,
        interval=item.interval,
        run_date=run_date,
        crontab=item.crontab or {},
        env_id=item.env_id,
        device_id=item.device_id,
        app_udid=item.app_udid or "",
        app_id=item.app_id or "",
        state=item.state,
        create_by=username,
        update_by=username,
    )
    if item.state:
        await _create_real_cron_job(job)
    return await _cron_job_to_out(job)


@router.get("", summary="App 定时任务列表")
async def list_cron_jobs(
    project_id: int = Query(...),
    state: Optional[bool] = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=500),
    user_info: dict = Depends(require_permissions(APP_PLAN_VIEW)),
):
    await assert_user_project_viewer(user_info, project_id)
    qs = AppCronJob.filter(project_id=project_id, is_del=False)
    if state is not None:
        qs = qs.filter(state=state)
    total = await qs.count()
    jobs = await qs.order_by("-create_time").offset((page - 1) * size).limit(size)
    return {"data": [await _cron_job_to_out(j) for j in jobs], "total": total, "page": page, "size": size}


@router.get("/{job_id}", summary="App 定时任务详情")
async def get_cron_job(job_id: str, user_info: dict = Depends(require_permissions(APP_PLAN_VIEW))):
    job = await AppCronJob.get_or_none(id=job_id, is_del=False)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    await assert_user_project_viewer(user_info, job.project_id)
    return await _cron_job_to_out(job)


@router.put("/{job_id}", summary="更新 App 定时任务", dependencies=[Depends(require_permissions(APP_PLAN_EDIT))])
async def update_cron_job(
    job_id: str,
    item: AppCronJobUpdate,
    user_info: dict = Depends(require_permissions(APP_PLAN_EDIT)),
    username: str = Depends(get_current_username),
):
    job = await AppCronJob.get_or_none(id=job_id, is_del=False)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    await assert_user_project_member(user_info, job.project_id)
    if not item.suite_id and not item.plan_id:
        raise HTTPException(status_code=422, detail="suite_id 和 plan_id 必须填写一个")
    if item.suite_id and item.plan_id:
        raise HTTPException(status_code=422, detail="suite_id 和 plan_id 只能填写一个")

    run_date = job.run_date
    if item.run_date is not None:
        run_date = None
        if str(item.run_date).strip():
            try:
                run_date = datetime.fromisoformat(str(item.run_date).replace("Z", "+00:00"))
            except ValueError:
                run_date = None

    job.name = item.name
    job.suite_id = item.suite_id
    job.plan_id = item.plan_id
    job.env_id = item.env_id
    job.run_type = item.run_type
    job.interval = item.interval
    job.run_date = run_date
    job.crontab = item.crontab or {}
    job.device_id = item.device_id
    job.app_udid = item.app_udid or ""
    job.app_id = item.app_id or ""
    job.state = item.state
    job.update_by = username
    await job.save()

    if item.state:
        await _remove_real_cron_job(job.id)
        await _create_real_cron_job(job)
    else:
        await _remove_real_cron_job(job.id)
    return await _cron_job_to_out(job)


@router.delete("/{job_id}", summary="删除 App 定时任务", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(APP_PLAN_EDIT))])
async def delete_cron_job(job_id: str, user_info: dict = Depends(require_permissions(APP_PLAN_EDIT))):
    job = await AppCronJob.get_or_none(id=job_id, is_del=False)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    await assert_user_project_member(user_info, job.project_id)
    await _remove_real_cron_job(job_id)
    job.is_del = True
    await job.save()


@router.post("/{job_id}/toggle", summary="启用/禁用 App 定时任务",
             dependencies=[Depends(require_permissions(APP_PLAN_EDIT))])
async def toggle_cron_job(
    job_id: str,
    user_info: dict = Depends(require_permissions(APP_PLAN_EDIT)),
    username: str = Depends(get_current_username),
):
    job = await AppCronJob.get_or_none(id=job_id, is_del=False)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    await assert_user_project_member(user_info, job.project_id)
    job.state = not job.state
    job.update_by = username
    await job.save()
    if job.state:
        await _create_real_cron_job(job)
    else:
        await _remove_real_cron_job(job.id)
    return await _cron_job_to_out(job)


@router.get("/{job_id}/records", summary="获取 App 定时任务执行记录")
async def get_cron_job_records(
    job_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    user_info: dict = Depends(require_permissions(APP_PLAN_VIEW)),
):
    from app.models.app import AppSuiteExecution

    job = await AppCronJob.get_or_none(id=job_id, is_del=False)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    await assert_user_project_viewer(user_info, job.project_id)

    result: list[dict] = []
    total = 0
    if job.plan_id:
        qs = AppPlanExecution.filter(cronjob_id=job_id, is_del=False).order_by("-start_time")
        total = await qs.count()
        records = await qs.offset((page - 1) * size).limit(size).prefetch_related("plan")
        for record in records:
            plan = await record.plan
            result.append({
                "id": record.id,
                "record_type": "plan",
                "name": plan.name if plan else "未知计划",
                "status": record.status,
                "case_count": record.case_count,
                "success": record.success,
                "fail": record.fail,
                "error": record.error,
                "skip": record.skip,
                "no_run": record.no_run,
                "pass_rate": record.pass_rate,
                "start_time": record.start_time,
                "duration": record.duration,
                "username": record.username,
                "env": record.env,
            })
    else:
        qs = AppSuiteExecution.filter(cronjob_id=job_id, is_del=False).order_by("-start_time")
        total = await qs.count()
        records = await qs.offset((page - 1) * size).limit(size).prefetch_related("suite")
        for record in records:
            suite = await record.suite
            result.append({
                "id": record.id,
                "record_type": "suite",
                "name": suite.name if suite else "未知套件",
                "status": record.status,
                "case_count": record.case_count,
                "success": record.success,
                "fail": record.fail,
                "error": record.error,
                "skip": record.skip,
                "no_run": record.no_run,
                "pass_rate": record.pass_rate,
                "start_time": record.start_time,
                "duration": record.duration,
                "username": record.username,
                "env": record.env,
            })

    return {"data": result, "total": total, "page": page, "size": size}


@router.post("/{job_id}/run-now", summary="立即执行 App 定时任务",
             dependencies=[Depends(require_permissions(APP_PLAN_EXECUTE))])
async def run_cron_now(job_id: str, user_info: dict = Depends(require_permissions(APP_PLAN_EXECUTE))):
    job = await AppCronJob.get_or_none(id=job_id, is_del=False)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    await assert_user_project_member(user_info, job.project_id)
    await execute_app_cron_job(job_id)
    job = await AppCronJob.get_or_none(id=job_id)
    return {
        "msg": "已触发执行",
        "last_run_status": job.last_run_status if job else None,
        "last_run_record_id": job.last_run_record_id if job else None,
    }
