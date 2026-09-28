"""MCP Wave A：Browser Lab / UI Agent 任务闭环（list/get/stop/rerun/convert）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from tortoise.expressions import Q

from app.core.integration.mcp_confirm import consume_confirm_token, create_confirm_token
from app.core.platform.permissions import AI_TEST_EXECUTE, AI_TEST_VIEW
from app.core.platform.project_access import PROJECT_ROLE_MEMBER, PROJECT_ROLE_VIEWER
from app.mcp.auth import McpAuthContext, ensure_permission
from app.models.ai import BrowserLabCase, BrowserLabTask, UiAgentJob
from app.models.sys import Device


def _http_detail(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, str) and detail.strip():
        return detail
    return str(exc)


def _clip(text: Any, limit: int = 400) -> str:
    s = ("" if text is None else str(text)).strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _iso(dt: Any) -> str | None:
    if not dt:
        return None
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)


async def _require_project(ctx: McpAuthContext, project_id: int, *, member: bool = False) -> int:
    from brickcore_assist.skills.access import require_project_access

    return await require_project_access(
        ctx,
        int(project_id),
        min_role=PROJECT_ROLE_MEMBER if member else PROJECT_ROLE_VIEWER,
    )


def _bl_task_summary(task: BrowserLabTask, *, include_steps: bool = False, max_steps: int = 12) -> dict[str, Any]:
    cfg = task.config_json if isinstance(task.config_json, dict) else {}
    out: dict[str, Any] = {
        "id": task.id,
        "project_id": task.project_id,
        "case_id": task.case_id,
        "case_name": task.case_name or "",
        "source_task_id": task.source_task_id,
        "task_text": _clip(task.task_text, 300),
        "start_url": _clip(task.start_url, 300),
        "status": task.status,
        "result_summary": _clip(task.result_summary, 500),
        "error_message": _clip(task.error_message, 500),
        "steps_count": task.steps_count,
        "tokens_used": task.tokens_used,
        "device_id": cfg.get("device_id"),
        "run_mode": cfg.get("run_mode") or "runner",
        "env_id": cfg.get("env_id"),
        "ai_config_id": task.ai_config_id or cfg.get("ai_config_id"),
        "created_by": task.created_by or "",
        "started_at": _iso(task.started_at),
        "finished_at": _iso(task.finished_at),
        "create_time": _iso(task.create_time),
        "report_url": f"/browser-lab/report/{task.id}",
        "is_terminal": (task.status or "") not in ("pending", "running"),
    }
    if include_steps:
        log = task.step_log if isinstance(task.step_log, list) else []
        steps = [e for e in log if isinstance(e, dict) and e.get("type") == "step"]
        slim: list[dict[str, Any]] = []
        for e in steps[: max(1, min(int(max_steps), 40))]:
            slim.append(
                {
                    "step": e.get("step") or e.get("index"),
                    "action": _clip(e.get("action") or e.get("next_goal") or e.get("summary"), 200),
                    "url": _clip(e.get("url"), 200),
                    "success": e.get("success"),
                    "error": _clip(e.get("error") or e.get("error_message"), 200),
                }
            )
        out["key_steps"] = slim
        out["key_steps_truncated"] = len(steps) > len(slim)
        out["step_count"] = len(steps)
        out["success"] = task.status == "done"
    return out


def _bl_case_summary(case: BrowserLabCase) -> dict[str, Any]:
    cfg = case.config_json if isinstance(case.config_json, dict) else {}
    return {
        "id": case.id,
        "project_id": case.project_id,
        "name": case.name,
        "description": _clip(case.description, 300),
        "task_text": _clip(case.task_text, 300),
        "start_url": _clip(case.start_url, 300),
        "tags": case.tags or "",
        "ai_config_id": cfg.get("ai_config_id"),
        "max_steps": cfg.get("max_steps"),
        "env_id": cfg.get("env_id"),
        "device_id": cfg.get("device_id"),
        "run_count": case.run_count,
        "last_status": case.last_status,
        "last_run_at": _iso(case.last_run_at),
        "created_by": case.created_by or "",
        "update_time": _iso(case.update_time),
    }


def _ua_job_summary(job: UiAgentJob, *, include_steps: bool = False, max_steps: int = 12) -> dict[str, Any]:
    from app.modules.ui.ui_agent_job_service import is_job_terminal, job_stop_requested

    steps = job.steps_json if isinstance(job.steps_json, list) else []
    log = job.agent_log_json if isinstance(job.agent_log_json, list) else []
    out: dict[str, Any] = {
        "id": job.id,
        "project_id": job.project_id,
        "status": job.status,
        "source": job.source,
        "run_mode": job.run_mode,
        "device_id": job.device_id,
        "page_url": _clip(job.page_url, 300),
        "description": _clip(job.description, 300),
        "max_steps": job.max_steps,
        "steps_count": len(steps),
        "tokens_used": job.tokens_used,
        "error_message": _clip(job.error_message, 500),
        "ai_config_id": job.ai_config_id,
        "created_by": job.created_by or "",
        "stop_requested": job_stop_requested(job),
        "is_terminal": is_job_terminal(job.status),
        "started_at": _iso(job.started_at),
        "finished_at": _iso(job.finished_at),
        "create_time": _iso(job.create_time),
        "report_url": f"/ui-agent/report/{job.id}",
    }
    if include_steps:
        slim_steps: list[dict[str, Any]] = []
        for s in steps[: max(1, min(int(max_steps), 40))]:
            if not isinstance(s, dict):
                continue
            params = s.get("params") if isinstance(s.get("params"), dict) else {}
            slim_steps.append(
                {
                    "method": s.get("method") or "",
                    "keyword": _clip(s.get("keyword") or s.get("desc"), 120),
                    "locator": _clip(params.get("locator") or params.get("selector"), 160),
                }
            )
        slim_log: list[dict[str, Any]] = []
        for e in log[-8:]:
            if not isinstance(e, dict):
                continue
            slim_log.append(
                {
                    "phase": e.get("phase") or e.get("type") or "",
                    "message": _clip(e.get("message") or e.get("summary"), 200),
                }
            )
        out["key_steps"] = slim_steps
        out["key_steps_truncated"] = len(steps) > len(slim_steps)
        out["recent_log"] = slim_log
        out["success"] = (job.status or "") == "done"
    return out


# ---------- Browser Lab 只读 ----------


async def tool_list_browser_lab_tasks(
    ctx: McpAuthContext,
    project_id: int,
    status: str = "",
    case_id: Optional[int] = None,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目智能浏览器（Browser Lab）执行任务。"""
    ensure_permission(ctx, AI_TEST_VIEW)
    pid = await _require_project(ctx, project_id)
    page = max(int(page or 1), 1)
    size = min(max(int(size or 20), 1), 50)
    qs = BrowserLabTask.filter(project_id=pid)
    st = (status or "").strip()
    if st:
        qs = qs.filter(status=st)
    if case_id:
        qs = qs.filter(case_id=int(case_id))
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(
            Q(task_text__icontains=kw)
            | Q(case_name__icontains=kw)
            | Q(start_url__icontains=kw)
            | Q(created_by__icontains=kw)
        )
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [_bl_task_summary(t) for t in rows],
    }


async def tool_get_browser_lab_task(
    ctx: McpAuthContext,
    project_id: int,
    task_id: int,
) -> dict[str, Any]:
    """获取单个 Browser Lab 任务状态与摘要（不含完整截图/step 明细）。"""
    ensure_permission(ctx, AI_TEST_VIEW)
    pid = await _require_project(ctx, project_id)
    task = await BrowserLabTask.get_or_none(id=int(task_id), project_id=pid)
    if not task:
        raise ValueError("Browser Lab 任务不存在或不属于当前项目")
    from app.modules.browser_lab.browser_lab_heartbeat import maybe_fail_stale_runner_task
    from app.modules.browser_lab.browser_lab_usage import ensure_browser_lab_usage_logged

    task = await maybe_fail_stale_runner_task(task)
    await ensure_browser_lab_usage_logged(task)
    task = await BrowserLabTask.get(id=task.id)
    return _bl_task_summary(task)


async def tool_get_browser_lab_task_report(
    ctx: McpAuthContext,
    project_id: int,
    task_id: int,
    max_steps: int = 12,
) -> dict[str, Any]:
    """获取 Browser Lab 报告摘要：状态、失败原因、关键步骤（截断）。"""
    ensure_permission(ctx, AI_TEST_VIEW)
    pid = await _require_project(ctx, project_id)
    task = await BrowserLabTask.get_or_none(id=int(task_id), project_id=pid)
    if not task:
        raise ValueError("Browser Lab 任务不存在或不属于当前项目")
    from app.modules.browser_lab.browser_lab_heartbeat import maybe_fail_stale_runner_task
    from app.modules.browser_lab.browser_lab_usage import ensure_browser_lab_usage_logged

    task = await maybe_fail_stale_runner_task(task)
    await ensure_browser_lab_usage_logged(task)
    task = await BrowserLabTask.get(id=task.id)
    return _bl_task_summary(task, include_steps=True, max_steps=max_steps)


async def tool_list_browser_lab_cases(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目 Browser Lab 用例库。"""
    ensure_permission(ctx, AI_TEST_VIEW)
    pid = await _require_project(ctx, project_id)
    page = max(int(page or 1), 1)
    size = min(max(int(size or 20), 1), 50)
    qs = BrowserLabCase.filter(project_id=pid, is_del=False)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(
            Q(name__icontains=kw)
            | Q(task_text__icontains=kw)
            | Q(tags__icontains=kw)
            | Q(start_url__icontains=kw)
        )
    total = await qs.count()
    rows = await qs.order_by("-update_time", "-id").offset((page - 1) * size).limit(size)
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [_bl_case_summary(c) for c in rows],
    }


async def tool_get_browser_lab_case(
    ctx: McpAuthContext,
    project_id: int,
    case_id: int,
) -> dict[str, Any]:
    """获取单个 Browser Lab 用例详情。"""
    ensure_permission(ctx, AI_TEST_VIEW)
    pid = await _require_project(ctx, project_id)
    case = await BrowserLabCase.get_or_none(id=int(case_id), project_id=pid, is_del=False)
    if not case:
        raise ValueError("Browser Lab 用例不存在或不属于当前项目")
    return _bl_case_summary(case)


# ---------- Browser Lab 停止 / 重跑 ----------


async def tool_preview_stop_browser_lab_task(
    ctx: McpAuthContext,
    project_id: int,
    task_id: int,
) -> dict[str, Any]:
    """预览停止 Browser Lab 任务；需确认后执行。"""
    ensure_permission(ctx, AI_TEST_EXECUTE)
    pid = await _require_project(ctx, project_id, member=True)
    task = await BrowserLabTask.get_or_none(id=int(task_id), project_id=pid)
    if not task:
        raise ValueError("Browser Lab 任务不存在或不属于当前项目")
    if task.status not in ("pending", "running"):
        raise ValueError(f"任务已结束（status={task.status}），无法停止")
    cfg = task.config_json if isinstance(task.config_json, dict) else {}
    impact = {
        "project_id": pid,
        "task_id": task.id,
        "status": task.status,
        "task_text": _clip(task.task_text, 200),
        "device_id": cfg.get("device_id"),
        "warning": "将向执行机发送停止信令并标记任务为 stopped",
    }
    confirm_token = await create_confirm_token(
        "stop_browser_lab_task",
        {"project_id": pid, "task_id": int(task.id)},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_stop_browser_lab_task 并传入 confirm_token",
    }


async def tool_confirm_stop_browser_lab_task(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    task_id: int,
) -> dict[str, Any]:
    ensure_permission(ctx, AI_TEST_EXECUTE)
    payload = await consume_confirm_token(confirm_token, "stop_browser_lab_task", ctx.username)
    if int(payload.get("project_id") or 0) != int(project_id):
        raise ValueError("project_id 与确认 Token 不匹配")
    if int(payload.get("task_id") or 0) != int(task_id):
        raise ValueError("task_id 与确认 Token 不匹配")
    pid = await _require_project(ctx, int(payload["project_id"]), member=True)
    tid = int(payload["task_id"])
    task = await BrowserLabTask.get_or_none(id=tid, project_id=pid)
    if not task:
        raise ValueError("Browser Lab 任务不存在或不属于当前项目")
    if task.status not in ("pending", "running"):
        return {
            "task_id": task.id,
            "status": task.status,
            "message": "任务已结束，无需停止",
            **_bl_task_summary(task),
        }

    from app.modules.browser_lab.browser_lab_runner import request_stop

    request_stop(tid)
    cfg = task.config_json or {}
    if (cfg.get("run_mode") or "").strip().lower() == "runner" and cfg.get("device_id"):
        from app.modules.browser_lab.browser_lab_dispatch import send_browser_lab_stop

        send_browser_lab_stop(str(cfg.get("device_id")), tid)
    log = list(task.step_log or [])
    if not any(isinstance(e, dict) and e.get("type") == "done" for e in log):
        log.append({"type": "done", "status": "stopped", "summary": "用户已停止（MCP）"})
    task.status = "stopped"
    task.error_message = "用户已停止"
    task.result_summary = "用户已停止"
    task.finished_at = datetime.now(timezone.utc)
    task.step_log = log
    await task.save(
        update_fields=["status", "error_message", "result_summary", "finished_at", "step_log"]
    )
    try:
        from app.modules.browser_lab.browser_lab_usage import ensure_browser_lab_usage_logged

        await ensure_browser_lab_usage_logged(task)
    except Exception:
        pass
    task = await BrowserLabTask.get(id=task.id)
    return {
        "task_id": task.id,
        "status": task.status,
        "message": "任务已停止",
        **_bl_task_summary(task),
    }


async def tool_preview_rerun_browser_lab_task(
    ctx: McpAuthContext,
    project_id: int,
    task_id: int,
    device_id: Optional[str] = None,
    headless: Optional[bool] = None,
) -> dict[str, Any]:
    """预览重跑 Browser Lab 任务；需确认后创建新任务。"""
    ensure_permission(ctx, AI_TEST_EXECUTE)
    pid = await _require_project(ctx, project_id, member=True)
    src = await BrowserLabTask.get_or_none(id=int(task_id), project_id=pid)
    if not src:
        raise ValueError("Browser Lab 任务不存在或不属于当前项目")
    cfg = dict(src.config_json or {})
    device = (device_id or "").strip() or str(cfg.get("device_id") or "").strip()
    if not device:
        raise ValueError("缺少 device_id：请指定在线 Runner，或源任务配置中需有设备")
    device_row = await Device.get_or_none(id=device, is_del=False)
    device_online = bool(device_row and (device_row.status or "") == "在线")
    impact = {
        "project_id": pid,
        "source_task_id": src.id,
        "task_text": _clip(src.task_text, 200),
        "start_url": _clip(src.start_url, 200),
        "device_id": device,
        "device_online": device_online,
        "headless": bool(cfg.get("headless", True) if headless is None else headless),
        "warning": "将基于源任务配置新建一条 Browser Lab 执行记录并派发到 Runner",
    }
    if not device_online:
        impact["warning"] = "指定设备当前不在线，确认后可能启动失败"
    confirm_token = await create_confirm_token(
        "rerun_browser_lab_task",
        {
            "project_id": pid,
            "task_id": int(src.id),
            "device_id": device,
            "headless": None if headless is None else bool(headless),
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_rerun_browser_lab_task 并传入 confirm_token",
    }


async def tool_confirm_rerun_browser_lab_task(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    task_id: int,
    device_id: Optional[str] = None,
    headless: Optional[bool] = None,
) -> dict[str, Any]:
    from fastapi import HTTPException

    ensure_permission(ctx, AI_TEST_EXECUTE)
    payload = await consume_confirm_token(confirm_token, "rerun_browser_lab_task", ctx.username)
    if int(payload.get("project_id") or 0) != int(project_id):
        raise ValueError("project_id 与确认 Token 不匹配")
    if int(payload.get("task_id") or 0) != int(task_id):
        raise ValueError("task_id 与确认 Token 不匹配")
    tok_device = (payload.get("device_id") or "").strip()
    if device_id is not None and (device_id or "").strip() != tok_device:
        raise ValueError("device_id 与确认 Token 不匹配")
    tok_headless = payload.get("headless")
    if headless is not None and tok_headless is not None and bool(tok_headless) != bool(headless):
        raise ValueError("headless 与确认 Token 不匹配")

    pid = await _require_project(ctx, int(payload["project_id"]), member=True)
    src = await BrowserLabTask.get_or_none(id=int(payload["task_id"]), project_id=pid)
    if not src:
        raise ValueError("Browser Lab 任务不存在或不属于当前项目")

    from app.routers.ai.browser_lab import _start_task

    config_json = dict(src.config_json or {})
    if tok_device:
        config_json["device_id"] = tok_device
    if tok_headless is not None:
        config_json["headless"] = bool(tok_headless)
    try:
        task = await _start_task(
            project_id=pid,
            username=ctx.username or "",
            task_text=src.task_text,
            start_url=src.start_url,
            config_json=config_json,
            case_id=src.case_id,
            case_name=src.case_name,
            source_task_id=src.id,
        )
    except HTTPException as exc:
        raise ValueError(_http_detail(exc)) from exc
    return {
        "task_id": task.id,
        "source_task_id": src.id,
        "status": task.status,
        "message": "已重新执行",
        **_bl_task_summary(task),
    }


# ---------- Browser Lab → UI 用例（复用 Skill） ----------


async def tool_preview_convert_browser_lab_to_ui_case(
    ctx: McpAuthContext,
    project_id: int,
    task_id: int,
    case_name: str = "",
    catalog_id: Optional[int] = None,
) -> dict[str, Any]:
    """预览将成功 Browser Lab 任务转为 Web UI 用例（复用 Skill 确认链路）。"""
    from brickcore_assist.skills.browser_lab_to_ui_case import run_browser_lab_to_ui_case

    out = await run_browser_lab_to_ui_case(
        ctx=ctx,
        project_id=int(project_id),
        task_id=int(task_id),
        case_name=case_name or "",
        catalog_id=int(catalog_id) if catalog_id else None,
        entry_source="mcp",
        run_mode="preview",
    )
    if isinstance(out, dict):
        out = dict(out)
        out["next_step"] = (
            "调用 confirm_convert_browser_lab_to_ui_case（或 confirm_run_skill）并传入 confirm_token"
        )
    return out


async def tool_confirm_convert_browser_lab_to_ui_case(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    task_id: int,
) -> dict[str, Any]:
    """确认导入 Web UI 用例（复用 Skill confirm_browser_lab_to_ui_case）。"""
    from brickcore_assist.skills.browser_lab_to_ui_case import confirm_browser_lab_to_ui_case

    return await confirm_browser_lab_to_ui_case(
        ctx=ctx,
        confirm_token=confirm_token,
        project_id=int(project_id),
        task_id=int(task_id),
    )


# ---------- UI Agent ----------


async def tool_list_ui_agent_jobs(
    ctx: McpAuthContext,
    project_id: int,
    status: str = "",
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目 UI Agent 探索任务。"""
    ensure_permission(ctx, AI_TEST_VIEW)
    pid = await _require_project(ctx, project_id)
    page = max(int(page or 1), 1)
    size = min(max(int(size or 20), 1), 50)
    qs = UiAgentJob.filter(project_id=pid)
    st = (status or "").strip()
    if st:
        qs = qs.filter(status=st)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(
            Q(description__icontains=kw)
            | Q(page_url__icontains=kw)
            | Q(created_by__icontains=kw)
        )
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [_ua_job_summary(j) for j in rows],
    }


async def tool_get_ui_agent_job(
    ctx: McpAuthContext,
    project_id: int,
    job_id: int,
) -> dict[str, Any]:
    """获取单个 UI Agent 任务状态与摘要。"""
    ensure_permission(ctx, AI_TEST_VIEW)
    pid = await _require_project(ctx, project_id)
    job = await UiAgentJob.get_or_none(id=int(job_id), project_id=pid)
    if not job:
        raise ValueError("UI Agent 任务不存在或不属于当前项目")
    from app.modules.ui.ui_agent_heartbeat import maybe_fail_stale_runner_job
    from app.modules.ui.ui_agent_usage import ensure_ui_agent_usage_logged

    job = await maybe_fail_stale_runner_job(job)
    await ensure_ui_agent_usage_logged(job)
    job = await UiAgentJob.get(id=job.id)
    return _ua_job_summary(job)


async def tool_get_ui_agent_job_report(
    ctx: McpAuthContext,
    project_id: int,
    job_id: int,
    max_steps: int = 12,
) -> dict[str, Any]:
    """获取 UI Agent 步骤结果摘要（截断）。"""
    ensure_permission(ctx, AI_TEST_VIEW)
    pid = await _require_project(ctx, project_id)
    job = await UiAgentJob.get_or_none(id=int(job_id), project_id=pid)
    if not job:
        raise ValueError("UI Agent 任务不存在或不属于当前项目")
    from app.modules.ui.ui_agent_heartbeat import maybe_fail_stale_runner_job
    from app.modules.ui.ui_agent_usage import ensure_ui_agent_usage_logged

    job = await maybe_fail_stale_runner_job(job)
    await ensure_ui_agent_usage_logged(job)
    job = await UiAgentJob.get(id=job.id)
    return _ua_job_summary(job, include_steps=True, max_steps=max_steps)


async def tool_preview_stop_ui_agent_job(
    ctx: McpAuthContext,
    project_id: int,
    job_id: int,
) -> dict[str, Any]:
    """预览停止 UI Agent 任务；需确认后执行。"""
    ensure_permission(ctx, AI_TEST_EXECUTE)
    pid = await _require_project(ctx, project_id, member=True)
    job = await UiAgentJob.get_or_none(id=int(job_id), project_id=pid)
    if not job:
        raise ValueError("UI Agent 任务不存在或不属于当前项目")
    from app.modules.ui.ui_agent_job_service import is_job_terminal

    if is_job_terminal(job.status):
        raise ValueError(f"任务已结束（status={job.status}），无法停止")
    impact = {
        "project_id": pid,
        "job_id": job.id,
        "status": job.status,
        "description": _clip(job.description, 200),
        "device_id": job.device_id,
        "warning": "将请求执行机停止 UI Agent，并标记 stop_requested",
    }
    confirm_token = await create_confirm_token(
        "stop_ui_agent_job",
        {"project_id": pid, "job_id": int(job.id)},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_stop_ui_agent_job 并传入 confirm_token",
    }


async def tool_confirm_stop_ui_agent_job(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    job_id: int,
) -> dict[str, Any]:
    from fastapi import HTTPException

    ensure_permission(ctx, AI_TEST_EXECUTE)
    payload = await consume_confirm_token(confirm_token, "stop_ui_agent_job", ctx.username)
    if int(payload.get("project_id") or 0) != int(project_id):
        raise ValueError("project_id 与确认 Token 不匹配")
    if int(payload.get("job_id") or 0) != int(job_id):
        raise ValueError("job_id 与确认 Token 不匹配")
    pid = await _require_project(ctx, int(payload["project_id"]), member=True)
    jid = int(payload["job_id"])
    job = await UiAgentJob.get_or_none(id=jid, project_id=pid)
    if not job:
        raise ValueError("UI Agent 任务不存在或不属于当前项目")

    from app.modules.ui.ui_agent_dispatch import send_ui_agent_stop
    from app.modules.ui.ui_agent_job_service import is_job_terminal, request_stop_ui_agent_job

    if is_job_terminal(job.status):
        return {
            "job_id": job.id,
            "status": job.status,
            "message": "任务已结束，无需停止",
            **_ua_job_summary(job),
        }
    if job.run_mode == "runner" and job.device_id:
        send_ui_agent_stop(job.device_id, job.id)
    try:
        job = await request_stop_ui_agent_job(job.id)
    except HTTPException as exc:
        raise ValueError(_http_detail(exc)) from exc
    return {
        "job_id": job.id,
        "status": job.status,
        "message": "已请求停止，等待执行机确认",
        **_ua_job_summary(job),
    }
