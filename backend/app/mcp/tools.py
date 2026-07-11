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
    return {"id": ctx.user_id, "username": ctx.username}


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
    ensure_permission(ctx, PROJECT_VIEW)
    page = max(page, 1)
    size = min(max(size, 1), 100)
    qs = Project.filter(is_del=False).order_by("-id")
    total = await qs.count()
    rows = await qs.offset((page - 1) * size).limit(size)
    return {
        "total": total,
        "items": [{"id": p.id, "name": p.name, "username": p.username} for p in rows],
    }


async def tool_get_project(ctx: McpAuthContext, project_id: int) -> dict[str, Any]:
    ensure_permission(ctx, PROJECT_VIEW)
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
    ensure_any_permission(ctx, UI_CASE_EXECUTE, APP_CASE_EXECUTE, APP_PLAN_VIEW)
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
) -> dict[str, Any]:
    """资料库问答：retrieve 仅检索；smart 检索后一次 LLM 生成答案。"""
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
        {"suite_id": suite_id, "env_id": resolved_env_id},
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
    payload = await consume_confirm_token(confirm_token, "run_api_suite", ctx.username)
    if int(payload.get("suite_id", 0)) != suite_id:
        raise ValueError("suite_id 与确认 Token 不匹配")
    resolved_env_id = env_id or int(payload.get("env_id") or 0)
    result = await run_suite_async(
        suite_id,
        ApiSuiteRunRequest(env_id=resolved_env_id, trigger_type=ASSISTANT_TRIGGER),
        _AsyncBackgroundTasks(),
        username=ctx.username,
    )
    return {"record_id": result.record_id, "message": result.message}


async def tool_preview_run_api_plan(
    ctx: McpAuthContext, plan_id: int, env_id: Optional[int] = None
) -> dict[str, Any]:
    ensure_permission(ctx, API_PLAN_EDIT)
    plan = await ApiTestPlan.get_or_none(id=plan_id, is_del=False)
    if not plan:
        raise ValueError("接口测试计划不存在")
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
        {"plan_id": plan_id, "env_id": resolved_env_id},
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
    payload = await consume_confirm_token(confirm_token, "run_api_plan", ctx.username)
    if int(payload.get("plan_id", 0)) != plan_id:
        raise ValueError("plan_id 与确认 Token 不匹配")
    resolved_env_id = env_id or int(payload.get("env_id") or 0)
    result = await run_plan_async(
        plan_id,
        ApiPlanRunRequest(env_id=resolved_env_id, trigger_type=ASSISTANT_TRIGGER),
        _AsyncBackgroundTasks(),
        username=ctx.username,
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
    if resolved_project_id and case.project_id != resolved_project_id:
        raise ValueError("用例不属于当前项目")
    if case.data_set:
        result = await run_data_driven_case(
            case_id, resolved_env_id, ctx.username, {}, False
        )
        return {
            "case_id": case_id,
            "case_name": case.name,
            "data_driven": True,
            "result": _serialize_api_run_result(result),
            "message": "数据驱动用例已执行",
        }
    result = await run_single_case(case_id, resolved_env_id, None, ctx.username, {}, False)
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
        {"task_id": task_id, "env_id": env_id, "device_id": device_id},
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
    payload = await consume_confirm_token(confirm_token, "run_ui_task", ctx.username)
    if int(payload.get("task_id", 0)) != task_id:
        raise ValueError("task_id 与确认 Token 不匹配")
    from app.routers.ui.exec import run_task

    result = await run_task(
        task_id,
        UiRunForm(
            env_id=int(payload["env_id"]),
            device_id=str(payload["device_id"]),
            username=ctx.username,
            trigger_source=ASSISTANT_TRIGGER,
        ),
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
    payload = await consume_confirm_token(confirm_token, "run_ui_suite", ctx.username)
    if int(payload.get("suite_id", 0)) != suite_id:
        raise ValueError("suite_id 与确认 Token 不匹配")
    resolved_env_id = env_id or int(payload.get("env_id") or 0)
    resolved_device = (device_id or payload.get("device_id") or "").strip()
    result = await run_ui_suite(
        suite_id,
        UiRunForm(
            env_id=resolved_env_id,
            device_id=resolved_device,
            username=ctx.username,
            trigger_source=ASSISTANT_TRIGGER,
        ),
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
    if resolved_project_id and case.project_id != resolved_project_id:
        raise ValueError("用例不属于当前项目")
    result = await run_ui_case(
        case_id,
        UiRunForm(
            env_id=resolved_env_id,
            device_id=resolved_device,
            username=ctx.username,
            trigger_source=ASSISTANT_TRIGGER,
        ),
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
    use_workers: bool = False,
) -> dict[str, Any]:
    ensure_permission(ctx, PERF_SCENE_EXECUTE)
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise ValueError("压测场景不存在")
    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise ValueError("运行环境不存在")
    item_count = len(scene.scene_items or [])
    config = dict(scene.config or {})
    impact = {
        "scene_id": scene_id,
        "scene_name": scene.name,
        "project_id": scene.project_id,
        "env_id": env_id,
        "env_name": env.name,
        "item_count": item_count,
        "use_workers": bool(use_workers),
        "mode": config.get("mode", "constant"),
        "warning": "将启动性能压测，可能产生大量 HTTP 请求并占用 Worker",
    }
    confirm_token = await create_confirm_token(
        "run_perf_scene",
        {"scene_id": scene_id, "env_id": env_id, "use_workers": bool(use_workers)},
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
    use_workers: bool = False,
) -> dict[str, Any]:
    ensure_permission(ctx, PERF_SCENE_EXECUTE)
    payload = await consume_confirm_token(confirm_token, "run_perf_scene", ctx.username)
    if int(payload.get("scene_id", 0)) != scene_id:
        raise ValueError("scene_id 与确认 Token 不匹配")
    resolved_env_id = env_id or int(payload.get("env_id") or 0)
    use_workers = bool(payload.get("use_workers", use_workers))
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise ValueError("压测场景不存在")
    config = dict(scene.config or {})
    config["env_id"] = resolved_env_id
    record = await PerfRecord.create(
        scene_id=scene_id,
        project_id=scene.project_id,
        status="pending",
        trigger_type="manual",
        config_snapshot=config,
        scene_items_snapshot=scene.scene_items or [],
        run_by=ctx.username,
    )
    _AsyncBackgroundTasks().add_task(run_perf_scene, record.id, use_workers)
    return {
        "record_id": record.id,
        "status": "pending",
        "message": "性能测试已启动",
    }


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
        return {
            "id": rec.id,
            "type": "ui_case",
            "case_id": rec.case_id,
            "case_name": rec.case.name if rec.case else "",
            "status": rec.status,
            "username": rec.username,
            "start_time": rec.start_time.isoformat() if rec.start_time else None,
            "env": rec.env if isinstance(rec.env, dict) else {},
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
        return {
            "id": rec.id,
            "type": "app_case",
            "case_id": rec.case_id,
            "case_name": rec.case.name if rec.case else "",
            "status": rec.status,
            "username": rec.username,
            "start_time": rec.start_time.isoformat() if rec.start_time else None,
            "env": rec.env if isinstance(rec.env, dict) else {},
            **meta,
        }
    raise ValueError("record_type 支持 api_suite / api_plan / ui_plan / ui_case / app_plan / app_suite / app_case / perf")


async def tool_analyze_failure(
    ctx: McpAuthContext,
    project_id: int,
    target_type: str,
    target_id: int,
    force_refresh: bool = False,
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
            force_refresh=force_refresh,
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
    size = min(max(size, 1), 50)
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
) -> dict[str, Any]:
    """获取 SQL 模板详情（只读，不含数据源密码）。"""
    ensure_permission(ctx, DATA_FACTORY_VIEW)
    tpl = await SqlTemplate.get_or_none(id=template_id, is_del=False)
    if not tpl:
        return {"error": "模板不存在"}
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
    payload = await consume_confirm_token(confirm_token, "run_app_plan", ctx.username)
    if int(payload.get("plan_id", 0)) != plan_id:
        raise ValueError("plan_id 与确认 Token 不匹配")
    from app.modules.app.app_plan_runner import execute_app_plan

    plan = await AppPlan.get_or_none(id=plan_id, is_del=False)
    if not plan:
        raise ValueError("App 计划不存在")
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
