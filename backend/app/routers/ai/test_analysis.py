"""
AI 测试分析：测试点（思维导图）+ 测试方案
"""
import json
import logging
import re
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.auth import is_authenticated, require_permissions
from app.core.permissions import AI_TEST_EXECUTE, AI_TEST_VIEW
from app.core.ai_prompts import PromptManager
from app.core.ai_usage_log import log_ai_usage
from app.core.requirement_document import (
    build_interleaved_content,
    collect_image_indices,
    estimate_scope,
    resolve_sections,
    truncate_scope_text,
)
from app.core.requirement_storage import load_images_from_meta
from urllib.parse import quote

from app.core.case_naming import (
    apply_naming_to_cases,
    build_section_context,
    format_naming_rules_for_prompt,
)
from app.core.test_analysis import (
    build_echarts_tree,
    build_mindmap_tree,
    build_xmind_bytes,
    compute_overview,
    filter_test_points,
    format_environment_hints_for_prompt,
    format_scope_section_titles,
    format_test_points_for_case_generation,
    format_test_points_for_prompt,
    map_point_section_titles,
    markdown_to_docx_bytes,
    normalize_scheme_content,
    normalize_test_points,
    render_scheme_markdown,
    resolve_mindmap_tree,
    test_points_cases_source_ref,
)
from app.core.zentao_bindings import apply_bindings_to_case_fields, build_requirement_case_extra, validate_bindings
from app.models.ai import (
    AiGenerateRecord,
    AiRequirement,
    AiRequirementCase,
    AiRequirementTestPoint,
    AiRequirementTestScheme,
)
from app.routers.ai.generate import _call_llm, _extract_json_array
from app.routers.ai.requirements import (
    _analyze_images_with_vision,
    _case_to_dict,
    _effective_zentao_bindings,
    _extract_json_object,
    _format_existing_cases_for_prompt,
    _get_ai_config,
    _merge_test_point_keywords,
    _normalize_cases,
    _requirement_to_dict,
    _resolve_naming_template,
    _resolve_project_id,
)
from app.schemas.ai import StandardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/test-analysis", tags=["AI测试分析"])


class GenerateTestPointsRequest(BaseModel):
    vision_config_id: Optional[int] = None
    text_config_id: Optional[int] = None
    scope_section_ids: list[str] = Field(default_factory=list)
    count: int = Field(default=30, ge=5, le=100)
    replace_existing: bool = False
    replace_all: bool = False
    batch_name: str = ""
    supplement: bool = False


class UpdateTestPointBody(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    test_type: Optional[str] = None
    priority: Optional[str] = None
    module_path: Optional[str] = None
    main_module: Optional[str] = None
    sub_module: Optional[str] = None
    acceptance_ref: Optional[str] = None
    status: Optional[str] = None


class BatchStatusBody(BaseModel):
    point_ids: list[int]
    status: str = "confirmed"


class DeleteTestPointsBody(BaseModel):
    point_ids: list[int]


class GenerateCasesFromTestPointsRequest(BaseModel):
    case_gen_config_id: Optional[int] = None
    test_point_ids: list[int] = Field(default_factory=list, description="指定测试点 ID，空则按状态筛选")
    include_unconfirmed_points: bool = False
    count: int = Field(default=20, ge=1, le=50)
    batch_name: str = Field(default="", description="写入用例 source_ref=test_points:batch:名称")
    replace_existing: bool = Field(default=False, description="替换同 source_ref 的已有用例")
    supplement: bool = False
    include_requirement_excerpt: bool = True


class SchemeEnvironmentHints(BaseModel):
    """生成方案前可补充的环境信息（优先于 LLM 编造）。"""
    system_name: str = ""
    test_env: str = ""
    access_entry: str = ""
    deploy_version: str = ""
    client_requirements: str = ""
    accounts_roles: str = ""
    test_data: str = ""
    dependencies: str = ""
    tools: str = ""


class GenerateSchemeRequest(BaseModel):
    text_config_id: Optional[int] = None
    test_point_ids: list[int] = Field(default_factory=list)
    scope_section_ids: list[str] = Field(default_factory=list)
    title: str = ""
    include_unconfirmed_points: bool = False
    environment_hints: SchemeEnvironmentHints = Field(default_factory=SchemeEnvironmentHints)


class UpdateSchemeBody(BaseModel):
    title: Optional[str] = None
    content_md: Optional[str] = None
    status: Optional[str] = None


def _point_to_dict(pt: AiRequirementTestPoint) -> dict:
    return {
        "id": pt.id,
        "requirement_id": pt.requirement_id,
        "title": pt.title,
        "description": pt.description or "",
        "test_type": pt.test_type,
        "priority": pt.priority,
        "module_path": pt.module_path,
        "main_module": pt.main_module,
        "sub_module": pt.sub_module,
        "acceptance_ref": pt.acceptance_ref or "",
        "section_ids": pt.section_ids or [],
        "source_ref": pt.source_ref,
        "status": pt.status,
        "sort_order": pt.sort_order,
        "extra": pt.extra or {},
        "create_time": pt.create_time.strftime("%Y-%m-%d %H:%M:%S") if pt.create_time else "",
        "update_time": pt.update_time.strftime("%Y-%m-%d %H:%M:%S") if pt.update_time else "",
    }


def _scheme_to_dict(scheme: AiRequirementTestScheme) -> dict:
    return {
        "id": scheme.id,
        "requirement_id": scheme.requirement_id,
        "title": scheme.title,
        "version": scheme.version,
        "status": scheme.status,
        "content": scheme.content or {},
        "content_md": scheme.content_md or "",
        "test_point_ids": scheme.test_point_ids or [],
        "scope_section_ids": scheme.scope_section_ids or [],
        "generate_report": scheme.generate_report or {},
        "create_time": scheme.create_time.strftime("%Y-%m-%d %H:%M:%S") if scheme.create_time else "",
        "update_time": scheme.update_time.strftime("%Y-%m-%d %H:%M:%S") if scheme.update_time else "",
    }


def _batch_source_ref(batch_name: str) -> str:
    name = (batch_name or "").strip()
    return f"batch:{name}" if name else ""


def _attachment_headers(filename: str, fallback: str) -> dict[str, str]:
    """Content-Disposition 兼容中文文件名（RFC 5987）。"""
    ascii_name = fallback
    utf8_name = filename or fallback
    return {
        "Content-Disposition": (
            f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(utf8_name)}"
        )
    }


def _requirement_sections(req: AiRequirement) -> list[dict]:
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    return meta.get("sections") or []


def _parse_section_ids_param(raw: Optional[str]) -> Optional[list[str]]:
    if not raw or not raw.strip():
        return None
    return [p.strip() for p in raw.split(",") if p.strip()]


async def _get_requirement(req_id: int, project_id: int) -> AiRequirement:
    req = await AiRequirement.get_or_none(id=req_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    return req


async def _build_scoped_content(req: AiRequirement, scope_section_ids: list[str], vision_config_id: Optional[int]):
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    blocks = meta.get("blocks") or []
    all_sections = meta.get("sections") or []
    if not all_sections:
        all_sections = [{
            "id": "sec-1",
            "title": "全文",
            "level": 1,
            "block_ids": [b.get("id") for b in blocks if b.get("id")],
            "char_count": len(req.original_content or ""),
            "image_indices": list(range(meta.get("image_count", 0))),
        }]
    selected_sections = resolve_sections(all_sections, scope_section_ids)
    if not selected_sections:
        raise HTTPException(status_code=400, detail="请至少选择一个章节/范围")

    scoped_image_indices = collect_image_indices(selected_sections)
    image_count = len(scoped_image_indices)
    vision_text_by_index: dict[int, str] = {}
    total_tokens = 0
    vision_report: dict = {"skipped": True, "message": "当前范围内无图片，已跳过读图"}

    if image_count > 0:
        if not vision_config_id:
            raise HTTPException(
                status_code=400,
                detail=f"选中范围包含 {image_count} 张图片，请选择 Vision 模型配置",
            )
        vision_config = await _get_ai_config(vision_config_id)
        vision_report = {
            "skipped": False,
            "config_name": vision_config.name,
            "model": vision_config.model,
            "provider": vision_config.provider,
        }
        images = load_images_from_meta(meta)
        vision_text_by_index, v_tokens, vision_detail = await _analyze_images_with_vision(
            vision_config,
            images,
            blocks,
            selected_sections,
            scoped_image_indices,
        )
        vision_report.update(vision_detail)
        total_tokens += v_tokens

    scoped_content = build_interleaved_content(blocks, selected_sections, vision_text_by_index)
    if not scoped_content.strip():
        scoped_content = (req.original_content or "")[:8000]
    scoped_content, _ = truncate_scope_text(scoped_content)
    scope_est = estimate_scope(scoped_content, image_count)
    if scope_est["level"] == "block":
        raise HTTPException(status_code=400, detail=scope_est["message"] + "；请减少勾选的章节后重试")
    if not scoped_content.strip():
        raise HTTPException(status_code=400, detail="选中范围内无有效文字或图片内容")

    return scoped_content, vision_report, scope_est, selected_sections, total_tokens


@router.get("/requirements", summary="需求列表（含测试分析统计）", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def list_requirements_for_analysis(
    page: int = 1,
    size: int = 20,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    query = AiRequirement.filter(project_id=project_id, is_del=False).order_by("-id")
    total = await query.count()
    items = await query.offset((page - 1) * size).limit(size)
    req_ids = [r.id for r in items]

    point_counts: dict[int, int] = {}
    scheme_counts: dict[int, int] = {}
    case_counts: dict[int, int] = {}
    if req_ids:
        for rid in await AiRequirementTestPoint.filter(requirement_id__in=req_ids, is_del=False).values_list(
            "requirement_id", flat=True
        ):
            point_counts[rid] = point_counts.get(rid, 0) + 1
        for rid in await AiRequirementTestScheme.filter(requirement_id__in=req_ids, is_del=False).values_list(
            "requirement_id", flat=True
        ):
            scheme_counts[rid] = scheme_counts.get(rid, 0) + 1
        for rid in await AiRequirementCase.filter(requirement_id__in=req_ids, is_del=False).values_list(
            "requirement_id", flat=True
        ):
            case_counts[rid] = case_counts.get(rid, 0) + 1

    rows = []
    for req in items:
        row = _requirement_to_dict(req)
        row["test_point_count"] = point_counts.get(req.id, 0)
        row["scheme_count"] = scheme_counts.get(req.id, 0)
        row["case_count"] = case_counts.get(req.id, 0)
        rows.append(row)
    return StandardResponse(data={"list": rows, "total": total, "page": page, "size": size})


@router.get("/requirements/{req_id}/overview", summary="整体测试内容视图", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def get_overview(
    req_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    await _get_requirement(req_id, project_id)
    points = await AiRequirementTestPoint.filter(requirement_id=req_id, is_del=False).order_by("sort_order", "id")
    schemes = await AiRequirementTestScheme.filter(requirement_id=req_id, is_del=False).order_by("-version", "-id")
    case_count = await AiRequirementCase.filter(requirement_id=req_id, is_del=False).count()
    pt_dicts = [_point_to_dict(p) for p in points]
    sc_dicts = [_scheme_to_dict(s) for s in schemes]
    overview = compute_overview(pt_dicts, sc_dicts, case_count)
    req = await AiRequirement.get(id=req_id)
    sections = _requirement_sections(req)
    mindmap = resolve_mindmap_tree(req.name, pt_dicts, sections, layout="section")
    return StandardResponse(data={
        "overview": overview,
        "mindmap": mindmap,
        "echarts_tree": build_echarts_tree(req.name, pt_dicts, sections, layout="section"),
    })


@router.get("/requirements/{req_id}/mindmap", summary="测试点思维导图数据", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def get_mindmap(
    req_id: int,
    project_id: Optional[int] = Query(None),
    section_ids: Optional[str] = Query(None, description="逗号分隔的章节ID，仅展示这些章节下的测试点"),
    batch_name: Optional[str] = Query(None, description="批次名，仅展示该批次测试点"),
    layout: str = Query("section", description="section=按章节 | module=按LLM模块"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await _get_requirement(req_id, project_id)
    points = await AiRequirementTestPoint.filter(requirement_id=req_id, is_del=False).order_by("sort_order", "id")
    pt_dicts = [_point_to_dict(p) for p in points]
    filter_sections = _parse_section_ids_param(section_ids)
    pt_dicts = filter_test_points(pt_dicts, section_ids=filter_sections, batch_name=batch_name)
    sections = _requirement_sections(req)
    tree_layout = "section" if layout == "section" else "module"
    return StandardResponse(data={
        "mindmap": resolve_mindmap_tree(req.name, pt_dicts, sections, layout=tree_layout),
        "echarts_tree": build_echarts_tree(req.name, pt_dicts, sections, layout=tree_layout),
        "total": len(pt_dicts),
        "filtered": bool(filter_sections or batch_name),
    })


@router.get("/requirements/{req_id}/test-points/export-xmind", summary="导出测试点 XMind", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def export_xmind(
    req_id: int,
    project_id: Optional[int] = Query(None),
    section_ids: Optional[str] = Query(None, description="逗号分隔章节ID，仅导出范围内测试点"),
    batch_name: Optional[str] = Query(None, description="批次名"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await _get_requirement(req_id, project_id)
    points = await AiRequirementTestPoint.filter(requirement_id=req_id, is_del=False).order_by("sort_order", "id")
    pt_dicts = [_point_to_dict(p) for p in points]
    filter_sections = _parse_section_ids_param(section_ids)
    pt_dicts = filter_test_points(pt_dicts, section_ids=filter_sections, batch_name=batch_name)
    if not pt_dicts:
        raise HTTPException(status_code=400, detail="暂无测试点可导出（请检查章节/批次筛选）")
    sections = _requirement_sections(req)
    tree = resolve_mindmap_tree(req.name, pt_dicts, sections, layout="section")
    data = build_xmind_bytes(req.name, pt_dicts, tree_root=tree)
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", req.name)[:80].strip() or f"requirement_{req_id}"
    filename = f"{safe_name}_test_points.xmind"
    return Response(
        content=data,
        media_type="application/vnd.xmind.workbook",
        headers=_attachment_headers(filename, f"requirement_{req_id}_test_points.xmind"),
    )


def _build_scheme_excerpt(req: AiRequirement, scope_section_ids: list[str], max_chars: int = 14000) -> str:
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    blocks = meta.get("blocks") or []
    all_sections = meta.get("sections") or []
    if not all_sections:
        return (req.original_content or "")[:max_chars]
    selected = resolve_sections(all_sections, scope_section_ids) if scope_section_ids else all_sections
    content = build_interleaved_content(blocks, selected, {})
    if not content.strip():
        content = (req.original_content or "")[:max_chars]
    content, _ = truncate_scope_text(content, max_chars=max_chars)
    return content


def _hints_to_dict(hints: SchemeEnvironmentHints) -> dict:
    d = hints.model_dump() if hasattr(hints, "model_dump") else dict(hints)
    out = {}
    for k, v in d.items():
        if not v or not str(v).strip():
            continue
        if k in ("client_requirements", "accounts_roles", "dependencies", "tools"):
            lines = [ln.strip() for ln in str(v).splitlines() if ln.strip()]
            out[k] = lines if lines else [str(v).strip()]
        else:
            out[k] = str(v).strip()
    return out


@router.get("/requirements/{req_id}/test-points", summary="测试点列表", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def list_test_points(
    req_id: int,
    project_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="draft/confirmed"),
    test_type: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    batch_name: Optional[str] = Query(None, description="批次名（不含 batch: 前缀）"),
    main_module: Optional[str] = Query(None, description="主模块模糊匹配"),
    keyword: Optional[str] = Query(None, description="标题/描述关键词"),
    section_ids: Optional[str] = Query(None, description="逗号分隔章节ID"),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    await _get_requirement(req_id, project_id)
    points = await AiRequirementTestPoint.filter(requirement_id=req_id, is_del=False).order_by(
        "sort_order", "id"
    )
    pt_dicts = [_point_to_dict(p) for p in points]
    filter_sections = _parse_section_ids_param(section_ids)
    filtered = filter_test_points(
        pt_dicts,
        section_ids=filter_sections,
        batch_name=batch_name,
        status=status,
        test_type=test_type,
        priority=priority,
        main_module=main_module,
        keyword=keyword,
    )
    batches = sorted({
        (p.get("source_ref") or "").replace("batch:", "")
        for p in pt_dicts
        if (p.get("source_ref") or "").startswith("batch:")
    })
    return StandardResponse(data={
        "list": filtered,
        "total": len(filtered),
        "total_all": len(pt_dicts),
        "filter_options": {
            "batches": batches,
            "test_types": sorted({p.get("test_type") for p in pt_dicts if p.get("test_type")}),
            "priorities": sorted({p.get("priority") for p in pt_dicts if p.get("priority")}),
            "main_modules": sorted({p.get("main_module") for p in pt_dicts if p.get("main_module")}),
        },
    })


@router.post("/requirements/{req_id}/test-points/generate", summary="AI 生成测试点", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def generate_test_points(
    req_id: int,
    body: GenerateTestPointsRequest,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await _get_requirement(req_id, project_id)
    start_time = time.time()
    batch_ref = _batch_source_ref(body.batch_name)

    scoped_content, vision_report, scope_est, selected_sections, total_tokens = await _build_scoped_content(
        req, body.scope_section_ids, body.vision_config_id
    )

    if body.replace_all:
        await AiRequirementTestPoint.filter(requirement_id=req_id, is_del=False).update(is_del=True)
    elif body.replace_existing and batch_ref:
        await AiRequirementTestPoint.filter(
            requirement_id=req_id, source_ref=batch_ref, is_del=False
        ).update(is_del=True)

    existing_titles = ""
    if body.supplement and batch_ref:
        existing = await AiRequirementTestPoint.filter(
            requirement_id=req_id, source_ref=batch_ref, is_del=False
        ).order_by("id")
        if existing:
            existing_titles = "\n".join(f"- {p.title}" for p in existing[:60])

    gen_config = await _get_ai_config(body.text_config_id)
    try:
        system_prompt, user_prompt = await PromptManager.render(
            "requirement_doc_to_test_points",
            {
                "requirement_name": req.name,
                "scoped_content": scoped_content,
                "scope_section_titles": format_scope_section_titles(selected_sections),
                "count": body.count,
            },
        )
        if body.supplement and existing_titles:
            user_prompt += f"\n\n【已有测试点 · 请勿重复】\n{existing_titles}"
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        resp = await _call_llm(system_prompt, user_prompt, gen_config, min_timeout=600, max_retries=2)
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        await log_ai_usage(
            gen_config,
            "requirement_test_point",
            user_info=user_info,
            project_id=project_id,
            tokens_used=total_tokens,
            duration_ms=duration_ms,
            status="failed",
            input_summary=f"需求#{req_id} {req.name}"[:500],
            output_summary=str(e)[:500],
            requirement_id=req_id,
        )
        logger.error("[test_analysis] 测试点生成失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI 生成失败: {str(e)}")

    raw_response = resp.get("content", "") or ""
    total_tokens += resp.get("tokens", 0)
    default_section_ids = [s.get("id") for s in selected_sections if s.get("id")]
    normalized = normalize_test_points(_extract_json_array(raw_response), section_ids=default_section_ids)
    for item in normalized:
        mapped = map_point_section_titles(item, _requirement_sections(req))
        if mapped:
            item["section_ids"] = mapped

    username = user_info.get("username") or user_info.get("sub") or "system"
    created = []
    for idx, item in enumerate(normalized):
        pt = await AiRequirementTestPoint.create(
            requirement_id=req_id,
            project_id=project_id,
            title=item["title"],
            description=item.get("description"),
            test_type=item.get("test_type", "正向"),
            priority=item.get("priority", "P2"),
            module_path=item.get("module_path", ""),
            main_module=item.get("main_module", ""),
            sub_module=item.get("sub_module", ""),
            acceptance_ref=item.get("acceptance_ref"),
            section_ids=item.get("section_ids") or default_section_ids,
            source_ref=batch_ref or None,
            status="draft",
            sort_order=idx,
            extra=item.get("extra") or {},
            create_by=username,
        )
        created.append(_point_to_dict(pt))

    duration_ms = int((time.time() - start_time) * 1000)
    report = {
        "vision": vision_report,
        "scope_estimate": scope_est,
        "parsed_count": len(created),
        "requested_count": body.count,
        "model": gen_config.model,
        "config_name": gen_config.name,
    }
    await AiGenerateRecord.create(
        project_id=project_id,
        generate_type="requirement_test_point",
        input_summary={
            "requirement_id": req_id,
            "scope_section_ids": body.scope_section_ids,
            "batch_name": body.batch_name,
        },
        output_content={"created_count": len(created), "report": report},
        status="imported",
        ai_config_id=gen_config.id,
        tokens_used=total_tokens,
        duration_ms=duration_ms,
        create_by=username,
    )
    await log_ai_usage(
        gen_config,
        "requirement_test_point",
        user_info=user_info,
        project_id=project_id,
        tokens_used=total_tokens,
        duration_ms=duration_ms,
        input_summary=f"需求#{req_id} {req.name}, count={body.count}"[:500],
        output_summary=f"生成 {len(created)} 条测试点",
        requirement_id=req_id,
        batch_name=body.batch_name,
    )
    return StandardResponse(
        message=f"成功生成 {len(created)} 条测试点",
        data={"created_count": len(created), "points": created, "generate_report": report},
    )


@router.put("/requirements/{req_id}/test-points/batch-status", summary="批量更新测试点状态", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def batch_update_status(
    req_id: int,
    body: BatchStatusBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    await _get_requirement(req_id, project_id)
    if not body.point_ids:
        raise HTTPException(status_code=400, detail="请至少选择一条测试点")
    if body.status not in ("draft", "confirmed"):
        raise HTTPException(status_code=400, detail="status 仅支持 draft / confirmed")
    updated = await AiRequirementTestPoint.filter(
        requirement_id=req_id, id__in=body.point_ids, is_del=False
    ).update(status=body.status)
    return StandardResponse(message=f"已更新 {updated} 条", data={"updated": updated})


@router.post(
    "/requirements/{req_id}/test-points/generate-cases",
    summary="基于测试点 AI 生成功能测试用例",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def generate_cases_from_test_points(
    req_id: int,
    body: GenerateCasesFromTestPointsRequest,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await _get_requirement(req_id, project_id)
    start_time = time.time()

    qs = AiRequirementTestPoint.filter(requirement_id=req_id, is_del=False)
    if body.test_point_ids:
        qs = qs.filter(id__in=body.test_point_ids)
    elif not body.include_unconfirmed_points:
        qs = qs.filter(status="confirmed")
    points = await qs.order_by("sort_order", "id")
    pt_dicts = [_point_to_dict(p) for p in points]
    if not pt_dicts:
        raise HTTPException(
            status_code=400,
            detail="没有可用的测试点：请先生成并确认，或勾选「包含未确认」/指定测试点 ID",
        )

    effective = await _effective_zentao_bindings(project_id, req)
    missing = validate_bindings(effective)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"请先在「禅道导入配置」中填写：{', '.join(missing)}",
        )

    scope_ids: list[str] = []
    for p in pt_dicts:
        for sid in p.get("section_ids") or []:
            if sid and sid not in scope_ids:
                scope_ids.append(sid)
    all_sections = _requirement_sections(req)
    selected_sections = resolve_sections(all_sections, scope_ids) if scope_ids else all_sections
    section_ctx = build_section_context(selected_sections, all_sections)

    excerpt = ""
    if body.include_requirement_excerpt:
        excerpt = _build_scheme_excerpt(req, scope_ids, max_chars=12000)
    if not excerpt.strip():
        excerpt = "（未附带需求摘录；请严格依据测试点标题与说明编写步骤）"

    _naming_config, naming_template = await _resolve_naming_template(project_id, req)
    naming_rules = format_naming_rules_for_prompt(naming_template)
    case_batch = (body.batch_name or "").strip() or "测试点用例"
    source_ref = test_points_cases_source_ref(body.batch_name)
    test_points_text = format_test_points_for_case_generation(pt_dicts)

    existing_cases_text = ""
    existing_count = 0
    if body.supplement:
        existing_rows = await AiRequirementCase.filter(
            requirement_id=req_id, source_ref=source_ref, is_del=False
        ).order_by("id")
        existing_cases_text, existing_count = _format_existing_cases_for_prompt(existing_rows)

    gen_config = await _get_ai_config(body.case_gen_config_id)
    try:
        system_prompt, user_prompt = await PromptManager.render(
            "requirement_test_points_to_cases",
            {
                "requirement_name": req.name,
                "case_batch_name": case_batch,
                "count": body.count,
                "naming_rules": naming_rules,
                "requirement_excerpt": excerpt,
                "test_point_count": len(pt_dicts),
                "test_points": test_points_text,
            },
        )
        if body.supplement and existing_cases_text:
            user_prompt += (
                f"\n\n【本批次已有用例 {existing_count} 条 · 请补充遗漏，勿重复相同验证点】\n"
                f"{existing_cases_text}"
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        resp = await _call_llm(system_prompt, user_prompt, gen_config, min_timeout=600, max_retries=2)
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        await log_ai_usage(
            gen_config,
            "requirement_test_point_case",
            user_info=user_info,
            project_id=project_id,
            tokens_used=0,
            duration_ms=duration_ms,
            status="failed",
            input_summary=f"需求#{req_id} 测试点→用例"[:500],
            output_summary=str(e)[:500],
            requirement_id=req_id,
            test_point_count=len(pt_dicts),
        )
        logger.error("[test_analysis] 测试点→用例生成失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI 生成失败: {str(e)}")

    raw_response = resp.get("content", "") or ""
    total_tokens = resp.get("tokens", 0)
    raw_cases = _extract_json_array(raw_response)

    point_id_set = {p["id"] for p in pt_dicts}
    expanded: list[dict] = []
    for item in raw_cases:
        if not isinstance(item, dict):
            continue
        tp_ids = item.get("source_test_point_ids") or item.get("test_point_ids") or []
        if isinstance(tp_ids, (int, str)):
            tp_ids = [int(tp_ids)]
        tp_ids = [int(x) for x in tp_ids if str(x).isdigit()]
        if not tp_ids:
            kw = item.get("keywords") or ""
            for m in re.findall(r"tp:#?(\d+)", str(kw)):
                tid = int(m)
                if tid in point_id_set:
                    tp_ids.append(tid)
        tp_ids = [i for i in tp_ids if i in point_id_set]
        desc = (item.get("case_description") or "").strip()
        if not desc and tp_ids:
            first_pt = next((p for p in pt_dicts if p["id"] == tp_ids[0]), None)
            if first_pt:
                desc = first_pt.get("title", "")
        item = {**item, "case_description": desc or item.get("case_description", "")}
        if tp_ids:
            item["test_point_ids"] = tp_ids
        expanded.append(item)

    normalized = _normalize_cases(expanded)
    named_cases, naming_warnings = apply_naming_to_cases(
        normalized,
        naming_template,
        effective,
        section_ctx,
        batch_name=case_batch,
        requirement_name=req.name,
    )
    cases_data = [apply_bindings_to_case_fields(c, effective) for c in named_cases]

    if not cases_data:
        raise HTTPException(status_code=500, detail="AI 返回内容无法解析为用例 JSON，请重试")

    if body.replace_existing and not body.supplement:
        await AiRequirementCase.filter(
            requirement_id=req_id, source_ref=source_ref, is_del=False
        ).update(is_del=True)

    username = user_info.get("username") or user_info.get("sub") or "system"
    batch_section_ids = [s.get("id") for s in selected_sections if s.get("id")]
    created = []
    for item in cases_data:
        tp_ids = item.get("test_point_ids") or []
        if isinstance(tp_ids, (int, str)):
            tp_ids = [int(tp_ids)] if str(tp_ids).isdigit() else []
        tp_ids = [int(x) for x in tp_ids if str(x).isdigit()]
        keywords = _merge_test_point_keywords(item.get("keywords", ""), tp_ids)
        case_extra = build_requirement_case_extra(
            effective,
            existing={"test_point_ids": tp_ids} if tp_ids else {},
        )
        case = await AiRequirementCase.create(
            requirement_id=req.id,
            project_id=project_id,
            product=item.get("product", ""),
            module=item["module"],
            related_story=item.get("related_story", ""),
            title=item["title"],
            naming_template_id=item.get("naming_template_id"),
            naming_template_version=item.get("naming_template_version"),
            naming_slots=item.get("naming_slots") or {},
            precondition=item["precondition"],
            steps=item["steps"],
            priority=item["priority"],
            type=item["type"],
            stage=item.get("stage", "系统测试阶段"),
            keywords=keywords,
            status="draft",
            source_ref=source_ref,
            section_ids=batch_section_ids,
            extra=case_extra,
            create_by=username,
        )
        created.append(_case_to_dict(case))

    duration_ms = int((time.time() - start_time) * 1000)
    await AiGenerateRecord.create(
        project_id=project_id,
        generate_type="requirement_test_point_case",
        input_summary={
            "requirement_id": req_id,
            "test_point_ids": [p["id"] for p in pt_dicts],
            "source_ref": source_ref,
        },
        output_content={"case_ids": [c["id"] for c in created], "count": len(created)},
        status="accepted",
        ai_config_id=gen_config.id,
        tokens_used=total_tokens,
        duration_ms=duration_ms,
        create_by=username,
    )

    await log_ai_usage(
        gen_config,
        "requirement_test_point_case",
        user_info=user_info,
        project_id=project_id,
        tokens_used=total_tokens,
        duration_ms=duration_ms,
        input_summary=f"需求#{req_id} {len(pt_dicts)} 测试点→用例"[:500],
        output_summary=f"生成 {len(created)} 条用例",
        requirement_id=req_id,
        source_ref=source_ref,
    )

    return StandardResponse(
        message=f"已生成 {len(created)} 条功能用例",
        data={
            "created_count": len(created),
            "cases": created,
            "source_ref": source_ref,
            "test_point_count": len(pt_dicts),
            "naming_warnings": naming_warnings[:20],
            "tokens_used": total_tokens,
            "duration_ms": duration_ms,
        },
    )


@router.put("/requirements/{req_id}/test-points/{point_id}", summary="编辑测试点", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def update_test_point(
    req_id: int,
    point_id: int,
    body: UpdateTestPointBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    await _get_requirement(req_id, project_id)
    pt = await AiRequirementTestPoint.get_or_none(id=point_id, requirement_id=req_id, is_del=False)
    if not pt:
        raise HTTPException(status_code=404, detail="测试点不存在")
    for field in ("title", "description", "test_type", "priority", "module_path", "main_module", "sub_module", "acceptance_ref", "status"):
        val = getattr(body, field, None)
        if val is not None:
            setattr(pt, field, val)
    if body.main_module or body.sub_module:
        parts = [p for p in [pt.main_module, pt.sub_module] if p]
        if parts:
            pt.module_path = "/".join(parts)
    await pt.save()
    return StandardResponse(message="已保存", data=_point_to_dict(pt))


@router.delete("/requirements/{req_id}/test-points", summary="批量删除测试点", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def delete_test_points(
    req_id: int,
    body: DeleteTestPointsBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    await _get_requirement(req_id, project_id)
    deleted = await AiRequirementTestPoint.filter(
        requirement_id=req_id, id__in=body.point_ids, is_del=False
    ).update(is_del=True)
    return StandardResponse(message=f"已删除 {deleted} 条", data={"deleted": deleted})


@router.get("/requirements/{req_id}/test-schemes", summary="测试方案列表", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def list_schemes(
    req_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    await _get_requirement(req_id, project_id)
    schemes = await AiRequirementTestScheme.filter(requirement_id=req_id, is_del=False).order_by("-version", "-id")
    return StandardResponse(data={"list": [_scheme_to_dict(s) for s in schemes], "total": len(schemes)})


@router.get("/requirements/{req_id}/test-schemes/{scheme_id}", summary="测试方案详情", dependencies=[Depends(require_permissions(AI_TEST_VIEW))])
async def get_scheme(
    req_id: int,
    scheme_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    await _get_requirement(req_id, project_id)
    scheme = await AiRequirementTestScheme.get_or_none(id=scheme_id, requirement_id=req_id, is_del=False)
    if not scheme:
        raise HTTPException(status_code=404, detail="测试方案不存在")
    return StandardResponse(data=_scheme_to_dict(scheme))


@router.get(
    "/requirements/{req_id}/test-schemes/{scheme_id}/export-docx",
    summary="导出测试方案 Word",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def export_scheme_docx(
    req_id: int,
    scheme_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    await _get_requirement(req_id, project_id)
    scheme = await AiRequirementTestScheme.get_or_none(id=scheme_id, requirement_id=req_id, is_del=False)
    if not scheme:
        raise HTTPException(status_code=404, detail="测试方案不存在")
    content_md = scheme.content_md or ""
    if not content_md.strip():
        raise HTTPException(status_code=400, detail="方案正文为空")
    data = markdown_to_docx_bytes(content_md, scheme.title)
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", scheme.title)[:80].strip() or f"scheme_{scheme_id}"
    filename = f"{safe_name}.docx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=_attachment_headers(filename, f"test_scheme_{scheme_id}.docx"),
    )


@router.post("/requirements/{req_id}/test-schemes/generate", summary="AI 生成测试方案", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def generate_scheme(
    req_id: int,
    body: GenerateSchemeRequest,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    req = await _get_requirement(req_id, project_id)
    start_time = time.time()

    qs = AiRequirementTestPoint.filter(requirement_id=req_id, is_del=False)
    if body.test_point_ids:
        qs = qs.filter(id__in=body.test_point_ids)
    elif not body.include_unconfirmed_points:
        qs = qs.filter(status="confirmed")
    points = await qs.order_by("sort_order", "id")
    pt_dicts = [_point_to_dict(p) for p in points]
    if not pt_dicts:
        raise HTTPException(status_code=400, detail="没有可用的测试点，请先生成或确认测试点")

    scheme_title = (body.title or "").strip() or f"{req.name} 测试方案"
    scope_ids = list(body.scope_section_ids or [])
    if not scope_ids:
        for p in pt_dicts:
            for sid in p.get("section_ids") or []:
                if sid and sid not in scope_ids:
                    scope_ids.append(sid)
    all_sections = _requirement_sections(req)
    scope_sections = resolve_sections(all_sections, scope_ids) if scope_ids else all_sections
    requirement_excerpt = _build_scheme_excerpt(req, scope_ids)
    env_hints = _hints_to_dict(body.environment_hints)

    gen_config = await _get_ai_config(body.text_config_id)
    try:
        system_prompt, user_prompt = await PromptManager.render(
            "requirement_test_points_to_scheme",
            {
                "requirement_name": req.name,
                "scheme_title": scheme_title,
                "test_point_count": len(pt_dicts),
                "test_points": format_test_points_for_prompt(pt_dicts),
                "scope_section_titles": format_scope_section_titles(scope_sections),
                "requirement_excerpt": requirement_excerpt,
                "environment_hints": format_environment_hints_for_prompt(env_hints),
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        resp = await _call_llm(system_prompt, user_prompt, gen_config, min_timeout=600, max_retries=2)
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        await log_ai_usage(
            gen_config,
            "requirement_test_scheme",
            user_info=user_info,
            project_id=project_id,
            tokens_used=0,
            duration_ms=duration_ms,
            status="failed",
            input_summary=f"需求#{req_id} {scheme_title}"[:500],
            output_summary=str(e)[:500],
            requirement_id=req_id,
        )
        raise HTTPException(status_code=500, detail=f"AI 生成失败: {str(e)}")

    raw = resp.get("content", "") or ""
    content = normalize_scheme_content(_extract_json_object(raw), env_hints)
    if not content:
        raise HTTPException(status_code=500, detail="未能解析测试方案 JSON")

    content_md = render_scheme_markdown(scheme_title, content, pt_dicts)
    last_version = await AiRequirementTestScheme.filter(requirement_id=req_id, is_del=False).order_by("-version").first()
    version = (last_version.version + 1) if last_version else 1
    username = user_info.get("username") or user_info.get("sub") or "system"
    duration_ms = int((time.time() - start_time) * 1000)
    tokens = resp.get("tokens", 0)

    scheme = await AiRequirementTestScheme.create(
        requirement_id=req_id,
        project_id=project_id,
        title=scheme_title,
        version=version,
        status="draft",
        content=content,
        content_md=content_md,
        test_point_ids=[p["id"] for p in pt_dicts],
        scope_section_ids=scope_ids,
        generate_report={
            "model": gen_config.model,
            "config_name": gen_config.name,
            "tokens": tokens,
            "duration_ms": duration_ms,
        },
        create_by=username,
    )
    await AiGenerateRecord.create(
        project_id=project_id,
        generate_type="requirement_test_scheme",
        input_summary={"requirement_id": req_id, "test_point_ids": body.test_point_ids},
        output_content={"scheme_id": scheme.id, "version": version},
        status="imported",
        ai_config_id=gen_config.id,
        tokens_used=tokens,
        duration_ms=duration_ms,
        create_by=username,
    )
    await log_ai_usage(
        gen_config,
        "requirement_test_scheme",
        user_info=user_info,
        project_id=project_id,
        tokens_used=tokens,
        duration_ms=duration_ms,
        input_summary=f"需求#{req_id} {scheme_title}"[:500],
        output_summary=f"方案 v{version}",
        requirement_id=req_id,
        scheme_id=scheme.id,
        test_point_count=len(pt_dicts),
    )
    return StandardResponse(
        message=f"测试方案 v{version} 已生成",
        data=_scheme_to_dict(scheme),
    )


@router.put("/requirements/{req_id}/test-schemes/{scheme_id}", summary="编辑测试方案", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def update_scheme(
    req_id: int,
    scheme_id: int,
    body: UpdateSchemeBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    await _get_requirement(req_id, project_id)
    scheme = await AiRequirementTestScheme.get_or_none(id=scheme_id, requirement_id=req_id, is_del=False)
    if not scheme:
        raise HTTPException(status_code=404, detail="测试方案不存在")
    if body.title is not None:
        scheme.title = body.title
    if body.content_md is not None:
        scheme.content_md = body.content_md
    if body.status is not None:
        if body.status not in ("draft", "confirmed"):
            raise HTTPException(status_code=400, detail="status 仅支持 draft / confirmed")
        scheme.status = body.status
    await scheme.save()
    return StandardResponse(message="已保存", data=_scheme_to_dict(scheme))


@router.delete("/requirements/{req_id}/test-schemes/{scheme_id}", summary="删除测试方案", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def delete_scheme(
    req_id: int,
    scheme_id: int,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    project_id = _resolve_project_id(user_info, project_id)
    await _get_requirement(req_id, project_id)
    scheme = await AiRequirementTestScheme.get_or_none(id=scheme_id, requirement_id=req_id, is_del=False)
    if not scheme:
        raise HTTPException(status_code=404, detail="测试方案不存在")
    scheme.is_del = True
    await scheme.save()
    return StandardResponse(message="已删除")
