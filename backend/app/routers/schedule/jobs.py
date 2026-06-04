import datetime
import time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import APIRouter, HTTPException, Depends, status
from app.models.schedule import Cronjob
from app.schemas.schedule import CronjobForm, CronjobUpdateForm, CronjobSchemas
from app.models.sys import Project
from app.models.sys import Environment
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz
from app.models.ui import Task
from app.core import config as settings
from app.core.auth import is_authenticated, require_permissions
from app.core.permissions import UI_CRON_VIEW, UI_CRON_EDIT
from tortoise import transactions
from app.models.ui import UiPlanExecution, UiSuiteExecution, UiCaseExecution
from app.models.ui import Suite
from app.core.mq_producer import MQProducer
from app.core.ai_project_settings import resolve_locator_heal_for_execute
from app.core.scheduler_lock import with_scheduler_lock
from app.models.sys import Device

# 创建路由对象
router = APIRouter(prefix="/jobs", tags=["定时任务"], dependencies=[Depends(is_authenticated), Depends(require_permissions(UI_CRON_VIEW))])

# 配置APScheduler存储器
job_stores = {
    'default': RedisJobStore(host=settings.APSCHEDULER_CONFIG['host'], port=settings.APSCHEDULER_CONFIG['port'],
                             db=settings.APSCHEDULER_CONFIG['db'], password=settings.APSCHEDULER_CONFIG['password'])
}
# 任务默认参数
job_defaults = {'coalesce': False, 'max_instances': 10}
# 时区
local_timezone = pytz.timezone('Asia/Shanghai')
# 创建异步调度器
scheduler = AsyncIOScheduler(jobstores=job_stores, job_defaults=job_defaults, timezone=local_timezone)


@with_scheduler_lock(lock_prefix="scheduler:ui", expire_seconds=300)
async def run_task(task_id, env_id, cronjob_id=None):
    """提交任务到rabbitmq（补充关联资源的删除状态校验）"""
    # 校验任务是否存在且未被删除
    task = await Task.get_or_none(id=task_id, is_del=False).prefetch_related('suites', 'project')
    if not task:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="测试计划不存在或已被删除！")
    # 校验环境是否存在且未被删除
    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="测试环境不存在或已被删除！")
    # 获取第一个在线且未删除的设备
    device = await Device.filter(status="在线", is_del=False).first()
    if not device:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="在线设备不存在！")
    device_id = device.id

    ai_heal_enabled = await resolve_locator_heal_for_execute(task.project_id, None)

    # 组装执行的数据（保持原有逻辑）
    env_config = {
        "is_debug": True,
        "browser_type": 'chromium',
        "host": env.host,
        "global_variable": env.global_vars,
        "ai_heal_enabled": ai_heal_enabled,
    }
    # 创建任务执行记录（带 cronjob_id）
    task_record = await UiPlanExecution.create(
        task=task, 
        username=task.username, 
        env=env_config, 
        project=task.project,
        cronjob_id=cronjob_id
    )
    task_count = 0
    mq = MQProducer()
    # 获取测试计划的套件（过滤已删除的套件）
    for suite in await task.suites.filter(is_del=False).all():
        cases = []
        suite_ = await Suite.get_or_none(id=suite.id, is_del=False).prefetch_related('steps')
        if not suite_:
            continue  # 跳过已删除的套件
        # 创建套件运行记录
        suite_record = await UiSuiteExecution.create(suite=suite_, username=suite_.username, env=env_config,
                                                   plan_execution=task_record)
        # 遍历套件中的用例（过滤已删除的用例）
        for i in await suite_.steps.filter(is_del=False).all().order_by("sort"):
            case_ = await i.cases
            if not case_ or case_.is_del:
                continue  # 跳过已删除的用例
            # 创建用例执行记录
            case_record = await UiCaseExecution.create(case=case_, username=case_.username, suite_execution=suite_record,
                                                     env=env_config)
            cases.append({
                "record_id": case_record.id,
                'id': case_.id,
                'name': case_.name,
                "skip": i.skip,
                "steps": case_.steps
            })
        task_count += len(cases)
        suite_record.case_count = len(cases)
        await suite_record.save()
        # 发送套件任务到MQ
        run_suite = {
            'id': suite_.id,
            'suite_execution_id': suite_record.id,
            'plan_execution_id': task_record.id,
            'name': suite_.name,
            "username": suite_.username,
            'pre_actions': suite_.pre_actions or [],
            "cases": cases
        }
        mq.send_test_task(env_config=env_config, run_case=run_suite, device_id=device_id)
    mq.close()
    # 更新任务总用例数
    task_record.case_count = task_count
    await task_record.save()
    return {"msg": "定时任务已经提交到对应的设备，等待执行完毕！", "plan_execution_id": task_record.id}


# 创建定时任务
@router.post("", summary="创建定时任务", response_model=CronjobSchemas, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(UI_CRON_EDIT))])
async def create_cronjob(item: CronjobForm):
    # 校验关联资源是否存在且未被删除
    project = await Project.get_or_none(id=item.project, is_del=False)
    if not project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="所属项目不存在或已被删除")
    env = await Environment.get_or_none(id=item.env, is_del=False)
    if not env:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="执行环境不存在或已被删除")
    task = await Task.get_or_none(id=item.task, is_del=False)
    if not task:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="测试计划不存在或已被删除")

    # 校验任务类型
    if item.run_type not in ["Interval", "date", "crontab"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="任务类型参数不存在")
    # 转换时间格式并校验
    try:
        date_obj = datetime.datetime.strptime(item.date, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="时间格式错误（应为YYYY-MM-DD HH:MM:SS）")
    if date_obj < datetime.datetime.now():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="指定的执行时间不能小于当前时间")

    # 生成任务ID（时间戳）
    cronjob_id = str(int(time.time() * 1000))
    # 创建事务
    async with transactions.in_transaction('default') as cronjob_transaction:
        try:
            # 创建触发器
            if item.run_type == "date":
                trigger = DateTrigger(run_date=date_obj, timezone=local_timezone)
            elif item.run_type == "crontab":
                trigger = CronTrigger(**item.crontab.model_dump(), timezone=local_timezone)
            elif item.run_type == "Interval":
                trigger = IntervalTrigger(seconds=item.interval, timezone=local_timezone)
            else:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="定时任务类型参数错误")

            # 创建定时任务记录（显式设置is_del=False，使用本地时间）
            cronjob = await Cronjob.create(
                id=cronjob_id,
                name=item.name,
                username=item.username,
                project_id=item.project,
                env_id=item.env,
                task_id=item.task,
                run_type=item.run_type,
                interval=item.interval,
                date=date_obj.strftime("%Y-%m-%d %H:%M:%S"),
                crontab=item.crontab.model_dump(),
                state=item.state,
                is_del=False  # 新增：默认未删除
            )
            # 添加任务到调度器
            scheduler.add_job(
                func=run_task,
                trigger=trigger,
                id=cronjob_id,
                name=item.name,
                kwargs={'task_id': item.task, 'env_id': item.env, 'cronjob_id': cronjob_id}
            )
        except Exception as e:
            # 失败回滚
            scheduler.remove_job(job_id=cronjob_id)
            await cronjob_transaction.rollback()
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail=f"定时任务调度器创建失败：{str(e)}")
        else:
            # 处理任务状态（启用/暂停）
            try:
                if cronjob.state:
                    scheduler.resume_job(job_id=cronjob_id)
                else:
                    scheduler.pause_job(job_id=cronjob_id)
                await cronjob.save()
            except Exception as e:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="修改任务状态失败")
            await cronjob_transaction.commit()
            return cronjob


# 获取定时任务列表（只返回未删除的任务）
@router.get("", summary="定时任务列表", status_code=status.HTTP_200_OK)
async def get_cronjob(project_id: int | None = None, name: str | None = None,
                      run_type: str | None = None, state: bool | None = None):
    query = Cronjob.filter(is_del=False)
    # 校验项目是否存在且未被删除
    if project_id:
        project = await Project.get_or_none(id=project_id, is_del=False)
        if not project:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="测试项目不存在或已被删除")
        query = query.filter(project_id=project_id)
    if name:
        query = query.filter(name__icontains=name)
    if run_type:
        query = query.filter(run_type=run_type)
    if state is not None:
        query = query.filter(state=state)
    cronjobs = await query.order_by("-id")

    result = []
    for cronjob in cronjobs:
        # 关联资源只查询未删除的
        env = await Environment.get_or_none(id=cronjob.env_id, is_del=False)
        task = await Task.get_or_none(id=cronjob.task_id, is_del=False)
        result.append({
            "id": cronjob.id,
            "name": cronjob.name,
            "username": cronjob.username,
            "create_time": cronjob.create_time,
            "update_time": cronjob.update_time,
            "run_type": cronjob.run_type,
            "interval": cronjob.interval,
            "date": cronjob.date,
            "crontab": cronjob.crontab,
            "state": cronjob.state,
            "is_del": cronjob.is_del,  # 新增：返回删除状态
            "task": task.id if task else None,
            "env": env.id if env else None,
            "env_name": env.name if env else "已删除环境",
            "task_name": task.name if task else "已删除计划"
        })
    return result


# 删除定时任务（逻辑删除）
@router.delete("/{cronjob_id}", summary="删除定时任务", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(UI_CRON_EDIT))])
async def delete_cronjob(cronjob_id: str):
    # 只删除未删除的任务
    cronjob = await Cronjob.get_or_none(id=cronjob_id, is_del=False)
    if not cronjob:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="定时任务不存在或已被删除")

    try:
        # 尝试移除调度器中的任务（可能已不存在）
        try:
            scheduler.remove_job(job_id=cronjob_id)
        except:
            pass  # 调度器中不存在该任务，忽略
        # 逻辑删除：设置is_del=True
        cronjob.is_del = True
        await cronjob.save()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"删除任务失败：{str(e)}")


# 切换定时任务状态（只操作未删除的任务）
@router.post("/{cronjob_id}/switch", summary="修改定时任务状态", response_model=CronjobSchemas,
             dependencies=[Depends(require_permissions(UI_CRON_EDIT))],
             status_code=status.HTTP_200_OK)
async def switch_cronjob(cronjob_id: str):
    cronjob = await Cronjob.get_or_none(id=cronjob_id, is_del=False)
    if not cronjob:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="定时任务不存在或已被删除")

    async with transactions.in_transaction('default') as tx:
        try:
            # 切换状态（启用↔暂停）
            cronjob.state = not cronjob.state
            if cronjob.state:
                scheduler.resume_job(job_id=cronjob_id)
            else:
                scheduler.pause_job(job_id=cronjob_id)
            await cronjob.save()
        except Exception as e:
            await tx.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"修改状态失败：{str(e)}")
        await tx.commit()
        return cronjob


# 获取定时任务的执行记录
@router.get("/{cronjob_id}/records", summary="获取定时任务执行记录", status_code=status.HTTP_200_OK)
async def get_cronjob_records(cronjob_id: str, page: int = 1, size: int = 10):
    """获取指定定时任务的执行记录列表"""
    # 校验定时任务是否存在且未被删除
    cronjob = await Cronjob.get_or_none(id=cronjob_id, is_del=False)
    if not cronjob:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="定时任务不存在或已被删除")
    
    # 查询该定时任务的执行记录（通过 cronjob_id 精确关联）
    task_records = await UiPlanExecution.filter(
        cronjob_id=cronjob_id,
        is_del=False
    ).order_by("-start_time").offset((page - 1) * size).limit(size)
    
    # 获取总数
    total = await UiPlanExecution.filter(
        cronjob_id=cronjob_id,
        is_del=False
    ).count()
    
    # 构建返回数据
    result = []
    for record in task_records:
        result.append({
            "id": record.id,
            "task_name": (await record.task).name if await record.task else "未知任务",
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
    
    return {
        "data": result,
        "total": total,
        "page": page,
        "size": size
    }


# 修改定时任务配置（只修改未删除的任务）
@router.put("/{cronjob_id}", summary="修改定时任务配置", response_model=CronjobSchemas,
            dependencies=[Depends(require_permissions(UI_CRON_EDIT))],
            status_code=status.HTTP_200_OK)
async def update_cronjob(cronjob_id: str, item: CronjobUpdateForm):
    # 校验任务是否存在且未被删除
    cronjob = await Cronjob.get_or_none(id=cronjob_id, is_del=False)
    if not cronjob:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="定时任务不存在或已被删除")

    # 校验时间格式
    if item.date:
        try:
            date_obj = datetime.datetime.strptime(item.date, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="时间格式错误")
        if date_obj < datetime.datetime.now():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="修改的时间不能小于当前时间")

    # 校验关联资源（若修改了项目/环境/任务）
    if item.project:
        project = await Project.get_or_none(id=item.project, is_del=False)
        if not project:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="所属项目不存在或已被删除")
    if item.env:
        env = await Environment.get_or_none(id=item.env, is_del=False)
        if not env:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="执行环境不存在或已被删除")
    if item.task:
        task = await Task.get_or_none(id=item.task, is_del=False)
        if not task:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="测试计划不存在或已被删除")

    async with transactions.in_transaction('default') as tx:
        try:
            # 构建新触发器
            if item.run_type:
                run_type = item.run_type
            else:
                run_type = cronjob.run_type

            if run_type == "date":
                date = item.date or cronjob.date
                date_obj = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
                trigger = DateTrigger(run_date=date_obj, timezone=local_timezone)
            elif run_type == "crontab":
                crontab = item.crontab.model_dump() if item.crontab else cronjob.crontab
                trigger = CronTrigger(**crontab, timezone=local_timezone)
            elif run_type == "Interval":
                interval = item.interval or cronjob.interval
                trigger = IntervalTrigger(seconds=interval, timezone=local_timezone)
            else:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="任务类型错误")

            # 更新调度器任务（如果不存在则重新添加）
            try:
                scheduler.modify_job(job_id=cronjob_id, trigger=trigger)
            except:
                # 调度器中不存在该任务，重新添加
                scheduler.add_job(
                    func=run_task,
                    trigger=trigger,
                    id=cronjob_id,
                    name=cronjob.name,
                    kwargs={'task_id': cronjob.task_id, 'env_id': cronjob.env_id, 'cronjob_id': cronjob_id}
                )
                # 根据状态启用或暂停
                if cronjob.state:
                    scheduler.resume_job(job_id=cronjob_id)
                else:
                    scheduler.pause_job(job_id=cronjob_id)
            
            # 更新数据库记录（使用本地时间，不转换UTC）
            if item.date:
                item.date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            
            # 排除外键字段，手动处理，避免 update_from_dict 直接赋 int 给 ForeignKey
            update_data = item.model_dump(exclude_unset=True)
            for fk_field in ['project', 'env', 'task']:
                update_data.pop(fk_field, None)
            await cronjob.update_from_dict(update_data)
            
            # 手动设置外键关联
            if item.project is not None:
                cronjob.project_id = item.project
            if item.env is not None:
                cronjob.env_id = item.env
            if item.task is not None:
                cronjob.task_id = item.task
            
            await cronjob.save()
        except Exception as e:
            await tx.rollback()
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"修改任务失败：{str(e)}")
        await tx.commit()
        return cronjob
