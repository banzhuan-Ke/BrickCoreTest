"""App 执行记录"""
import asyncio
import json
import os
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.config import BASE_DIR
from app.core.infra.minio_client import is_minio_storage, minio_client
from app.core.platform.permissions import APP_RECORD_VIEW
from app.core.ops.notification import NotificationService
from app.core.shared.report_export import ImageExportOptions, generate_html_report
from app.core.platform.platform_settings_service import (
    delete_app_case_execution,
    get_ui_case_record_delete_mode,
    restore_app_case_execution,
)
from app.modules.app.app_execution_env import enrich_app_env_for_display
from app.modules.ui.ui_project_guard import assert_user_project_member, assert_user_project_viewer
from app.models.app import AppCaseExecution, AppPlanExecution, AppSuiteExecution

router = APIRouter(
    prefix="/records",
    dependencies=[Depends(is_authenticated), Depends(require_permissions(APP_RECORD_VIEW))],
    tags=["App执行记录"],
)

export_tasks: dict = {}
EXPORT_DIR = os.path.join(BASE_DIR, "static", "exports")
EXPORT_TASK_TTL_SECONDS = 24 * 3600
os.makedirs(EXPORT_DIR, exist_ok=True)


async def _case_execution_cronjob_id(record: AppCaseExecution) -> str | None:
    if not record.suite_execution_id:
        return None
    suite_exec = await AppSuiteExecution.get_or_none(id=record.suite_execution_id)
    if not suite_exec:
        return None
    return suite_exec.cronjob_id or None


def _display_env(env, *, case=None, cronjob_id=None):
    return enrich_app_env_for_display(env, case=case, cronjob_id=cronjob_id)


class CaseRecordIdsForm(BaseModel):
    record_ids: list[int]
    permanent: bool = False


def _presign_media_urls(result_data):
    if not result_data or not is_minio_storage():
        return result_data
    if isinstance(result_data, str):
        try:
            result_data = json.loads(result_data)
        except Exception:
            return result_data

    def presign(url):
        if not url or not isinstance(url, str):
            return url
        bucket = minio_client.bucket_name
        marker = f"/{bucket}/"
        if marker not in url:
            return url
        filename = url.split(marker, 1)[-1]
        return minio_client.get_presigned_url(filename, expires=7200) or url

    data = dict(result_data)
    if "img" in data:
        data["img"] = presign(data["img"])
    if "video_url" in data:
        data["video_url"] = presign(data["video_url"])
    for step in data.get("steps", []):
        if not isinstance(step, dict):
            continue
        if "screenshot" in step:
            step["screenshot"] = presign(step["screenshot"])
        key = step.get("template_image_key")
        if key:
            step["template_image"] = (
                minio_client.get_presigned_url_for_app_element(str(key).lstrip("/"), 7200) or key
            )
    return data


def _cleanup_export_tasks() -> None:
    now = time.time()
    expired = [
        task_id
        for task_id, meta in export_tasks.items()
        if now - meta.get("created_at", now) > EXPORT_TASK_TTL_SECONDS
    ]
    for task_id in expired:
        export_tasks.pop(task_id, None)
        path = os.path.join(EXPORT_DIR, f"{task_id}.html")
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass


async def _build_report_context(
    record_id: int,
    record_type: str,
    include_images: bool,
    image_mode: str,
    include_video: bool,
    user_info: dict | None = None,
):
    if record_type == "task":
        record = await AppPlanExecution.get_or_none(id=record_id, is_del=False).prefetch_related("plan")
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="计划执行记录不存在")
        plan = await record.plan
        if user_info:
            await assert_user_project_viewer(user_info, record.project_id)
        record_data = {
            "id": record.id,
            "task_name": plan.name if plan else "",
            "username": record.username,
            "start_time": record.start_time,
            "duration": record.duration,
            "status": record.status,
            "case_count": record.case_count,
            "success": record.success,
            "fail": record.fail,
            "error": record.error,
            "skip": record.skip,
            "quarantine_skip": getattr(record, "quarantine_skip", 0) or 0,
            "no_run": record.no_run,
            "pass_rate": record.pass_rate,
            "env": _display_env(record.env, cronjob_id=record.cronjob_id),
            "device_id": record.device_id,
            "execution_log": record.execution_log,
        }
        filename = f"App测试报告-计划-{plan.name if plan else record.id}-{record.id}.html"

        suite_records_db = await AppSuiteExecution.filter(plan_execution_id=record_id, is_del=False).prefetch_related("suite")
        suite_records = []
        for sr in suite_records_db:
            suite = await sr.suite
            suite_records.append({
                "id": sr.id,
                "suite_name": suite.name if suite else "",
                "status": sr.status,
                "case_count": sr.case_count,
                "success": sr.success,
                "fail": sr.fail,
                "error": sr.error,
                "skip": sr.skip,
                "quarantine_skip": getattr(sr, "quarantine_skip", 0) or 0,
                "no_run": sr.no_run,
                "pass_rate": sr.pass_rate,
                "execution_log": sr.execution_log,
                "duration": sr.duration,
                "start_time": sr.start_time,
            })

        case_records = []
        for sr in suite_records_db:
            case_records_db = await AppCaseExecution.filter(suite_execution_id=sr.id, is_del=False).prefetch_related("case")
            for cr in case_records_db:
                case = await cr.case
                case_records.append({
                    "id": cr.id,
                    "case_name": case.name if case else "",
                    "status": cr.status,
                    "result_data": _presign_media_urls(cr.result_data),
                    "suite_execution_id": sr.id,
                    "start_time": cr.start_time,
                })

    elif record_type == "suite":
        record = await AppSuiteExecution.get_or_none(id=record_id, is_del=False).prefetch_related("suite")
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="套件执行记录不存在")
        suite = await record.suite
        if user_info and suite:
            await assert_user_project_viewer(user_info, suite.project_id)
        record_data = {
            "id": record.id,
            "suite_id": record.suite_id,
            "suite_name": suite.name if suite else "",
            "username": record.username,
            "start_time": record.start_time,
            "duration": record.duration,
            "status": record.status,
            "case_count": record.case_count,
            "success": record.success,
            "fail": record.fail,
            "error": record.error,
            "skip": record.skip,
            "quarantine_skip": getattr(record, "quarantine_skip", 0) or 0,
            "no_run": record.no_run,
            "pass_rate": record.pass_rate,
            "env": _display_env(record.env, cronjob_id=record.cronjob_id),
            "device_id": record.device_id,
            "execution_log": record.execution_log,
        }
        filename = f"App测试报告-套件-{suite.name if suite else record.id}-{record.id}.html"
        suite_records = [{
            "id": record.id,
            "suite_name": suite.name if suite else "",
            "status": record.status,
            "case_count": record.case_count,
            "success": record.success,
            "fail": record.fail,
            "error": record.error,
            "skip": record.skip,
            "quarantine_skip": getattr(record, "quarantine_skip", 0) or 0,
            "no_run": record.no_run,
            "pass_rate": record.pass_rate,
            "execution_log": record.execution_log,
            "duration": record.duration,
            "start_time": record.start_time,
        }]

        case_records_db = await AppCaseExecution.filter(suite_execution_id=record_id, is_del=False).prefetch_related("case")
        case_records = []
        for cr in case_records_db:
            case = await cr.case
            case_records.append({
                "id": cr.id,
                "case_name": case.name if case else "",
                "status": cr.status,
                "result_data": _presign_media_urls(cr.result_data),
                "suite_execution_id": record.id,
                "start_time": cr.start_time,
            })

    elif record_type == "case":
        record = await AppCaseExecution.get_or_none(id=record_id, is_del=False).prefetch_related("case")
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用例执行记录不存在")
        case = await record.case
        if not case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用例执行记录不存在")
        if user_info:
            await assert_user_project_viewer(user_info, case.project_id)
        result_data = _presign_media_urls(record.result_data)
        status = record.status or "no_run"
        record_data = {
            "id": record.id,
            "case_id": record.case_id,
            "case_name": case.name,
            "username": record.username,
            "start_time": record.start_time,
            "duration": (result_data or {}).get("duration", 0) if isinstance(result_data, dict) else 0,
            "status": status,
            "case_count": 1,
            "success": 1 if status == "success" else 0,
            "fail": 1 if status in ("fail", "failed") else 0,
            "error": 1 if status == "error" else 0,
            "skip": 1 if status == "skip" else 0,
            "quarantine_skip": 0,
            "no_run": 1 if status in ("no_run", "running", "waiting") else 0,
            "pass_rate": 100.0 if status == "success" else 0.0,
            "env": _display_env(
                record.env,
                case=case,
                cronjob_id=await _case_execution_cronjob_id(record),
            ),
            "device_id": (record.env or {}).get("device_udid") if isinstance(record.env, dict) else None,
            "execution_log": (result_data or {}).get("log_data", []) if isinstance(result_data, dict) else [],
        }
        filename = f"App测试报告-用例-{case.name}-{record.id}.html"
        suite_records = []
        case_records = [{
            "id": record.id,
            "case_name": case.name,
            "status": status,
            "result_data": result_data,
            "suite_execution_id": None,
            "start_time": record.start_time,
        }]

    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的记录类型")

    img_options = ImageExportOptions(
        include_images=include_images,
        image_mode=image_mode,
        include_video=include_video,
    )
    return record_data, suite_records, case_records, filename, img_options


async def _case_rows_for_suite(suite_execution_id: int) -> list:
    cases = await AppCaseExecution.filter(suite_execution_id=suite_execution_id, is_del=False).prefetch_related("case")
    rows = []
    for c in cases:
        case = await c.case
        rows.append({
            "id": c.id,
            "case_id": c.case_id,
            "case_name": case.name if case else "",
            "status": c.status,
            "result_data": _presign_media_urls(c.result_data),
            "start_time": c.start_time,
        })
    return rows


@router.get("/plans", summary="App 计划执行记录")
async def list_plan_records(
    project_id: int,
    plan_id: int | None = None,
    page: int = 1,
    size: int = 10,
    recycle_bin: bool = False,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    await assert_user_project_viewer(user_info, project_id)
    query = AppPlanExecution.filter(project_id=project_id, is_del=recycle_bin)
    if plan_id is not None:
        query = query.filter(plan_id=plan_id)
    query = query.order_by("-id")
    total = await query.count()
    rows = await query.offset((page - 1) * size).limit(size).prefetch_related("plan")
    data = []
    for row in rows:
        plan = await row.plan
        data.append({
            "id": row.id,
            "plan_id": row.plan_id,
            "plan_name": plan.name if plan else "",
            "status": row.status,
            "case_count": row.case_count,
            "success": row.success,
            "fail": row.fail,
            "skip": row.skip,
            "quarantine_skip": getattr(row, "quarantine_skip", 0) or 0,
            "pass_rate": row.pass_rate,
            "duration": row.duration,
            "device_id": row.device_id,
            "start_time": row.start_time,
            "username": row.username,
        })
    return {"data": data, "total": total}


@router.get("/suites", summary="App 套件执行记录")
async def list_suite_records(
    project_id: int,
    suite_id: int | None = None,
    page: int = 1,
    size: int = 10,
    recycle_bin: bool = False,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    await assert_user_project_viewer(user_info, project_id)
    query = AppSuiteExecution.filter(
        suite__project_id=project_id,
        suite__is_del=False,
        plan_execution_id=None,
        is_del=recycle_bin,
    )
    if suite_id is not None:
        query = query.filter(suite_id=suite_id)
    query = query.order_by("-id")
    total = await query.count()
    rows = await query.offset((page - 1) * size).limit(size).prefetch_related("suite")
    data = []
    for row in rows:
        suite = await row.suite
        data.append({
            "id": row.id,
            "suite_id": row.suite_id,
            "suite_name": suite.name if suite else "",
            "status": row.status,
            "case_count": row.case_count,
            "success": getattr(row, "success", None),
            "fail": getattr(row, "fail", None),
            "skip": getattr(row, "skip", None),
            "quarantine_skip": getattr(row, "quarantine_skip", 0) or 0,
            "pass_rate": row.pass_rate,
            "duration": row.duration,
            "start_time": row.start_time,
            "username": row.username,
        })
    return {"data": data, "total": total}


@router.get("/cases", summary="App 用例执行记录")
async def list_case_records(
    project_id: int,
    case_id: int | None = None,
    page: int = 1,
    size: int = 10,
    recycle_bin: bool = False,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    await assert_user_project_viewer(user_info, project_id)
    query = AppCaseExecution.filter(
        case__project_id=project_id,
        case__is_del=False,
        suite_execution_id=None,
        is_del=recycle_bin,
    )
    if case_id is not None:
        query = query.filter(case_id=case_id)
    query = query.order_by("-id")
    total = await query.count()
    rows = await query.offset((page - 1) * size).limit(size).prefetch_related("case")
    delete_mode = await get_ui_case_record_delete_mode()
    data = []
    for row in rows:
        case = await row.case
        data.append({
            "id": row.id,
            "case_id": row.case_id,
            "case_name": case.name if case else "",
            "status": row.status,
            "start_time": row.start_time,
            "username": row.username,
            "result_data": _presign_media_urls(row.result_data),
            "env": row.env,
            "is_del": row.is_del,
        })
    return {"data": data, "total": total, "delete_mode": delete_mode}


@router.get("/plans/{record_id}", summary="App 计划执行详情")
async def get_plan_record(
    record_id: int,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    record = await AppPlanExecution.get_or_none(id=record_id, is_del=False).prefetch_related("plan")
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    await assert_user_project_viewer(user_info, record.project_id)
    plan = await record.plan
    suites = await AppSuiteExecution.filter(plan_execution_id=record.id, is_del=False).prefetch_related("suite")
    suite_rows = []
    for sr in suites:
        suite = await sr.suite
        suite_rows.append({
            "id": sr.id,
            "suite_id": sr.suite_id,
            "suite_name": suite.name if suite else "",
            "status": sr.status,
            "pass_rate": sr.pass_rate,
            "duration": sr.duration,
            "quarantine_skip": getattr(sr, "quarantine_skip", 0) or 0,
            "cases": await _case_rows_for_suite(sr.id),
        })
    return {
        "id": record.id,
        "plan_id": record.plan_id,
        "plan_name": plan.name if plan else "",
        "status": record.status,
        "pass_rate": record.pass_rate,
        "duration": record.duration,
        "case_count": record.case_count,
        "success": record.success,
        "fail": record.fail,
        "error": record.error,
        "skip": record.skip,
        "quarantine_skip": getattr(record, "quarantine_skip", 0) or 0,
        "username": record.username,
        "start_time": record.start_time,
        "device_id": record.device_id,
        "env": _display_env(record.env, cronjob_id=record.cronjob_id),
        "execution_log": record.execution_log,
        "suites": suite_rows,
    }


@router.get("/suites/{record_id}", summary="App 套件执行详情")
async def get_suite_record(
    record_id: int,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    record = await AppSuiteExecution.get_or_none(id=record_id, is_del=False).prefetch_related("suite")
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    suite = await record.suite
    if not suite:
        raise HTTPException(status_code=404, detail="记录不存在")
    await assert_user_project_viewer(user_info, suite.project_id)
    cases = await AppCaseExecution.filter(suite_execution_id=record.id, is_del=False).prefetch_related("case")
    case_rows = []
    for c in cases:
        case = await c.case
        case_rows.append({
            "id": c.id,
            "case_id": c.case_id,
            "case_name": case.name if case else "",
            "status": c.status,
            "result_data": _presign_media_urls(c.result_data),
            "start_time": c.start_time,
        })
    return {
        "id": record.id,
        "suite_id": record.suite_id,
        "suite_name": suite.name if suite else "",
        "status": record.status,
        "pass_rate": record.pass_rate,
        "duration": record.duration,
        "case_count": record.case_count,
        "success": record.success,
        "fail": record.fail,
        "error": record.error,
        "skip": record.skip,
        "quarantine_skip": getattr(record, "quarantine_skip", 0) or 0,
        "username": record.username,
        "start_time": record.start_time,
        "device_id": record.device_id,
        "env": _display_env(record.env, cronjob_id=record.cronjob_id),
        "execution_log": record.execution_log,
        "cases": case_rows,
    }


@router.get("/cases/{record_id}", summary="App 用例执行详情")
async def get_case_record(
    record_id: int,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    record = await AppCaseExecution.get_or_none(id=record_id, is_del=False).prefetch_related("case")
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    case = await record.case
    if not case:
        raise HTTPException(status_code=404, detail="记录不存在")
    await assert_user_project_viewer(user_info, case.project_id)
    cronjob_id = await _case_execution_cronjob_id(record)
    return {
        "id": record.id,
        "case_id": record.case_id,
        "case_name": case.name if case else "",
        "status": record.status,
        "result_data": _presign_media_urls(record.result_data),
        "env": _display_env(record.env, case=case, cronjob_id=cronjob_id),
        "start_time": record.start_time,
        "username": record.username,
    }


@router.delete("/plans/{record_id}", summary="删除 App 计划执行记录", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan_record(
    record_id: int,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    record = await AppPlanExecution.get_or_none(id=record_id, is_del=False)
    if not record:
        raise HTTPException(status_code=422, detail="计划执行记录不存在或已被删除")
    await assert_user_project_member(user_info, record.project_id)
    record.is_del = True
    await record.save()
    suite_ids = await AppSuiteExecution.filter(plan_execution_id=record_id, is_del=False).values_list("id", flat=True)
    if suite_ids:
        await AppSuiteExecution.filter(id__in=list(suite_ids)).update(is_del=True)
        await AppCaseExecution.filter(suite_execution_id__in=list(suite_ids), is_del=False).update(is_del=True)


@router.delete("/suites/{record_id}", summary="删除 App 套件执行记录", status_code=status.HTTP_204_NO_CONTENT)
async def delete_suite_record(
    record_id: int,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    record = await AppSuiteExecution.get_or_none(id=record_id, is_del=False).prefetch_related("suite")
    if not record:
        raise HTTPException(status_code=422, detail="套件执行记录不存在或已被删除")
    suite = await record.suite
    if not suite:
        raise HTTPException(status_code=422, detail="套件执行记录不存在或已被删除")
    await assert_user_project_member(user_info, suite.project_id)
    record.is_del = True
    await record.save()
    await AppCaseExecution.filter(suite_execution_id=record_id, is_del=False).update(is_del=True)


@router.delete("/cases/{record_id}", summary="删除 App 用例执行记录", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case_record(
    record_id: int,
    permanent: bool = False,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    if permanent:
        record = await AppCaseExecution.get_or_none(id=record_id, is_del=True).prefetch_related("case")
    else:
        record = await AppCaseExecution.get_or_none(id=record_id, is_del=False).prefetch_related("case")
    if not record:
        raise HTTPException(status_code=422, detail="用例执行记录不存在或已被删除")
    case = await record.case
    if not case:
        raise HTTPException(status_code=422, detail="用例执行记录不存在或已被删除")
    await assert_user_project_member(user_info, case.project_id)
    await delete_app_case_execution(record, permanent=permanent)


@router.post("/cases/batch-delete", summary="批量删除 App 用例执行记录")
async def batch_delete_case_records(
    body: CaseRecordIdsForm,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    deleted = 0
    for record_id in body.record_ids:
        if body.permanent:
            record = await AppCaseExecution.get_or_none(id=record_id, is_del=True).prefetch_related("case")
        else:
            record = await AppCaseExecution.get_or_none(id=record_id, is_del=False).prefetch_related("case")
        if not record:
            continue
        case = await record.case
        if not case:
            continue
        await assert_user_project_member(user_info, case.project_id)
        await delete_app_case_execution(record, permanent=body.permanent)
        deleted += 1
    if deleted == 0:
        raise HTTPException(status_code=400, detail="未找到可删除的记录")
    return {"deleted": deleted}


@router.post("/cases/batch-restore", summary="批量恢复 App 用例执行记录")
async def batch_restore_case_records(
    body: CaseRecordIdsForm,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    restored = 0
    for record_id in body.record_ids:
        record = await AppCaseExecution.get_or_none(id=record_id, is_del=True).prefetch_related("case")
        if not record:
            continue
        case = await record.case
        if not case:
            continue
        await assert_user_project_member(user_info, case.project_id)
        await restore_app_case_execution(record)
        restored += 1
    if restored == 0:
        raise HTTPException(status_code=400, detail="未找到可恢复的记录")
    return {"restored": restored}


@router.post("/plans/{record_id}/restore", summary="恢复 App 计划执行记录", status_code=status.HTTP_204_NO_CONTENT)
async def restore_plan_record(
    record_id: int,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    record = await AppPlanExecution.get_or_none(id=record_id, is_del=True)
    if not record:
        raise HTTPException(status_code=422, detail="计划执行记录不存在或不在回收站中")
    await assert_user_project_member(user_info, record.project_id)
    record.is_del = False
    await record.save()
    suite_ids = await AppSuiteExecution.filter(plan_execution_id=record_id).values_list("id", flat=True)
    if suite_ids:
        await AppSuiteExecution.filter(id__in=list(suite_ids)).update(is_del=False)
        await AppCaseExecution.filter(suite_execution_id__in=list(suite_ids)).update(is_del=False)


@router.post("/suites/{record_id}/restore", summary="恢复 App 套件执行记录", status_code=status.HTTP_204_NO_CONTENT)
async def restore_suite_record(
    record_id: int,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    record = await AppSuiteExecution.get_or_none(id=record_id, is_del=True).prefetch_related("suite")
    if not record:
        raise HTTPException(status_code=422, detail="套件执行记录不存在或不在回收站中")
    suite = await record.suite
    if not suite:
        raise HTTPException(status_code=422, detail="套件执行记录不存在或不在回收站中")
    await assert_user_project_member(user_info, suite.project_id)
    record.is_del = False
    await record.save()
    await AppCaseExecution.filter(suite_execution_id=record_id).update(is_del=False)


@router.post("/cases/{record_id}/restore", summary="恢复 App 用例执行记录", status_code=status.HTTP_204_NO_CONTENT)
async def restore_case_record(
    record_id: int,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    record = await AppCaseExecution.get_or_none(id=record_id, is_del=True).prefetch_related("case")
    if not record:
        raise HTTPException(status_code=422, detail="用例执行记录不存在或不在回收站中")
    case = await record.case
    if not case:
        raise HTTPException(status_code=422, detail="用例执行记录不存在或不在回收站中")
    await assert_user_project_member(user_info, case.project_id)
    await restore_app_case_execution(record)


@router.get("/export/{record_id}", summary="导出 App 测试报告")
async def export_report(
    record_id: int,
    record_type: str = "task",
    include_images: bool = True,
    image_mode: str = "all",
    include_video: bool = True,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    record_data, suite_records, case_records, filename, img_options = await _build_report_context(
        record_id, record_type, include_images, image_mode, include_video, user_info
    )
    html_content = generate_html_report(record_data, record_type, suite_records, case_records, img_options)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"
    }
    return Response(content=html_content, media_type="text/html", headers=headers)


@router.post("/export-async/{record_id}", summary="异步导出 App 测试报告")
async def export_report_async(
    record_id: int,
    record_type: str = "task",
    include_images: bool = True,
    image_mode: str = "all",
    include_video: bool = True,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    context = await _build_report_context(
        record_id, record_type, include_images, image_mode, include_video, user_info
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
            html_content = await loop.run_in_executor(
                None,
                generate_html_report,
                context[0], record_type, context[1], context[2], context[4],
            )
            os.makedirs(EXPORT_DIR, exist_ok=True)
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


@router.get("/export-status/{task_id}", summary="查询 App 异步导出任务状态")
async def export_report_status(task_id: str):
    _cleanup_export_tasks()
    task = export_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="导出任务不存在")
    return task


class SendAppReportPayload(BaseModel):
    recipients: list[str] | None = None
    config_ids: list[int] | None = None


@router.post("/plans/{record_id}/send-report", summary="发送 App 计划报告")
async def send_plan_report(
    record_id: int,
    payload: SendAppReportPayload | None = None,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    record = await AppPlanExecution.get_or_none(id=record_id, is_del=False)
    if not record:
        raise HTTPException(status_code=404, detail="计划执行记录不存在")
    await assert_user_project_member(user_info, record.project_id)
    body = payload or SendAppReportPayload()
    try:
        result = await NotificationService.send_app_plan_report(
            record_id,
            body.recipients,
            config_ids=body.config_ids,
        )
        return {"msg": NotificationService.format_dispatch_detail(result)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/suites/{record_id}/send-report", summary="发送 App 套件报告")
async def send_suite_report(
    record_id: int,
    payload: SendAppReportPayload | None = None,
    user_info: dict = Depends(require_permissions(APP_RECORD_VIEW)),
):
    record = await AppSuiteExecution.get_or_none(id=record_id, is_del=False).prefetch_related("suite")
    if not record:
        raise HTTPException(status_code=404, detail="套件执行记录不存在")
    suite = await record.suite
    if not suite:
        raise HTTPException(status_code=404, detail="套件执行记录不存在")
    await assert_user_project_member(user_info, suite.project_id)
    body = payload or SendAppReportPayload()
    try:
        result = await NotificationService.send_app_suite_report(
            record_id,
            body.recipients,
            config_ids=body.config_ids,
        )
        return {"msg": NotificationService.format_dispatch_detail(result)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
