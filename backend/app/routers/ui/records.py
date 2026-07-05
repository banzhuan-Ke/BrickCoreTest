import json
import os
import time
import uuid
import asyncio
from typing import List
from fastapi import APIRouter, HTTPException, Depends, status, Response
from pydantic import BaseModel, Field
from app.models.ui import (
    Task, Suite, Case,
    UiPlanExecution, UiSuiteExecution, UiCaseExecution
)
from app.core.auth import is_authenticated, require_permissions
from app.core.permissions import UI_RECORD_EDIT, UI_RECORD_VIEW
from app.core.ui_project_guard import assert_user_project_member, assert_user_project_viewer
from app.core.platform_settings_service import (
    delete_ui_case_execution,
    get_ui_case_record_delete_mode,
    restore_ui_case_execution,
)
from app.core.report_export import generate_html_report, ImageExportOptions
from app.core.ui_case_status import apply_ui_case_status_filter
from app.core.minio_client import minio_client, is_minio_storage
from app.schemas.ui import SuiteResultSchemas, TaskResultSchemas

# 异步导出任务缓存（内存，24h TTL）
export_tasks: dict = {}
EXPORT_TASK_TTL_SECONDS = 24 * 3600


def _cleanup_export_tasks() -> None:
    now = time.time()
    expired = [
        task_id
        for task_id, meta in export_tasks.items()
        if now - meta.get("created_at", now) > EXPORT_TASK_TTL_SECONDS
    ]
    for task_id in expired:
        export_tasks.pop(task_id, None)
        file_path = os.path.join(EXPORT_DIR, f"{task_id}.html")
        if os.path.isfile(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
# 导出文件存放目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
EXPORT_DIR = os.path.join(BASE_DIR, "static", "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)


def _presign_media_urls(result_data) -> dict:
    """将 result_data 中的 MinIO 静态 URL 替换为预签名 URL"""
    if not result_data or not is_minio_storage():
        return result_data
    
    # 兼容 result_data 为 JSON 字符串的情况
    if isinstance(result_data, str):
        try:
            result_data = json.loads(result_data)
        except:
            return result_data

    def presign(url):
        if not url or not isinstance(url, str):
            return url
        # 只处理 MinIO 外部地址的 URL
        bucket = minio_client.bucket_name
        marker = f"/{bucket}/"
        if marker not in url:
            return url
        filename = url.split(marker, 1)[-1]
        signed = minio_client.get_presigned_url(filename, expires=7200)
        return signed or url

    data = dict(result_data)
    if "img" in data:
        data["img"] = presign(data["img"])
    if "video_url" in data:
        data["video_url"] = presign(data["video_url"])
    for step in data.get("steps", []):
        if isinstance(step, dict) and "screenshot" in step:
            step["screenshot"] = presign(step["screenshot"])
    return data

router = APIRouter(
    prefix="/records",
    dependencies=[Depends(is_authenticated), Depends(require_permissions(UI_RECORD_VIEW))],
    tags=["测试记录"]
)


# ==================== 任务运行记录 ====================

@router.get("/tasks", summary="任务运行记录", status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(UI_RECORD_VIEW))])
async def get_task_record(project_id: int, task_id: int = None, page: int = 1, size: int = 10,
                          name: str | None = None, status: str | None = None,
                          start_date: str | None = None, end_date: str | None = None):
    """获取测试计划运行记录列表"""
    query = UiPlanExecution.filter(project=project_id, is_del=False)
    if task_id:
        query = query.filter(task=task_id)
    if name:
        query = query.filter(task__name__icontains=name)
    if status:
        query = query.filter(status=status)
    if start_date:
        query = query.filter(start_time__gte=start_date)
    if end_date:
        query = query.filter(start_time__lte=f"{end_date} 23:59:59")
    query = query.order_by("-id")
    total = await query.count()
    data = await query.offset((page - 1) * size).limit(size).prefetch_related('task')
    result = []
    for i in data:
        result.append({
            "id": i.id,
            "task_id": i.task.id,
            "task_name": i.task.name,
            "username": i.username,
            "start_time": i.start_time,
            "duration": i.duration,
            "status": i.status,
            "run_all": i.run_all,
            "success": i.success,
            "fail": i.fail,
            "error": i.error,
            "skip": i.skip,
            "case_count": i.case_count,
            "no_run": i.no_run,
            "env": i.env,
            "pass_rate": i.pass_rate,
            "execution_log": i.execution_log,
            "is_del": i.is_del
        })
    return {"total": total, "data": result}


# 未知
@router.delete(
    '/tasks/{record_id}',
    summary='删除任务运行记录',
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions(UI_RECORD_EDIT))],
)
async def delete_task_record(
    record_id: int,
    user_info: dict = Depends(require_permissions(UI_RECORD_EDIT)),
):
    """删除任务运行记录"""
    record = await UiPlanExecution.get_or_none(id=record_id, is_del=False)
    if not record:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="任务运行记录不存在或已被删除")
    await assert_user_project_member(user_info, record.project_id)
    # 逻辑删除
    record.is_del = True
    await record.save()


# 获取单个测试计划执行结果详情
@router.get("/tasks/{record_id}", summary="任务的执行详情", status_code=status.HTTP_200_OK, response_model=TaskResultSchemas)
async def get_task_record_detail(
    record_id: int,
    user_info: dict = Depends(require_permissions(UI_RECORD_VIEW)),
):
    """获取单个测试计划执行结果详情"""
    record = await UiPlanExecution.get_or_none(id=record_id, is_del=False).prefetch_related('task')
    if not record:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="测试计划执行记录不存在或已被删除")
    await assert_user_project_viewer(user_info, record.project_id)
    result = TaskResultSchemas(**record.__dict__, task_name=record.task.name)
    return result


# ==================== 套件运行记录 ====================

@router.get("/suites", summary="套件运行记录", status_code=status.HTTP_200_OK)
async def get_suite_record(
    project_id: int | None = None,
    suite_id: int | None = None,
    task_records_id: int | None = None,
    page: int = 1,
    size: int = 10,
    name: str | None = None,
    status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    user_info: dict = Depends(require_permissions(UI_RECORD_VIEW)),
):
    """获取测试套件运行记录列表（按 project_id / suite_id / task_records_id 筛选）"""
    query = UiSuiteExecution.filter(is_del=False)
    if task_records_id:
        query = query.filter(plan_execution=task_records_id)
        query = query.order_by("id")
    elif suite_id:
        query = query.filter(suite=suite_id)
    elif project_id:
        await assert_user_project_viewer(user_info, project_id)
        query = query.filter(suite__project_id=project_id, suite__is_del=False)
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="project_id、suite_id、task_records_id 至少传递一个！",
        )
    if name:
        query = query.filter(suite__name__icontains=name)
    if status:
        query = query.filter(status=status)
    if start_date:
        query = query.filter(start_time__gte=start_date)
    if end_date:
        query = query.filter(start_time__lte=f"{end_date} 23:59:59")
    if not task_records_id:
        query = query.order_by("-id")
    total = await query.count()
    data = await query.offset((page - 1) * size).limit(size).prefetch_related('suite')
    result = []
    for i in data:
        result.append({
            "id": i.id,
            "suite_id": i.suite.id,
            "suite_name": i.suite.name,
            "duration": i.duration,
            "username": i.username,
            "start_time": i.start_time,
            "status": i.status,
            "run_all": i.run_all,
            "success": i.success,
            "fail": i.fail,
            "error": i.error,
            "skip": i.skip,
            "case_count": i.case_count,
            "no_run": i.no_run,
            "pass_rate": i.pass_rate,
            "env": i.env,
            "execution_log": i.execution_log,
            "is_del": i.is_del
        })
    return {"total": total, "data": result}


# 未知
@router.delete(
    '/suites/{record_id}',
    summary='删除套件运行记录',
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions(UI_RECORD_EDIT))],
)
async def delete_suite_record(
    record_id: int,
    user_info: dict = Depends(require_permissions(UI_RECORD_EDIT)),
):
    """删除套件运行记录"""
    record = await UiSuiteExecution.get_or_none(id=record_id, is_del=False).prefetch_related("suite")
    if not record:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="套件运行记录不存在或已被删除")
    await assert_user_project_member(user_info, record.suite.project_id)
    # 逻辑删除
    record.is_del = True
    await record.save()


# 获取单个测试套件执行结果详情
@router.get("/suites/{record_id}", summary="套件的执行详情", status_code=status.HTTP_200_OK, response_model=SuiteResultSchemas)
async def get_suite_record_detail(
    record_id: int,
    user_info: dict = Depends(require_permissions(UI_RECORD_VIEW)),
):
    """获取单个测试套件执行结果详情"""
    record = await UiSuiteExecution.get_or_none(id=record_id, is_del=False).prefetch_related('suite')
    if not record:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="测试套件执行记录不存在或已被删除")
    await assert_user_project_viewer(user_info, record.suite.project_id)
    result = SuiteResultSchemas(**record.__dict__, suite_name=record.suite.name)
    return result


# ==================== 用例运行记录 ====================

class CaseRecordIdsForm(BaseModel):
    record_ids: List[int] = Field(..., min_length=1, description="记录 ID 列表")
    permanent: bool = Field(default=False, description="是否永久删除（回收站）")


@router.get("/cases", summary="用例运行记录", status_code=status.HTTP_200_OK)
async def get_case_record(
    case_id: int = None,
    suite_execution_id: int = None,
    task_records_id: int = None,
    status: str | None = None,
    page: int = 1,
    size: int = 10,
    recycle_bin: bool = False,
):
    """获取测试用例运行记录列表"""
    query = UiCaseExecution.filter(is_del=recycle_bin)
    if case_id:
        query = query.filter(case=case_id)
    elif suite_execution_id:
        query = query.filter(suite_execution=suite_execution_id)
    elif task_records_id:
        query = query.filter(suite_execution__plan_execution_id=task_records_id)
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="case_id、suite_execution_id、task_records_id 至少传递一个！")
    query = apply_ui_case_status_filter(query, status)
    query = query.order_by("-id")
    total = await query.count()
    data = await query.offset((page - 1) * size).limit(size).prefetch_related(
        'case', 'suite_execution__suite'
    )
    delete_mode = await get_ui_case_record_delete_mode()
    result = []
    loop = asyncio.get_running_loop()
    for i in data:
        presigned_data = await loop.run_in_executor(
            None, _presign_media_urls, i.result_data
        )
        suite_exec = i.suite_execution
        suite_name = suite_exec.suite.name if suite_exec and suite_exec.suite else None
        result.append({
            "id": i.id,
            "case_id": i.case.id,
            "case_name": i.case.name,
            "suite_execution_id": suite_exec.id if suite_exec else None,
            "suite_name": suite_name,
            "username": i.username,
            "start_time": i.start_time,
            "status": i.status,
            "result_data": presigned_data,
            "env": i.env,
            "is_del": i.is_del
        })
    return {"total": total, "data": result, "delete_mode": delete_mode}


@router.post(
    "/cases/batch-delete",
    summary="批量删除用例运行记录",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permissions(UI_RECORD_EDIT))],
)
async def batch_delete_case_records(
    body: CaseRecordIdsForm,
    user_info: dict = Depends(require_permissions(UI_RECORD_EDIT)),
):
    """批量删除用例运行记录（遵循平台删除策略）"""
    deleted = 0
    for record_id in body.record_ids:
        if body.permanent:
            record = await UiCaseExecution.get_or_none(id=record_id, is_del=True).prefetch_related("case")
        else:
            record = await UiCaseExecution.get_or_none(id=record_id, is_del=False).prefetch_related("case")
        if not record:
            continue
        await assert_user_project_member(user_info, record.case.project_id)
        await delete_ui_case_execution(record, permanent=body.permanent)
        deleted += 1
    if deleted == 0:
        raise HTTPException(status_code=400, detail="未找到可删除的记录")
    return {"deleted": deleted}


@router.post(
    "/cases/batch-restore",
    summary="批量恢复用例运行记录",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permissions(UI_RECORD_EDIT))],
)
async def batch_restore_case_records(
    body: CaseRecordIdsForm,
    user_info: dict = Depends(require_permissions(UI_RECORD_EDIT)),
):
    """从回收站批量恢复用例运行记录"""
    restored = 0
    for record_id in body.record_ids:
        record = await UiCaseExecution.get_or_none(id=record_id, is_del=True).prefetch_related("case")
        if not record:
            continue
        await assert_user_project_member(user_info, record.case.project_id)
        await restore_ui_case_execution(record)
        restored += 1
    if restored == 0:
        raise HTTPException(status_code=400, detail="未找到可恢复的记录")
    return {"restored": restored}


@router.post(
    "/cases/{record_id}/restore",
    summary="恢复用例运行记录",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions(UI_RECORD_EDIT))],
)
async def restore_case_record(
    record_id: int,
    user_info: dict = Depends(require_permissions(UI_RECORD_EDIT)),
):
    """从回收站恢复用例运行记录"""
    record = await UiCaseExecution.get_or_none(id=record_id, is_del=True).prefetch_related("case")
    if not record:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="记录不存在或不在回收站中")
    await assert_user_project_member(user_info, record.case.project_id)
    await restore_ui_case_execution(record)


@router.delete(
    '/cases/{record_id}',
    summary='删除用例运行记录',
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions(UI_RECORD_EDIT))],
)
async def delete_case_record(
    record_id: int,
    permanent: bool = False,
    user_info: dict = Depends(require_permissions(UI_RECORD_EDIT)),
):
    """删除用例运行记录（遵循平台删除策略；回收站中 permanent=true 为物理删除）"""
    if permanent:
        record = await UiCaseExecution.get_or_none(id=record_id, is_del=True).prefetch_related("case")
    else:
        record = await UiCaseExecution.get_or_none(id=record_id, is_del=False).prefetch_related("case")
    if not record:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用例运行记录不存在或已被删除")
    await assert_user_project_member(user_info, record.case.project_id)
    await delete_ui_case_execution(record, permanent=permanent)


# 获取单个测试用例执行结果详情
@router.get("/cases/{record_id}", summary="用例的执行详情", status_code=status.HTTP_200_OK)
async def get_case_record_detail(
    record_id: int,
    user_info: dict = Depends(require_permissions(UI_RECORD_VIEW)),
):
    """获取单个测试用例执行结果详情"""
    record = await UiCaseExecution.get_or_none(id=record_id, is_del=False).prefetch_related("case")
    if not record:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="测试用例执行记录不存在或已被删除")
    await assert_user_project_viewer(user_info, record.case.project_id)
    return record


# ==================== 报告导出 ====================

async def _build_report_context(
    record_id: int,
    record_type: str,
    include_images: bool,
    image_mode: str,
    include_video: bool
):
    """构建报告导出所需的数据上下文（仅查数据库，不生成 HTML）"""
    if record_type == "task":
        record = await UiPlanExecution.get_or_none(id=record_id, is_del=False).prefetch_related('task')
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务执行记录不存在")
        record_data = {
            "id": record.id,
            "task_name": record.task.name,
            "username": record.username,
            "start_time": record.start_time,
            "duration": record.duration,
            "status": record.status,
            "case_count": record.case_count,
            "success": record.success,
            "fail": record.fail,
            "error": record.error,
            "skip": record.skip,
            "no_run": record.no_run,
            "pass_rate": record.pass_rate,
            "env": record.env,
            "execution_log": record.execution_log
        }
        filename = f"测试报告-任务-{record.task.name}-{record.id}.html"
        
        suite_records_db = await UiSuiteExecution.filter(plan_execution=record_id, is_del=False).prefetch_related('suite')
        suite_records = []
        for sr in suite_records_db:
            suite_records.append({
                "id": sr.id,
                "suite_name": sr.suite.name,
                "status": sr.status,
                "case_count": sr.case_count,
                "success": sr.success,
                "fail": sr.fail,
                "error": sr.error,
                "skip": sr.skip,
                "no_run": sr.no_run,
                "pass_rate": sr.pass_rate,
                "execution_log": sr.execution_log,
                "duration": sr.duration,
                "start_time": sr.start_time
            })
        
        case_records = []
        for sr in suite_records_db:
            case_records_db = await UiCaseExecution.filter(suite_execution=sr.id, is_del=False).prefetch_related('case')
            for cr in case_records_db:
                case_records.append({
                    "id": cr.id,
                    "case_name": cr.case.name,
                    "status": cr.status,
                    "result_data": cr.result_data,
                    "suite_execution_id": sr.id,
                    "start_time": cr.start_time
                })
    
    elif record_type == "suite":
        record = await UiSuiteExecution.get_or_none(id=record_id, is_del=False).prefetch_related('suite')
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="套件执行记录不存在")
        record_data = {
            "id": record.id,
            "suite_name": record.suite.name,
            "username": record.username,
            "start_time": record.start_time,
            "duration": record.duration,
            "status": record.status,
            "case_count": record.case_count,
            "success": record.success,
            "fail": record.fail,
            "error": record.error,
            "skip": record.skip,
            "no_run": record.no_run,
            "pass_rate": record.pass_rate,
            "env": record.env,
            "execution_log": record.execution_log
        }
        filename = f"测试报告-套件-{record.suite.name}-{record.id}.html"
        suite_records = [{
            "id": record.id,
            "suite_name": record.suite.name,
            "status": record.status,
            "case_count": record.case_count,
            "success": record.success,
            "fail": record.fail,
            "error": record.error,
            "skip": record.skip,
            "no_run": record.no_run,
            "pass_rate": record.pass_rate,
            "execution_log": record.execution_log,
            "duration": record.duration,
            "start_time": record.start_time
        }]
        
        case_records_db = await UiCaseExecution.filter(suite_execution=record_id, is_del=False).prefetch_related('case')
        case_records = []
        for cr in case_records_db:
            case_records.append({
                "id": cr.id,
                "case_name": cr.case.name,
                "status": cr.status,
                "result_data": cr.result_data,
                "suite_execution_id": record.id,
                "start_time": cr.start_time
            })
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的记录类型")
    
    img_options = ImageExportOptions(
        include_images=include_images,
        image_mode=image_mode,
        include_video=include_video
    )
    return record_data, suite_records, case_records, filename, img_options


@router.get("/export/{record_id}", summary="导出测试报告")
async def export_report(
    record_id: int, 
    record_type: str = "task",
    include_images: bool = True,
    image_mode: str = "all",
    include_video: bool = True
):
    """同步导出测试报告（适合短用例）"""
    record_data, suite_records, case_records, filename, img_options = await _build_report_context(
        record_id, record_type, include_images, image_mode, include_video
    )
    html_content = generate_html_report(record_data, record_type, suite_records, case_records, img_options)
    
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"
    }
    return Response(
        content=html_content,
        media_type="text/html",
        headers=headers
    )


@router.post("/export-async/{record_id}", summary="异步导出测试报告")
async def export_report_async(
    record_id: int,
    record_type: str = "task",
    include_images: bool = True,
    image_mode: str = "all",
    include_video: bool = True
):
    """提交异步导出任务，后端在后台生成 HTML 文件"""
    # 先快速查询数据库（这部分很快，在主线程完成）
    context = await _build_report_context(
        record_id, record_type, include_images, image_mode, include_video
    )
    
    _cleanup_export_tasks()
    task_id = str(uuid.uuid4())
    export_tasks[task_id] = {
        "status": "pending",
        "download_url": None,
        "filename": context[3],
        "error": None,
        "created_at": time.time(),
    }
    
    async def _run_export():
        try:
            export_tasks[task_id]["status"] = "running"
            loop = asyncio.get_running_loop()
            # 把耗时操作放到线程池执行
            html_content = await loop.run_in_executor(
                None,
                generate_html_report,
                context[0], record_type, context[1], context[2], context[4]
            )
            # 写入文件
            file_path = os.path.join(EXPORT_DIR, f"{task_id}.html")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            
            export_tasks[task_id]["status"] = "completed"
            export_tasks[task_id]["download_url"] = f"/static/exports/{task_id}.html"
        except Exception as e:
            export_tasks[task_id]["status"] = "failed"
            export_tasks[task_id]["error"] = str(e)
    
    asyncio.create_task(_run_export())
    return {"task_id": task_id, "status": "pending"}


@router.get("/export-status/{task_id}", summary="查询异步导出任务状态")
async def export_report_status(task_id: str):
    """查询导出任务状态和下载链接"""
    _cleanup_export_tasks()
    task = export_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导出任务不存在")
    return task
