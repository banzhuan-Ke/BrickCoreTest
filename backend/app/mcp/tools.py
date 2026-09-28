"""BrickCore MCP 工具实现"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from tortoise.expressions import Q

from app.core.integration.mcp_confirm import consume_confirm_token, create_confirm_token
from app.core.shared.report_summary_context import fetch_recent_failures
from app.mcp.auth import McpAuthContext, ensure_permission, ensure_any_permission
from app.core.platform.permissions import (
    AI_TEST_EXECUTE,
    AI_TEST_VIEW,
    DATA_FACTORY_VIEW,
    API_CASE_EXECUTE,
    API_CASE_VIEW,
    API_CRON_VIEW,
    API_MOCK_VIEW,
    API_PLAN_EDIT,
    API_PLAN_VIEW,
    API_RECORD_VIEW,
    PERF_CRON_VIEW,
    PERF_RECORD_VIEW,
    PERF_SCENE_EXECUTE,
    PERF_SCENE_VIEW,
    PERF_WORKER_VIEW,
    PROJECT_VIEW,
    UI_CRON_VIEW,
    UI_CASE_EDIT,
    UI_CASE_EXECUTE,
    UI_RECORD_VIEW,
    UI_SUITE_EXECUTE,
    UI_SUITE_VIEW,
    UI_TASK_EXECUTE,
    APP_CASE_VIEW,
    APP_CASE_EXECUTE,
    APP_SUITE_VIEW,
    APP_SUITE_EXECUTE,
    APP_PLAN_VIEW,
    APP_PLAN_EXECUTE,
    APP_RECORD_VIEW,
)
from app.models.ai import (
    AiFunctionalCase,
    AiRequirement,
    AiRequirementCase,
    AiRequirementGenerateJob,
)
from app.models.http import (
    ApiCronJob,
    ApiDefinition,
    ApiPlanItem,
    ApiPlanRunRecord,
    ApiRunRecord,
    ApiSuiteCase,
    ApiSuiteRunRecord,
    ApiTestCase,
    ApiTestPlan,
    ApiTestSuite,
    MockApi,
    EnvDatasource,
    SqlTemplate,
)
from app.models.perf import PerfCronJob, PerfRecord, PerfScene, PerfWorker
from app.models.schedule import Cronjob
from app.models.sys import Device, Environment, TestCatalog, Project
from app.models.ui import Case, Step, Suite, Task, UiCaseExecution, UiPlanExecution
from app.models.app import (
    AppCase,
    AppCaseExecution,
    AppCronJob,
    AppPlan,
    AppPlanExecution,
    AppSuite,
    AppSuiteExecution,
    AppSuiteStep,
)
from app.schemas.app import AppRunForm
from app.routers.ai.analyze import _execute_failure_analysis
from app.modules.ai.functional_case_service import functional_case_to_dict
from app.core.db.db_factory_service import datasource_to_dict, sql_template_to_dict
from app.routers.ai.requirements import (
    GenerateCasesBatchRequest,
    GenerateCasesBatchItem,
    _create_generate_job,
    _job_to_dict,
    _requirement_to_dict,
)
from app.routers.http.exec import ApiSuiteRunRequest, run_suite_async
from app.routers.http.plan import run_plan_async
from app.routers.http.suites import run_data_driven_case, run_single_case
from app.routers.perf.exec import run_perf_scene
from app.routers.ui.exec import run_case as run_ui_case, run_suite as run_ui_suite
from app.schemas.http import ApiPlanRunRequest
from app.schemas.ui import RunForm as UiRunForm


class _AsyncBackgroundTasks:
    """兼容 FastAPI BackgroundTasks 的最小实现"""

    def add_task(self, fn, *args, **kwargs):
        asyncio.create_task(fn(*args, **kwargs))


ASSISTANT_TRIGGER = "assistant"
_TRIGGER_LABELS = {"manual": "手动", "assistant": "小测", "cron": "定时任务", "plan": "计划执行"}


def _ui_trigger_meta(env: Any) -> dict[str, str]:
    data = env if isinstance(env, dict) else {}
    ts = (data.get("trigger_source") or "manual").strip()
    return {
        "trigger_source": ts,
        "trigger_source_label": _TRIGGER_LABELS.get(ts, ts),
    }


def _user_info(ctx: McpAuthContext) -> dict:
    """构造可供路由层 assert_project_access 使用的 user_info。

    MCP/助手直调 FastAPI 路由时必须显式传入，否则默认的 Depends(...) 不会被解析，
    会在 user_info.get(...) 处报 ``'Depends' object has no attribute 'get'``。
    """
    return {
        "id": ctx.user_id,
        "username": ctx.username,
        "is_superuser": bool(ctx.is_superuser or ctx.is_api_key),
        "is_api_key": bool(ctx.is_api_key),
    }


async def _require_project_member(
    ctx: McpAuthContext,
    project_id: int | None,
    *,
    min_role: str | None = None,
) -> int:
    """执行类 preview/confirm 统一要求项目成员（默认 MEMBER）。"""
    from app.core.platform.project_access import PROJECT_ROLE_MEMBER
    from brickcore_assist.skills.access import require_project_access

    return await require_project_access(
        ctx, project_id, min_role=min_role or PROJECT_ROLE_MEMBER
    )


async def _await_route(coro):
    """直调带 Depends 的路由函数；将 HTTPException 转为 ValueError 便于 MCP/助手展示。"""
    from fastapi import HTTPException

    try:
        return await coro
    except HTTPException as exc:
        detail = exc.detail
        raise ValueError(detail if isinstance(detail, str) else str(detail)) from exc


def _build_generate_batches(req: AiRequirement, batch_count: int) -> list[GenerateCasesBatchItem]:
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    sections = meta.get("sections") or []
    section_ids = [str(s.get("id")) for s in sections if s.get("id")]
    if not section_ids:
        section_ids = ["all"]
    return [
        GenerateCasesBatchItem(
            name="MCP 批量生成",
            scope_section_ids=section_ids[:20],
            count=batch_count,
        )
    ]


async def tool_list_projects(ctx: McpAuthContext, page: int = 1, size: int = 20) -> dict[str, Any]:
    """列出当前身份可访问的项目（普通用户按项目成员过滤；API Key/超管不限制）。"""
    ensure_permission(ctx, PROJECT_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 100)
    from app.core.platform.project_access import get_accessible_project_ids

    qs = Project.filter(is_del=False)
    accessible = await get_accessible_project_ids(
        int(ctx.user_id or 0),
        is_superuser=bool(ctx.is_superuser or ctx.is_api_key),
    )
    if accessible is not None:
        if not accessible:
            return {"total": 0, "items": [], "scoped": True}
        qs = qs.filter(id__in=accessible)
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    return {
        "total": total,
        "items": [{"id": p.id, "name": p.name, "username": p.username} for p in rows],
        "scoped": accessible is not None,
    }


async def tool_get_project(ctx: McpAuthContext, project_id: int) -> dict[str, Any]:
    ensure_permission(ctx, PROJECT_VIEW)
    from app.core.platform.project_access import PROJECT_ROLE_VIEWER

    await _require_project_member(ctx, project_id, min_role=PROJECT_ROLE_VIEWER)
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise ValueError("项目不存在")
    return {"id": project.id, "name": project.name, "username": project.username}


async def tool_get_project_overview(
    ctx: McpAuthContext,
    project_id: int,
    requirement_limit: int = 10,
    include_failures: bool = True,
) -> dict[str, Any]:
    """一次返回项目、环境、模块、需求摘要、用例库规模与最近失败（供外部 AI 做项目全貌总结）。"""
    ensure_permission(ctx, PROJECT_VIEW)
    from app.core.platform.project_access import PROJECT_ROLE_VIEWER

    await _require_project_member(ctx, project_id, min_role=PROJECT_ROLE_VIEWER)
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise ValueError("项目不存在")

    env_rows = await Environment.filter(project_id=project_id, is_del=False).order_by("-id")
    catalog_rows = await TestCatalog.filter(project_id=project_id, is_del=False).order_by("sort", "-id")

    requirements_block: dict[str, Any] = {"total": 0, "items": []}
    functional_case_total = 0
    try:
        ensure_permission(ctx, AI_TEST_VIEW)
        requirement_limit = min(max(requirement_limit, 1), 50)
        req_qs = AiRequirement.filter(project_id=project_id, is_del=False).order_by("-id")
        req_total = await req_qs.count()
        req_rows = await req_qs.limit(requirement_limit)
        req_ids = [r.id for r in req_rows]
        case_counts = await _requirement_case_counts(req_ids)
        req_items = []
        for r in req_rows:
            meta = r.parsed_content if isinstance(r.parsed_content, dict) else {}
            sections = meta.get("sections") or []
            item = {
                "id": r.id,
                "name": r.name,
                "parse_status": r.parse_status,
                "file_name": meta.get("file_name", ""),
                "text_length": len(r.original_content or ""),
                "page_count": meta.get("page_count", 0),
                "image_count": meta.get("image_count", 0),
                "section_count": len(sections),
                "section_titles": [
                    (s.get("title") or s.get("name") or "").strip()
                    for s in sections[:20]
                    if isinstance(s, dict) and (s.get("title") or s.get("name"))
                ],
                "case_count": case_counts.get(r.id, 0),
                "last_generate": _summarize_last_generate(meta),
                "update_time": r.update_time.strftime("%Y-%m-%d %H:%M:%S") if r.update_time else "",
            }
            req_items.append(item)
        requirements_block = {"total": req_total, "items": req_items}
        functional_case_total = await AiFunctionalCase.filter(
            project_id=project_id, is_del=False
        ).count()
    except ValueError:
        pass

    failures_block: dict[str, Any] = {"total": 0, "items": []}
    if include_failures:
        try:
            failures = await fetch_recent_failures(project_id, limit=5)
            failures_block = {"total": len(failures), "items": failures}
        except Exception:
            failures_block = {"total": 0, "items": [], "note": "无权限或暂无失败记录"}

    return {
        "project": {"id": project.id, "name": project.name, "username": project.username},
        "environments": [
            {"id": e.id, "name": e.name, "host": e.host}
            for e in env_rows
        ],
        "catalogs": [_catalog_to_dict(c) for c in catalog_rows],
        "modules": [_catalog_to_dict(c) for c in catalog_rows],
        "requirements": requirements_block,
        "functional_case_total": functional_case_total,
        "recent_failures": failures_block,
        "hint": "需求正文与用例步骤请用 get_requirement / list_requirement_cases 进一步查询",
    }


async def tool_list_environments(ctx: McpAuthContext, project_id: int) -> dict[str, Any]:
    ensure_permission(ctx, PROJECT_VIEW)
    rows = await Environment.filter(project_id=project_id, is_del=False).order_by("-id")
    return {
        "items": [
            {"id": e.id, "name": e.name, "host": e.host, "project_id": e.project_id}
            for e in rows
        ]
    }


async def tool_list_online_devices(
    ctx: McpAuthContext,
    project_id: int | None = None,
) -> dict[str, Any]:
    """列出当前在线 Runner 设备（含 Web / App 能力）。"""
    ensure_any_permission(ctx, UI_CASE_EXECUTE, APP_CASE_EXECUTE, APP_PLAN_VIEW, AI_TEST_EXECUTE, AI_TEST_VIEW)
    rows = await Device.filter(status="在线", is_del=False).order_by("-update_time")
    items = []
    for d in rows:
        engine_types = d.runner_engine_types or ["web"]
        items.append(
            {
                "id": d.id,
                "name": d.name or d.hostname or d.id,
                "ip": d.ip,
                "system": d.system,
                "status": d.status,
                "version": d.version or "",
                "runner_engine_types": engine_types,
                "app_udid": (d.app_udid or "").strip(),
                "app_connection": (d.app_connection or "").strip(),
                "app_platform": (d.app_platform or "").strip(),
            }
        )
    return {
        "project_id": project_id,
        "items": items,
        "total": len(items),
        "note": "Runner 为全局资源；Web UI 执行需 device_id；App 执行需勾选 App 的 Runner 且 adb 设备在线",
    }


def _catalog_to_dict(c: TestCatalog) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "project_id": c.project_id,
        "parent_id": c.parent_id,
        "sort": c.sort,
        "description": (c.description or "")[:200],
        "username": c.username,
    }


def _module_to_dict(m: TestCatalog) -> dict[str, Any]:
    return _catalog_to_dict(m)


async def _requirement_case_counts(req_ids: list[int]) -> dict[int, int]:
    if not req_ids:
        return {}
    counts: dict[int, int] = {rid: 0 for rid in req_ids}
    try:
        from tortoise.functions import Count

        rows = (
            await AiRequirementCase.filter(requirement_id__in=req_ids, is_del=False)
            .annotate(cnt=Count("id"))
            .group_by("requirement_id")
            .values("requirement_id", "cnt")
        )
        for r in rows:
            counts[int(r["requirement_id"])] = int(r["cnt"] or 0)
    except Exception:
        for rid in req_ids:
            counts[rid] = await AiRequirementCase.filter(requirement_id=rid, is_del=False).count()
    return counts


def _summarize_last_generate(meta: dict) -> Optional[dict[str, Any]]:
    lg = meta.get("last_generate") if isinstance(meta, dict) else None
    if not isinstance(lg, dict) or not lg:
        return None
    report = lg.get("generate_report") if isinstance(lg.get("generate_report"), dict) else {}
    vision = report.get("vision") if isinstance(report.get("vision"), dict) else {}
    case_gen = report.get("case_gen") if isinstance(report.get("case_gen"), dict) else {}
    return {
        "time": lg.get("time"),
        "case_count": lg.get("case_count"),
        "tokens_used": lg.get("tokens_used"),
        "duration_ms": lg.get("duration_ms"),
        "text_model": case_gen.get("model") or report.get("text_model") or report.get("model"),
        "vision_model": vision.get("model") or report.get("vision_model"),
        "vision_image_count": vision.get("image_count"),
        "vision_warnings": vision.get("warnings") or [],
    }


async def tool_list_modules(ctx: McpAuthContext, project_id: int) -> dict[str, Any]:
    ensure_permission(ctx, PROJECT_VIEW)
    rows = await TestCatalog.filter(project_id=project_id, is_del=False).order_by("sort", "-id")
    return {"items": [_catalog_to_dict(c) for c in rows]}


async def tool_list_requirements(
    ctx: McpAuthContext, project_id: int, page: int = 1, size: int = 20
) -> dict[str, Any]:
    ensure_permission(ctx, AI_TEST_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 100)
    qs = AiRequirement.filter(project_id=project_id, is_del=False).order_by("-id")
    total = await qs.count()
    rows = await qs.offset((page - 1) * size).limit(size)
    req_ids = [r.id for r in rows]
    case_counts = await _requirement_case_counts(req_ids)
    items = []
    for r in rows:
        d = _requirement_to_dict(r)
        d["case_count"] = case_counts.get(r.id, 0)
        d["last_generate_summary"] = _summarize_last_generate(
            r.parsed_content if isinstance(r.parsed_content, dict) else {}
        )
        items.append(d)
    return {"total": total, "items": items}


async def tool_get_requirement(
    ctx: McpAuthContext,
    requirement_id: int,
    project_id: int,
    include_section_titles: bool = True,
) -> dict[str, Any]:
    ensure_permission(ctx, AI_TEST_VIEW)
    req = await AiRequirement.get_or_none(id=requirement_id, project_id=project_id, is_del=False)
    if not req:
        raise ValueError("需求不存在")
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    data = _requirement_to_dict(req)
    data["case_count"] = await AiRequirementCase.filter(requirement_id=req.id, is_del=False).count()
    data["last_generate_summary"] = _summarize_last_generate(meta)
    if include_section_titles:
        sections = meta.get("sections") or []
        data["section_titles"] = [
            (s.get("title") or s.get("name") or "").strip()
            for s in sections
            if isinstance(s, dict) and (s.get("title") or s.get("name"))
        ]
    latest = await AiRequirementGenerateJob.filter(
        requirement_id=requirement_id, project_id=project_id
    ).order_by("-id").first()
    data["latest_job"] = _job_to_dict(latest) if latest else None
    return data


async def tool_list_requirement_cases(
    ctx: McpAuthContext,
    requirement_id: int,
    project_id: int,
    page: int = 1,
    size: int = 20,
    summary_only: bool = True,
) -> dict[str, Any]:
    """列出需求工作区用例；summary_only=true 时不返回 steps 全文，便于外部 AI 概览。"""
    ensure_permission(ctx, AI_TEST_VIEW)
    req = await AiRequirement.get_or_none(id=requirement_id, project_id=project_id, is_del=False)
    if not req:
        raise ValueError("需求不存在")
    page = max(page, 1)
    size = min(max(size, 1), 100)
    qs = AiRequirementCase.filter(requirement_id=requirement_id, is_del=False)
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    items = []
    for c in rows:
        if summary_only:
            items.append({
                "id": c.id,
                "title": c.title,
                "priority": c.priority,
                "module": c.module,
                "status": c.status,
                "type": c.type,
                "stage": getattr(c, "stage", None) or "",
            })
        else:
            from app.routers.ai.requirements import _case_to_dict
            items.append(_case_to_dict(c))
    priority_stats: dict[str, int] = {}
    if summary_only and page == 1:
        all_rows = await AiRequirementCase.filter(requirement_id=requirement_id, is_del=False).values(
            "priority"
        )
        for row in all_rows:
            p = (row.get("priority") or "P2").upper()
            priority_stats[p] = priority_stats.get(p, 0) + 1
    return {
        "requirement_id": requirement_id,
        "requirement_name": req.name,
        "total": total,
        "priority_stats": priority_stats,
        "items": items,
    }


async def tool_get_generate_job(ctx: McpAuthContext, job_id: int, project_id: int) -> dict[str, Any]:
    ensure_permission(ctx, AI_TEST_VIEW)
    job = await AiRequirementGenerateJob.get_or_none(id=job_id, project_id=project_id)
    if not job:
        raise ValueError("生成任务不存在")
    return _job_to_dict(job)


async def tool_get_requirement_latest_job(
    ctx: McpAuthContext, requirement_id: int, project_id: int
) -> dict[str, Any]:
    ensure_permission(ctx, AI_TEST_VIEW)
    job = await AiRequirementGenerateJob.filter(
        requirement_id=requirement_id, project_id=project_id
    ).order_by("-id").first()
    if not job:
        return {"job": None}
    return {"job": _job_to_dict(job)}


async def tool_preview_trigger_generate(
    ctx: McpAuthContext, requirement_id: int, project_id: int, batch_count: int = 10
) -> dict[str, Any]:
    ensure_permission(ctx, AI_TEST_EXECUTE)
    req = await AiRequirement.get_or_none(id=requirement_id, project_id=project_id, is_del=False)
    if not req:
        raise ValueError("需求不存在")
    running = await AiRequirementGenerateJob.filter(
        requirement_id=requirement_id,
        project_id=project_id,
        status__in=["pending", "running"],
    ).first()
    existing_cases = await AiRequirementCase.filter(requirement_id=requirement_id, is_del=False).count()
    impact = {
        "requirement_id": requirement_id,
        "requirement_name": req.name,
        "project_id": project_id,
        "existing_cases": existing_cases,
        "planned_batch_count": batch_count,
        "has_running_job": bool(running),
        "running_job_id": running.id if running else None,
        "warning": "将提交异步批量生成任务，消耗 LLM Token",
    }
    if running:
        raise ValueError(f"该需求已有进行中的生成任务 #{running.id}，请等待完成")
    confirm_token = await create_confirm_token(
        "trigger_generate",
        {"requirement_id": requirement_id, "project_id": project_id, "batch_count": batch_count},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_trigger_generate 并传入 confirm_token",
    }


async def tool_confirm_trigger_generate(
    ctx: McpAuthContext, confirm_token: str, project_id: int
) -> dict[str, Any]:
    ensure_permission(ctx, AI_TEST_EXECUTE)
    payload = await consume_confirm_token(confirm_token, "trigger_generate", ctx.username)
    if int(payload.get("project_id", 0)) != project_id:
        raise ValueError("project_id 与确认 Token 不匹配")
    requirement_id = int(payload["requirement_id"])
    batch_count = int(payload.get("batch_count") or 10)
    req = await AiRequirement.get_or_none(id=requirement_id, project_id=project_id, is_del=False)
    if not req:
        raise ValueError("需求不存在")
    body = GenerateCasesBatchRequest(
        replace_existing=False,
        batches=_build_generate_batches(req, batch_count),
    )
    resp = await _create_generate_job(requirement_id, body, project_id, _user_info(ctx))
    return {"message": resp.message, "job": resp.data}


async def tool_search_functional_cases(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    ensure_permission(ctx, AI_TEST_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 100)
    qs = AiFunctionalCase.filter(project_id=project_id, is_del=False)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(Q(title__icontains=kw) | Q(module__icontains=kw) | Q(keywords__icontains=kw))
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    return {"total": total, "items": [functional_case_to_dict(c) for c in rows]}


async def tool_search_test_knowledge(
    ctx: McpAuthContext,
    project_id: int,
    query: str,
    folder_ids: Optional[list[int]] = None,
    document_ids: Optional[list[int]] = None,
    top_k: int = 12,
    strategy: Optional[str] = None,
) -> dict[str, Any]:
    """检索迭代测试资料库（RAG 分块优先，无索引时回退全文）。"""
    ensure_permission(ctx, AI_TEST_VIEW)
    from app.modules.knowledge.knowledge_retrieve import retrieve_knowledge

    return await retrieve_knowledge(
        project_id,
        query=query,
        folder_ids=folder_ids,
        document_ids=document_ids,
        top_k=top_k,
        strategy=strategy,
    )


async def tool_ask_test_knowledge(
    ctx: McpAuthContext,
    project_id: int,
    query: str,
    mode: str = "smart",
    folder_ids: Optional[list[int]] = None,
    document_ids: Optional[list[int]] = None,
    top_k: int = 12,
    strategy: Optional[str] = None,
    ai_config_id: Optional[int] = None,
) -> dict[str, Any]:
    """资料库问答：retrieve 仅检索；smart 检索后 LLM 生成答案。

    v2 路由：表格统计题优先走程序引擎（需指定 1 份 Excel/CSV）；长文档语义题可全文/章节注入（范围建议 1～3 份）；其余回退 RAG。
    统计题解析失败时不返回伪装精确数字，会标记 tabular_fallback 并回退检索。
    """
    ensure_permission(ctx, AI_TEST_VIEW)
    from app.modules.knowledge.knowledge_qa import ask_knowledge

    return await ask_knowledge(
        project_id,
        mode=mode,
        query=query,
        folder_ids=folder_ids,
        document_ids=document_ids,
        top_k=top_k,
        strategy=strategy,
        username=ctx.username or "",
        ai_config_id=ai_config_id,
    )


async def tool_list_knowledge_folders(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 50,
) -> dict[str, Any]:
    """列出迭代测试资料库文件夹（含文档数量）。"""
    ensure_permission(ctx, AI_TEST_VIEW)
    from app.modules.knowledge import knowledge_service as svc

    page = max(page, 1)
    size = min(max(size, 1), 100)
    items = await svc.list_folders(project_id)
    kw = (keyword or "").strip().lower()
    if kw:
        items = [
            x for x in items
            if kw in (x.get("name") or "").lower()
            or kw in (x.get("iteration_label") or "").lower()
            or kw in (x.get("description") or "").lower()
        ]
    total = len(items)
    start = (page - 1) * size
    page_items = items[start : start + size]
    return {"total": total, "items": page_items}


async def tool_get_functional_case(ctx: McpAuthContext, case_id: int, project_id: int) -> dict[str, Any]:
    ensure_permission(ctx, AI_TEST_VIEW)
    case = await AiFunctionalCase.get_or_none(id=case_id, project_id=project_id, is_del=False)
    if not case:
        raise ValueError("功能用例不存在")
    return functional_case_to_dict(case)


async def tool_preview_run_api_suite(
    ctx: McpAuthContext, suite_id: int, env_id: Optional[int] = None
) -> dict[str, Any]:
    ensure_permission(ctx, API_CASE_EXECUTE)
    suite = await ApiTestSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise ValueError("接口套件不存在")
    await _require_project_member(ctx, suite.project_id)
    suite_cases = await ApiSuiteCase.filter(suite_id=suite_id).count()
    resolved_env_id = env_id or suite.env_id
    env_name = ""
    if resolved_env_id:
        env = await Environment.get_or_none(id=resolved_env_id, is_del=False)
        env_name = env.name if env else "未知环境"
    impact = {
        "suite_id": suite_id,
        "suite_name": suite.name,
        "project_id": suite.project_id,
        "case_count": suite_cases,
        "env_id": resolved_env_id,
        "env_name": env_name,
        "warning": "将异步执行接口套件，可能触发大量 HTTP 请求",
    }
    if not resolved_env_id:
        raise ValueError("请指定 env_id 或在套件上配置默认环境")
    if suite_cases == 0:
        raise ValueError("套件中没有用例")
    confirm_token = await create_confirm_token(
        "run_api_suite",
        {"suite_id": suite_id, "env_id": resolved_env_id, "project_id": int(suite.project_id)},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_run_api_suite 并传入 confirm_token",
    }


async def tool_confirm_run_api_suite(
    ctx: McpAuthContext, confirm_token: str, suite_id: int, env_id: Optional[int] = None
) -> dict[str, Any]:
    ensure_permission(ctx, API_CASE_EXECUTE)
    from app.core.integration.mcp_confirm import peek_confirm_token

    peeked = await peek_confirm_token(confirm_token, ctx.username)
    suite = await ApiTestSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise ValueError("接口套件不存在")
    await _require_project_member(ctx, suite.project_id)
    payload = await consume_confirm_token(confirm_token, "run_api_suite", ctx.username)
    if int(payload.get("suite_id", 0)) != suite_id:
        raise ValueError("suite_id 与确认 Token 不匹配")
    if peeked and int(peeked.get("project_id") or 0) not in (0, int(suite.project_id)):
        raise ValueError("project_id 与确认 Token 不匹配")
    resolved_env_id = env_id or int(payload.get("env_id") or 0)
    result = await _await_route(
        run_suite_async(
            suite_id,
            ApiSuiteRunRequest(env_id=resolved_env_id, trigger_type=ASSISTANT_TRIGGER),
            _AsyncBackgroundTasks(),
            username=ctx.username,
        )
    )
    return {"record_id": result.record_id, "message": result.message}


async def tool_preview_run_api_plan(
    ctx: McpAuthContext, plan_id: int, env_id: Optional[int] = None
) -> dict[str, Any]:
    ensure_permission(ctx, API_PLAN_EDIT)
    plan = await ApiTestPlan.get_or_none(id=plan_id, is_del=False)
    if not plan:
        raise ValueError("接口测试计划不存在")
    await _require_project_member(ctx, plan.project_id)
    item_count = await ApiPlanItem.filter(plan_id=plan_id).count()
    resolved_env_id = env_id or plan.env_id
    env_name = ""
    if resolved_env_id:
        env = await Environment.get_or_none(id=resolved_env_id, is_del=False)
        env_name = env.name if env else "未知环境"
    if not resolved_env_id:
        raise ValueError("请指定 env_id 或在计划上配置默认环境")
    if item_count == 0:
        raise ValueError("计划中没有任何 Item")
    impact = {
        "plan_id": plan_id,
        "plan_name": plan.name,
        "project_id": plan.project_id,
        "item_count": item_count,
        "env_id": resolved_env_id,
        "env_name": env_name,
        "warning": "将异步执行接口测试计划，可能触发大量 HTTP 请求",
    }
    confirm_token = await create_confirm_token(
        "run_api_plan",
        {"plan_id": plan_id, "env_id": resolved_env_id, "project_id": int(plan.project_id)},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_run_api_plan 并传入 confirm_token",
    }


async def tool_confirm_run_api_plan(
    ctx: McpAuthContext, confirm_token: str, plan_id: int, env_id: Optional[int] = None
) -> dict[str, Any]:
    ensure_permission(ctx, API_PLAN_EDIT)
    plan = await ApiTestPlan.get_or_none(id=plan_id, is_del=False)
    if not plan:
        raise ValueError("接口测试计划不存在")
    await _require_project_member(ctx, plan.project_id)
    payload = await consume_confirm_token(confirm_token, "run_api_plan", ctx.username)
    if int(payload.get("plan_id", 0)) != plan_id:
        raise ValueError("plan_id 与确认 Token 不匹配")
    resolved_env_id = env_id or int(payload.get("env_id") or 0)
    result = await _await_route(
        run_plan_async(
            plan_id,
            ApiPlanRunRequest(env_id=resolved_env_id, trigger_type=ASSISTANT_TRIGGER),
            _AsyncBackgroundTasks(),
            username=ctx.username,
        )
    )
    return {"record_id": result.record_id, "message": result.message}


async def _resolve_api_case(
    project_id: int,
    *,
    case_id: int | None = None,
    case_name: str | None = None,
) -> ApiTestCase:
    if case_id:
        case = await ApiTestCase.get_or_none(id=case_id, project_id=project_id, is_del=False)
        if not case:
            raise ValueError(f"接口用例 #{case_id} 不存在")
        return case
    name = (case_name or "").strip()
    if not name:
        raise ValueError("请提供 case_id 或 case_name")
    exact = await ApiTestCase.filter(project_id=project_id, is_del=False, name=name).limit(2)
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        ids = ", ".join(f"#{c.id}" for c in exact)
        raise ValueError(f"名称「{name}」匹配到多条用例，请指定 case_id：{ids}")
    partial = await ApiTestCase.filter(project_id=project_id, is_del=False, name__icontains=name).limit(6)
    if not partial:
        raise ValueError(f"未找到名称包含「{name}」的接口用例")
    if len(partial) == 1:
        return partial[0]
    hints = ", ".join(f"#{c.id}:{c.name}" for c in partial[:5])
    raise ValueError(f"名称「{name}」匹配到多条用例，请指定 case_id：{hints}")


def _serialize_api_run_result(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        data = result.model_dump()
    elif isinstance(result, dict):
        data = dict(result)
    else:
        data = {"status": getattr(result, "status", "unknown")}
    for key in ("request_detail", "response_detail"):
        val = data.get(key)
        if isinstance(val, dict):
            body = val.get("body")
            if isinstance(body, str) and len(body) > 2000:
                val["body"] = body[:2000] + "…(已截断)"
    return data


async def tool_preview_run_api_case(
    ctx: McpAuthContext,
    project_id: int,
    env_id: int,
    case_id: int | None = None,
    case_name: str | None = None,
) -> dict[str, Any]:
    ensure_permission(ctx, API_CASE_EXECUTE)
    await _require_project_member(ctx, project_id)
    case = await _resolve_api_case(project_id, case_id=case_id, case_name=case_name)
    env = await Environment.get_or_none(id=env_id, project_id=project_id, is_del=False)
    if not env:
        raise ValueError("执行环境不存在或不属于当前项目")
    api = await case.api
    impact = {
        "project_id": project_id,
        "case_id": case.id,
        "case_name": case.name,
        "api_id": case.api_id,
        "api_name": api.name if api else "",
        "method": api.method if api else "",
        "path": api.path if api else "",
        "env_id": env_id,
        "env_name": env.name,
        "data_driven": bool(case.data_set),
        "warning": "将同步执行单条接口用例并立即返回 HTTP 结果",
    }
    confirm_token = await create_confirm_token(
        "run_api_case",
        {"case_id": case.id, "env_id": env_id, "project_id": project_id},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_run_api_case 并传入 confirm_token",
    }


async def tool_confirm_run_api_case(
    ctx: McpAuthContext,
    confirm_token: str,
    case_id: int,
    env_id: int,
    project_id: int | None = None,
) -> dict[str, Any]:
    ensure_permission(ctx, API_CASE_EXECUTE)
    payload = await consume_confirm_token(confirm_token, "run_api_case", ctx.username)
    if int(payload.get("case_id", 0)) != case_id:
        raise ValueError("case_id 与确认 Token 不匹配")
    resolved_env_id = env_id or int(payload.get("env_id") or 0)
    resolved_project_id = int(project_id or payload.get("project_id") or 0)
    case = await ApiTestCase.get_or_none(id=case_id, is_del=False)
    if not case:
        raise ValueError("接口用例不存在")
    await _require_project_member(ctx, case.project_id)
    if resolved_project_id and case.project_id != resolved_project_id:
        raise ValueError("用例不属于当前项目")
    if case.data_set:
        result = await _await_route(
            run_data_driven_case(case_id, resolved_env_id, ctx.username, {}, False)
        )
        return {
            "case_id": case_id,
            "case_name": case.name,
            "data_driven": True,
            "result": _serialize_api_run_result(result),
            "message": "数据驱动用例已执行",
        }
    result = await _await_route(
        run_single_case(case_id, resolved_env_id, None, ctx.username, {}, False)
    )
    serialized = _serialize_api_run_result(result)
    return {
        "case_id": case_id,
        "case_name": serialized.get("case_name") or case.name,
        "status": serialized.get("status"),
        "response_status": serialized.get("response_status"),
        "response_time": serialized.get("response_time"),
        "error": serialized.get("error"),
        "assertions": serialized.get("assertions"),
        "message": "用例执行完成",
        "result": serialized,
    }


async def tool_preview_run_ui_task(
    ctx: McpAuthContext, task_id: int, env_id: int, device_id: str
) -> dict[str, Any]:
    ensure_permission(ctx, UI_TASK_EXECUTE)
    task = await Task.get_or_none(id=task_id, is_del=False)
    if not task:
        raise ValueError("UI 测试计划不存在")
    await _require_project_member(ctx, task.project_id)
    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise ValueError("运行环境不存在")
    if not (device_id or "").strip():
        raise ValueError("请指定 device_id（在线 Runner 设备 ID）")
    impact = {
        "task_id": task_id,
        "task_name": task.name,
        "project_id": task.project_id,
        "env_id": env_id,
        "env_name": env.name,
        "device_id": device_id,
        "warning": "将触发 UI 测试计划执行，占用 Runner 设备",
    }
    confirm_token = await create_confirm_token(
        "run_ui_task",
        {
            "task_id": task_id,
            "env_id": env_id,
            "device_id": device_id,
            "project_id": int(task.project_id),
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_run_ui_task 并传入 confirm_token",
    }


async def tool_confirm_run_ui_task(ctx: McpAuthContext, confirm_token: str, task_id: int) -> dict[str, Any]:
    ensure_permission(ctx, UI_TASK_EXECUTE)
    task = await Task.get_or_none(id=task_id, is_del=False)
    if not task:
        raise ValueError("UI 测试计划不存在")
    await _require_project_member(ctx, task.project_id)
    payload = await consume_confirm_token(confirm_token, "run_ui_task", ctx.username)
    if int(payload.get("task_id", 0)) != task_id:
        raise ValueError("task_id 与确认 Token 不匹配")
    from app.routers.ui.exec import run_task

    result = await _await_route(
        run_task(
            task_id,
            UiRunForm(
                env_id=int(payload["env_id"]),
                device_id=str(payload["device_id"]),
                username=ctx.username,
                trigger_source=ASSISTANT_TRIGGER,
            ),
            user_info=_user_info(ctx),
        )
    )
    task_record_id = result.get("task_record_id") if isinstance(result, dict) else None
    return {
        "result": result,
        "task_record_id": task_record_id,
        "message": result.get("msg") if isinstance(result, dict) else str(result),
    }


async def tool_preview_run_ui_suite(
    ctx: McpAuthContext,
    suite_id: int,
    env_id: int,
    device_id: str,
) -> dict[str, Any]:
    ensure_permission(ctx, UI_SUITE_EXECUTE)
    suite = await Suite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise ValueError("Web UI 套件不存在")
    await _require_project_member(ctx, suite.project_id)
    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise ValueError("运行环境不存在")
    if not (device_id or "").strip():
        raise ValueError("请指定 device_id（在线 Runner 设备 ID，可在设备管理查看）")
    case_count = await Step.filter(suite_id=suite_id, is_del=False).count()
    if case_count == 0:
        raise ValueError("套件中没有用例步骤")
    impact = {
        "suite_id": suite_id,
        "suite_name": suite.name,
        "project_id": suite.project_id,
        "case_count": case_count,
        "env_id": env_id,
        "env_name": env.name,
        "device_id": device_id.strip(),
        "warning": "将触发 Web UI 套件执行，占用 Runner 设备",
    }
    confirm_token = await create_confirm_token(
        "run_ui_suite",
        {
            "suite_id": suite_id,
            "env_id": env_id,
            "device_id": device_id.strip(),
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_run_ui_suite 并传入 confirm_token",
    }


async def tool_confirm_run_ui_suite(
    ctx: McpAuthContext,
    confirm_token: str,
    suite_id: int,
    env_id: Optional[int] = None,
    device_id: Optional[str] = None,
) -> dict[str, Any]:
    ensure_permission(ctx, UI_SUITE_EXECUTE)
    suite = await Suite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise ValueError("Web UI 套件不存在")
    await _require_project_member(ctx, suite.project_id)
    payload = await consume_confirm_token(confirm_token, "run_ui_suite", ctx.username)
    if int(payload.get("suite_id", 0)) != suite_id:
        raise ValueError("suite_id 与确认 Token 不匹配")
    resolved_env_id = env_id or int(payload.get("env_id") or 0)
    resolved_device = (device_id or payload.get("device_id") or "").strip()
    result = await _await_route(
        run_ui_suite(
            suite_id,
            UiRunForm(
                env_id=resolved_env_id,
                device_id=resolved_device,
                username=ctx.username,
                trigger_source=ASSISTANT_TRIGGER,
            ),
            user_info=_user_info(ctx),
        )
    )
    suite_record_id = result.get("suite_record_id") if isinstance(result, dict) else None
    return {
        "result": result,
        "suite_record_id": suite_record_id,
        "message": result.get("msg") if isinstance(result, dict) else str(result),
    }


async def _resolve_ui_case(
    project_id: int,
    *,
    case_id: int | None = None,
    case_name: str | None = None,
) -> Case:
    if case_id:
        case = await Case.get_or_none(id=case_id, project_id=project_id, is_del=False)
        if not case:
            raise ValueError(f"Web UI 用例 #{case_id} 不存在")
        return case
    name = (case_name or "").strip()
    if not name:
        raise ValueError("请提供 case_id 或 case_name")
    exact = await Case.filter(project_id=project_id, is_del=False, name=name).limit(2)
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        ids = ", ".join(f"#{c.id}" for c in exact)
        raise ValueError(f"名称「{name}」匹配到多条 Web UI 用例，请指定 case_id：{ids}")
    partial = await Case.filter(project_id=project_id, is_del=False, name__icontains=name).limit(6)
    if not partial:
        raise ValueError(f"未找到名称包含「{name}」的 Web UI 用例")
    if len(partial) == 1:
        return partial[0]
    hints = ", ".join(f"#{c.id}:{c.name}" for c in partial[:5])
    raise ValueError(f"名称「{name}」匹配到多条 Web UI 用例，请指定 case_id：{hints}")


async def tool_preview_run_ui_case(
    ctx: McpAuthContext,
    project_id: int,
    env_id: int,
    device_id: str,
    case_id: int | None = None,
    case_name: str | None = None,
) -> dict[str, Any]:
    ensure_permission(ctx, UI_CASE_EXECUTE)
    await _require_project_member(ctx, project_id)
    case = await _resolve_ui_case(project_id, case_id=case_id, case_name=case_name)
    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise ValueError("运行环境不存在")
    if not (device_id or "").strip():
        raise ValueError("请指定 device_id（在线 Runner 设备 ID，可在设备管理查看）")
    step_count = len(case.steps) if isinstance(case.steps, list) else 0
    if step_count == 0:
        raise ValueError("用例没有步骤，无法执行")
    impact = {
        "project_id": project_id,
        "case_id": case.id,
        "case_name": case.name,
        "step_count": step_count,
        "env_id": env_id,
        "env_name": env.name,
        "device_id": device_id.strip(),
        "warning": "将触发单条 Web UI 用例执行，占用 Runner 设备",
    }
    confirm_token = await create_confirm_token(
        "run_ui_case",
        {
            "case_id": case.id,
            "env_id": env_id,
            "device_id": device_id.strip(),
            "project_id": project_id,
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_run_ui_case 并传入 confirm_token",
    }


async def tool_confirm_run_ui_case(
    ctx: McpAuthContext,
    confirm_token: str,
    case_id: int,
    env_id: int | None = None,
    device_id: str | None = None,
    project_id: int | None = None,
) -> dict[str, Any]:
    ensure_permission(ctx, UI_CASE_EXECUTE)
    payload = await consume_confirm_token(confirm_token, "run_ui_case", ctx.username)
    if int(payload.get("case_id", 0)) != case_id:
        raise ValueError("case_id 与确认 Token 不匹配")
    resolved_env_id = env_id or int(payload.get("env_id") or 0)
    resolved_device = (device_id or payload.get("device_id") or "").strip()
    resolved_project_id = int(project_id or payload.get("project_id") or 0)
    case = await Case.get_or_none(id=case_id, is_del=False)
    if not case:
        raise ValueError("Web UI 用例不存在")
    await _require_project_member(ctx, case.project_id)
    if resolved_project_id and case.project_id != resolved_project_id:
        raise ValueError("用例不属于当前项目")
    result = await _await_route(
        run_ui_case(
            case_id,
            UiRunForm(
                env_id=resolved_env_id,
                device_id=resolved_device,
                username=ctx.username,
                trigger_source=ASSISTANT_TRIGGER,
            ),
            user_info=_user_info(ctx),
        )
    )
    execution_id = result.get("execution_id") if isinstance(result, dict) else None
    msg = result.get("msg") if isinstance(result, dict) else str(result)
    return {
        "case_id": case_id,
        "case_name": case.name,
        "execution_id": execution_id,
        "message": msg,
        "hint": (
            f"可说「查询 UI 用例执行记录 {execution_id}」查看执行结果"
            if execution_id
            else "任务已提交，可在 Web UI 执行记录中查看"
        ),
    }


async def tool_preview_run_perf_scene(
    ctx: McpAuthContext,
    scene_id: int,
    env_id: int,
    use_workers: bool = True,
) -> dict[str, Any]:
    """use_workers 已废弃：施压一律走在线 Worker，参数忽略。"""
    _ = use_workers
    ensure_permission(ctx, PERF_SCENE_EXECUTE)
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise ValueError("压测场景不存在")
    await _require_project_member(ctx, scene.project_id)
    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise ValueError("运行环境不存在")
    from app.routers.perf.workers import get_active_workers

    active = await get_active_workers(scene.project_id)
    item_count = len(scene.scene_items or [])
    config = dict(scene.config or {})
    impact = {
        "scene_id": scene_id,
        "scene_name": scene.name,
        "project_id": scene.project_id,
        "env_id": env_id,
        "env_name": env.name,
        "item_count": item_count,
        "requires_worker": True,
        "online_workers": len(active),
        "mode": config.get("mode", "constant"),
        "warning": (
            "将启动性能压测（必须有在线压测 Worker；后端不再本机直跑），"
            "可能产生大量 HTTP 请求"
        ),
    }
    if not active:
        impact["warning"] = "当前无在线压测 Worker，确认启动将失败；请先上线执行器"
    confirm_token = await create_confirm_token(
        "run_perf_scene",
        {"scene_id": scene_id, "env_id": env_id},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_run_perf_scene 并传入 confirm_token",
    }


async def tool_confirm_run_perf_scene(
    ctx: McpAuthContext,
    confirm_token: str,
    scene_id: int,
    env_id: Optional[int] = None,
    use_workers: bool = True,
) -> dict[str, Any]:
    """use_workers 已废弃，始终派发 Runner Worker。"""
    _ = use_workers
    ensure_permission(ctx, PERF_SCENE_EXECUTE)
    payload = await consume_confirm_token(confirm_token, "run_perf_scene", ctx.username)
    if int(payload.get("scene_id", 0)) != scene_id:
        raise ValueError("scene_id 与确认 Token 不匹配")
    resolved_env_id = env_id or int(payload.get("env_id") or 0)
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise ValueError("压测场景不存在")
    await _require_project_member(ctx, scene.project_id)
    from app.routers.perf.workers import get_active_workers

    if not await get_active_workers(scene.project_id):
        raise ValueError("无可用压测 Worker，请上线执行器后再启动")
    config = dict(scene.config or {})
    config["env_id"] = resolved_env_id
    from app.modules.perf.perf_target_eval import normalize_perf_targets

    if config.get("perf_targets") is not None:
        config["perf_targets"] = normalize_perf_targets(config.get("perf_targets"))
    from app.modules.perf.sut_bind import apply_sut_binding_to_config
    from app.modules.perf.sut_force import activate_sut_force_for_record

    config = await apply_sut_binding_to_config(
        config,
        project_id=scene.project_id,
        env_id=resolved_env_id,
        apply_force=False,
    )
    record = await PerfRecord.create(
        scene_id=scene_id,
        project_id=scene.project_id,
        status="pending",
        trigger_type="manual",
        config_snapshot=config,
        scene_items_snapshot=scene.scene_items or [],
        run_by=ctx.username,
    )
    await activate_sut_force_for_record(record)
    _AsyncBackgroundTasks().add_task(run_perf_scene, record.id, True)
    return {
        "record_id": record.id,
        "status": "pending",
        "message": "性能测试已启动（派发 Worker）",
    }


async def tool_preview_spawn_browser_lab(
    ctx: McpAuthContext,
    project_id: int,
    task_text: str,
    start_url: str,
    device_id: str,
    env_id: Optional[int] = None,
    ai_config_id: Optional[int] = None,
    max_steps: Optional[int] = None,
    headless: bool = True,
) -> dict[str, Any]:
    """预览派发智能浏览器（Browser Lab）任务；需用户确认后才创建。"""
    ensure_permission(ctx, AI_TEST_EXECUTE)
    from app.core.platform.project_access import PROJECT_ROLE_MEMBER
    from brickcore_assist.skills.access import require_project_access

    await require_project_access(ctx, int(project_id), min_role=PROJECT_ROLE_MEMBER)
    text = (task_text or "").strip()[:500]
    url = (start_url or "").strip()[:500]
    device = (device_id or "").strip()
    if len((task_text or "").strip()) > 500:
        raise ValueError("任务描述过长（最多 500 字符）")
    if len((start_url or "").strip()) > 500:
        raise ValueError("起始 URL 过长（最多 500 字符）")
    if len(text) < 2:
        raise ValueError("任务描述太短")
    if len(url) < 8:
        raise ValueError("起始 URL 无效")
    if not device:
        raise ValueError("请指定在线 Runner 的 device_id（可先 list_online_devices）")

    env_name = ""
    if env_id:
        env = await Environment.get_or_none(id=int(env_id), is_del=False)
        if not env:
            raise ValueError("参考环境不存在")
        env_name = env.name or ""

    device_row = await Device.get_or_none(id=device, is_del=False)
    device_name = ""
    device_online = False
    if device_row:
        device_name = device_row.name or device_row.hostname or device
        device_online = (device_row.status or "") == "在线"

    impact = {
        "project_id": int(project_id),
        "task_text": text,
        "start_url": url,
        "device_id": device,
        "device_name": device_name,
        "device_online": device_online,
        "env_id": int(env_id) if env_id else None,
        "env_name": env_name,
        "ai_config_id": ai_config_id,
        "max_steps": max_steps,
        "headless": bool(headless),
        "warning": (
            "将派发智能浏览器（Browser Lab）任务到在线 Runner，"
            "可能打开真实浏览器并产生 AI Token 消耗"
        ),
    }
    if not device_online:
        impact["warning"] = "指定设备当前不在线，确认启动可能失败；请先上线执行器"
    confirm_token = await create_confirm_token(
        "spawn_browser_lab",
        {
            "project_id": int(project_id),
            "task_text": text,
            "start_url": url,
            "device_id": device,
            "env_id": int(env_id) if env_id else None,
            "ai_config_id": ai_config_id,
            "max_steps": max_steps,
            "headless": bool(headless),
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_spawn_browser_lab 并传入 confirm_token",
    }


async def tool_confirm_spawn_browser_lab(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    task_text: str,
    start_url: str,
    device_id: str,
    env_id: Optional[int] = None,
    ai_config_id: Optional[int] = None,
    max_steps: Optional[int] = None,
    headless: bool = True,
) -> dict[str, Any]:
    ensure_permission(ctx, AI_TEST_EXECUTE)
    payload = await consume_confirm_token(confirm_token, "spawn_browser_lab", ctx.username)

    # Token payload 为唯一可信源；请求参数若传入则必须与 Token 一致（防篡改）
    def _mismatch(label: str) -> ValueError:
        return ValueError(f"{label} 与确认 Token 不匹配")

    if int(payload.get("project_id") or 0) != int(project_id):
        raise _mismatch("project_id")
    if (payload.get("device_id") or "").strip() != (device_id or "").strip():
        raise _mismatch("device_id")
    if (payload.get("task_text") or "").strip() != (task_text or "").strip():
        raise _mismatch("task_text")
    if (payload.get("start_url") or "").strip() != (start_url or "").strip():
        raise _mismatch("start_url")
    tok_env = payload.get("env_id")
    if env_id is not None and int(tok_env or 0) != int(env_id):
        raise _mismatch("env_id")
    tok_ai = payload.get("ai_config_id")
    if ai_config_id is not None and int(tok_ai or 0) != int(ai_config_id):
        raise _mismatch("ai_config_id")
    tok_steps = payload.get("max_steps")
    if max_steps is not None and int(tok_steps or 0) != int(max_steps):
        raise _mismatch("max_steps")
    if bool(payload.get("headless", True)) != bool(headless):
        raise _mismatch("headless")

    from brickcore_assist.skills.access import require_project_access
    from app.core.platform.project_access import PROJECT_ROLE_MEMBER
    from app.modules.assistant.assistant_jobs import spawn_browser_lab_task

    await require_project_access(
        ctx, int(payload["project_id"]), min_role=PROJECT_ROLE_MEMBER
    )

    task = await spawn_browser_lab_task(
        project_id=int(payload["project_id"]),
        username=ctx.username or "",
        task_text=str(payload.get("task_text") or ""),
        start_url=str(payload.get("start_url") or ""),
        device_id=str(payload.get("device_id") or ""),
        env_id=int(tok_env) if tok_env else None,
        ai_config_id=int(tok_ai) if tok_ai else None,
        max_steps=int(tok_steps) if tok_steps is not None else None,
        headless=bool(payload.get("headless", True)),
    )
    return {
        "task_id": task.id,
        "status": task.status,
        "project_id": task.project_id,
        "task_text": task.task_text,
        "start_url": task.start_url,
        "device_id": (task.config_json or {}).get("device_id") or payload.get("device_id"),
        "title": "Browser Lab 任务",
        "report_url": f"/browser-lab/report/{task.id}",
        "message": "智能浏览器任务已创建，正在启动",
    }


async def tool_preview_spawn_ui_agent(
    ctx: McpAuthContext,
    project_id: int,
    page_url: str,
    description: str,
    device_id: str,
    ai_config_id: Optional[int] = None,
    max_steps: Optional[int] = None,
    headless: bool = True,
) -> dict[str, Any]:
    """预览派发 UI Agent 探索任务；需用户确认后才创建。"""
    ensure_permission(ctx, AI_TEST_EXECUTE)
    ensure_permission(ctx, UI_CASE_EDIT)
    from app.core.platform.project_access import PROJECT_ROLE_MEMBER
    from brickcore_assist.skills.access import require_project_access

    await require_project_access(ctx, int(project_id), min_role=PROJECT_ROLE_MEMBER)
    url = (page_url or "").strip()[:500]
    desc = (description or "").strip()[:500]
    device = (device_id or "").strip()
    if len((page_url or "").strip()) > 500:
        raise ValueError("起始 URL 过长（最多 500 字符）")
    if len((description or "").strip()) > 500:
        raise ValueError("探索目标描述过长（最多 500 字符）")
    if len(url) < 8:
        raise ValueError("起始 URL 无效")
    if len(desc) < 2:
        raise ValueError("探索目标描述太短")
    if not device:
        raise ValueError("请指定在线 Runner 的 device_id（可先 list_online_devices）")

    device_row = await Device.get_or_none(id=device, is_del=False)
    device_name = ""
    device_online = False
    if device_row:
        device_name = device_row.name or device_row.hostname or device
        device_online = (device_row.status or "") == "在线"

    impact = {
        "project_id": int(project_id),
        "page_url": url,
        "description": desc,
        "device_id": device,
        "device_name": device_name,
        "device_online": device_online,
        "ai_config_id": ai_config_id,
        "max_steps": max_steps,
        "headless": bool(headless),
        "warning": (
            "将派发 UI Agent 探索任务到在线 Runner，"
            "可能打开真实浏览器并产生 AI Token 消耗"
        ),
    }
    if not device_online:
        impact["warning"] = "指定设备当前不在线，确认启动可能失败；请先上线执行器"
    confirm_token = await create_confirm_token(
        "spawn_ui_agent",
        {
            "project_id": int(project_id),
            "page_url": url,
            "description": desc,
            "device_id": device,
            "ai_config_id": ai_config_id,
            "max_steps": max_steps,
            "headless": bool(headless),
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_spawn_ui_agent 并传入 confirm_token",
    }


async def tool_confirm_spawn_ui_agent(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    page_url: str,
    description: str,
    device_id: str,
    ai_config_id: Optional[int] = None,
    max_steps: Optional[int] = None,
    headless: bool = True,
) -> dict[str, Any]:
    ensure_permission(ctx, AI_TEST_EXECUTE)
    ensure_permission(ctx, UI_CASE_EDIT)
    payload = await consume_confirm_token(confirm_token, "spawn_ui_agent", ctx.username)

    def _mismatch(label: str) -> ValueError:
        return ValueError(f"{label} 与确认 Token 不匹配")

    if int(payload.get("project_id") or 0) != int(project_id):
        raise _mismatch("project_id")
    if (payload.get("device_id") or "").strip() != (device_id or "").strip():
        raise _mismatch("device_id")
    if (payload.get("page_url") or "").strip() != (page_url or "").strip():
        raise _mismatch("page_url")
    if (payload.get("description") or "").strip() != (description or "").strip():
        raise _mismatch("description")
    tok_ai = payload.get("ai_config_id")
    if ai_config_id is not None and int(tok_ai or 0) != int(ai_config_id):
        raise _mismatch("ai_config_id")
    tok_steps = payload.get("max_steps")
    if max_steps is not None and int(tok_steps or 0) != int(max_steps):
        raise _mismatch("max_steps")
    if bool(payload.get("headless", True)) != bool(headless):
        raise _mismatch("headless")

    from app.core.platform.project_access import PROJECT_ROLE_MEMBER
    from brickcore_assist.skills.access import require_project_access
    from app.modules.assistant.assistant_jobs import spawn_ui_agent_job

    await require_project_access(
        ctx, int(payload["project_id"]), min_role=PROJECT_ROLE_MEMBER
    )

    return await spawn_ui_agent_job(
        project_id=int(payload["project_id"]),
        username=ctx.username or "",
        page_url=str(payload.get("page_url") or ""),
        description=str(payload.get("description") or ""),
        device_id=str(payload.get("device_id") or ""),
        ai_config_id=int(tok_ai) if tok_ai else None,
        max_steps=int(tok_steps) if tok_steps is not None else None,
        headless=bool(payload.get("headless", True)),
    )


async def tool_get_execution_record(
    ctx: McpAuthContext, record_type: str, record_id: int
) -> dict[str, Any]:
    record_type = (record_type or "").lower()
    if record_type == "api_suite":
        ensure_permission(ctx, API_RECORD_VIEW)
        rec = await ApiSuiteRunRecord.get_or_none(id=record_id)
        if not rec:
            raise ValueError("接口套件执行记录不存在")
        suite = await ApiTestSuite.get_or_none(id=rec.suite_id)
        return {
            "id": rec.id,
            "type": "api_suite",
            "suite_id": rec.suite_id,
            "name": suite.name if suite else "",
            "status": rec.status,
            "run_by": rec.run_by,
            "total_cases": rec.total_cases,
            "success_cases": rec.success_cases,
            "failed_cases": rec.failed_cases,
            "start_time": rec.start_time.isoformat() if rec.start_time else None,
            "env_name": rec.env_name,
            "trigger_type": rec.trigger_type,
            "trigger_type_label": _TRIGGER_LABELS.get(rec.trigger_type, rec.trigger_type),
        }
    if record_type in ("api_plan", "plan"):
        ensure_permission(ctx, API_RECORD_VIEW)
        rec = await ApiPlanRunRecord.get_or_none(id=record_id)
        if not rec:
            raise ValueError("接口测试计划执行记录不存在")
        plan = await ApiTestPlan.get_or_none(id=rec.plan_id)
        return {
            "id": rec.id,
            "type": "api_plan",
            "plan_id": rec.plan_id,
            "name": plan.name if plan else "",
            "status": rec.status,
            "run_by": rec.run_by,
            "total_cases": rec.total_cases,
            "success_cases": rec.success_cases,
            "failed_cases": rec.failed_cases,
            "trigger_type": rec.trigger_type,
            "start_time": rec.start_time.isoformat() if rec.start_time else None,
            "env_name": rec.env_name,
        }
    if record_type in ("ui_plan", "ui_task"):
        ensure_permission(ctx, UI_RECORD_VIEW)
        rec = await UiPlanExecution.get_or_none(id=record_id, is_del=False).prefetch_related("task")
        if not rec:
            raise ValueError("UI 测试计划执行记录不存在")
        meta = _ui_trigger_meta(rec.env)
        return {
            "id": rec.id,
            "type": "ui_plan",
            "task_id": rec.task_id,
            "task_name": rec.task.name if rec.task else "",
            "status": rec.status,
            "username": rec.username,
            "case_count": rec.case_count,
            "success": rec.success,
            "fail": rec.fail,
            "error": rec.error,
            "pass_rate": rec.pass_rate,
            "start_time": rec.start_time.isoformat() if rec.start_time else None,
            "duration": rec.duration,
            **meta,
        }
    if record_type in ("ui_case", "ui_case_execution", "web_ui_case"):
        ensure_permission(ctx, UI_RECORD_VIEW)
        rec = await UiCaseExecution.get_or_none(id=record_id, is_del=False).prefetch_related("case")
        if not rec:
            raise ValueError("Web UI 用例执行记录不存在")
        meta = _ui_trigger_meta(rec.env)
        from app.modules.ui.ui_result_extract import extract_ui_case_failure_summary

        summary = extract_ui_case_failure_summary(getattr(rec, "result_data", None))
        return {
            "id": rec.id,
            "type": "ui_case",
            "case_id": rec.case_id,
            "case_name": rec.case.name if rec.case else "",
            "status": rec.status,
            "username": rec.username,
            "start_time": rec.start_time.isoformat() if rec.start_time else None,
            "error_hint": summary.get("error_hint") or "",
            "failed_step_index": summary.get("failed_step_index"),
            "failed_step_keyword": summary.get("failed_step_keyword") or "",
            "failed_step_desc": (summary.get("failed_step_desc") or "")[:200],
            "log_error_excerpt": (summary.get("log_error_excerpt") or "")[:400],
            "has_screenshot": bool(summary.get("has_screenshot")),
            **meta,
        }
    if record_type == "perf":
        ensure_permission(ctx, PERF_RECORD_VIEW)
        rec = await PerfRecord.get_or_none(id=record_id).prefetch_related("scene")
        if not rec:
            raise ValueError("压测执行记录不存在")
        return {
            "id": rec.id,
            "type": "perf",
            "perf_scene_id": rec.scene_id,
            "scene_name": rec.scene.name if rec.scene else "",
            "status": rec.status,
            "qps": rec.qps,
            "avg_response_time": rec.avg_response_time,
            "error_rate": rec.error_rate,
            "total_requests": rec.total_requests,
            "run_by": rec.run_by,
            "started_at": rec.started_at.isoformat() if rec.started_at else None,
            "duration": rec.duration,
        }
    if record_type in ("app_plan", "app_task"):
        ensure_permission(ctx, APP_RECORD_VIEW)
        rec = await AppPlanExecution.get_or_none(id=record_id, is_del=False).prefetch_related("plan")
        if not rec:
            raise ValueError("App 计划执行记录不存在")
        meta = _ui_trigger_meta(rec.env)
        return {
            "id": rec.id,
            "type": "app_plan",
            "plan_id": rec.plan_id,
            "plan_name": rec.plan.name if rec.plan else "",
            "status": rec.status,
            "username": rec.username,
            "case_count": rec.case_count,
            "success": rec.success,
            "fail": rec.fail,
            "error": rec.error,
            "pass_rate": rec.pass_rate,
            "start_time": rec.start_time.isoformat() if rec.start_time else None,
            "duration": rec.duration,
            "device_id": rec.device_id or "",
            **meta,
        }
    if record_type in ("app_suite",):
        ensure_permission(ctx, APP_RECORD_VIEW)
        rec = await AppSuiteExecution.get_or_none(id=record_id, is_del=False).prefetch_related("suite")
        if not rec:
            raise ValueError("App 套件执行记录不存在")
        return {
            "id": rec.id,
            "type": "app_suite",
            "suite_id": rec.suite_id,
            "suite_name": rec.suite.name if rec.suite else "",
            "status": rec.status,
            "username": rec.username,
            "case_count": rec.case_count,
            "success": rec.success,
            "fail": rec.fail,
            "error": rec.error,
            "pass_rate": rec.pass_rate,
            "start_time": rec.start_time.isoformat() if rec.start_time else None,
            "duration": rec.duration,
            "device_id": rec.device_id or "",
        }
    if record_type in ("app_case", "app_case_execution"):
        ensure_permission(ctx, APP_RECORD_VIEW)
        rec = await AppCaseExecution.get_or_none(id=record_id, is_del=False).prefetch_related("case")
        if not rec:
            raise ValueError("App 用例执行记录不存在")
        meta = _ui_trigger_meta(rec.env)
        from app.modules.ui.ui_result_extract import extract_ui_case_failure_summary

        summary = extract_ui_case_failure_summary(getattr(rec, "result_data", None))
        return {
            "id": rec.id,
            "type": "app_case",
            "case_id": rec.case_id,
            "case_name": rec.case.name if rec.case else "",
            "status": rec.status,
            "username": rec.username,
            "start_time": rec.start_time.isoformat() if rec.start_time else None,
            "error_hint": summary.get("error_hint") or "",
            "failed_step_index": summary.get("failed_step_index"),
            "failed_step_keyword": summary.get("failed_step_keyword") or "",
            "failed_step_desc": (summary.get("failed_step_desc") or "")[:200],
            "log_error_excerpt": (summary.get("log_error_excerpt") or "")[:400],
            "has_screenshot": bool(summary.get("has_screenshot")),
            **meta,
        }
    raise ValueError("record_type 支持 api_suite / api_plan / ui_plan / ui_case / app_plan / app_suite / app_case / perf")


async def tool_get_case_latest_failure(
    ctx: McpAuthContext,
    project_id: int,
    case_name: str = "",
    case_id: int | None = None,
    target_type: str = "ui",
) -> dict[str, Any]:
    """按用例名/ID 取最新失败记录的轻量错误摘要（禁止返回完整 result_data）。

    target_type: ui | app | api。查「某用例详细错误」优先本工具，勿用 list_ui_run_records（那是计划级）。
    """
    from app.core.platform.project_access import PROJECT_ROLE_VIEWER
    from app.core.shared.report_summary_context import APP_FAIL_STATUSES, UI_FAIL_STATUSES
    from app.modules.ui.ui_result_extract import extract_ui_case_failure_summary

    tt = (target_type or "ui").strip().lower()
    if tt not in ("ui", "app", "api"):
        raise ValueError("target_type 支持 ui、app 或 api")
    await _require_project_member(ctx, project_id, min_role=PROJECT_ROLE_VIEWER)

    name = (case_name or "").strip()
    cid = int(case_id) if case_id else None
    if not cid and not name:
        raise ValueError("请提供 case_id 或 case_name")

    if tt == "ui":
        ensure_permission(ctx, UI_RECORD_VIEW)
        case = None
        if cid:
            case = await Case.get_or_none(id=cid, project_id=project_id, is_del=False)
        if not case and name:
            case = await Case.get_or_none(project_id=project_id, is_del=False, name=name)
            if not case:
                case = await Case.filter(
                    project_id=project_id, is_del=False, name__icontains=name
                ).order_by("-id").first()
        if not case:
            raise ValueError("未找到匹配的 Web UI 用例")
        rec = (
            await UiCaseExecution.filter(
                case_id=case.id,
                is_del=False,
                status__in=list(UI_FAIL_STATUSES),
            )
            .order_by("-id")
            .first()
        )
        if not rec:
            return {
                "ok": False,
                "target_type": "ui",
                "case_id": case.id,
                "case_name": case.name,
                "message": "该用例暂无失败执行记录",
            }
        summary = extract_ui_case_failure_summary(getattr(rec, "result_data", None))
        return {
            "ok": True,
            "target_type": "ui",
            "target_id": rec.id,
            "case_id": case.id,
            "case_name": case.name,
            "status": rec.status,
            "run_at": rec.start_time.strftime("%Y-%m-%d %H:%M:%S") if rec.start_time else "",
            "error_hint": summary.get("error_hint") or "",
            "failed_step_index": summary.get("failed_step_index"),
            "failed_step_keyword": summary.get("failed_step_keyword") or "",
            "failed_step_desc": (summary.get("failed_step_desc") or "")[:200],
            "log_error_excerpt": (summary.get("log_error_excerpt") or "")[:500],
            "has_screenshot": bool(summary.get("has_screenshot")),
            "report_path": (
                f"/record/report/suite/{rec.suite_execution_id}"
                if getattr(rec, "suite_execution_id", None)
                else "/record"
            ),
        }

    if tt == "app":
        ensure_permission(ctx, APP_RECORD_VIEW)
        case = None
        if cid:
            case = await AppCase.get_or_none(id=cid, project_id=project_id, is_del=False)
        if not case and name:
            case = await AppCase.get_or_none(project_id=project_id, is_del=False, name=name)
            if not case:
                case = await AppCase.filter(
                    project_id=project_id, is_del=False, name__icontains=name
                ).order_by("-id").first()
        if not case:
            raise ValueError("未找到匹配的 App 用例")
        rec = (
            await AppCaseExecution.filter(
                case_id=case.id,
                is_del=False,
                status__in=list(APP_FAIL_STATUSES),
            )
            .order_by("-id")
            .first()
        )
        if not rec:
            return {
                "ok": False,
                "target_type": "app",
                "case_id": case.id,
                "case_name": case.name,
                "message": "该用例暂无失败执行记录",
            }
        summary = extract_ui_case_failure_summary(getattr(rec, "result_data", None))
        return {
            "ok": True,
            "target_type": "app",
            "target_id": rec.id,
            "case_id": case.id,
            "case_name": case.name,
            "status": rec.status,
            "run_at": rec.start_time.strftime("%Y-%m-%d %H:%M:%S") if rec.start_time else "",
            "error_hint": summary.get("error_hint") or "",
            "failed_step_index": summary.get("failed_step_index"),
            "failed_step_keyword": summary.get("failed_step_keyword") or "",
            "failed_step_desc": (summary.get("failed_step_desc") or "")[:200],
            "log_error_excerpt": (summary.get("log_error_excerpt") or "")[:500],
            "has_screenshot": bool(summary.get("has_screenshot")),
            "report_path": "/app",
        }

    # api
    ensure_permission(ctx, API_RECORD_VIEW)
    case = None
    if cid:
        case = await ApiTestCase.get_or_none(id=cid, project_id=project_id, is_del=False)
    if not case and name:
        case = await ApiTestCase.get_or_none(project_id=project_id, is_del=False, name=name)
        if not case:
            case = await ApiTestCase.filter(
                project_id=project_id, is_del=False, name__icontains=name
            ).order_by("-id").first()
    if not case:
        raise ValueError("未找到匹配的接口用例")
    rec = (
        await ApiRunRecord.filter(
            project_id=project_id,
            case_id=case.id,
            status__in=["failed", "error", "fail"],
        )
        .order_by("-id")
        .first()
    )
    if not rec:
        return {
            "ok": False,
            "target_type": "api",
            "case_id": case.id,
            "case_name": case.name,
            "message": "该用例暂无失败执行记录",
        }
    err = (getattr(rec, "error_msg", None) or "")[:500]
    return {
        "ok": True,
        "target_type": "api",
        "target_id": rec.id,
        "case_id": case.id,
        "case_name": case.name,
        "status": rec.status,
        "run_at": rec.start_time.strftime("%Y-%m-%d %H:%M:%S") if rec.start_time else "",
        "error_hint": err,
        "failed_step_index": None,
        "failed_step_keyword": "",
        "failed_step_desc": "",
        "log_error_excerpt": err,
        "has_screenshot": False,
        "report_path": (
            f"/api/suite-report/{rec.suite_run_record_id}"
            if getattr(rec, "suite_run_record_id", None)
            else "/api"
        ),
    }


async def tool_analyze_failure(
    ctx: McpAuthContext,
    project_id: int,
    target_type: str,
    target_id: int,
    force_refresh: bool = False,
    use_vision: bool = False,
    usage_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_permission(ctx, AI_TEST_EXECUTE)
    if target_type not in ("api", "ui", "app"):
        raise ValueError("target_type 支持 api、ui 或 app")
    try:
        return await _execute_failure_analysis(
            project_id=project_id,
            target_type=target_type,
            target_id=target_id,
            username=ctx.username,
            ai_config_id=None,
            vision_config_id=None,
            use_vision=use_vision,
            force_refresh=force_refresh,
            usage_extra=usage_extra,
        )
    except Exception as exc:
        detail = getattr(exc, "detail", None) or str(exc)
        raise ValueError(str(detail)) from exc


async def tool_list_api_definitions(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 30,
) -> dict[str, Any]:
    """列出项目下的接口定义（名称、方法、路径、描述、关联用例数）。"""
    ensure_permission(ctx, API_CASE_VIEW)
    page = max(page, 1)
    # 选择卡场景可能一次展示约百条；上限 100
    size = min(max(size, 1), 100)
    qs = ApiDefinition.filter(project_id=project_id, is_del=False)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(
            Q(name__icontains=kw)
            | Q(path__icontains=kw)
            | Q(description__icontains=kw)
            | Q(method__icontains=kw)
        )
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    api_ids = [r.id for r in rows]
    case_counts: dict[int, int] = {}
    if api_ids:
        from tortoise.functions import Count

        try:
            count_rows = (
                await ApiTestCase.filter(api_id__in=api_ids, is_del=False)
                .annotate(cnt=Count("id"))
                .group_by("api_id")
                .values("api_id", "cnt")
            )
            case_counts = {int(r["api_id"]): int(r["cnt"] or 0) for r in count_rows}
        except Exception:
            for aid in api_ids:
                case_counts[aid] = await ApiTestCase.filter(api_id=aid, is_del=False).count()
    items = []
    for api in rows:
        items.append(
            {
                "id": api.id,
                "name": api.name,
                "protocol": getattr(api, "protocol", "http") or "http",
                "method": api.method,
                "path": api.path,
                "description": (api.description or "")[:300],
                "base_url": api.base_url or "",
                "catalog_id": api.catalog_id,
                "case_count": case_counts.get(api.id, 0),
                "version": api.version,
                "update_time": api.update_time.strftime("%Y-%m-%d %H:%M:%S") if api.update_time else "",
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_api_categories(
    ctx: McpAuthContext,
    project_id: int,
) -> dict[str, Any]:
    """列出项目测试目录及接口/用例数量统计。"""
    ensure_permission(ctx, API_CASE_VIEW)
    cat_rows = await TestCatalog.filter(project_id=project_id, is_del=False).order_by("sort", "-id")
    items = []
    for cat in cat_rows:
        api_count = await ApiDefinition.filter(catalog_id=cat.id, project_id=project_id, is_del=False).count()
        case_count = await ApiTestCase.filter(catalog_id=cat.id, project_id=project_id, is_del=False).count()
        items.append(
            {
                "id": cat.id,
                "name": cat.name,
                "parent_id": cat.parent_id,
                "api_count": api_count,
                "api_case_count": case_count,
                "description": (cat.description or "")[:200],
            }
        )
    total_apis = await ApiDefinition.filter(project_id=project_id, is_del=False).count()
    uncategorized = await ApiDefinition.filter(
        project_id=project_id, is_del=False, catalog_id__isnull=True
    ).count()
    total_cases = await ApiTestCase.filter(project_id=project_id, is_del=False).count()
    total_suites = await ApiTestSuite.filter(project_id=project_id, is_del=False).count()
    return {
        "total_categories": len(items),
        "total_catalogs": len(items),
        "total_apis": total_apis,
        "uncategorized_api_count": uncategorized,
        "total_api_test_cases": total_cases,
        "total_api_suites": total_suites,
        "items": items,
    }


async def tool_list_api_test_cases(
    ctx: McpAuthContext,
    project_id: int,
    api_id: int | None = None,
    keyword: str = "",
    page: int = 1,
    size: int = 30,
) -> dict[str, Any]:
    """列出项目接口测试用例（关联接口方法/路径、断言数等摘要）。"""
    ensure_permission(ctx, API_CASE_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = ApiTestCase.filter(project_id=project_id, is_del=False)
    if api_id:
        qs = qs.filter(api_id=api_id)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(Q(name__icontains=kw))
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size).prefetch_related("api")
    items = []
    for case in rows:
        api = case.api
        items.append(
            {
                "id": case.id,
                "name": case.name,
                "api_id": case.api_id,
                "api_name": api.name if api else "",
                "method": api.method if api else "",
                "path": api.path if api else "",
                "priority": case.priority or "",
                "tags": case.tags if isinstance(case.tags, list) else [],
                "assertion_count": len(case.assertions) if isinstance(case.assertions, list) else 0,
                "catalog_id": case.catalog_id,
                "update_time": case.update_time.strftime("%Y-%m-%d %H:%M:%S") if case.update_time else "",
            }
        )
    return {
        "total": total,
        "page": page,
        "size": size,
        "api_id_filter": api_id,
        "items": items,
    }


async def tool_list_recent_failures(
    ctx: McpAuthContext, project_id: int, limit: int = 8
) -> dict[str, Any]:
    ensure_permission(ctx, AI_TEST_VIEW)
    limit = min(max(limit, 1), 20)
    items = await fetch_recent_failures(project_id, limit=limit)
    return {"items": items}


async def tool_get_api_definition(
    ctx: McpAuthContext,
    api_id: int,
    project_id: int,
    include_body: bool = False,
) -> dict[str, Any]:
    """获取单个接口定义详情（默认不含完整 body，避免 token 过大）。"""
    ensure_permission(ctx, API_CASE_VIEW)
    api = await ApiDefinition.get_or_none(id=api_id, project_id=project_id, is_del=False)
    if not api:
        raise ValueError("接口定义不存在")
    case_count = await ApiTestCase.filter(api_id=api_id, is_del=False).count()
    data: dict[str, Any] = {
        "id": api.id,
        "name": api.name,
        "method": api.method,
        "path": api.path,
        "description": api.description or "",
        "base_url": api.base_url or "",
        "catalog_id": api.catalog_id,
        "headers": api.headers or {},
        "params": api.params or [],
        "body_type": api.body_type or "json",
        "version": api.version,
        "case_count": case_count,
        "update_time": api.update_time.strftime("%Y-%m-%d %H:%M:%S") if api.update_time else "",
    }
    if include_body:
        data["body"] = api.body or {}
        data["body_fields"] = api.body_fields or []
        data["response_schema"] = api.response_schema or {}
    else:
        data["hint"] = "如需完整 body/响应结构，请设置 include_body=true"
    return data


async def tool_list_api_suites(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目接口测试套件（执行前可先查 suite_id）。"""
    ensure_permission(ctx, API_CASE_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = ApiTestSuite.filter(project_id=project_id, is_del=False)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(Q(name__icontains=kw))
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    items = []
    for suite in rows:
        case_count = await ApiSuiteCase.filter(suite_id=suite.id).count()
        env_name = ""
        if suite.env_id:
            env = await Environment.get_or_none(id=suite.env_id, is_del=False)
            env_name = env.name if env else ""
        items.append(
            {
                "id": suite.id,
                "name": suite.name,
                "env_id": suite.env_id,
                "env_name": env_name,
                "case_count": case_count,
                "update_time": suite.update_time.strftime("%Y-%m-%d %H:%M:%S") if suite.update_time else "",
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_ui_tasks(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目 UI 测试计划（Task）。"""
    ensure_permission(ctx, PROJECT_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = Task.filter(project_id=project_id, is_del=False)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(Q(name__icontains=kw))
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    items = []
    for task in rows:
        suite_count = await task.suites.filter(is_del=False).count()
        items.append(
            {
                "id": task.id,
                "name": task.name,
                "suite_count": suite_count,
                "username": task.username,
                "update_time": task.update_time.strftime("%Y-%m-%d %H:%M:%S") if task.update_time else "",
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_ui_cases(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目 Web UI 用例（摘要，不含 steps 全文）。"""
    ensure_permission(ctx, PROJECT_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = Case.filter(project_id=project_id, is_del=False)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(Q(name__icontains=kw))
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    items = []
    for case in rows:
        step_count = len(case.steps) if isinstance(case.steps, list) else 0
        items.append(
            {
                "id": case.id,
                "name": case.name,
                "level": case.level,
                "step_count": step_count,
                "username": case.username,
                "update_time": case.update_time.strftime("%Y-%m-%d %H:%M:%S") if case.update_time else "",
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_api_plans(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目接口测试计划（编排套件/用例，含 item 数量）。"""
    ensure_permission(ctx, API_PLAN_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = ApiTestPlan.filter(project_id=project_id, is_del=False)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(Q(name__icontains=kw) | Q(description__icontains=kw))
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    items = []
    for plan in rows:
        item_count = await ApiPlanItem.filter(plan_id=plan.id).count()
        env_name = ""
        if plan.env_id:
            env = await Environment.get_or_none(id=plan.env_id, is_del=False)
            env_name = env.name if env else ""
        items.append(
            {
                "id": plan.id,
                "name": plan.name,
                "description": (plan.description or "")[:200],
                "env_id": plan.env_id,
                "env_name": env_name,
                "item_count": item_count,
                "parallel": plan.parallel,
                "update_time": plan.update_time.strftime("%Y-%m-%d %H:%M:%S") if plan.update_time else "",
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_api_run_records(
    ctx: McpAuthContext,
    project_id: int,
    record_type: str = "",
    status: str = "",
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出接口执行记录（套件 + 测试计划合并，按时间倒序）。"""
    ensure_permission(ctx, API_RECORD_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    kw = (keyword or "").strip().lower()
    rt = (record_type or "").strip().lower()
    st = (status or "").strip().lower()
    unified: list[dict[str, Any]] = []

    if rt in ("", "suite"):
        suite_qs = ApiSuiteRunRecord.filter(project_id=project_id).exclude(trigger_type="plan")
        if st:
            suite_qs = suite_qs.filter(status=st)
        suite_rows = await suite_qs.order_by("-id").limit(100)
        for rec in suite_rows:
            suite = await ApiTestSuite.get_or_none(id=rec.suite_id)
            name = suite.name if suite else "未知套件"
            if kw and kw not in name.lower():
                continue
            unified.append(
                {
                    "id": rec.id,
                    "record_type": "suite",
                    "suite_id": rec.suite_id,
                    "name": name,
                    "status": rec.status,
                    "trigger_type": rec.trigger_type,
                    "total_cases": rec.total_cases,
                    "success_cases": rec.success_cases,
                    "failed_cases": rec.failed_cases,
                    "env_name": rec.env_name or "",
                    "run_by": rec.run_by,
                    "start_time": rec.start_time.strftime("%Y-%m-%d %H:%M:%S") if rec.start_time else "",
                }
            )

    if rt in ("", "plan"):
        plan_qs = ApiPlanRunRecord.filter(project_id=project_id)
        if st:
            plan_qs = plan_qs.filter(status=st)
        plan_rows = await plan_qs.order_by("-id").limit(100)
        for rec in plan_rows:
            plan = await ApiTestPlan.get_or_none(id=rec.plan_id)
            name = plan.name if plan else "未知计划"
            if kw and kw not in name.lower():
                continue
            unified.append(
                {
                    "id": rec.id,
                    "record_type": "plan",
                    "plan_id": rec.plan_id,
                    "name": name,
                    "status": rec.status,
                    "trigger_type": rec.trigger_type,
                    "total_cases": rec.total_cases,
                    "success_cases": rec.success_cases,
                    "failed_cases": rec.failed_cases,
                    "env_name": rec.env_name or "",
                    "run_by": rec.run_by,
                    "start_time": rec.start_time.strftime("%Y-%m-%d %H:%M:%S") if rec.start_time else "",
                }
            )

    unified.sort(key=lambda x: x.get("start_time") or "", reverse=True)
    total = len(unified)
    start = (page - 1) * size
    items = unified[start : start + size]
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_ui_run_records(
    ctx: McpAuthContext,
    project_id: int,
    task_id: int | None = None,
    keyword: str = "",
    status: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出 UI 测试计划执行记录（不含步骤详情）。"""
    ensure_permission(ctx, UI_RECORD_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = UiPlanExecution.filter(project_id=project_id, is_del=False)
    if task_id:
        qs = qs.filter(task_id=task_id)
    st = (status or "").strip()
    if st:
        qs = qs.filter(status=st)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(task__name__icontains=kw)
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size).prefetch_related("task")
    items = []
    for rec in rows:
        meta = _ui_trigger_meta(rec.env)
        items.append(
            {
                "id": rec.id,
                "task_id": rec.task_id,
                "task_name": rec.task.name if rec.task else "",
                "status": rec.status,
                "username": rec.username,
                "case_count": rec.case_count,
                "success": rec.success,
                "fail": rec.fail,
                "error": rec.error,
                "pass_rate": rec.pass_rate,
                "start_time": rec.start_time.strftime("%Y-%m-%d %H:%M:%S") if rec.start_time else "",
                "duration": rec.duration,
                **meta,
            }
        )
    return {"total": total, "page": page, "size": size, "task_id_filter": task_id, "items": items}


async def tool_list_perf_scenes(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出性能测试场景（压测配置摘要）。"""
    ensure_permission(ctx, PERF_SCENE_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = PerfScene.filter(project_id=project_id, is_del=False)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(Q(name__icontains=kw) | Q(description__icontains=kw))
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    items = []
    for scene in rows:
        cfg = scene.config if isinstance(scene.config, dict) else {}
        items.append(
            {
                "id": scene.id,
                "name": scene.name,
                "description": (scene.description or "")[:200],
                "case_item_count": len(scene.scene_items) if isinstance(scene.scene_items, list) else 0,
                "concurrent_users": cfg.get("concurrent_users"),
                "duration_seconds": cfg.get("duration_seconds"),
                "update_time": scene.update_time.strftime("%Y-%m-%d %H:%M:%S") if scene.update_time else "",
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_perf_records(
    ctx: McpAuthContext,
    project_id: int,
    scene_id: int | None = None,
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出性能测试执行记录（QPS、响应时间、错误率摘要）。"""
    ensure_permission(ctx, PERF_RECORD_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = PerfRecord.filter(project_id=project_id)
    if scene_id:
        qs = qs.filter(scene_id=scene_id)
    total = await qs.count()
    rows = await (
        qs.order_by("-id")
        .offset((page - 1) * size)
        .limit(size)
        .only(
            "id", "scene_id", "status", "qps", "avg_response_time", "error_rate",
            "total_requests", "run_by", "started_at", "duration",
        )
        .prefetch_related("scene")
        .all()
    )
    items = []
    for rec in rows:
        items.append(
            {
                "id": rec.id,
                "perf_scene_id": rec.scene_id,
                "scene_name": rec.scene.name if rec.scene else "",
                "status": rec.status,
                "qps": rec.qps,
                "avg_response_time": rec.avg_response_time,
                "error_rate": rec.error_rate,
                "total_requests": rec.total_requests,
                "run_by": rec.run_by,
                "started_at": rec.started_at.strftime("%Y-%m-%d %H:%M:%S") if rec.started_at else "",
                "duration": rec.duration,
            }
        )
    return {"total": total, "page": page, "size": size, "scene_id_filter": scene_id, "items": items}


async def tool_list_mock_apis(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目 Mock 接口配置。"""
    ensure_permission(ctx, API_MOCK_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = MockApi.filter(project_id=project_id, is_del=False)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(Q(name__icontains=kw) | Q(path__icontains=kw))
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    items = []
    for mock in rows:
        items.append(
            {
                "id": mock.id,
                "name": mock.name,
                "method": mock.method,
                "path": mock.path,
                "is_enabled": mock.is_enabled,
                "call_count": mock.call_count,
                "response_status": mock.response_status,
                "update_time": mock.update_time.strftime("%Y-%m-%d %H:%M:%S") if mock.update_time else "",
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_api_cron_jobs(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目接口定时任务（关联套件或测试计划）。"""
    ensure_permission(ctx, API_CRON_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = ApiCronJob.filter(project_id=project_id, is_del=False)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(name__icontains=kw)
    total = await qs.count()
    rows = await qs.order_by("-create_time").offset((page - 1) * size).limit(size)
    items = []
    for job in rows:
        target_type = ""
        target_name = ""
        if job.suite_id:
            target_type = "suite"
            suite = await ApiTestSuite.get_or_none(id=job.suite_id, is_del=False)
            target_name = suite.name if suite else ""
        elif job.plan_id:
            target_type = "plan"
            plan = await ApiTestPlan.get_or_none(id=job.plan_id, is_del=False)
            target_name = plan.name if plan else ""
        items.append(
            {
                "id": job.id,
                "name": job.name,
                "target_type": target_type,
                "target_name": target_name,
                "suite_id": job.suite_id,
                "plan_id": job.plan_id,
                "run_type": job.run_type,
                "state": job.state,
                "last_run_time": job.last_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.last_run_time else "",
                "last_run_status": job.last_run_status or "",
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_ui_suites(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目 Web UI 测试套件（摘要）。"""
    ensure_permission(ctx, UI_SUITE_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = Suite.filter(project_id=project_id, is_del=False)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(Q(name__icontains=kw))
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    items = []
    for suite in rows:
        case_count = await Step.filter(suite_id=suite.id).count()
        items.append(
            {
                "id": suite.id,
                "name": suite.name,
                "suite_type": suite.suite_type,
                "case_count": case_count,
                "username": suite.username,
                "update_time": suite.update_time.strftime("%Y-%m-%d %H:%M:%S") if suite.update_time else "",
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_ui_cron_jobs(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目 UI 定时任务（关联 UI 测试计划）。"""
    ensure_permission(ctx, UI_CRON_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = Cronjob.filter(project_id=project_id, is_del=False)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(Q(name__icontains=kw))
    total = await qs.count()
    rows = await qs.order_by("-create_time").offset((page - 1) * size).limit(size)
    items = []
    for job in rows:
        task = await Task.get_or_none(id=job.task_id, is_del=False)
        env = await Environment.get_or_none(id=job.env_id, is_del=False)
        items.append(
            {
                "id": job.id,
                "name": job.name,
                "task_id": job.task_id,
                "task_name": task.name if task else "",
                "env_name": env.name if env else "",
                "run_type": job.run_type,
                "state": job.state,
                "username": job.username,
                "update_time": job.update_time.strftime("%Y-%m-%d %H:%M:%S") if job.update_time else "",
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_perf_cron_jobs(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目性能测试定时任务。"""
    ensure_permission(ctx, PERF_CRON_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = PerfCronJob.filter(project_id=project_id, is_del=False)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(name__icontains=kw)
    total = await qs.count()
    rows = await qs.order_by("-create_time").offset((page - 1) * size).limit(size)
    items = []
    for job in rows:
        scene = await PerfScene.get_or_none(id=job.scene_id, is_del=False)
        items.append(
            {
                "id": job.id,
                "name": job.name,
                "perf_scene_id": job.scene_id,
                "scene_name": scene.name if scene else "",
                "run_type": job.run_type,
                "state": job.state,
                "last_run_time": job.last_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.last_run_time else "",
                "last_run_status": job.last_run_status or "",
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_perf_workers(
    ctx: McpAuthContext,
    project_id: int,
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目性能测试 Worker 节点（不含 token）。"""
    ensure_permission(ctx, PERF_WORKER_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = PerfWorker.filter(project_id=project_id)
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    items = []
    for worker in rows:
        items.append(
            {
                "id": worker.id,
                "name": worker.name,
                "host": worker.host,
                "port": worker.port,
                "status": worker.status,
                "max_concurrent": worker.max_concurrent,
                "current_record_id": worker.current_record_id,
                "last_heartbeat": worker.last_heartbeat.strftime("%Y-%m-%d %H:%M:%S")
                if worker.last_heartbeat
                else "",
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_data_factory_datasources(
    ctx: McpAuthContext,
    project_id: int,
    environment_id: Optional[int] = None,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出数据工厂数据源（只读，不含密码明文）。"""
    ensure_permission(ctx, DATA_FACTORY_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = EnvDatasource.filter(project_id=project_id, is_del=False)
    if environment_id:
        qs = qs.filter(environment_id=environment_id)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(name__icontains=kw)
    total = await qs.count()
    rows = await qs.order_by("-update_time").offset((page - 1) * size).limit(size)
    items = []
    for ds in rows:
        env = await Environment.get_or_none(id=ds.environment_id)
        items.append(datasource_to_dict(ds, env.name if env else ""))
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_sql_templates(
    ctx: McpAuthContext,
    project_id: int,
    environment_id: Optional[int] = None,
    template_type: str = "",
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出数据工厂 SQL 模板（只读）。"""
    ensure_permission(ctx, DATA_FACTORY_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = SqlTemplate.filter(project_id=project_id, is_del=False)
    if environment_id:
        qs = qs.filter(environment_id=environment_id)
    ttype = (template_type or "").strip()
    if ttype:
        qs = qs.filter(template_type=ttype)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(Q(name__icontains=kw) | Q(description__icontains=kw))
    total = await qs.count()
    rows = await qs.order_by("-update_time").offset((page - 1) * size).limit(size)
    items = []
    for tpl in rows:
        ds = await EnvDatasource.get_or_none(id=tpl.datasource_id)
        env_name = ""
        if tpl.environment_id:
            env = await Environment.get_or_none(id=tpl.environment_id)
            env_name = env.name if env else ""
        item = sql_template_to_dict(tpl, ds.name if ds else "", env_name)
        sql_text = item.get("sql_text") or ""
        if len(sql_text) > 500:
            item["sql_text"] = sql_text[:500] + "…"
            item["sql_text_truncated"] = True
        items.append(item)
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_get_sql_template(
    ctx: McpAuthContext,
    template_id: int,
    project_id: Optional[int] = None,
) -> dict[str, Any]:
    """获取 SQL 模板详情（只读，不含数据源密码）。

    project_id 可选：助手侧会自动注入当前项目并校验成员与归属。
    """
    ensure_permission(ctx, DATA_FACTORY_VIEW)
    tpl = await SqlTemplate.get_or_none(id=template_id, is_del=False)
    if not tpl:
        return {"error": "模板不存在"}
    if project_id is not None:
        from app.core.platform.project_access import PROJECT_ROLE_VIEWER
        from brickcore_assist.skills.access import require_project_access

        await require_project_access(ctx, int(project_id), min_role=PROJECT_ROLE_VIEWER)
        env_pid = None
        if tpl.environment_id:
            env = await Environment.get_or_none(id=tpl.environment_id)
            env_pid = getattr(env, "project_id", None) if env else None
        if env_pid is not None and int(env_pid) != int(project_id):
            return {"error": "模板不属于当前项目"}
    ds = await EnvDatasource.get_or_none(id=tpl.datasource_id)
    env_name = ""
    if tpl.environment_id:
        env = await Environment.get_or_none(id=tpl.environment_id)
        env_name = env.name if env else ""
    data = sql_template_to_dict(tpl, ds.name if ds else "", env_name)
    if ds:
        ds_env = await Environment.get_or_none(id=ds.environment_id)
        data["datasource"] = datasource_to_dict(ds, ds_env.name if ds_env else "")
    return data


async def tool_query_datasource(
    ctx: McpAuthContext,
    project_id: int,
    datasource_id: int,
    statement: str,
    max_rows: Optional[int] = None,
    variables: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """对数据工厂数据源执行只读查询（禁止写；结果截断供模型阅读）。"""
    from app.core.db.db_drivers import is_write_command
    from app.core.db.db_factory_service import (
        execute_sql_on_datasource,
        get_datasource_by_id,
        resolve_env_default_df_worker_id,
    )
    from app.core.platform.project_access import PROJECT_ROLE_VIEWER
    from brickcore_assist.skills.access import require_project_access

    ensure_permission(ctx, DATA_FACTORY_VIEW)
    await require_project_access(ctx, int(project_id), min_role=PROJECT_ROLE_VIEWER)

    sql = (statement or "").strip()
    if not sql:
        return {"success": False, "error": "statement 不能为空", "rows": [], "row_count": 0, "readonly": True}

    ds = await get_datasource_by_id(int(datasource_id), int(project_id))
    if not ds or not ds.is_enabled:
        return {"success": False, "error": "数据源不存在或未启用", "rows": [], "row_count": 0, "readonly": True}

    db_type = (ds.db_type or "mysql").lower()
    if is_write_command(sql, db_type=db_type):
        return {
            "success": False,
            "error": "写操作不可通过助手/MCP 静默执行；请到数据工厂「查询控制台」确认后执行",
            "rows": [],
            "row_count": 0,
            "readonly": True,
            "is_write": True,
            "navigate": f"/api-data-factory?tab=console&datasource_id={ds.id}",
        }

    model_hard_cap = 50
    try:
        req = int(max_rows) if max_rows is not None else 30
    except (TypeError, ValueError):
        req = 30
    limit = max(1, min(req, model_hard_cap, int(ds.max_rows or 100)))

    worker_id = await resolve_env_default_df_worker_id(ds.environment_id)
    out = await execute_sql_on_datasource(
        ds,
        sql,
        variables or {},
        for_assertion=True,
        max_rows=limit,
        worker_id=worker_id,
    )
    rows = out.get("rows") if isinstance(out.get("rows"), list) else []
    # 单元格过长截断，避免撑爆模型上下文
    clipped: list[dict[str, Any]] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        item: dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, str) and len(v) > 200:
                item[str(k)] = v[:199] + "…"
            else:
                item[str(k)] = v
        clipped.append(item)

    return {
        "success": bool(out.get("success")),
        "error": out.get("error"),
        "columns": out.get("columns") or (list(clipped[0].keys()) if clipped else []),
        "rows": clipped,
        "row_count": len(clipped),
        "truncated": bool(out.get("truncated")) or len(rows) > len(clipped),
        "max_rows_applied": limit,
        "elapsed_ms": out.get("elapsed_ms"),
        "sql": out.get("sql"),
        "datasource_id": ds.id,
        "datasource_name": ds.name,
        "db_type": db_type,
        "readonly": True,
        "is_write": False,
        "via_worker": bool(out.get("via_worker")),
        "worker_id": out.get("worker_id"),
        "navigate": f"/api-data-factory?tab=console&datasource_id={ds.id}",
    }


async def _resolve_app_case(
    project_id: int,
    *,
    case_id: int | None = None,
    case_name: str | None = None,
) -> AppCase:
    if case_id:
        case = await AppCase.get_or_none(id=case_id, is_del=False, project_id=project_id)
        if not case:
            raise ValueError(f"App 用例不存在: case_id={case_id}")
        return case
    name = (case_name or "").strip()
    if not name:
        raise ValueError("请指定 case_id 或 case_name")
    exact = await AppCase.filter(project_id=project_id, is_del=False, name=name).first()
    if exact:
        return exact
    partial_list = list(await AppCase.filter(project_id=project_id, is_del=False, name__icontains=name).limit(6))
    if not partial_list:
        raise ValueError(f"未找到名称包含「{name}」的 App 用例")
    if len(partial_list) == 1:
        return partial_list[0]
    hints = ", ".join(f"#{c.id}:{c.name}" for c in partial_list[:5])
    raise ValueError(f"名称「{name}」匹配到多条 App 用例，请指定 case_id：{hints}")


async def tool_list_app_cases(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目 App 用例（摘要，不含 steps 全文）。"""
    ensure_permission(ctx, APP_CASE_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = AppCase.filter(project_id=project_id, is_del=False)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(Q(name__icontains=kw) | Q(description__icontains=kw))
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    items = []
    for case in rows:
        step_count = len(case.steps) if isinstance(case.steps, list) else 0
        items.append(
            {
                "id": case.id,
                "name": case.name,
                "level": case.level,
                "driver_mode": case.driver_mode,
                "step_count": step_count,
                "username": case.username,
                "update_time": case.update_time.strftime("%Y-%m-%d %H:%M:%S") if case.update_time else "",
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_app_suites(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目 App 测试套件（摘要）。"""
    ensure_permission(ctx, APP_SUITE_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = AppSuite.filter(project_id=project_id, is_del=False)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(Q(name__icontains=kw))
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    items = []
    for suite in rows:
        case_count = await AppSuiteStep.filter(suite_id=suite.id, is_del=False).count()
        items.append(
            {
                "id": suite.id,
                "name": suite.name,
                "case_count": case_count,
                "username": suite.username,
                "update_time": suite.update_time.strftime("%Y-%m-%d %H:%M:%S") if suite.update_time else "",
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_app_plans(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目 App 测试计划。"""
    ensure_permission(ctx, APP_PLAN_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = AppPlan.filter(project_id=project_id, is_del=False)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(Q(name__icontains=kw))
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size).prefetch_related("suites")
    items = []
    for plan in rows:
        suites = await plan.suites.all()
        suite_count = len(suites)
        items.append(
            {
                "id": plan.id,
                "name": plan.name,
                "suite_count": suite_count,
                "parallel": plan.parallel,
                "record_video": plan.record_video,
                "username": plan.username,
                "update_time": plan.update_time.strftime("%Y-%m-%d %H:%M:%S") if plan.update_time else "",
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_app_run_records(
    ctx: McpAuthContext,
    project_id: int,
    record_type: str = "",
    keyword: str = "",
    status: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出 App 执行记录（计划 + 套件合并，按时间倒序）。"""
    ensure_permission(ctx, APP_RECORD_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    kw = (keyword or "").strip().lower()
    rt = (record_type or "").strip().lower()
    st = (status or "").strip().lower()
    unified: list[dict[str, Any]] = []

    if rt in ("", "suite"):
        suite_qs = AppSuiteExecution.filter(is_del=False, suite__project_id=project_id).prefetch_related("suite")
        if st:
            suite_qs = suite_qs.filter(status=st)
        for rec in await suite_qs.order_by("-id").limit(100):
            suite = rec.suite
            name = suite.name if suite else "未知套件"
            if kw and kw not in name.lower():
                continue
            unified.append(
                {
                    "id": rec.id,
                    "record_type": "suite",
                    "suite_id": rec.suite_id,
                    "name": name,
                    "status": rec.status,
                    "pass_rate": rec.pass_rate,
                    "username": rec.username,
                    "start_time": rec.start_time.strftime("%Y-%m-%d %H:%M:%S") if rec.start_time else "",
                }
            )

    if rt in ("", "plan"):
        plan_qs = AppPlanExecution.filter(project_id=project_id, is_del=False).prefetch_related("plan")
        if st:
            plan_qs = plan_qs.filter(status=st)
        for rec in await plan_qs.order_by("-id").limit(100):
            plan = rec.plan
            name = plan.name if plan else "未知计划"
            if kw and kw not in name.lower():
                continue
            unified.append(
                {
                    "id": rec.id,
                    "record_type": "plan",
                    "plan_id": rec.plan_id,
                    "name": name,
                    "status": rec.status,
                    "pass_rate": rec.pass_rate,
                    "username": rec.username,
                    "start_time": rec.start_time.strftime("%Y-%m-%d %H:%M:%S") if rec.start_time else "",
                }
            )

    unified.sort(key=lambda x: x.get("start_time") or "", reverse=True)
    total = len(unified)
    start = (page - 1) * size
    items = unified[start : start + size]
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_list_app_cron_jobs(
    ctx: McpAuthContext,
    project_id: int,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目 App 定时任务。"""
    ensure_permission(ctx, APP_PLAN_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 50)
    qs = AppCronJob.filter(project_id=project_id, is_del=False)
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(Q(name__icontains=kw))
    total = await qs.count()
    rows = await qs.order_by("-create_time").offset((page - 1) * size).limit(size)
    items = []
    for job in rows:
        suite = await AppSuite.get_or_none(id=job.suite_id, is_del=False) if job.suite_id else None
        plan = await AppPlan.get_or_none(id=job.plan_id, is_del=False) if job.plan_id else None
        env = await Environment.get_or_none(id=job.env_id, is_del=False)
        items.append(
            {
                "id": job.id,
                "name": job.name,
                "target_type": "plan" if job.plan_id else "suite",
                "plan_name": plan.name if plan else "",
                "suite_name": suite.name if suite else "",
                "env_name": env.name if env else "",
                "run_type": job.run_type,
                "state": job.state,
                "last_run_time": job.last_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.last_run_time else "",
                "last_run_status": job.last_run_status or "",
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_preview_run_app_case(
    ctx: McpAuthContext,
    project_id: int,
    env_id: int,
    device_id: str,
    case_id: int | None = None,
    case_name: str | None = None,
) -> dict[str, Any]:
    ensure_permission(ctx, APP_CASE_EXECUTE)
    await _require_project_member(ctx, project_id)
    case = await _resolve_app_case(project_id, case_id=case_id, case_name=case_name)
    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise ValueError("运行环境不存在")
    if not (device_id or "").strip():
        raise ValueError("请指定 device_id（在线 App Runner，可在设备管理查看 app_udid）")
    step_count = len(case.steps) if isinstance(case.steps, list) else 0
    if step_count == 0:
        raise ValueError("用例没有步骤，无法执行")
    impact = {
        "project_id": project_id,
        "case_id": case.id,
        "case_name": case.name,
        "driver_mode": case.driver_mode,
        "step_count": step_count,
        "env_id": env_id,
        "env_name": env.name,
        "device_id": device_id.strip(),
        "warning": "将触发单条 App 用例执行，占用 Runner 与 Android 设备",
    }
    confirm_token = await create_confirm_token(
        "run_app_case",
        {
            "case_id": case.id,
            "env_id": env_id,
            "device_id": device_id.strip(),
            "project_id": project_id,
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_run_app_case 并传入 confirm_token",
    }


async def tool_confirm_run_app_case(
    ctx: McpAuthContext,
    confirm_token: str,
    case_id: int,
    env_id: int | None = None,
    device_id: str | None = None,
    project_id: int | None = None,
) -> dict[str, Any]:
    ensure_permission(ctx, APP_CASE_EXECUTE)
    payload = await consume_confirm_token(confirm_token, "run_app_case", ctx.username)
    if int(payload.get("case_id", 0)) != case_id:
        raise ValueError("case_id 与确认 Token 不匹配")
    resolved_env_id = env_id or int(payload.get("env_id") or 0)
    resolved_device = (device_id or payload.get("device_id") or "").strip()
    resolved_project_id = int(project_id or payload.get("project_id") or 0)
    case = await AppCase.get_or_none(id=case_id, is_del=False)
    if not case:
        raise ValueError("App 用例不存在")
    await _require_project_member(ctx, case.project_id)
    if resolved_project_id and case.project_id != resolved_project_id:
        raise ValueError("用例不属于当前项目")
    from tortoise import transactions
    from app.routers.app.exec import AppExecutionService, expand_app_steps
    from app.modules.app.app_execution_env import build_case_env

    env_payload: dict[str, Any] = {}
    suite_payload: dict[str, Any] = {}
    case_execution_id: int | None = None
    async with transactions.in_transaction():
        env = await Environment.get_or_none(id=resolved_env_id, is_del=False)
        if not env:
            raise ValueError("运行环境不存在")
        device = await Device.get_or_none(id=resolved_device, is_del=False)
        if not device:
            raise ValueError("设备不存在")
        item = AppRunForm(
            env_id=resolved_env_id,
            device_id=resolved_device,
            username=ctx.username,
            trigger_source=ASSISTANT_TRIGGER,
        )
        env_payload = AppExecutionService.with_trigger_source(
            await AppExecutionService.build_env_payload(env, case.project_id, device, item),
            ASSISTANT_TRIGGER,
        )
        env_payload = build_case_env(env_payload, case, trigger_source=ASSISTANT_TRIGGER)
        case_execution = await AppCaseExecution.create(
            case=case, username=ctx.username, env=env_payload, is_del=False
        )
        case_execution_id = case_execution.id
        expanded_steps = await expand_app_steps(case.steps or [], case.project_id)
        suite_payload = {
            "engine_type": "app",
            "id": case.id,
            "name": case.name,
            "case_execution_id": case_execution.id,
            "pre_actions": [],
            "username": ctx.username,
            "cases": [
                {
                    "execution_id": case_execution.id,
                    "id": case.id,
                    "name": case.name,
                    "skip": False,
                    "driver_mode": case.driver_mode,
                    "steps": expanded_steps,
                }
            ],
        }
    dispatched = await AppExecutionService.dispatch_to_device(env_payload, suite_payload, resolved_device)
    return {
        "case_id": case_id,
        "case_name": case.name,
        "execution_id": case_execution_id,
        "dispatched": dispatched,
        "message": "App 用例已加入执行队列" if dispatched else "记录已创建，暂无支持 App 的在线 Runner 或未检测到 Android 设备",
        "hint": (
            f"可说「查询 App 用例执行记录 {case_execution_id}」查看结果"
            if case_execution_id
            else "请在 App 执行记录中查看"
        ),
    }


async def tool_preview_run_app_suite(
    ctx: McpAuthContext,
    suite_id: int,
    env_id: int,
    device_id: str,
) -> dict[str, Any]:
    ensure_permission(ctx, APP_SUITE_EXECUTE)
    suite = await AppSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise ValueError("App 套件不存在")
    await _require_project_member(ctx, suite.project_id)
    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise ValueError("运行环境不存在")
    if not (device_id or "").strip():
        raise ValueError("请指定 device_id（在线 App Runner）")
    case_count = await AppSuiteStep.filter(suite_id=suite_id, is_del=False).count()
    if case_count == 0:
        raise ValueError("套件中没有用例")
    impact = {
        "suite_id": suite_id,
        "suite_name": suite.name,
        "project_id": suite.project_id,
        "case_count": case_count,
        "env_id": env_id,
        "env_name": env.name,
        "device_id": device_id.strip(),
        "warning": "将触发 App 套件执行，占用 Runner 与 Android 设备",
    }
    confirm_token = await create_confirm_token(
        "run_app_suite",
        {"suite_id": suite_id, "env_id": env_id, "device_id": device_id.strip()},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_run_app_suite 并传入 confirm_token",
    }


async def tool_confirm_run_app_suite(
    ctx: McpAuthContext,
    confirm_token: str,
    suite_id: int,
    env_id: Optional[int] = None,
    device_id: Optional[str] = None,
) -> dict[str, Any]:
    ensure_permission(ctx, APP_SUITE_EXECUTE)
    suite = await AppSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise ValueError("App 套件不存在")
    await _require_project_member(ctx, suite.project_id)
    payload = await consume_confirm_token(confirm_token, "run_app_suite", ctx.username)
    if int(payload.get("suite_id", 0)) != suite_id:
        raise ValueError("suite_id 与确认 Token 不匹配")
    from app.routers.app.exec import execute_app_suite_internal

    result = await execute_app_suite_internal(
        suite_id,
        AppRunForm(
            env_id=env_id or int(payload.get("env_id") or 0),
            device_id=(device_id or payload.get("device_id") or "").strip(),
            username=ctx.username,
            trigger_source=ASSISTANT_TRIGGER,
        ),
        ctx.username,
    )
    return {
        "result": result,
        "suite_execution_id": result.get("execution_id"),
        "message": result.get("msg") if isinstance(result, dict) else str(result),
    }


async def tool_preview_run_app_plan(
    ctx: McpAuthContext,
    plan_id: int,
    env_id: int,
    device_id: str,
) -> dict[str, Any]:
    ensure_permission(ctx, APP_PLAN_EXECUTE)
    plan = await AppPlan.get_or_none(id=plan_id, is_del=False)
    if not plan:
        raise ValueError("App 计划不存在")
    await _require_project_member(ctx, plan.project_id)
    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise ValueError("运行环境不存在")
    if not (device_id or "").strip():
        raise ValueError("请指定 device_id（在线 App Runner）")
    await plan.fetch_related("suites")
    suite_count = len([s for s in plan.suites if not s.is_del])
    if suite_count == 0:
        raise ValueError("计划中没有套件")
    impact = {
        "plan_id": plan_id,
        "plan_name": plan.name,
        "project_id": plan.project_id,
        "suite_count": suite_count,
        "parallel": bool(plan.parallel),
        "env_id": env_id,
        "env_name": env.name,
        "device_id": device_id.strip(),
        "warning": "将触发 App 计划执行，可能占用多台 Runner/设备",
    }
    confirm_token = await create_confirm_token(
        "run_app_plan",
        {"plan_id": plan_id, "env_id": env_id, "device_id": device_id.strip()},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_run_app_plan 并传入 confirm_token",
    }


async def tool_confirm_run_app_plan(
    ctx: McpAuthContext,
    confirm_token: str,
    plan_id: int,
    env_id: Optional[int] = None,
    device_id: Optional[str] = None,
) -> dict[str, Any]:
    ensure_permission(ctx, APP_PLAN_EXECUTE)
    plan = await AppPlan.get_or_none(id=plan_id, is_del=False)
    if not plan:
        raise ValueError("App 计划不存在")
    await _require_project_member(ctx, plan.project_id)
    payload = await consume_confirm_token(confirm_token, "run_app_plan", ctx.username)
    if int(payload.get("plan_id", 0)) != plan_id:
        raise ValueError("plan_id 与确认 Token 不匹配")
    from app.modules.app.app_plan_runner import execute_app_plan

    result = await execute_app_plan(
        plan,
        env_id=env_id or int(payload.get("env_id") or 0),
        username=ctx.username,
        run_form=AppRunForm(
            env_id=env_id or int(payload.get("env_id") or 0),
            device_id=(device_id or payload.get("device_id") or "").strip(),
            username=ctx.username,
            trigger_source=ASSISTANT_TRIGGER,
        ),
        device_id=(device_id or payload.get("device_id") or "").strip(),
        trigger_source=ASSISTANT_TRIGGER,
    )
    return {
        "result": result,
        "plan_execution_id": result.get("execution_id"),
        "message": result.get("msg") if isinstance(result, dict) else str(result),
    }


# ---------- W4：Skill MCP（list / preview / confirm）----------


def _assist_premium_denied() -> dict[str, Any]:
    from app.modules.assistant.assist_gateway import (
        ASSIST_PREMIUM_REQUIRED_CODE,
        DOC_PATH,
        get_assist_premium_info,
    )

    info = get_assist_premium_info()
    return {
        "ok": False,
        "code": ASSIST_PREMIUM_REQUIRED_CODE,
        "message": info.get("message") or "需要安装并启用 BrickCore Assist 扩展包",
        "mode": info.get("mode") or "lite",
        "doc": DOC_PATH,
    }


async def tool_list_skills(ctx: McpAuthContext) -> dict[str, Any]:
    """列出内置 Skill 清单（无包时返回空列表 + mode=lite）。"""
    ensure_permission(ctx, AI_TEST_VIEW)
    from app.modules.assistant.assist_gateway import get_assist_premium_info

    info = get_assist_premium_info()
    if not info.get("ready"):
        return {
            "skills": [],
            "mode": info.get("mode") or "lite",
            "message": info.get("message") or "当前为基础模式，Skill 列表为空",
        }
    from brickcore_assist.skills.runner import list_skills

    skills = list(list_skills() or [])
    mcp_codes = {
        "requirement_to_test_points",
        "api_definition_to_cases",
        "test_points_to_functional_cases",
        "mock_response_generate",
        "perf_scene_from_nl",
        "browser_lab_to_ui_case",
        "ui_steps_from_nl",
        "report_narrative",
        "qa_eval_assist",
        "curl_to_cases",
        "ui_locator_suggest",
        "nl_to_sql_template",
    }
    enriched = []
    for s in skills:
        item = dict(s) if isinstance(s, dict) else {"code": str(s)}
        code = str(item.get("code") or "")
        modes = list(item.get("entry_modes") or [])
        item["mcp_executable"] = code in mcp_codes and "mcp" in modes
        enriched.append(item)
    return {"skills": enriched, "mode": "standard"}


async def tool_preview_run_skill(
    ctx: McpAuthContext,
    skill_code: str,
    project_id: int,
    requirement_id: Optional[int] = None,
    api_definition_id: Optional[int] = None,
    target_id: Optional[int] = None,
    count: Optional[int] = None,
    catalog_id: Optional[int] = None,
    query: Optional[str] = None,
    prompt: Optional[str] = None,
    method: Optional[str] = None,
    path: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    response_status: Optional[int] = None,
    suite_id: Optional[int] = None,
    case_ids: Optional[list[int]] = None,
    task_id: Optional[int] = None,
    case_name: Optional[str] = None,
    page_url: Optional[str] = None,
    device_id: Optional[str] = None,
    report_type: Optional[str] = None,
    record_id: Optional[int] = None,
    set_id: Optional[int] = None,
    test_point_ids: Optional[list[int]] = None,
    curl: Optional[str] = None,
    response_sample: Optional[str] = None,
    content: Optional[str] = None,
    requirement_name: Optional[str] = None,
    raw_element: Optional[str] = None,
    intent: Optional[str] = None,
    datasource_id: Optional[int] = None,
    schema_hint: Optional[str] = None,
    template_type: Optional[str] = None,
) -> dict[str, Any]:
    """预览运行生成类 Skill；返回 confirm_token，需再 confirm_run_skill。"""
    from app.modules.assistant.assist_gateway import assist_premium_ready

    if not assist_premium_ready():
        return _assist_premium_denied()
    code = (skill_code or "").strip()
    allowed = {
        "requirement_to_test_points",
        "api_definition_to_cases",
        "test_points_to_functional_cases",
        "mock_response_generate",
        "perf_scene_from_nl",
        "browser_lab_to_ui_case",
        "ui_steps_from_nl",
        "report_narrative",
        "qa_eval_assist",
        "curl_to_cases",
        "ui_locator_suggest",
        "nl_to_sql_template",
    }
    if code not in allowed:
        raise ValueError("preview_run_skill 不支持该 skill_code")
    from brickcore_assist.skills.policy import skill_required_permission

    req_perm = skill_required_permission(code) or AI_TEST_EXECUTE
    ensure_permission(ctx, req_perm)
    from brickcore_assist import api as assist_api

    # 只读定位建议：无 confirm；生成类仍走 preview
    run_mode = "direct" if code == "ui_locator_suggest" else "preview"
    return await assist_api.run_skill(
        ctx=ctx,
        skill_code=code,
        project_id=int(project_id),
        requirement_id=requirement_id,
        api_definition_id=api_definition_id,
        target_id=target_id,
        count=count,
        catalog_id=catalog_id,
        query=query,
        prompt=prompt,
        method=method,
        path=path,
        name=name,
        description=description,
        response_status=response_status,
        suite_id=suite_id,
        case_ids=case_ids,
        task_id=task_id,
        case_name=case_name,
        page_url=page_url,
        device_id=device_id,
        report_type=report_type,
        record_id=record_id,
        set_id=set_id,
        test_point_ids=test_point_ids,
        curl=curl,
        response_sample=response_sample,
        content=content,
        requirement_name=requirement_name,
        raw_element=raw_element,
        intent=intent,
        datasource_id=datasource_id,
        schema_hint=schema_hint,
        template_type=template_type,
        entry_source="mcp",
        run_mode=run_mode,
        ai_config_id=None,
        session_id=None,
    )


async def tool_confirm_run_skill(
    ctx: McpAuthContext,
    confirm_token: str,
    skill_code: str = "",
    project_id: Optional[int] = None,
    requirement_id: Optional[int] = None,
    api_definition_id: Optional[int] = None,
    task_id: Optional[int] = None,
    set_id: Optional[int] = None,
    target_id: Optional[int] = None,
    report_type: Optional[str] = None,
    record_id: Optional[int] = None,
) -> dict[str, Any]:
    """确认执行 Skill 写操作。"""
    from app.core.integration.mcp_confirm import peek_confirm_token
    from app.modules.assistant.assist_gateway import assist_premium_ready

    if not assist_premium_ready():
        return _assist_premium_denied()
    ensure_permission(ctx, AI_TEST_EXECUTE)

    peeked = await peek_confirm_token(confirm_token, ctx.username)
    payload = peeked.get("payload") if isinstance(peeked.get("payload"), dict) else {}
    token_code = str(payload.get("skill_code") or peeked.get("action") or "").strip()
    client_code = (skill_code or "").strip()

    def _norm(code: str) -> str:
        c = (code or "").strip()
        return c[6:] if c.startswith("skill_") else c

    if client_code and token_code and _norm(client_code) != _norm(token_code):
        raise ValueError(
            f"skill_code 与确认 Token 不匹配（token={token_code}，传入={client_code}）"
        )

    code = token_code or client_code
    from app.modules.assistant.assistant_tools import _confirm_run_skill

    return await _confirm_run_skill(
        ctx,
        code if str(code).startswith("skill_") else f"skill_{_norm(code)}",
        confirm_token,
        {
            "skill_code": _norm(code),
            "project_id": project_id,
            "requirement_id": requirement_id,
            "api_definition_id": api_definition_id,
            "task_id": task_id,
            "set_id": set_id,
            "target_id": target_id,
            "report_type": report_type,
            "record_id": record_id,
        },
    )


# Wave A：Browser Lab / UI Agent 任务闭环（实现见 tools_agent_jobs）
from app.mcp.tools_agent_jobs import (  # noqa: E402
    tool_confirm_convert_browser_lab_to_ui_case,
    tool_confirm_rerun_browser_lab_task,
    tool_confirm_stop_browser_lab_task,
    tool_confirm_stop_ui_agent_job,
    tool_get_browser_lab_case,
    tool_get_browser_lab_task,
    tool_get_browser_lab_task_report,
    tool_get_ui_agent_job,
    tool_get_ui_agent_job_report,
    tool_list_browser_lab_cases,
    tool_list_browser_lab_tasks,
    tool_list_ui_agent_jobs,
    tool_preview_convert_browser_lab_to_ui_case,
    tool_preview_rerun_browser_lab_task,
    tool_preview_stop_browser_lab_task,
    tool_preview_stop_ui_agent_job,
)

# Wave B：AI 配置 / 站内信 / 通知
from app.mcp.tools_ai_notify import (  # noqa: E402
    tool_confirm_mark_inbox_all_read,
    tool_confirm_mark_inbox_read,
    tool_confirm_test_ai_config,
    tool_get_ai_config,
    tool_get_ai_usage_logs,
    tool_get_inbox_preferences,
    tool_get_inbox_unread_count,
    tool_list_ai_config_select_options,
    tool_list_ai_configs,
    tool_list_ai_scene_bindings,
    tool_list_inbox_messages,
    tool_list_notification_configs,
    tool_list_notification_logs,
    tool_preview_mark_inbox_all_read,
    tool_preview_mark_inbox_read,
    tool_preview_test_ai_config,
)

# Wave C：鉴权 / 调试 / 执行详情
from app.mcp.tools_exec_detail import (  # noqa: E402
    tool_confirm_debug_api_definition,
    tool_confirm_refresh_api_auth_token,
    tool_confirm_test_api_auth_config,
    tool_debug_api_definition,
    tool_get_api_auth_config,
    tool_get_api_case_execution_detail,
    tool_get_app_case_execution_detail,
    tool_get_execution_report,
    tool_get_perf_record_detail,
    tool_get_ui_case_execution_detail,
    tool_list_api_auth_configs,
    tool_preview_debug_api_definition,
    tool_preview_refresh_api_auth_token,
    tool_preview_test_api_auth_config,
)

# Wave E：项目设置 / 环境 / 设备 / 成员
from app.mcp.tools_project_settings import (  # noqa: E402
    tool_get_device_detail,
    tool_get_environment_detail,
    tool_get_project_execution_settings,
    tool_get_project_settings_overview,
    tool_list_devices,
    tool_list_project_members,
)

# Wave D：目录 + 显式创建
from app.mcp.tools_catalog import (  # noqa: E402
    tool_confirm_create_api_definition,
    tool_confirm_create_api_test_case,
    tool_confirm_create_catalog,
    tool_confirm_create_ui_case,
    tool_confirm_move_assets_to_catalog,
    tool_get_catalog_detail,
    tool_list_catalog_assets,
    tool_preview_create_api_definition,
    tool_preview_create_api_test_case,
    tool_preview_create_catalog,
    tool_preview_create_ui_case,
    tool_preview_move_assets_to_catalog,
)

# Wave F：日志 / 看板 / 搜索 / 测试管理
from app.mcp.tools_wave_f import (  # noqa: E402
    tool_confirm_create_defect,
    tool_confirm_create_release,
    tool_confirm_create_review,
    tool_confirm_finalize_review,
    tool_confirm_submit_review_decision,
    tool_confirm_transition_defect,
    tool_confirm_transition_release,
    tool_get_dashboard_summary,
    tool_get_defect,
    tool_get_release,
    tool_get_review,
    tool_list_assistant_traces,
    tool_list_defects,
    tool_list_operation_logs,
    tool_list_releases,
    tool_list_reviews,
    tool_preview_create_defect,
    tool_preview_create_release,
    tool_preview_create_review,
    tool_preview_finalize_review,
    tool_preview_submit_review_decision,
    tool_preview_transition_defect,
    tool_preview_transition_release,
    tool_search_project_assets,
)

# 管理写操作：模型 / 通知 / 环境 / 设备 / 成员 / 质量门禁
from app.mcp.tools_admin_writes import (  # noqa: E402
    tool_confirm_add_project_member,
    tool_confirm_batch_env_vars,
    tool_confirm_delete_device,
    tool_confirm_register_device,
    tool_confirm_remove_project_member,
    tool_confirm_set_default_ai_config,
    tool_confirm_test_notification_config,
    tool_confirm_transfer_project_owner,
    tool_confirm_update_ai_config_api_key,
    tool_confirm_update_quality_gate_settings,
    tool_get_quality_gate_settings,
    tool_preview_add_project_member,
    tool_preview_batch_env_vars,
    tool_preview_delete_device,
    tool_preview_register_device,
    tool_preview_remove_project_member,
    tool_preview_set_default_ai_config,
    tool_preview_test_notification_config,
    tool_preview_transfer_project_owner,
    tool_preview_update_ai_config_api_key,
    tool_preview_update_quality_gate_settings,
)
