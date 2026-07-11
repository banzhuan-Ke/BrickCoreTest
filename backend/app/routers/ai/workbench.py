"""
AI 测试工作台：概览统计、最近需求、生成记录、进行中任务
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import AI_TEST_VIEW
from app.models.ai import (
    AiConfig,
    AiFunctionalCase,
    AiGenerateRecord,
    AiRequirement,
    AiRequirementCase,
    AiRequirementGenerateJob,
    AiRequirementTestPoint,
    AiRequirementTestScheme,
)
from app.core.shared.report_summary_context import fetch_recent_failures
from app.modules.ai.ai_dashboard_stats import (
    build_workbench_funnel,
    build_workbench_todos,
    collect_generate_trend,
    collect_token_stats,
    collect_usage_summary,
)
from app.models.ui import Case as UiCase
from app.routers.ai.requirements import _job_to_dict, _requirement_to_dict, _resolve_project_id
from app.schemas.ai import StandardResponse

router = APIRouter(prefix="/workbench", tags=["AI工作台"])

GENERATE_TYPE_LABELS = {
    "api_case": "API 用例",
    "ui_case": "UI 用例",
    "api_suite": "API 套件",
    "perf_scene": "性能场景",
    "test_data": "测试数据",
    "requirement_case": "需求功能用例",
    "requirement_test_point": "测试点",
    "requirement_test_point_case": "测试点→用例",
    "requirement_test_scheme": "测试方案",
    "failure_analysis": "失败分析",
    "report_summary": "报告摘要",
}

STATUS_LABELS = {
    "pending": "待处理",
    "accepted": "已生成",
    "imported": "已入库",
    "rejected": "失败",
}


def _is_likely_vision_model(model: str) -> bool:
    m = (model or "").lower()
    return "vl" in m or "vision" in m or "gpt-4o" in m


def _record_summary(record: AiGenerateRecord) -> str:
    out = record.output_content if isinstance(record.output_content, dict) else {}
    inp = record.input_summary if isinstance(record.input_summary, dict) else {}
    gt = record.generate_type or ""
    if gt == "requirement_case":
        n = out.get("count") or len(out.get("cases") or [])
        return f"功能用例 {n} 条"
    if gt == "requirement_test_point":
        n = out.get("created_count") or inp.get("parsed_count") or 0
        return f"测试点 {n} 条"
    if gt == "requirement_test_point_case":
        n = out.get("count") or len(out.get("case_ids") or [])
        return f"功能用例 {n} 条"
    if gt == "requirement_test_scheme":
        ver = out.get("version")
        return f"方案 v{ver}" if ver else "测试方案"
    if gt == "failure_analysis":
        return (out.get("root_cause") or "失败分析")[:40]
    if gt == "report_summary":
        return (out.get("summary") or "报告摘要")[:40]
    if gt == "api_case":
        n = len(out.get("cases") or [])
        return f"API 用例 {n} 条"
    if gt == "ui_case":
        n = len(out.get("steps") or [])
        return f"UI 步骤 {n} 步"
    return ""


def _record_to_dict(record: AiGenerateRecord, req_names: dict[int, str]) -> dict:
    inp = record.input_summary if isinstance(record.input_summary, dict) else {}
    req_id = inp.get("requirement_id")
    if req_id is not None:
        try:
            req_id = int(req_id)
        except (TypeError, ValueError):
            req_id = None
    return {
        "id": record.id,
        "generate_type": record.generate_type,
        "generate_type_label": GENERATE_TYPE_LABELS.get(
            record.generate_type or "", record.generate_type or "未知"
        ),
        "status": record.status,
        "status_label": STATUS_LABELS.get(record.status or "", record.status or ""),
        "requirement_id": req_id,
        "requirement_name": req_names.get(req_id) if req_id else None,
        "summary": _record_summary(record),
        "tokens_used": record.tokens_used or 0,
        "duration_ms": record.duration_ms or 0,
        "create_by": record.create_by or "",
        "create_time": record.create_time.strftime("%Y-%m-%d %H:%M:%S")
        if record.create_time
        else "",
    }


@router.get("/overview", summary="工作台概览", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def workbench_overview(
    project_id: Optional[int] = Query(None, description="项目ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)

    req_total = await AiRequirement.filter(project_id=project_id, is_del=False).count()
    point_total = await AiRequirementTestPoint.filter(project_id=project_id, is_del=False).count()
    scheme_total = await AiRequirementTestScheme.filter(project_id=project_id, is_del=False).count()
    case_total = await AiRequirementCase.filter(project_id=project_id, is_del=False).count()
    functional_case_total = await AiFunctionalCase.filter(project_id=project_id, is_del=False).count()
    ui_automated_count = await UiCase.filter(
        project_id=project_id,
        is_del=False,
        source_functional_case_id__not_isnull=True,
    ).count()

    configs = await AiConfig.filter(is_del=False).order_by("-is_default", "-id")
    enabled_configs = [c for c in configs if c.is_enabled]
    default_cfg = next((c for c in enabled_configs if c.is_default), None) or (
        enabled_configs[0] if enabled_configs else None
    )
    vision_cfg = next((c for c in enabled_configs if _is_likely_vision_model(c.model)), None)

    config_summary = {
        "enabled_count": len(enabled_configs),
        "default": None,
        "has_vision": vision_cfg is not None,
    }
    if default_cfg:
        config_summary["default"] = {
            "id": default_cfg.id,
            "name": default_cfg.name,
            "model": default_cfg.model,
            "provider": default_cfg.provider,
            "is_vision": _is_likely_vision_model(default_cfg.model),
        }
    if vision_cfg and (not default_cfg or vision_cfg.id != default_cfg.id):
        config_summary["vision"] = {
            "id": vision_cfg.id,
            "name": vision_cfg.name,
            "model": vision_cfg.model,
        }

    recent_reqs = await AiRequirement.filter(project_id=project_id, is_del=False).order_by("-id").limit(8)
    req_ids = [r.id for r in recent_reqs]
    point_counts: dict[int, int] = {}
    scheme_counts: dict[int, int] = {}
    case_counts: dict[int, int] = {}
    if req_ids:
        for rid in await AiRequirementTestPoint.filter(
            requirement_id__in=req_ids, is_del=False
        ).values_list("requirement_id", flat=True):
            point_counts[rid] = point_counts.get(rid, 0) + 1
        for rid in await AiRequirementTestScheme.filter(
            requirement_id__in=req_ids, is_del=False
        ).values_list("requirement_id", flat=True):
            scheme_counts[rid] = scheme_counts.get(rid, 0) + 1
        for rid in await AiRequirementCase.filter(
            requirement_id__in=req_ids, is_del=False
        ).values_list("requirement_id", flat=True):
            case_counts[rid] = case_counts.get(rid, 0) + 1

    recent_requirements = []
    for req in recent_reqs:
        row = _requirement_to_dict(req)
        row["test_point_count"] = point_counts.get(req.id, 0)
        row["scheme_count"] = scheme_counts.get(req.id, 0)
        row["case_count"] = case_counts.get(req.id, 0)
        recent_requirements.append(row)

    running_jobs_qs = await AiRequirementGenerateJob.filter(
        project_id=project_id,
        status__in=["pending", "running"],
    ).order_by("-id").limit(5)
    job_req_ids = list({j.requirement_id for j in running_jobs_qs})
    job_req_names: dict[int, str] = {}
    if job_req_ids:
        for r in await AiRequirement.filter(id__in=job_req_ids, is_del=False):
            job_req_names[r.id] = r.name

    running_jobs = []
    for job in running_jobs_qs:
        d = _job_to_dict(job)
        d["requirement_name"] = job_req_names.get(job.requirement_id, "")
        running_jobs.append(d)

    records = await AiGenerateRecord.filter(project_id=project_id).order_by("-id").limit(15)
    rec_req_ids: set[int] = set()
    for rec in records:
        inp = rec.input_summary if isinstance(rec.input_summary, dict) else {}
        rid = inp.get("requirement_id")
        if rid is not None:
            try:
                rec_req_ids.add(int(rid))
            except (TypeError, ValueError):
                pass
    for job in running_jobs_qs:
        rec_req_ids.add(job.requirement_id)

    req_names: dict[int, str] = dict(job_req_names)
    missing_ids = [i for i in rec_req_ids if i not in req_names]
    if missing_ids:
        for r in await AiRequirement.filter(id__in=missing_ids, is_del=False):
            req_names[r.id] = r.name

    recent_records = [_record_to_dict(r, req_names) for r in records]
    recent_failures = await fetch_recent_failures(project_id, limit=8)

    stats = {
        "requirement_total": req_total,
        "test_point_total": point_total,
        "scheme_total": scheme_total,
        "case_total": case_total,
        "functional_case_total": functional_case_total,
        "ui_automated_count": ui_automated_count,
    }
    funnel = build_workbench_funnel(stats)
    todos = await build_workbench_todos(project_id)
    token_stats = await collect_token_stats(project_id)
    generate_trend = await collect_generate_trend(project_id, days=7)
    usage_summary = await collect_usage_summary(project_id)

    return StandardResponse(
        data={
            "stats": stats,
            "funnel": funnel,
            "todos": todos,
            "token_stats": token_stats,
            "generate_trend": generate_trend,
            "usage_summary": usage_summary,
            "config": config_summary,
            "recent_requirements": recent_requirements,
            "recent_records": recent_records,
            "running_jobs": running_jobs,
            "recent_failures": recent_failures,
        }
    )
