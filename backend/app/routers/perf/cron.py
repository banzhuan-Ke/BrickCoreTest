"""性能测试定时任务 API"""
import time
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query, status
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.redis import RedisJobStore
import pytz

from app.models.perf import PerfScene, PerfRecord, PerfCronJob
from app.models.sys import Environment
from app.core.platform.auth import is_authenticated, require_permissions, get_current_username
from app.core.platform.permissions import PERF_SCENE_EXECUTE
from app.core.platform import config as settings
from app.core.infra.scheduler_lock import with_scheduler_lock

# 配置APScheduler存储器
job_stores = {
    'default': RedisJobStore(
        host=settings.APSCHEDULER_CONFIG['host'],
        port=settings.APSCHEDULER_CONFIG['port'],
        db=settings.APSCHEDULER_CONFIG['db'],
        password=settings.APSCHEDULER_CONFIG['password']
    )
}
job_defaults = {'coalesce': False, 'max_instances': 10}
local_timezone = pytz.timezone('Asia/Shanghai')
scheduler = AsyncIOScheduler(jobstores=job_stores, job_defaults=job_defaults, timezone=local_timezone)

router = APIRouter(prefix="/cron", tags=["性能测试定时任务"],
                   dependencies=[Depends(is_authenticated), Depends(require_permissions(PERF_SCENE_EXECUTE))])


# ============ 定时任务管理 ============

@router.post("", summary="创建定时任务")
async def create_cron_job(
    name: str,
    project_id: int,
    scene_id: int,
    env_id: int,
    run_type: str,
    interval: int = 3600,
    run_date: Optional[str] = None,
    crontab: Optional[dict] = None,
    state: bool = False,
    use_workers: bool = False,
    username: str = Depends(get_current_username),
):
    """创建性能测试定时任务"""
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")

    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")

    job_id = f"perf_cron_{project_id}_{int(datetime.now().timestamp())}"

    # 处理 run_date
    parsed_run_date = None
    if run_date and run_date.strip():
        try:
            parsed_run_date = datetime.fromisoformat(run_date.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            parsed_run_date = None

    cron_job = await PerfCronJob.create(
        id=job_id,
        name=name,
        project_id=project_id,
        scene_id=scene_id,
        env_id=env_id,
        run_type=run_type,
        interval=interval,
        run_date=parsed_run_date,
        crontab=crontab or {},
        state=state,
        use_workers=use_workers,
        create_by=username
    )

    if state:
        await _create_real_cron_job(cron_job)

    return await _cron_job_to_out(cron_job)


@router.get("", summary="定时任务列表")
async def get_cron_jobs(
    project_id: int = Query(..., description="项目ID"),
    state: Optional[bool] = Query(None, description="状态筛选"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=5000)
):
    """获取性能测试定时任务列表"""
    query = PerfCronJob.filter(project_id=project_id, is_del=False)

    if state is not None:
        query = query.filter(state=state)

    total = await query.count()
    jobs = await query.order_by("-create_time").offset((page - 1) * size).limit(size).all()

    result = []
    for job in jobs:
        result.append(await _cron_job_to_out(job))

    return {"data": result, "total": total, "page": page, "size": size}


@router.get("/{job_id}", summary="定时任务详情")
async def get_cron_job_detail(job_id: str):
    """获取定时任务详情"""
    job = await PerfCronJob.get_or_none(id=job_id, is_del=False)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return await _cron_job_to_out(job)


@router.put("/{job_id}", summary="更新定时任务")
async def update_cron_job(
    job_id: str,
    name: str,
    scene_id: int,
    env_id: int,
    run_type: str,
    interval: int = 3600,
    run_date: Optional[str] = None,
    crontab: Optional[dict] = None,
    state: bool = False,
    use_workers: bool = False,
    username: str = Depends(get_current_username),
):
    """更新性能测试定时任务"""
    job = await PerfCronJob.get_or_none(id=job_id, is_del=False)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")

    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")

    parsed_run_date = None
    if run_date and run_date.strip():
        try:
            parsed_run_date = datetime.fromisoformat(run_date.replace(' ', 'T').replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            parsed_run_date = None

    job.name = name
    job.scene_id = scene_id
    job.env_id = env_id
    job.run_type = run_type
    job.interval = interval
    job.run_date = parsed_run_date
    job.crontab = crontab or {}
    job.state = state
    job.use_workers = use_workers
    await job.save()

    if state:
        await _update_real_cron_job(job)
    else:
        await _remove_real_cron_job(job.id)

    return await _cron_job_to_out(job)


@router.delete("/{job_id}", summary="删除定时任务", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cron_job(job_id: str):
    """删除性能测试定时任务"""
    job = await PerfCronJob.get_or_none(id=job_id, is_del=False)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")

    await _remove_real_cron_job(job_id)
    job.is_del = True
    await job.save()


@router.post("/{job_id}/toggle", summary="启用/禁用定时任务")
async def toggle_cron_job(job_id: str):
    """切换定时任务状态"""
    job = await PerfCronJob.get_or_none(id=job_id, is_del=False)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")

    job.state = not job.state
    await job.save()

    if job.state:
        await _create_real_cron_job(job)
    else:
        await _remove_real_cron_job(job.id)

    return await _cron_job_to_out(job)


# ============ 辅助函数 ============

async def _cron_job_to_out(job: PerfCronJob) -> dict:
    """转换为输出格式"""
    scene = await PerfScene.get_or_none(id=job.scene_id)
    env = await Environment.get_or_none(id=job.env_id)

    run_date_str = None
    if job.run_date:
        if isinstance(job.run_date, datetime):
            run_date_str = job.run_date.isoformat()
        else:
            run_date_str = str(job.run_date) if job.run_date else None

    return {
        "id": job.id,
        "name": job.name,
        "project_id": job.project_id,
        "scene_id": job.scene_id,
        "scene_name": scene.name if scene else "未知场景",
        "env_id": job.env_id,
        "env_name": env.name if env else "未知环境",
        "run_type": job.run_type,
        "interval": job.interval,
        "run_date": run_date_str,
        "crontab": job.crontab,
        "state": job.state,
        "use_workers": bool(job.use_workers),
        "last_run_record_id": job.last_run_record_id,
        "last_run_time": job.last_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.last_run_time else None,
        "last_run_status": job.last_run_status,
        "create_by": job.create_by,
        "create_time": job.create_time.strftime("%Y-%m-%d %H:%M:%S") if job.create_time else "",
        "update_time": job.update_time.strftime("%Y-%m-%d %H:%M:%S") if job.update_time else ""
    }


async def _create_real_cron_job(job: PerfCronJob):
    """创建实际的定时任务"""
    try:
        if job.run_type == 'Interval':
            trigger = IntervalTrigger(seconds=job.interval)
        elif job.run_type == 'date':
            if not job.run_date:
                return
            trigger = DateTrigger(run_date=job.run_date)
        elif job.run_type == 'crontab':
            c = job.crontab or {}
            trigger = CronTrigger(
                minute=c.get('minute', '*'),
                hour=c.get('hour', '*'),
                day=c.get('day', '*'),
                month=c.get('month', '*'),
                day_of_week=c.get('day_of_week', '*')
            )
        else:
            return

        scheduler.add_job(
            func=execute_perf_cron_job,
            trigger=trigger,
            id=job.id,
            args=[job.id],
            replace_existing=True,
            misfire_grace_time=3600,
            max_instances=1,
            coalesce=True,
        )
    except Exception as e:
        print(f"[PerfScheduler] 创建定时任务失败: {e}")


async def _update_real_cron_job(job: PerfCronJob):
    """更新实际的定时任务"""
    await _remove_real_cron_job(job.id)
    await _create_real_cron_job(job)


async def _remove_real_cron_job(job_id: str):
    """移除实际的定时任务"""
    try:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
    except Exception as e:
        print(f"[PerfScheduler] 移除定时任务失败: {e}")


# ============ 定时任务执行 ============

@with_scheduler_lock(lock_prefix="scheduler:perf", expire_seconds=300)
async def execute_perf_cron_job(job_id: str):
    """定时任务执行入口"""
    print(f"[PerfCron] 开始执行: {job_id}")

    status = "failed"
    record = None
    try:
        job = await PerfCronJob.get_or_none(id=job_id, is_del=False, state=True)
        if not job:
            print(f"[PerfCron] 任务不存在或已禁用: {job_id}")
            return

        scene = await PerfScene.get_or_none(id=job.scene_id, is_del=False)
        if not scene:
            print(f"[PerfCron] 场景不存在: {job.scene_id}")
            return

        if await PerfRecord.filter(cron_job_id=job_id, status="running").exists():
            print(f"[PerfCron] 上一轮仍在执行，跳过: {job_id}")
            return

        env = await Environment.get_or_none(id=job.env_id, is_del=False)
        if not env:
            print(f"[PerfCron] 环境不存在: {job.env_id}")
            return

        # 复用 exec.py 中的 start_perf 逻辑
        config = scene.config or {}
        config["env_id"] = job.env_id
        config.setdefault("request_detail_level", "brief")

        record = await PerfRecord.create(
            scene_id=job.scene_id,
            project_id=job.project_id,
            status="pending",
            trigger_type="cron",
            config_snapshot=config,
            scene_items_snapshot=scene.scene_items or [],
            run_by=job.create_by,
            cron_job_id=job_id
        )

        # 导入并执行（可选分布式 Worker，无在线 Worker 时自动本机执行）
        from .exec import run_perf_scene
        await run_perf_scene(record.id, use_workers=bool(job.use_workers))

        # 重新获取记录状态
        record = await PerfRecord.get_or_none(id=record.id)
        status = record.status if record else "failed"
        print(f"[PerfCron] 执行完成: {status}")

    except Exception as e:
        print(f"[PerfCron] 执行异常: {e}")
        import traceback
        traceback.print_exc()
        status = "failed"
        record = None

    # 更新定时任务状态
    try:
        job = await PerfCronJob.get_or_none(id=job_id)
        if job:
            job.last_run_record_id = record.id if record else None
            job.last_run_time = datetime.now()
            job.last_run_status = status
            await job.save()
    except Exception as e:
        print(f"[PerfCron] 更新任务状态失败: {e}")


# ============ 执行记录查询 ============

@router.get("/{job_id}/records", summary="获取定时任务执行记录")
async def get_perf_cron_records(
    job_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100)
):
    """获取指定定时压测任务的执行记录列表"""
    job = await PerfCronJob.get_or_none(id=job_id, is_del=False)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")

    query = PerfRecord.filter(cron_job_id=job_id)
    total = await query.count()
    records = await (
        query.order_by("-id")
        .offset((page - 1) * size)
        .limit(size)
        .only(
            "id", "scene_id", "status", "trigger_type",
            "total_requests", "success_count", "fail_count",
            "qps", "avg_response_time", "error_rate", "duration",
            "started_at", "ended_at",
        )
        .prefetch_related("scene")
        .all()
    )

    result = []
    for r in records:
        scene = r.scene
        result.append({
            "id": r.id,
            "scene_id": r.scene_id,
            "scene_name": scene.name if scene else "未知场景",
            "status": r.status,
            "trigger_type": r.trigger_type,
            "total_requests": r.total_requests,
            "success_count": r.success_count,
            "fail_count": r.fail_count,
            "qps": r.qps,
            "avg_response_time": r.avg_response_time,
            "error_rate": r.error_rate,
            "duration": r.duration,
            "started_at": r.started_at.strftime("%Y-%m-%d %H:%M:%S") if r.started_at else None,
            "ended_at": r.ended_at.strftime("%Y-%m-%d %H:%M:%S") if r.ended_at else None,
            "run_by": r.run_by
        })

    return {"data": result, "total": total, "page": page, "size": size}
