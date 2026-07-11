"""接口自动化定时任务 API"""
import json
import time
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query, status, BackgroundTasks
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.redis import RedisJobStore
import pytz

from app.models.http import ApiTestSuite, ApiTestPlan, ApiSuiteRunRecord, ApiCronJob
from app.schemas.http import ApiCronJobCreate, ApiCronJobUpdate, ApiCronJobOut, ApiCronJobListResponse
from app.core.platform.auth import is_authenticated, require_permissions, get_current_username
from app.core.platform.permissions import API_CRON_VIEW, API_CRON_EDIT
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

router = APIRouter(tags=["接口定时任务"], dependencies=[Depends(is_authenticated), Depends(require_permissions(API_CRON_VIEW))])


# ============ 定时任务管理 ============

@router.post("/cron", summary="创建定时任务",
             dependencies=[Depends(require_permissions(API_CRON_EDIT))])
async def create_cron_job(item: ApiCronJobCreate, username: str = Depends(get_current_username)):
    """创建接口自动化定时任务（支持关联套件或测试计划）"""
    # 校验：suite_id 和 plan_id 必须填一个
    if not item.suite_id and not item.plan_id:
        raise HTTPException(status_code=422, detail="suite_id 和 plan_id 必须填写一个")
    if item.suite_id and item.plan_id:
        raise HTTPException(status_code=422, detail="suite_id 和 plan_id 只能填写一个")

    if item.suite_id:
        suite = await ApiTestSuite.get_or_none(id=item.suite_id, is_del=False)
        if not suite:
            raise HTTPException(status_code=404, detail="套件不存在")
    if item.plan_id:
        plan = await ApiTestPlan.get_or_none(id=item.plan_id, is_del=False)
        if not plan:
            raise HTTPException(status_code=404, detail="测试计划不存在")

    # 生成唯一ID
    job_id = f"api_cron_{item.project_id}_{int(datetime.now().timestamp())}"
    
    # 验证环境
    from app.models.sys import Environment
    env = await Environment.get_or_none(id=item.env_id, is_del=False)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")
    
    # 处理 run_date：空字符串转为 None，字符串转为 datetime
    run_date = None
    if item.run_date and item.run_date.strip():
        try:
            run_date = datetime.fromisoformat(item.run_date.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            run_date = None
    
    cron_job = await ApiCronJob.create(
        id=job_id,
        name=item.name,
        project_id=item.project_id,
        suite_id=item.suite_id,
        plan_id=item.plan_id,
        env_id=item.env_id,
        run_type=item.run_type,
        interval=item.interval,
        run_date=run_date,
        crontab=item.crontab,
        state=item.state,
        create_by=username,
        update_by=username,
    )
    
    # 如果启用状态，创建实际定时任务
    if item.state:
        await _create_real_cron_job(cron_job)
    
    return await _cron_job_to_out(cron_job)


@router.get("/cron", summary="定时任务列表", response_model=ApiCronJobListResponse)
async def get_cron_jobs(
    project_id: int = Query(..., description="项目ID"),
    state: Optional[bool] = Query(None, description="状态筛选"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=5000)
):
    """获取接口定时任务列表"""
    query = ApiCronJob.filter(project_id=project_id, is_del=False)

    if state is not None:
        query = query.filter(state=state)

    total = await query.count()
    jobs = await query.order_by("-create_time").offset((page - 1) * size).limit(size).all()

    result = []
    for job in jobs:
        result.append(await _cron_job_to_out(job))

    return ApiCronJobListResponse(data=result, total=total, page=page, size=size)


@router.get("/cron/{job_id}", summary="定时任务详情")
async def get_cron_job_detail(job_id: str):
    """获取定时任务详情"""
    job = await ApiCronJob.get_or_none(id=job_id, is_del=False)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")

    return await _cron_job_to_out(job)


@router.put("/cron/{job_id}", summary="更新定时任务",
            dependencies=[Depends(require_permissions(API_CRON_EDIT))])
async def update_cron_job(job_id: str, item: ApiCronJobUpdate, username: str = Depends(get_current_username)):
    """更新接口定时任务"""
    job = await ApiCronJob.get_or_none(id=job_id, is_del=False)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")

    # 校验目标
    if not item.suite_id and not item.plan_id:
        raise HTTPException(status_code=422, detail="suite_id 和 plan_id 必须填写一个")
    if item.suite_id and item.plan_id:
        raise HTTPException(status_code=422, detail="suite_id 和 plan_id 只能填写一个")

    # 验证环境
    from app.models.sys import Environment
    env = await Environment.get_or_none(id=item.env_id, is_del=False)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")
    
    # 处理 run_date：空字符串转为 None，字符串转为 datetime
    run_date = None
    if item.run_date and item.run_date.strip():
        try:
            run_date = datetime.fromisoformat(item.run_date.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            run_date = None
    
    # 更新字段
    job.name = item.name
    job.suite_id = item.suite_id
    job.plan_id = item.plan_id
    job.env_id = item.env_id
    job.run_type = item.run_type
    job.interval = item.interval
    job.run_date = run_date
    job.crontab = item.crontab
    job.state = item.state
    job.update_by = username
    await job.save()
    
    # 同步到任务调度器
    if item.state:
        await _update_real_cron_job(job)
    else:
        await _remove_real_cron_job(job.id)
    
    return await _cron_job_to_out(job)


@router.delete("/cron/{job_id}", summary="删除定时任务", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(API_CRON_EDIT))])
async def delete_cron_job(job_id: str):
    """删除接口定时任务"""
    job = await ApiCronJob.get_or_none(id=job_id, is_del=False)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    
    # 从调度器移除
    await _remove_real_cron_job(job_id)
    
    job.is_del = True
    await job.save()


@router.post("/cron/{job_id}/toggle", summary="启用/禁用定时任务",
             dependencies=[Depends(require_permissions(API_CRON_EDIT))])
async def toggle_cron_job(job_id: str, username: str = Depends(get_current_username)):
    """切换定时任务状态"""
    job = await ApiCronJob.get_or_none(id=job_id, is_del=False)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    
    job.state = not job.state
    job.update_by = username
    await job.save()
    
    # 同步到调度器
    if job.state:
        await _create_real_cron_job(job)
    else:
        await _remove_real_cron_job(job.id)
    
    return await _cron_job_to_out(job)


# ============ 辅助函数 ============

async def _cron_job_to_out(job: ApiCronJob) -> dict:
    """转换为输出格式"""
    suite = await ApiTestSuite.get_or_none(id=job.suite_id) if job.suite_id else None
    plan = await ApiTestPlan.get_or_none(id=job.plan_id) if job.plan_id else None

    # 处理 run_date 类型（可能是 datetime 或字符串）
    run_date_str = None
    if job.run_date:
        if isinstance(job.run_date, datetime):
            run_date_str = job.run_date.isoformat()
        else:
            run_date_str = str(job.run_date) if job.run_date else None

    target_type = "plan" if job.plan_id else "suite"

    return {
        "id": job.id,
        "name": job.name,
        "project_id": job.project_id,
        "suite_id": job.suite_id,
        "suite_name": suite.name if suite else None,
        "plan_id": job.plan_id,
        "plan_name": plan.name if plan else None,
        "target_type": target_type,
        "env_id": job.env_id,
        "run_type": job.run_type,
        "interval": job.interval,
        "run_date": run_date_str,
        "crontab": job.crontab,
        "state": job.state,
        "last_run_record_id": job.last_run_record_id,
        "last_run_time": job.last_run_time,
        "last_run_status": job.last_run_status,
        "create_by": job.create_by,
        "update_by": job.update_by,
        "create_time": job.create_time,
        "update_time": job.update_time
    }


async def _create_real_cron_job(job: ApiCronJob):
    """创建实际的定时任务"""
    try:
        print(f"[调度器] 创建任务: {job.id}, 类型: {job.run_type}")
        
        # 根据 run_type 创建不同的触发器
        if job.run_type == 'Interval':
            trigger = IntervalTrigger(seconds=job.interval)
            print(f"[调度器] Interval触发器: {job.interval}秒")
        elif job.run_type == 'date':
            if not job.run_date:
                print(f"[调度器] 固定时间未设置")
                return
            trigger = DateTrigger(run_date=job.run_date)
            print(f"[调度器] Date触发器: {job.run_date}")
        elif job.run_type == 'crontab':
            crontab = job.crontab or {}
            trigger = CronTrigger(
                minute=crontab.get('minute', '*'),
                hour=crontab.get('hour', '*'),
                day=crontab.get('day', '*'),
                month=crontab.get('month', '*'),
                day_of_week=crontab.get('day_of_week', '*')
            )
            print(f"[调度器] Cron触发器: {crontab}")
        else:
            print(f"[调度器] 未知类型: {job.run_type}")
            return
        
        # 添加任务到调度器
        scheduler.add_job(
            func=execute_cron_job,
            trigger=trigger,
            id=job.id,
            args=[job.id],
            replace_existing=True,
            misfire_grace_time=3600  # 允许1小时的容错时间
        )
        print(f"[调度器] 任务已添加: {job.id}")
        
        # 打印调度器中的所有任务
        print(f"[调度器] 当前任务列表: {[j.id for j in scheduler.get_jobs()]}")
    except Exception as e:
        print(f"[调度器] 创建定时任务失败: {e}")
        import traceback
        traceback.print_exc()


async def _update_real_cron_job(job: ApiCronJob):
    """更新实际的定时任务"""
    await _remove_real_cron_job(job.id)
    await _create_real_cron_job(job)


async def _remove_real_cron_job(job_id: str):
    """移除实际的定时任务"""
    try:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
    except Exception as e:
        print(f"移除定时任务失败: {e}")


# ============ 定时任务执行 ============

@with_scheduler_lock(lock_prefix="scheduler:api", expire_seconds=300)
async def execute_cron_job(job_id: str):
    """定时任务执行入口：支持套件模式和计划模式"""
    print(f"[定时任务] 开始执行: {job_id}")

    record_id = None
    exec_status = "failed"

    try:
        from app.models.sys import Environment

        job = await ApiCronJob.get_or_none(id=job_id, is_del=False, state=True)
        if not job:
            print(f"[定时任务] 任务不存在或已禁用: {job_id}")
            return

        print(f"[定时任务] 任务信息: {job.name}, plan_id={job.plan_id}, suite_id={job.suite_id}")

        env = await Environment.get_or_none(id=job.env_id, is_del=False)
        if not env:
            print(f"[定时任务] 环境不存在: {job.env_id}")
            return

        # -------- 计划执行模式 --------
        if job.plan_id:
            exec_status, record_id = await _execute_plan_cron(job, env)

        # -------- 套件执行模式 --------
        else:
            exec_status, record_id = await _execute_suite_cron(job, env)

    except Exception as e:
        print(f"[定时任务] 执行异常: {e}")
        import traceback
        traceback.print_exc()
        exec_status = "failed"
        record_id = None

    # 更新定时任务的执行记录
    try:
        job = await ApiCronJob.get_or_none(id=job_id)
        if job:
            job.last_run_record_id = record_id
            job.last_run_time = datetime.now()
            job.last_run_status = exec_status
            await job.save()
            print(f"[定时任务] 更新任务状态完成: {exec_status}")
    except Exception as e:
        print(f"[定时任务] 更新任务状态失败: {e}")


async def _execute_suite_cron(job: ApiCronJob, env) -> tuple:
    """套件模式执行，返回 (status, record_id)"""
    from app.models.http import ApiSuiteCase
    from app.modules.http.api_suite_runner import execute_api_suite_cases

    suite = await ApiTestSuite.get_or_none(id=job.suite_id, is_del=False)
    if not suite:
        print(f"[定时任务] 套件不存在: {job.suite_id}")
        return "failed", None

    suite_cases = await ApiSuiteCase.filter(suite_id=job.suite_id).order_by("sort").all()
    if not suite_cases:
        print(f"[定时任务] 套件下没有用例: {job.suite_id}")
        return "failed", None

    print(f"[定时任务] 套件模式，找到 {len(suite_cases)} 个用例")

    record = await ApiSuiteRunRecord.create(
        suite_id=job.suite_id,
        project_id=job.project_id,
        status="running",
        trigger_type="cron",
        total_cases=len(suite_cases),
        env_id=job.env_id,
        env_name=env.name,
        run_by=job.create_by
    )

    start_time = time.time()
    case_ids = [sc.case_id for sc in suite_cases]

    try:
        run_result = await execute_api_suite_cases(
            suite=suite,
            env=env,
            case_ids=case_ids,
            suite_record=record,
            username=job.create_by,
        )
    except Exception as e:
        print(f"[定时任务] 套件执行异常: {e}")
        import traceback
        traceback.print_exc()
        record.status = "failed"
        record.end_time = datetime.now()
        record.duration = round((time.time() - start_time) * 1000, 2)
        await record.save()
        return "failed", record.id

    success_count = run_result["success_count"]
    failed_count = run_result["failed_count"]
    hooks_result = run_result["hooks_result"]
    exec_status = "success" if failed_count == 0 and hooks_result.get("success", True) else "failed"
    record.status = exec_status
    record.success_cases = success_count
    record.failed_cases = failed_count
    record.end_time = datetime.now()
    record.duration = round((time.time() - start_time) * 1000, 2)
    record.hooks_result = hooks_result
    await record.save()
    print(f"[定时任务] 套件执行完成: {exec_status}, 成功: {success_count}, 失败: {failed_count}, 耗时: {record.duration:.0f}ms")
    return exec_status, record.id


async def _execute_plan_cron(job: ApiCronJob, env) -> tuple:
    """计划模式执行，返回 (status, record_id)"""
    from app.routers.http.plan import run_plan
    from app.schemas.http import ApiPlanRunRequest

    plan = await ApiTestPlan.get_or_none(id=job.plan_id, is_del=False)
    if not plan:
        print(f"[定时任务] 计划不存在: {job.plan_id}")
        return "failed", None

    print(f"[定时任务] 计划模式: {plan.name}")

    try:
        req = ApiPlanRunRequest(
            env_id=job.env_id,
            stop_on_failure=False,
            auto_validate_schema=False,
        )
        result = await run_plan(plan.id, req, username=job.create_by)
        # 将执行记录的 trigger_type 改为 cron
        if result.record_id:
            from app.models.http import ApiPlanRunRecord
            rec = await ApiPlanRunRecord.get_or_none(id=result.record_id)
            if rec:
                rec.trigger_type = "cron"
                await rec.save()
        print(f"[定时任务] 计划执行完成: {result.status}, 成功: {result.success}, 失败: {result.failed}")
        return result.status, result.record_id
    except Exception as e:
        print(f"[定时任务] 计划执行异常: {e}")
        import traceback
        traceback.print_exc()
        return "failed", None
