"""智能浏览器（browser-use）API：用例库 + 执行记录 + 报告。"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from tortoise.expressions import Q

from app.core.platform import config as settings
from app.core.platform.auth import is_authenticated, require_permissions
from app.modules.browser_lab.browser_lab_runner import ensure_browser_lab_dir, request_stop, run_browser_lab_task
from app.core.platform.permissions import AI_TEST_EXECUTE, AI_TEST_VIEW, UI_CASE_EDIT
from app.models.ai import BrowserLabCase, BrowserLabTask
from app.models.ui import Case
from app.schemas.ai import StandardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/browser-lab", tags=["智能浏览器"])


class BrowserLabRunConfig(BaseModel):
    ai_config_id: Optional[int] = None
    max_steps: int = Field(default=25, ge=3, le=50)
    use_vision: bool = True
    generate_gif: bool = True
    enable_browser_restart: bool = True
    max_browser_restarts: int = Field(default=2, ge=0, le=5)
    max_repeat_steps: int = Field(default=3, ge=2, le=8)


class CreateBrowserLabTaskRequest(BrowserLabRunConfig):
    task_text: str = Field(..., min_length=2, max_length=4000)
    start_url: str = Field(..., min_length=8, max_length=500)
    case_id: Optional[int] = None
    source_task_id: Optional[int] = None


class BrowserLabCaseBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    task_text: str = Field(..., min_length=2, max_length=4000)
    start_url: str = Field(..., min_length=8, max_length=500)
    tags: str = Field(default="", max_length=200)
    config: BrowserLabRunConfig = Field(default_factory=BrowserLabRunConfig)


class DeleteIdsBody(BaseModel):
    ids: list[int] = Field(..., min_length=1)


class OptimizeTaskTextRequest(BaseModel):
    task_text: str = Field(..., min_length=2, max_length=4000)
    start_url: Optional[str] = Field(default=None, max_length=500)
    case_name: Optional[str] = Field(default=None, max_length=200)
    ai_config_id: Optional[int] = None


def _resolve_project_id(user_info: dict, project_id: Optional[int]) -> int:
    pid = project_id or user_info.get("project_id") or user_info.get("current_project_id")
    if not pid:
        raise HTTPException(status_code=400, detail="请先选择项目")
    return int(pid)


def _case_to_dict(case: BrowserLabCase) -> dict[str, Any]:
    cfg = case.config_json or {}
    return {
        "id": case.id,
        "project_id": case.project_id,
        "name": case.name,
        "description": case.description,
        "task_text": case.task_text,
        "start_url": case.start_url,
        "tags": case.tags or "",
        "config_json": cfg,
        "ai_config_id": cfg.get("ai_config_id"),
        "max_steps": cfg.get("max_steps", settings.BROWSER_LAB_DEFAULT_MAX_STEPS),
        "use_vision": cfg.get("use_vision", True),
        "generate_gif": cfg.get("generate_gif", True),
        "enable_browser_restart": cfg.get("enable_browser_restart", True),
        "max_browser_restarts": cfg.get(
            "max_browser_restarts", settings.BROWSER_LAB_MAX_BROWSER_RESTARTS
        ),
        "max_repeat_steps": cfg.get(
            "max_repeat_steps", settings.BROWSER_LAB_MAX_REPEAT_STEPS
        ),
        "run_count": case.run_count,
        "last_run_at": case.last_run_at.isoformat() if case.last_run_at else None,
        "last_status": case.last_status,
        "created_by": case.created_by,
        "update_by": case.update_by,
        "create_time": case.create_time.isoformat() if case.create_time else None,
        "update_time": case.update_time.isoformat() if case.update_time else None,
    }


def _task_to_dict(task: BrowserLabTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "project_id": task.project_id,
        "case_id": task.case_id,
        "case_name": task.case_name,
        "source_task_id": task.source_task_id,
        "created_by": task.created_by,
        "task_text": task.task_text,
        "start_url": task.start_url,
        "status": task.status,
        "engine": task.engine,
        "config_json": task.config_json or {},
        "step_log": task.step_log or [],
        "result_summary": task.result_summary,
        "tokens_used": task.tokens_used,
        "steps_count": task.steps_count,
        "gif_path": task.gif_path,
        "gif_url": f"/static/{task.gif_path}" if task.gif_path else None,
        "error_message": task.error_message,
        "ai_config_id": task.ai_config_id,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "create_time": task.create_time.isoformat() if task.create_time else None,
        "duration_sec": _task_duration_sec(task),
    }


def _task_duration_sec(task: BrowserLabTask) -> Optional[int]:
    if not task.started_at or not task.finished_at:
        return None
    return int((task.finished_at - task.started_at).total_seconds())


def _task_report(task: BrowserLabTask) -> dict[str, Any]:
    steps = [e for e in (task.step_log or []) if e.get("type") == "step"]
    return {
        **_task_to_dict(task),
        "steps": steps,
        "step_count": len(steps),
        "success": task.status == "done",
    }


def _normalize_url(url: str) -> str:
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="起始 URL 须以 http:// 或 https:// 开头")
    return u


def _build_config_json(body: BrowserLabRunConfig) -> dict[str, Any]:
    max_steps = min(body.max_steps, settings.BROWSER_LAB_MAX_STEPS_CAP)
    cap = max(0, settings.BROWSER_LAB_MAX_BROWSER_RESTARTS_CAP)
    max_restarts = min(max(0, body.max_browser_restarts), cap)
    if not body.enable_browser_restart:
        max_restarts = 0
    repeat_cap = max(2, settings.BROWSER_LAB_MAX_REPEAT_STEPS_CAP)
    max_repeat = min(max(2, body.max_repeat_steps), repeat_cap)
    return {
        "ai_config_id": body.ai_config_id,
        "max_steps": max_steps,
        "use_vision": body.use_vision,
        "generate_gif": body.generate_gif,
        "enable_browser_restart": body.enable_browser_restart,
        "max_browser_restarts": max_restarts,
        "max_repeat_steps": max_repeat,
    }


def _remove_task_static_files(task_id: int) -> None:
    task_dir = os.path.join(settings.BROWSER_LAB_DIR, str(task_id))
    if not os.path.isdir(task_dir):
        return
    import shutil

    try:
        shutil.rmtree(task_dir, ignore_errors=True)
    except Exception as ex:
        logger.warning("[browser_lab] remove task dir failed: %s", ex)


async def _hard_delete_task(task: BrowserLabTask) -> None:
    """物理删除执行记录及截图/GIF 文件。"""
    task_id = task.id
    await task.delete()
    _remove_task_static_files(task_id)


async def _hard_delete_case(case: BrowserLabCase) -> None:
    """物理删除用例及其全部执行记录（含静态文件）。"""
    running = await BrowserLabTask.filter(
        case_id=case.id, status__in=("pending", "running")
    ).count()
    if running:
        raise HTTPException(
            status_code=400,
            detail=f"用例「{case.name}」仍有 {running} 个执行中的任务，请先停止后再删除",
        )
    tasks = await BrowserLabTask.filter(case_id=case.id)
    for task in tasks:
        await _hard_delete_task(task)
    await case.delete()


async def _check_daily_quota(project_id: int) -> None:
    limit = settings.BROWSER_LAB_DAILY_LIMIT
    if limit <= 0:
        return
    since = datetime.now(timezone.utc) - timedelta(days=1)
    count = await BrowserLabTask.filter(project_id=project_id, create_time__gte=since).count()
    if count >= limit:
        raise HTTPException(status_code=429, detail=f"今日智能浏览器任务已达上限（{limit} 次）")


async def _check_concurrent_limit() -> None:
    running = await BrowserLabTask.filter(status="running").count()
    if running >= settings.BROWSER_LAB_MAX_CONCURRENT:
        raise HTTPException(
            status_code=429,
            detail=f"当前有 {running} 个任务执行中，请稍后再试（并发上限 {settings.BROWSER_LAB_MAX_CONCURRENT}）",
        )


async def _start_task(
    *,
    project_id: int,
    username: str,
    task_text: str,
    start_url: str,
    config_json: dict[str, Any],
    case_id: Optional[int] = None,
    case_name: Optional[str] = None,
    source_task_id: Optional[int] = None,
) -> BrowserLabTask:
    ensure_browser_lab_dir()
    await _check_daily_quota(project_id)
    await _check_concurrent_limit()

    task = await BrowserLabTask.create(
        project_id=project_id,
        case_id=case_id,
        case_name=case_name,
        source_task_id=source_task_id,
        created_by=username,
        task_text=task_text.strip(),
        start_url=start_url,
        status="pending",
        config_json=config_json,
    )
    asyncio.create_task(run_browser_lab_task(task.id, username=username))
    return task


# ---------- 用例库 ----------


@router.get("/cases", summary="用例列表", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def list_cases(
    project_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    qs = BrowserLabCase.filter(project_id=pid, is_del=False)
    if keyword:
        kw = keyword.strip()
        qs = qs.filter(
            Q(name__icontains=kw)
            | Q(task_text__icontains=kw)
            | Q(tags__icontains=kw)
            | Q(start_url__icontains=kw)
        )
    total = await qs.count()
    rows = await qs.order_by("-update_time", "-id").offset((page - 1) * size).limit(size)
    return StandardResponse(
        data={"list": [_case_to_dict(c) for c in rows], "total": total, "page": page, "size": size}
    )


@router.get("/cases/{case_id}", summary="用例详情", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def get_case(
    case_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    case = await BrowserLabCase.get_or_none(id=case_id, project_id=pid, is_del=False)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    return StandardResponse(data=_case_to_dict(case))


@router.post("/cases", summary="新建用例", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def create_case(
    body: BrowserLabCaseBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    username = user_info.get("username") or user_info.get("sub") or ""
    url = _normalize_url(body.start_url)
    case = await BrowserLabCase.create(
        project_id=pid,
        name=body.name.strip(),
        description=(body.description or "").strip() or None,
        task_text=body.task_text.strip(),
        start_url=url,
        tags=(body.tags or "").strip(),
        config_json=_build_config_json(body.config),
        created_by=username,
        update_by=username,
    )
    return StandardResponse(data=_case_to_dict(case), message="用例已创建")


@router.put("/cases/{case_id}", summary="更新用例", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def update_case(
    case_id: int,
    body: BrowserLabCaseBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    case = await BrowserLabCase.get_or_none(id=case_id, project_id=pid, is_del=False)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    username = user_info.get("username") or user_info.get("sub") or ""
    case.name = body.name.strip()
    case.description = (body.description or "").strip() or None
    case.task_text = body.task_text.strip()
    case.start_url = _normalize_url(body.start_url)
    case.tags = (body.tags or "").strip()
    case.config_json = _build_config_json(body.config)
    case.update_by = username
    await case.save()
    return StandardResponse(data=_case_to_dict(case), message="用例已更新")


@router.delete("/cases", summary="删除用例（物理删除）", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def delete_cases(
    body: DeleteIdsBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    cases = await BrowserLabCase.filter(project_id=pid, id__in=body.ids, is_del=False)
    deleted = 0
    for case in cases:
        await _hard_delete_case(case)
        deleted += 1
    return StandardResponse(data={"deleted": deleted}, message=f"已永久删除 {deleted} 条用例及关联执行记录")


@router.post("/cases/{case_id}/run", summary="执行用例", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def run_case(
    case_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    case = await BrowserLabCase.get_or_none(id=case_id, project_id=pid, is_del=False)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    username = user_info.get("username") or user_info.get("sub") or ""
    cfg = case.config_json or {}
    task = await _start_task(
        project_id=pid,
        username=username,
        task_text=case.task_text,
        start_url=case.start_url,
        config_json=cfg,
        case_id=case.id,
        case_name=case.name,
    )
    return StandardResponse(data=_task_to_dict(task), message="用例已开始执行")


# ---------- 执行任务 ----------


@router.post("/tasks", summary="创建并启动任务", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def create_task(
    body: CreateBrowserLabTaskRequest,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    username = user_info.get("username") or user_info.get("sub") or ""
    url = _normalize_url(body.start_url)
    case_name = None
    if body.case_id:
        case = await BrowserLabCase.get_or_none(id=body.case_id, project_id=pid, is_del=False)
        if case:
            case_name = case.name
    task = await _start_task(
        project_id=pid,
        username=username,
        task_text=body.task_text,
        start_url=url,
        config_json=_build_config_json(body),
        case_id=body.case_id,
        case_name=case_name,
        source_task_id=body.source_task_id,
    )
    return StandardResponse(data=_task_to_dict(task), message="任务已创建，正在启动浏览器 Agent")


@router.post("/tasks/{task_id}/rerun", summary="重复执行", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def rerun_task(
    task_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    src = await BrowserLabTask.get_or_none(id=task_id, project_id=pid)
    if not src:
        raise HTTPException(status_code=404, detail="任务不存在")
    username = user_info.get("username") or user_info.get("sub") or ""
    task = await _start_task(
        project_id=pid,
        username=username,
        task_text=src.task_text,
        start_url=src.start_url,
        config_json=src.config_json or {},
        case_id=src.case_id,
        case_name=src.case_name,
        source_task_id=src.id,
    )
    return StandardResponse(data=_task_to_dict(task), message="已重新执行")


@router.get("/tasks", summary="执行记录列表", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def list_tasks(
    project_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    case_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    qs = BrowserLabTask.filter(project_id=pid)
    if status:
        qs = qs.filter(status=status.strip())
    if case_id:
        qs = qs.filter(case_id=case_id)
    if keyword:
        kw = keyword.strip()
        qs = qs.filter(
            Q(task_text__icontains=kw)
            | Q(case_name__icontains=kw)
            | Q(start_url__icontains=kw)
            | Q(created_by__icontains=kw)
        )
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    return StandardResponse(
        data={
            "list": [_task_to_dict(t) for t in rows],
            "total": total,
            "page": page,
            "size": size,
        }
    )


@router.get("/tasks/{task_id}", summary="任务详情", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def get_task(
    task_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    task = await BrowserLabTask.get_or_none(id=task_id, project_id=pid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return StandardResponse(data=_task_to_dict(task))


@router.get("/tasks/{task_id}/report", summary="执行报告", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def get_task_report(
    task_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    task = await BrowserLabTask.get_or_none(id=task_id, project_id=pid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return StandardResponse(data=_task_report(task))


@router.delete("/tasks", summary="批量删除执行记录（物理删除）", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def delete_tasks_batch(
    body: DeleteIdsBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    tasks = await BrowserLabTask.filter(project_id=pid, id__in=body.ids)
    deleted = 0
    skipped: list[int] = []
    for task in tasks:
        if task.status in ("pending", "running"):
            skipped.append(task.id)
            continue
        await _hard_delete_task(task)
        deleted += 1
    msg = f"已永久删除 {deleted} 条执行记录"
    if skipped:
        msg += f"，跳过执行中任务 {len(skipped)} 条"
    return StandardResponse(data={"deleted": deleted, "skipped": skipped}, message=msg)


@router.delete("/tasks/{task_id}", summary="删除执行记录（物理删除）", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def delete_task(
    task_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    task = await BrowserLabTask.get_or_none(id=task_id, project_id=pid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status in ("pending", "running"):
        raise HTTPException(status_code=400, detail="执行中的任务请先停止")
    await _hard_delete_task(task)
    return StandardResponse(message="执行记录已永久删除")


@router.post("/tasks/{task_id}/stop", summary="停止任务", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def stop_task(
    task_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    task = await BrowserLabTask.get_or_none(id=task_id, project_id=pid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status not in ("pending", "running"):
        raise HTTPException(status_code=400, detail="任务已结束，无法停止")
    request_stop(task_id)
    log = list(task.step_log or [])
    if not any(e.get("type") == "done" for e in log):
        log.append({"type": "done", "status": "stopped", "summary": "用户已停止"})
    task.status = "stopped"
    task.error_message = "用户已停止"
    task.result_summary = "用户已停止"
    task.finished_at = datetime.now(timezone.utc)
    task.step_log = log
    await task.save(update_fields=["status", "error_message", "result_summary", "finished_at", "step_log"])
    return StandardResponse(message="任务已停止")


@router.get(
    "/tasks/{task_id}/stream",
    summary="SSE 订阅任务进度",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def stream_task(
    task_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    task = await BrowserLabTask.get_or_none(id=task_id, project_id=pid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def event_generator():
        last_index = 0
        idle_rounds = 0
        while True:
            fresh = await BrowserLabTask.get_or_none(id=task_id, project_id=pid)
            if not fresh:
                yield f"data: {json.dumps({'type': 'error', 'message': '任务不存在'}, ensure_ascii=False)}\n\n"
                break

            events = fresh.step_log or []
            while last_index < len(events):
                evt = events[last_index]
                last_index += 1
                idle_rounds = 0
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                if evt.get("type") == "done":
                    return

            if fresh.status in ("done", "failed", "stopped"):
                payload = {
                    "type": "done",
                    "status": fresh.status,
                    "summary": fresh.result_summary or "",
                    "tokens_used": fresh.tokens_used,
                    "gif_path": fresh.gif_path,
                    "gif_url": f"/static/{fresh.gif_path}" if fresh.gif_path else None,
                    "error_message": fresh.error_message,
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                return

            idle_rounds += 1
            if idle_rounds > 600:
                yield f"data: {json.dumps({'type': 'error', 'message': '订阅超时'}, ensure_ascii=False)}\n\n"
                break
            await asyncio.sleep(0.6)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/tasks/{task_id}/screenshots/{filename}",
    summary="获取步骤截图",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_screenshot(
    task_id: int,
    filename: str,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    task = await BrowserLabTask.get_or_none(id=task_id, project_id=pid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    path = os.path.join(settings.BROWSER_LAB_DIR, str(task_id), filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="截图不存在")
    return FileResponse(path, media_type="image/jpeg")


@router.get(
    "/tasks/{task_id}/gif",
    summary="获取回放 GIF",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_task_gif(
    task_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    task = await BrowserLabTask.get_or_none(id=task_id, project_id=pid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.gif_path:
        raise HTTPException(status_code=404, detail="该任务未生成 GIF")
    path = os.path.join(settings.STATIC_DIR, task.gif_path)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="GIF 文件不存在")
    return FileResponse(path, media_type="image/gif")


@router.post(
    "/optimize-task-text",
    summary="AI 优化任务描述（browser-use 可执行性）",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def optimize_task_text(
    body: OptimizeTaskTextRequest,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    """将自然语言任务改写为更适合 browser-use Agent 执行的中文描述。"""
    pid = _resolve_project_id(user_info, project_id)
    username = user_info.get("username") or user_info.get("sub") or ""
    try:
        from app.modules.browser_lab.browser_lab_task_optimizer import optimize_browser_lab_task_text

        data = await optimize_browser_lab_task_text(
            task_text=body.task_text,
            start_url=(body.start_url or "").strip(),
            case_name=(body.case_name or "").strip(),
            ai_config_id=body.ai_config_id,
            username=username,
            project_id=pid,
        )
        return StandardResponse(data=data)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex
    except Exception as ex:
        logger.exception("[browser_lab] optimize task text failed")
        raise HTTPException(status_code=500, detail=f"AI 优化失败: {ex}") from ex


class BrowserLabImportUiCaseRequest(BaseModel):
    case_name: str = Field(..., min_length=1, max_length=200)
    catalog_id: Optional[int] = Field(default=None, description="Web 用例目录")
    description: Optional[str] = Field(default=None, max_length=4000)
    include_open_browser: bool = Field(default=True, description="是否插入 open_browser 步骤")
    steps: Optional[list] = Field(default=None, description="可选：前端预览后编辑过的步骤")


@router.get(
    "/tasks/{task_id}/ui-steps-preview",
    summary="预览 Browser Lab 转 Web UI 步骤",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def preview_ui_steps_from_task(
    task_id: int,
    project_id: Optional[int] = Query(None),
    include_open_browser: bool = Query(True),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    task = await BrowserLabTask.get_or_none(id=task_id, project_id=pid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status not in ("done", "failed", "stopped"):
        raise HTTPException(status_code=400, detail="任务尚未结束，无法导入")

    from app.modules.browser_lab.browser_lab_import import convert_browser_lab_to_ui_steps
    from app.routers.ai.generate import _normalize_ui_steps

    raw_steps = convert_browser_lab_to_ui_steps(
        start_url=task.start_url,
        task_text=task.task_text,
        step_log=list(task.step_log or []),
        include_open_browser=include_open_browser,
    )
    steps, errors = _normalize_ui_steps(raw_steps)
    default_name = task.case_name or f"BrowserLab-{task.id}"
    if not default_name.strip():
        default_name = f"BrowserLab-{task.id}"
    return StandardResponse(
        data={
            "task_id": task.id,
            "default_case_name": default_name[:200],
            "start_url": task.start_url,
            "steps": steps,
            "warnings": errors,
            "step_count": len(steps),
        }
    )


@router.post(
    "/tasks/{task_id}/import-ui-case",
    summary="Browser Lab 执行记录导入 Web 用例",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE, UI_CASE_EDIT))],
)
async def import_ui_case_from_task(
    task_id: int,
    body: BrowserLabImportUiCaseRequest,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    task = await BrowserLabTask.get_or_none(id=task_id, project_id=pid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status not in ("done", "failed", "stopped"):
        raise HTTPException(status_code=400, detail="任务尚未结束，无法导入")

    from app.modules.browser_lab.browser_lab_import import (
        convert_browser_lab_to_ui_steps,
        steps_match_browser_lab_import,
    )
    from app.routers.ai.generate import _normalize_ui_steps

    server_steps = convert_browser_lab_to_ui_steps(
        start_url=task.start_url,
        task_text=task.task_text,
        step_log=list(task.step_log or []),
        include_open_browser=body.include_open_browser,
    )
    if body.steps is not None:
        if not steps_match_browser_lab_import(body.steps, server_steps):
            raise HTTPException(
                status_code=422,
                detail="提交步骤须与本任务的服务端转换结果保持相同步骤结构与顺序，不可注入无关步骤",
            )
        raw_steps = body.steps
    else:
        raw_steps = server_steps
    steps, errors = _normalize_ui_steps(raw_steps)
    if not steps:
        raise HTTPException(status_code=422, detail="未能生成有效步骤，请检查 Browser Lab 记录是否包含操作")

    username = user_info.get("username") or user_info.get("sub") or ""
    desc_parts = [
        f"来源：智能浏览器任务 #{task.id}",
        (task.task_text or "")[:500],
    ]
    description = (body.description or "\n".join(p for p in desc_parts if p)).strip()[:4000]

    case = await Case.create(
        name=body.case_name.strip(),
        level="P2",
        project_id=pid,
        steps=steps,
        description=description or None,
        username=username,
        update_by=username,
        is_del=False,
        catalog_id=body.catalog_id,
    )
    return StandardResponse(
        data={
            "case_id": case.id,
            "case_name": case.name,
            "step_count": len(steps),
            "warnings": errors,
        },
        message="已导入 Web 用例，请核对定位器后保存到套件",
    )
