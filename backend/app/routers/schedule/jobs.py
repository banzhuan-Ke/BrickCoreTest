import datetime
import logging
import time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import APIRouter, HTTPException, Depends, status
from app.models.schedule import Cronjob
from app.schemas.schedule import CronjobForm, CronjobUpdateForm, CronjobSchemas
from app.models.sys import Project
from app.models.sys import Environment
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz
from app.models.ui import Task
from app.core.platform import config as settings
from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import UI_CRON_VIEW, UI_CRON_EDIT
from tortoise import transactions
from app.models.ui import UiPlanExecution
from app.core.infra.scheduler_lock import with_scheduler_lock
from app.modules.ui.ui_cron_run_config import normalize_run_config

# 创建路由对象
router = APIRouter(prefix="/jobs", tags=["定时任务"], dependencies=[Depends(is_authenticated), Depends(require_permissions(UI_CRON_VIEW))])

# 配置APScheduler存储器
job_stores = {
    'default': RedisJobStore(host=settings.APSCHEDULER_CONFIG['host'], port=settings.APSCHEDULER_CONFIG['port'],
                             db=settings.APSCHEDULER_CONFIG['db'], password=settings.APSCHEDULER_CONFIG['password'])
}
# 任务默认参数（misfire 与接口/App/压测定时对齐：错过触发点后仍允许约 1 小时内补跑）
_MISFIRE_GRACE_SECONDS = 3600
job_defaults = {"coalesce": False, "max_instances": 10, "misfire_grace_time": _MISFIRE_GRACE_SECONDS}

# 时区
local_timezone = pytz.timezone('Asia/Shanghai')
# 创建异步调度器
scheduler = AsyncIOScheduler(jobstores=job_stores, job_defaults=job_defaults, timezone=local_timezone)
logger = logging.getLogger(__name__)


def _to_naive_local(value) -> datetime.datetime:
    """把表单字符串 / ORM datetime 统一成上海本地 naive。"""
    if isinstance(value, datetime.datetime):
        if value.tzinfo is not None:
            return value.astimezone(local_timezone).replace(tzinfo=None)
        return value
    if isinstance(value, str):
        return datetime.datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S")
    raise ValueError(f"无法解析执行时间: {value!r}")


def _build_trigger(run_type: str, interval: int, date_value, crontab: dict | None):
    if run_type == "date":
        date_obj = _to_naive_local(date_value)
        return DateTrigger(run_date=local_timezone.localize(date_obj))
    if run_type == "crontab":
        c = crontab or {}
        return CronTrigger(
            minute=str(c.get("minute", "*")),
            hour=str(c.get("hour", "*")),
            day=str(c.get("day", "*")),
            month=str(c.get("month", "*")),
            day_of_week=str(c.get("day_of_week", "*")),
            timezone=local_timezone,
        )
    if run_type == "Interval":
        return IntervalTrigger(seconds=interval or 60, timezone=local_timezone)
    raise ValueError(f"不支持的任务类型: {run_type}")


def _upsert_scheduler_job(
    *,
    cronjob_id: str,
    name: str,
    run_type: str,
    interval: int,
    date_value,
    crontab: dict | None,
    task_id: int,
    env_id: int,
    state: bool,
) -> None:
    """按 DB 配置强制重挂到 APScheduler（replace），避免 Redis 里旧 job / 过短 misfire 残留。"""
    trigger = _build_trigger(run_type, interval, date_value, crontab)
    if run_type == "date":
        run_at = _to_naive_local(date_value)
        grace_deadline = datetime.datetime.now() - datetime.timedelta(seconds=_MISFIRE_GRACE_SECONDS)
        if run_at < grace_deadline:
            try:
                if scheduler.get_job(cronjob_id):
                    scheduler.remove_job(cronjob_id)
            except Exception:
                pass
            logger.warning(
                "Web 定时任务已超过 misfire 窗口，跳过挂载 cronjob_id=%s run_at=%s",
                cronjob_id,
                run_at,
            )
            return

    try:
        if scheduler.get_job(cronjob_id):
            scheduler.remove_job(cronjob_id)
    except Exception:
        pass

    scheduler.add_job(
        func=run_task,
        trigger=trigger,
        id=str(cronjob_id),
        name=name,
        kwargs={"task_id": task_id, "env_id": env_id, "cronjob_id": str(cronjob_id)},
        replace_existing=True,
        misfire_grace_time=_MISFIRE_GRACE_SECONDS,
    )
    if not state:
        try:
            scheduler.pause_job(job_id=str(cronjob_id))
        except Exception:
            pass


async def reconcile_ui_cron_jobs() -> dict:
    """进程启动后按 DB 校准启用中的 Web 定时任务（修复 Redis 丢失 / 旧 misfire）。"""
    synced = 0
    skipped = 0
    rows = await Cronjob.filter(is_del=False, state=True).all()
    for job in rows:
        try:
            _upsert_scheduler_job(
                cronjob_id=str(job.id),
                name=job.name,
                run_type=job.run_type,
                interval=job.interval or 60,
                date_value=job.date,
                crontab=job.crontab if isinstance(job.crontab, dict) else None,
                task_id=job.task_id,
                env_id=job.env_id,
                state=True,
            )
            if scheduler.get_job(str(job.id)):
                synced += 1
            else:
                skipped += 1
        except Exception as exc:
            skipped += 1
            logger.warning("校准 Web 定时任务失败 id=%s: %s", job.id, exc)
    logger.info("Web 定时任务校准完成 synced=%s skipped=%s", synced, skipped)
    return {"synced": synced, "skipped": skipped}


@with_scheduler_lock(lock_prefix="scheduler:ui", expire_seconds=300)
async def run_task(task_id, env_id, cronjob_id=None):
    """提交任务到 RabbitMQ（支持计划级并行；可读 Cronjob.run_config）。"""
    from app.core.ops.notification import NotificationService
    from app.modules.ui.ui_cron_run_config import normalize_run_config, resolve_cron_dispatch
    from app.modules.ui.ui_plan_runner import execute_ui_plan

    logger.info("Web 定时任务触发 cronjob_id=%s task_id=%s env_id=%s", cronjob_id, task_id, env_id)
    task = await Task.get_or_none(id=task_id, is_del=False).prefetch_related("suites", "project")
    if not task:
        logger.error("定时任务触发失败：计划不存在 task_id=%s", task_id)
        return {"ok": False, "detail": "测试计划不存在或已被删除"}

    run_config = None
    cron_name = getattr(task, "name", "") or str(task_id)
    if cronjob_id:
        cron = await Cronjob.get_or_none(id=str(cronjob_id), is_del=False)
        if cron:
            run_config = cron.run_config
            cron_name = cron.name or cron_name

    device_id, devices, concurrency, browser_type, headless, warning = await resolve_cron_dispatch(
        parallel=bool(task.parallel),
        run_config=run_config,
    )
    if warning:
        logger.warning("定时任务 %s：%s", cronjob_id or task_id, warning)

    if not device_id and not devices:
        detail = "无在线 Web 执行器，定时任务未派发"
        logger.error("%s cronjob_id=%s task_id=%s", detail, cronjob_id, task_id)
        plan_record = await UiPlanExecution.create(
            task=task,
            username=task.username or "cron",
            env={
                "trigger_source": "cron",
                "cron_skip_reason": detail,
                "run_config": normalize_run_config(run_config),
            },
            device_id=None,
            project=task.project,
            is_del=False,
            status="执行完成",
            execution_log=[{"level": "error", "message": detail}],
            error=1,
            cronjob_id=str(cronjob_id) if cronjob_id else None,
        )
        try:
            await NotificationService.send_alert(
                task.project_id,
                title=f"定时任务未执行：{cron_name}",
                content={
                    "execution_type": "UI计划(定时)",
                    "name": cron_name,
                    "status": "failed",
                    "total": 0,
                    "success": 0,
                    "failed": 1,
                    "pass_rate": 0,
                    "duration": 0,
                    "run_by": task.username or "cron",
                    "message": detail,
                },
                related_id=plan_record.id,
                related_type="ui_plan_execution",
                alert_scope="ui",
            )
        except Exception as exc:
            logger.warning("定时无执行器告警发送失败: %s", exc)
        return {"ok": False, "detail": detail, "plan_execution_id": plan_record.id}

    return await execute_ui_plan(
        task,
        env_id=env_id,
        browser_type=browser_type,
        headless=headless,
        username=task.username,
        device_id=device_id,
        devices=devices,
        concurrency=concurrency,
        ai_heal_enabled=None,
        trigger_source="cron",
        cronjob_id=cronjob_id,
    )


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
    if env.project_id != item.project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="执行环境与所选项目不匹配")
    if task.project_id != item.project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="测试计划与所选项目不匹配")

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
            # 创建定时任务记录（显式设置is_del=False，使用本地时间）
            run_cfg = None
            if item.run_config is not None:
                run_cfg = normalize_run_config(item.run_config.model_dump())
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
                run_config=run_cfg or None,
                state=item.state,
                is_del=False  # 新增：默认未删除
            )
            _upsert_scheduler_job(
                cronjob_id=cronjob_id,
                name=item.name,
                run_type=item.run_type,
                interval=item.interval,
                date_value=date_obj,
                crontab=item.crontab.model_dump() if item.crontab else None,
                task_id=item.task,
                env_id=item.env,
                state=bool(item.state),
            )
        except Exception as e:
            # 失败回滚
            try:
                scheduler.remove_job(job_id=cronjob_id)
            except Exception:
                pass
            await cronjob_transaction.rollback()
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail=f"定时任务调度器创建失败：{str(e)}")
        else:
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
            "run_config": cronjob.run_config,
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
                # 启用：强制按 DB 重挂（date 任务 misfire 后 Redis 里可能已无 job，resume 会失败）
                _upsert_scheduler_job(
                    cronjob_id=str(cronjob.id),
                    name=cronjob.name,
                    run_type=cronjob.run_type,
                    interval=cronjob.interval or 60,
                    date_value=cronjob.date,
                    crontab=cronjob.crontab if isinstance(cronjob.crontab, dict) else None,
                    task_id=cronjob.task_id,
                    env_id=cronjob.env_id,
                    state=True,
                )
                if cronjob.run_type == "date":
                    run_at = _to_naive_local(cronjob.date)
                    if run_at < datetime.datetime.now() - datetime.timedelta(seconds=_MISFIRE_GRACE_SECONDS):
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="固定执行时间已过期，请先编辑为未来时间再启用",
                        )
                    if not scheduler.get_job(str(cronjob.id)):
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="固定执行时间已过期，请先编辑为未来时间再启用",
                        )
            else:
                try:
                    scheduler.pause_job(job_id=cronjob_id)
                except Exception:
                    try:
                        scheduler.remove_job(job_id=cronjob_id)
                    except Exception:
                        pass
            await cronjob.save()
        except HTTPException:
            await tx.rollback()
            raise
        except Exception as e:
            await tx.rollback()
            # 调度器缺 job / Redis 抖动：勿把开关打成 500，引导用户改时间或重试
            detail = str(e)
            if "No job by the id" in detail or "JobLookupError" in type(e).__name__:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="调度任务已失效，请编辑为未来时间后重新保存再启用",
                ) from e
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"修改状态失败：{detail}",
            ) from e
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

    target_project_id = item.project if item.project is not None else cronjob.project_id
    target_env_id = item.env if item.env is not None else cronjob.env_id
    target_task_id = item.task if item.task is not None else cronjob.task_id
    if target_env_id and target_project_id:
        env_row = await Environment.get_or_none(id=target_env_id, is_del=False)
        if env_row and env_row.project_id != target_project_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="执行环境与所选项目不匹配")
    if target_task_id and target_project_id:
        task_row = await Task.get_or_none(id=target_task_id, is_del=False)
        if task_row and task_row.project_id != target_project_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="测试计划与所选项目不匹配")

    async with transactions.in_transaction('default') as tx:
        try:
            run_type = item.run_type or cronjob.run_type
            date_value = item.date if item.date else cronjob.date
            if item.crontab is not None:
                crontab_value = item.crontab.model_dump()
            elif isinstance(cronjob.crontab, dict):
                crontab_value = cronjob.crontab
            else:
                crontab_value = None
            interval_value = item.interval if item.interval is not None else (cronjob.interval or 60)
            next_state = bool(item.state) if item.state is not None else bool(cronjob.state)

            # 更新数据库记录（使用本地时间，不转换UTC）
            if item.date:
                item.date = _to_naive_local(item.date).strftime("%Y-%m-%d %H:%M:%S")

            # 排除外键字段与嵌套模型，手动处理
            update_data = item.model_dump(exclude_unset=True)
            for fk_field in ['project', 'env', 'task']:
                update_data.pop(fk_field, None)
            if "run_config" in update_data:
                raw_cfg = update_data.pop("run_config")
                cronjob.run_config = (
                    normalize_run_config(raw_cfg) if raw_cfg is not None else None
                )
            await cronjob.update_from_dict(update_data)

            # 手动设置外键关联
            if item.project is not None:
                cronjob.project_id = item.project
            if item.env is not None:
                cronjob.env_id = item.env
            if item.task is not None:
                cronjob.task_id = item.task

            await cronjob.save()

            # 按最新 DB 强制重挂调度（对齐接口定时：remove + add）
            _upsert_scheduler_job(
                cronjob_id=str(cronjob_id),
                name=cronjob.name,
                run_type=run_type,
                interval=interval_value,
                date_value=date_value,
                crontab=crontab_value,
                task_id=cronjob.task_id,
                env_id=cronjob.env_id,
                state=next_state,
            )
        except Exception as e:
            await tx.rollback()
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"修改任务失败：{str(e)}")
        await tx.commit()
        return cronjob
