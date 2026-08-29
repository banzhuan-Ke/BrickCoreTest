"""智能浏览器（browser-use）API：用例库 + 执行记录 + 报告。"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from tortoise.expressions import Q

from app.core.platform import config as settings
from app.core.platform.auth import is_authenticated, require_permissions
from app.modules.browser_lab.browser_lab_media import (
    enrich_step_log_media,
    is_browser_lab_object_key,
    presign_browser_lab_object,
    resolve_browser_lab_gif_url,
    resolve_browser_lab_screenshot_url,
)
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
    use_action_cache: bool = True
    force_refresh_cache: bool = False
    on_replay_fail: str = Field(default="fallback_agent")
    env_id: Optional[int] = Field(default=None, description="参考环境，用于解析 ${{变量}}")
    run_mode: Optional[str] = Field(default=None, description="已忽略；固定 runner")
    device_id: Optional[str] = Field(default=None, description="Runner 设备 ID（必填）")
    headless: bool = Field(default=True, description="无头模式（默认 true；false 为有头，便于 Runner 本机调试）")


class CreateBrowserLabTaskRequest(BrowserLabRunConfig):
    task_text: str = Field(..., min_length=2, max_length=4000)
    start_url: str = Field(..., min_length=8, max_length=500)
    case_id: Optional[int] = None
    source_task_id: Optional[int] = None


class RerunBrowserLabTaskRequest(BaseModel):
    device_id: Optional[str] = Field(default=None, max_length=100, description="覆盖执行设备")
    headless: Optional[bool] = Field(default=None, description="覆盖浏览器模式")


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
    optimize_mode: Optional[str] = Field(
        default="browser_use",
        description="browser_use（默认）| solidify（Agent 固化目标）",
    )


class PatchCacheActionBody(BaseModel):
    action_index: int = Field(..., ge=0)
    action: dict[str, Any]


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
        "use_action_cache": cfg.get("use_action_cache", True),
        "force_refresh_cache": cfg.get("force_refresh_cache", False),
        "on_replay_fail": cfg.get("on_replay_fail", "fallback_agent"),
        "env_id": cfg.get("env_id"),
        "run_count": case.run_count,
        "last_run_at": case.last_run_at.isoformat() if case.last_run_at else None,
        "last_status": case.last_status,
        "created_by": case.created_by,
        "update_by": case.update_by,
        "create_time": case.create_time.isoformat() if case.create_time else None,
        "update_time": case.update_time.isoformat() if case.update_time else None,
    }


def _task_to_dict(task: BrowserLabTask) -> dict[str, Any]:
    from app.modules.browser_dispatch import pop_internal_platform_base_url
    from app.modules.browser_lab.browser_lab_usage import resolve_browser_lab_tokens

    cfg = pop_internal_platform_base_url(task.config_json or {})
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
        "config_json": cfg,
        "step_log": enrich_step_log_media(task.step_log or []),
        "result_summary": task.result_summary,
        "tokens_used": resolve_browser_lab_tokens(task),
        "steps_count": task.steps_count,
        "gif_path": task.gif_path,
        "gif_url": resolve_browser_lab_gif_url(task.gif_path),
        "error_message": task.error_message,
        "ai_config_id": task.ai_config_id,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "create_time": task.create_time.isoformat() if task.create_time else None,
        "duration_sec": _task_duration_sec(task),
        "cache_status": cfg.get("cache_status"),
        "cache_hit": bool(cfg.get("cache_hit")),
        "cache_entry_id": cfg.get("cache_entry_id"),
        "token_saved_estimate": cfg.get("token_saved_estimate") or 0,
        "use_action_cache": cfg.get("use_action_cache", True),
        "force_refresh_cache": cfg.get("force_refresh_cache", False),
        "on_replay_fail": cfg.get("on_replay_fail", "fallback_agent"),
        "env_id": cfg.get("env_id"),
        "run_mode": cfg.get("run_mode", "local"),
        "device_id": cfg.get("device_id"),
    }


def _task_duration_sec(task: BrowserLabTask) -> Optional[int]:
    if not task.started_at or not task.finished_at:
        return None
    return int((task.finished_at - task.started_at).total_seconds())


def _task_report(task: BrowserLabTask) -> dict[str, Any]:
    base = _task_to_dict(task)
    # steps 须与 step_log 一样走 enrich，否则 MinIO 对象 key 无 screenshot_url，报告页无法展示
    steps = [e for e in (base.get("step_log") or []) if e.get("type") == "step"]
    return {
        **base,
        "steps": steps,
        "step_count": len(steps),
        "success": task.status == "done",
    }


def _normalize_url(url: str) -> str:
    u = url.strip()
    if u.startswith(("http://", "https://")):
        return u
    if "${{" in u or "${" in u:
        return u
    raise HTTPException(status_code=400, detail="起始 URL 须以 http:// 或 https:// 开头，或使用 ${{变量}}")


def _build_config_json(body: BrowserLabRunConfig) -> dict[str, Any]:
    max_steps = min(body.max_steps, settings.BROWSER_LAB_MAX_STEPS_CAP)
    cap = max(0, settings.BROWSER_LAB_MAX_BROWSER_RESTARTS_CAP)
    max_restarts = min(max(0, body.max_browser_restarts), cap)
    if not body.enable_browser_restart:
        max_restarts = 0
    repeat_cap = max(2, settings.BROWSER_LAB_MAX_REPEAT_STEPS_CAP)
    max_repeat = min(max(2, body.max_repeat_steps), repeat_cap)
    on_fail = (body.on_replay_fail or "fallback_agent").strip().lower()
    if on_fail not in ("fail", "fallback_agent"):
        on_fail = "fallback_agent"
    run_mode = "runner"
    device_id = (body.device_id or "").strip() or None
    if not device_id:
        raise HTTPException(status_code=400, detail="请选择在线 Runner 执行设备")
    return {
        "ai_config_id": body.ai_config_id,
        "max_steps": max_steps,
        "use_vision": body.use_vision,
        "generate_gif": body.generate_gif,
        "enable_browser_restart": body.enable_browser_restart,
        "max_browser_restarts": max_restarts,
        "max_repeat_steps": max_repeat,
        "use_action_cache": bool(body.use_action_cache),
        "force_refresh_cache": bool(body.force_refresh_cache),
        "on_replay_fail": on_fail,
        "env_id": int(body.env_id) if body.env_id else None,
        "run_mode": run_mode,
        "device_id": device_id,
        "headless": bool(body.headless),
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
    from app.modules.browser_lab.browser_lab_action_cache import delete_case_cache

    await delete_case_cache(case.id, project_id=case.project_id)
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
    platform_base_url: str | None = None,
) -> BrowserLabTask:
    from app.modules.browser_dispatch import (
        stash_platform_base_url,
        validate_device_online,
    )

    cfg = stash_platform_base_url(config_json, platform_base_url)
    cfg["run_mode"] = "runner"
    if not settings.BROWSER_RUN_DISPATCH_ENABLED:
        raise HTTPException(
            status_code=400,
            detail="Runner 派发未启用（BROWSER_RUN_DISPATCH_ENABLED=0）",
        )
    await validate_device_online(cfg.get("device_id"))
    ensure_browser_lab_dir()
    await _check_daily_quota(project_id)
    await _check_concurrent_limit()

    from app.modules.browser_lab.browser_lab_action_cache import sanitize_run_config

    task = await BrowserLabTask.create(
        project_id=project_id,
        case_id=case_id,
        case_name=case_name,
        source_task_id=source_task_id,
        created_by=username,
        task_text=task_text.strip(),
        start_url=start_url,
        status="pending",
        config_json=sanitize_run_config(cfg),
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
        config_json={**_build_config_json(body.config), "force_refresh_cache": False},
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
    case.config_json = {**_build_config_json(body.config), "force_refresh_cache": False}
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
    request: Request,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.browser_dispatch import request_base_url

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
        platform_base_url=request_base_url(request),
    )
    return StandardResponse(data=_task_to_dict(task), message="用例已开始执行")


# ---------- 执行任务 ----------


@router.get(
    "/run-defaults",
    summary="浏览器 Agent 运行位置默认配置",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def browser_run_defaults():
    from app.modules.browser_dispatch import get_browser_run_defaults

    return StandardResponse(data=get_browser_run_defaults())


@router.post("/tasks", summary="创建并启动任务", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def create_task(
    body: CreateBrowserLabTaskRequest,
    request: Request,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.browser_dispatch import request_base_url

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
        platform_base_url=request_base_url(request),
    )
    return StandardResponse(data=_task_to_dict(task), message="任务已创建，正在启动浏览器 Agent")


@router.post("/tasks/{task_id}/rerun", summary="重复执行", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def rerun_task(
    task_id: int,
    request: Request,
    body: RerunBrowserLabTaskRequest = RerunBrowserLabTaskRequest(),
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.browser_dispatch import request_base_url

    pid = _resolve_project_id(user_info, project_id)
    src = await BrowserLabTask.get_or_none(id=task_id, project_id=pid)
    if not src:
        raise HTTPException(status_code=404, detail="任务不存在")
    username = user_info.get("username") or user_info.get("sub") or ""
    config_json = dict(src.config_json or {})
    if body.device_id:
        config_json["device_id"] = body.device_id.strip()
    if body.headless is not None:
        config_json["headless"] = bool(body.headless)
    task = await _start_task(
        project_id=pid,
        username=username,
        task_text=src.task_text,
        start_url=src.start_url,
        config_json=config_json,
        case_id=src.case_id,
        case_name=src.case_name,
        source_task_id=src.id,
        platform_base_url=request_base_url(request),
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
    from app.modules.browser_lab.browser_lab_heartbeat import maybe_fail_stale_runner_task

    task = await maybe_fail_stale_runner_task(task)
    from app.modules.browser_lab.browser_lab_usage import ensure_browser_lab_usage_logged

    await ensure_browser_lab_usage_logged(task)
    task = await BrowserLabTask.get(id=task.id)
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
    from app.modules.browser_lab.browser_lab_heartbeat import maybe_fail_stale_runner_task

    task = await maybe_fail_stale_runner_task(task)
    from app.modules.browser_lab.browser_lab_usage import ensure_browser_lab_usage_logged

    await ensure_browser_lab_usage_logged(task)
    task = await BrowserLabTask.get(id=task.id)
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
    cfg = task.config_json or {}
    if (cfg.get("run_mode") or "").strip().lower() == "runner" and cfg.get("device_id"):
        from app.modules.browser_lab.browser_lab_dispatch import send_browser_lab_stop

        send_browser_lab_stop(str(cfg.get("device_id")), task_id)
    log = list(task.step_log or [])
    if not any(e.get("type") == "done" for e in log):
        log.append({"type": "done", "status": "stopped", "summary": "用户已停止"})
    task.status = "stopped"
    task.error_message = "用户已停止"
    task.result_summary = "用户已停止"
    task.finished_at = datetime.now(timezone.utc)
    task.step_log = log
    await task.save(update_fields=["status", "error_message", "result_summary", "finished_at", "step_log"])
    from app.modules.browser_lab.browser_lab_usage import ensure_browser_lab_usage_logged

    await ensure_browser_lab_usage_logged(task)
    return StandardResponse(message="任务已停止")


@router.post(
    "/tasks/{task_id}/runner-callback",
    summary="Runner 上报 Browser Lab 事件",
    include_in_schema=False,
)
async def browser_lab_runner_callback(
    task_id: int,
    body: BrowserLabRunnerCallbackBody,
    authorization: Optional[str] = Header(None),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
):
    token = _extract_browser_lab_job_token(authorization, x_internal_token)
    task = await BrowserLabTask.get_or_none(id=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    _verify_browser_lab_job_token(task_id, token, project_id=task.project_id)
    from app.modules.browser_lab.browser_lab_callback import handle_browser_lab_runner_callback

    updated = await handle_browser_lab_runner_callback(task, body.event, body.payload)
    return StandardResponse(data=_task_to_dict(updated))


@router.post(
    "/tasks/{task_id}/llm/v1/chat/completions",
    summary="Browser Lab Runner LLM 代理",
    include_in_schema=False,
)
async def browser_lab_llm_proxy(
    task_id: int,
    request: Request,
    authorization: Optional[str] = Header(None),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
):
    """Runner browser-use 经平台转发 LLM，密钥不落执行机。"""
    token = _extract_browser_lab_job_token(authorization, x_internal_token)
    task = await BrowserLabTask.get_or_none(id=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    _verify_browser_lab_job_token(task_id, token, project_id=task.project_id)

    from app.modules.ai.ai_scene_config import get_scene_llm_overrides, resolve_config_for_scene
    from app.modules.ai.browser_use_llm import build_deepseek_thinking_options, needs_openai_compat_for_browser_use
    from app.core.platform.encryption import decrypt_value
    from openai import AsyncOpenAI

    cfg = task.config_json or {}
    ai_config_id = cfg.get("ai_config_id") or task.ai_config_id
    config = await resolve_config_for_scene("browser_lab", ai_config_id)
    scene_overrides = await get_scene_llm_overrides("browser_lab")
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="无效请求体")

    api_key = decrypt_value(config.api_key)
    base_url = (config.api_base or "").strip() or None
    llm_timeout = max(120, int(scene_overrides.get("timeout") or config.timeout or 180))

    extra_body, reasoning_effort = build_deepseek_thinking_options(config)
    create_kwargs = dict(body)
    if extra_body:
        merged = dict(extra_body)
        merged.update(create_kwargs.pop("extra_body", None) or {})
        create_kwargs["extra_body"] = merged
    if reasoning_effort:
        create_kwargs["reasoning_effort"] = reasoning_effort
    if needs_openai_compat_for_browser_use(config):
        create_kwargs.pop("tool_choice", None)

    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=float(llm_timeout))
    try:
        response = await client.chat.completions.create(**create_kwargs)
    except Exception as exc:
        logger.warning("[browser_lab] llm proxy failed task %s: %s", task_id, exc)
        raise HTTPException(status_code=502, detail=f"LLM 转发失败: {exc}") from exc

    usage = getattr(response, "usage", None)
    if usage is not None:
        from app.modules.browser_lab.browser_lab_usage import accumulate_browser_lab_llm_tokens

        try:
            await accumulate_browser_lab_llm_tokens(task, usage)
        except Exception as exc:
            logger.warning("[browser_lab] llm token accumulate failed task=%s: %s", task_id, exc)

    return response.model_dump()


@router.get(
    "/tasks/{task_id}/stream",
    summary="SSE 订阅任务进度（已废弃，请用 GET /tasks/{id} 轮询）",
    include_in_schema=False,
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
            from app.modules.browser_lab.browser_lab_heartbeat import maybe_fail_stale_runner_task

            fresh = await BrowserLabTask.get_or_none(id=task_id, project_id=pid)
            if not fresh:
                yield f"data: {json.dumps({'type': 'error', 'message': '任务不存在'}, ensure_ascii=False)}\n\n"
                break

            fresh = await maybe_fail_stale_runner_task(fresh)

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
                    "gif_url": resolve_browser_lab_gif_url(fresh.gif_path),
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
    raw = (filename or "").strip().lstrip("/")
    if ".." in raw:
        raise HTTPException(status_code=400, detail="非法文件名")
    if is_browser_lab_object_key(raw):
        signed = presign_browser_lab_object(raw)
        if signed:
            return RedirectResponse(url=signed, status_code=307)
        raise HTTPException(status_code=404, detail="截图不存在")
    if "/" in raw or "\\" in raw:
        raise HTTPException(status_code=400, detail="非法文件名")
    path = os.path.join(settings.BROWSER_LAB_DIR, str(task_id), raw)
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
    if is_browser_lab_object_key(task.gif_path):
        signed = presign_browser_lab_object(task.gif_path)
        if signed:
            return RedirectResponse(url=signed, status_code=307)
        raise HTTPException(status_code=404, detail="GIF 文件不存在")
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
            optimize_mode=(body.optimize_mode or "browser_use").strip(),
        )
        return StandardResponse(data=data)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex
    except Exception as ex:
        logger.exception("[browser_lab] optimize task text failed")
        raise HTTPException(status_code=500, detail=f"AI 优化失败: {ex}") from ex


async def _ui_steps_from_browser_lab_task(
    task: BrowserLabTask,
    *,
    include_open_browser: bool,
    steps_source: str = "auto",
) -> list[dict]:
    """缓存命中任务用缓存动作转步骤；其余走 step_log。steps_source: auto|cache|steps。"""
    from app.models.ai import BrowserLabActionCache
    from app.modules.browser_lab.browser_lab_import import (
        convert_browser_lab_to_ui_steps,
        convert_cache_actions_to_ui_steps,
    )
    from app.modules.browser_lab.browser_lab_import_candidates import enrich_ui_steps_with_candidates

    cfg = task.config_json or {}
    cache_id = cfg.get("cache_entry_id")
    cache_row = None
    cache_actions = None
    if cache_id:
        cache_row = await BrowserLabActionCache.get_or_none(id=int(cache_id), project_id=task.project_id)
        if cache_row and isinstance(cache_row.actions_json, list) and cache_row.actions_json:
            cache_actions = cache_row.actions_json

    source = (steps_source or "auto").strip().lower()
    if source == "cache" and cache_actions:
        steps = convert_cache_actions_to_ui_steps(
            start_url=task.start_url,
            task_text=task.task_text,
            actions=cache_actions,
            include_open_browser=include_open_browser,
        )
    elif source == "steps" or not cache_actions:
        steps = convert_browser_lab_to_ui_steps(
            start_url=task.start_url,
            task_text=task.task_text,
            step_log=list(task.step_log or []),
            include_open_browser=include_open_browser,
        )
    elif (task.engine == "action_cache" or cfg.get("cache_hit")) and cache_actions:
        steps = convert_cache_actions_to_ui_steps(
            start_url=task.start_url,
            task_text=task.task_text,
            actions=cache_actions,
            include_open_browser=include_open_browser,
        )
    else:
        steps = convert_browser_lab_to_ui_steps(
            start_url=task.start_url,
            task_text=task.task_text,
            step_log=list(task.step_log or []),
            include_open_browser=include_open_browser,
        )
    return enrich_ui_steps_with_candidates(steps)


class BrowserLabImportUiCaseRequest(BaseModel):
    case_name: str = Field(..., min_length=1, max_length=200)
    catalog_id: Optional[int] = Field(default=None, description="Web 用例目录")
    description: Optional[str] = Field(default=None, max_length=4000)
    include_open_browser: bool = Field(default=True, description="是否插入 open_browser 步骤")
    steps_source: Optional[str] = Field(default="auto", description="auto|cache|steps，与预览一致")
    steps: Optional[list] = Field(default=None, description="可选：前端预览后编辑过的步骤")
    solidify_job_id: Optional[int] = Field(
        default=None,
        description="Agent 固化 job ID；提供时跳过 W-2 草稿校验",
    )


class BrowserLabSolidifyRequest(BaseModel):
    run_mode: Optional[str] = Field(default=None, description="已忽略；固定 runner")
    device_id: Optional[str] = Field(default=None, max_length=100)
    ai_config_id: Optional[int] = Field(default=None)
    max_steps: int = Field(default=15, ge=3, le=30)
    case_name: Optional[str] = Field(default=None, max_length=200)
    include_open_browser: bool = Field(default=True)
    headless: bool = Field(default=True, description="无头模式（false 为有头调试）")
    agent_goal_text: Optional[str] = Field(
        default=None,
        max_length=4000,
        description="可选：覆盖 Agent 固化目标描述（如经 AI 优化后的文本）",
    )


class BrowserLabRunnerCallbackBody(BaseModel):
    event: str = Field(..., min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


def _extract_browser_lab_job_token(
    authorization: Optional[str] = None,
    x_internal_token: Optional[str] = None,
) -> str:
    token = (x_internal_token or "").strip()
    if not token and authorization:
        auth = authorization.strip()
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        else:
            token = auth
    if not token:
        raise HTTPException(status_code=401, detail="缺少任务鉴权 token")
    return token


def _verify_browser_lab_job_token(task_id: int, token: str, *, project_id: int) -> dict[str, Any]:
    from app.modules.browser_dispatch import verify_internal_job_token

    data = verify_internal_job_token(token, expected_project_id=project_id)
    if str(data.get("job_id")) != str(task_id):
        raise HTTPException(status_code=403, detail="任务 token 与任务 ID 不匹配")
    return data


@router.get(
    "/tasks/{task_id}/ui-steps-preview",
    summary="预览 Browser Lab 转 Web UI 步骤",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def preview_ui_steps_from_task(
    task_id: int,
    project_id: Optional[int] = Query(None),
    include_open_browser: bool = Query(True),
    steps_source: str = Query("auto", description="auto|cache|steps"),
    user_info: dict = Depends(is_authenticated),
):
    pid = _resolve_project_id(user_info, project_id)
    task = await BrowserLabTask.get_or_none(id=task_id, project_id=pid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status not in ("done", "failed", "stopped"):
        raise HTTPException(status_code=400, detail="任务尚未结束，无法导入")

    from app.models.ai import BrowserLabActionCache
    from app.modules.browser_lab.browser_lab_import_plan import build_browser_lab_import_plan
    from app.routers.ai.generate import _normalize_ui_steps

    cfg = dict(task.config_json or {})
    cache_actions = None
    cache_id = cfg.get("cache_entry_id")
    if cache_id:
        row = await BrowserLabActionCache.get_or_none(id=int(cache_id), project_id=pid)
        if row and isinstance(row.actions_json, list):
            cache_actions = row.actions_json

    raw_steps = await _ui_steps_from_browser_lab_task(
        task,
        include_open_browser=include_open_browser,
        steps_source=steps_source,
    )
    steps, errors = _normalize_ui_steps(raw_steps)
    import_meta = build_browser_lab_import_plan(
        task_status=task.status,
        steps=steps,
        cache_actions=cache_actions,
        cache_hit=bool(cfg.get("cache_hit")),
        engine=task.engine or "",
    )
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
            "steps_source": (steps_source or "auto").strip().lower(),
            "cache_available": bool(cache_actions),
            "cache_entry_id": cache_id,
            "task_device_id": cfg.get("device_id"),
            "task_headless": cfg.get("headless", True),
            **import_meta,
        }
    )


@router.post(
    "/tasks/{task_id}/solidify-ui-case",
    summary="Browser Lab Agent 重新固化（创建 ui_agent_job）",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE, UI_CASE_EDIT))],
)
async def solidify_ui_case_from_task(
    task_id: int,
    body: BrowserLabSolidifyRequest,
    request: Request,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    """用任务 URL + 描述启动 Agent 探索；进度通过 GET ui-agent-jobs 轮询，不用 SSE。"""
    from app.modules.browser_dispatch import merge_job_platform_base_url, request_base_url

    pid = _resolve_project_id(user_info, project_id)
    task = await BrowserLabTask.get_or_none(id=task_id, project_id=pid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status not in ("done", "failed", "stopped"):
        raise HTTPException(status_code=400, detail="任务尚未结束，无法固化")

    from app.core.platform import config as settings
    from app.modules.browser_dispatch import merge_job_platform_base_url, validate_device_online
    from app.modules.browser_lab.browser_lab_solidify import build_solidify_description
    from app.modules.ui.ui_agent_dispatch import dispatch_ui_agent_to_runner
    from app.modules.ui.ui_agent_job_service import create_ui_agent_job, job_to_dict
    from app.routers.ai.generate import _check_agent_daily_quota, _get_ai_config

    await _check_agent_daily_quota(pid)
    config = await _get_ai_config(body.ai_config_id, scene="ui_case_agent")
    description = await build_solidify_description(
        task,
        goal_text_override=(body.agent_goal_text or "").strip() or None,
    )
    if not settings.BROWSER_RUN_DISPATCH_ENABLED:
        raise HTTPException(status_code=400, detail="Runner 派发未启用")
    await validate_device_online(body.device_id)

    default_name = task.case_name or f"BrowserLab-{task.id}"
    case_name = (body.case_name or default_name).strip()[:200]

    job = await create_ui_agent_job(
        project_id=pid,
        page_url=task.start_url.strip(),
        description=description,
        max_steps=body.max_steps,
        ai_config_id=config.id,
        created_by=user_info.get("username") or user_info.get("sub") or "",
        run_mode="runner",
        device_id=(body.device_id or "").strip() or None,
        source="browser_lab_import",
        source_ref=merge_job_platform_base_url(
            {
                "browser_lab_task_id": task.id,
                "case_name": case_name,
                "include_open_browser": body.include_open_browser,
                "headless": bool(body.headless),
            },
            request_base_url(request),
        ),
    )

    try:
        await dispatch_ui_agent_to_runner(job, config=config)
    except HTTPException:
        await job.delete()
        raise
    except Exception as exc:
        await job.delete()
        raise HTTPException(status_code=500, detail=f"启动 Agent 固化失败: {exc}") from exc

    return StandardResponse(
        data={
            "async": True,
            "job_id": job.id,
            "run_mode": "runner",
            "device_id": job.device_id,
            "poll_path": f"/ai/ui-agent-jobs/{job.id}",
            "job": job_to_dict(job),
        },
        message="Agent 固化任务已启动，请轮询查询进度",
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
        steps_match_browser_lab_import,
    )
    from app.routers.ai.generate import _normalize_ui_steps
    from app.models.ai import UiAgentJob

    username = user_info.get("username") or user_info.get("sub") or ""

    if body.solidify_job_id:
        job = await UiAgentJob.get_or_none(id=body.solidify_job_id, project_id=pid)
        if not job:
            raise HTTPException(status_code=404, detail="固化任务不存在")
        if job.source != "browser_lab_import":
            raise HTTPException(status_code=422, detail="非 Browser Lab 固化任务")
        ref = job.source_ref or {}
        if int(ref.get("browser_lab_task_id") or 0) != task_id:
            raise HTTPException(status_code=422, detail="固化任务与当前 Browser Lab 记录不匹配")
        if job.status not in ("done", "stopped", "failed"):
            raise HTTPException(status_code=400, detail="Agent 固化尚未完成")
        job_steps = list(job.steps_json or [])
        if job.status == "failed" and not job_steps:
            raise HTTPException(
                status_code=400,
                detail=job.error_message or "Agent 固化失败且无步骤",
            )
        if body.steps is not None:
            from app.modules.ui.ui_agent_job_service import steps_match_agent_job

            if not steps_match_agent_job(body.steps, job_steps):
                raise HTTPException(
                    status_code=422,
                    detail="提交步骤须与 Agent 固化任务产出一致（method/locator/语义参数不可篡改）",
                )
            raw_steps = body.steps
        else:
            raw_steps = job_steps
        steps, errors = _normalize_ui_steps(raw_steps)
    else:
        server_steps = await _ui_steps_from_browser_lab_task(
            task,
            include_open_browser=body.include_open_browser,
            steps_source=(body.steps_source or "auto"),
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

    desc_parts = [
        f"来源：智能浏览器任务 #{task.id}",
        (task.task_text or "")[:500],
    ]
    if body.solidify_job_id:
        desc_parts.insert(0, f"Agent 固化 job #{body.solidify_job_id}")
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
            "solidify_job_id": body.solidify_job_id,
        },
        message="已导入 Web 用例，请核对定位器后保存到套件",
    )


# ---------- BL-1 动作缓存 ----------


@router.get(
    "/cases/{case_id}/action-cache",
    summary="查看用例动作缓存",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def get_case_action_cache(
    case_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.models.ai import BrowserLabActionCache
    from app.modules.browser_lab.browser_lab_action_cache import cache_row_to_summary

    pid = _resolve_project_id(user_info, project_id)
    case = await BrowserLabCase.get_or_none(id=case_id, project_id=pid, is_del=False)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    rows = await BrowserLabActionCache.filter(project_id=pid, case_id=case_id).order_by("-updated_at")
    return StandardResponse(
        data={
            "case_id": case_id,
            "list": [cache_row_to_summary(r, include_actions=True) for r in rows],
            "total": len(rows),
        }
    )


@router.delete(
    "/cases/{case_id}/action-cache",
    summary="清除用例动作缓存",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def clear_case_action_cache(
    case_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.browser_lab.browser_lab_action_cache import delete_case_cache

    pid = _resolve_project_id(user_info, project_id)
    case = await BrowserLabCase.get_or_none(id=case_id, project_id=pid, is_del=False)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    deleted = await delete_case_cache(case_id, project_id=pid)
    return StandardResponse(data={"deleted": deleted}, message=f"已清除 {deleted} 条动作缓存")


@router.get(
    "/action-cache/stats",
    summary="项目动作缓存命中统计",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def action_cache_stats(
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.browser_lab.browser_lab_action_cache import project_cache_stats

    pid = _resolve_project_id(user_info, project_id)
    return StandardResponse(data=await project_cache_stats(pid))


@router.patch(
    "/action-cache/{cache_id}/actions",
    summary="修补缓存单步动作",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def patch_action_cache_action(
    cache_id: int,
    body: PatchCacheActionBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    from app.models.ai import BrowserLabActionCache
    from app.modules.browser_lab.browser_lab_action_cache import cache_row_to_summary

    pid = _resolve_project_id(user_info, project_id)
    row = await BrowserLabActionCache.get_or_none(id=cache_id, project_id=pid)
    if not row:
        raise HTTPException(status_code=404, detail="缓存不存在")
    actions = list(row.actions_json or [])
    if body.action_index >= len(actions):
        raise HTTPException(status_code=400, detail="action_index 越界")
    if not isinstance(body.action, dict) or not body.action.get("op"):
        raise HTTPException(status_code=400, detail="action 须包含 op")
    from app.modules.browser_lab.browser_lab_action_cache_core import normalize_patch_action

    try:
        actions[body.action_index] = normalize_patch_action(body.action)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex
    row.actions_json = actions
    row.status = "ready"
    await row.save(update_fields=["actions_json", "status", "updated_at"])
    return StandardResponse(data=cache_row_to_summary(row, include_actions=True), message="已更新缓存动作")


@router.post(
    "/tasks/{task_id}/promote-cache",
    summary="将任务关联缓存升格为 Web 用例（复用导入）",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE, UI_CASE_EDIT))],
)
async def promote_cache_to_ui_case(
    task_id: int,
    body: BrowserLabImportUiCaseRequest,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    """缓存命中任务也可升格；底层仍走 step_log → UI steps 转换与校验。"""
    return await import_ui_case_from_task(task_id, body, project_id, user_info)

