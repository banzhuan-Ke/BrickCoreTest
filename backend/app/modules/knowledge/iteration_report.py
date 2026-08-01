"""迭代测试报告生成编排：LLM → JSON → docxtpl 渲染"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

from fastapi import HTTPException

from app.models.knowledge import AiIterationReport, AiKnowledgeDocument, AiKnowledgeFolder
from app.models.sys import Project
from app.modules.ai.ai_prompts import PromptManager
from app.modules.knowledge.default_templates import load_builtin_template_bytes
from app.modules.knowledge.knowledge_context import build_knowledge_context, load_documents_for_refs
from app.modules.knowledge.knowledge_storage import load_document_source, load_report_output, save_report_output
from app.modules.knowledge.template_registry import (
    apply_custom_defaults,
    missing_bug_template_hints,
    template_covers_bug_data,
    variables_response,
)
from app.modules.knowledge.template_render import render_template, scan_template_placeholders
from app.routers.ai.generate import _call_llm, _get_ai_config


from app.modules.knowledge.report_helpers import (
    aggregate_exec_records as _aggregate_exec_records,
    build_bug_analysis_lines,
    build_bug_analysis_text,
    build_bug_detail_rows,
    build_bug_stats_rows,
    build_source_refs,
    extract_json_object as _extract_json_object,
    format_counter_text as _format_counter_text,
    format_multiline_lines,
    pass_rate_display,
)
from app.modules.knowledge.input_doc_slots import (
    GENERIC_REPORT_SLOT_PROFILES,
    ROLE_LABELS,
    build_folder_slot_preview,
    build_input_doc_source_refs,
    input_docs_to_document_ids,
    iter_input_doc_selections,
)
from app.modules.knowledge.knowledge_context_builder import build_llm_knowledge_context
from app.modules.knowledge.knowledge_project_settings import resolve_knowledge_settings
from app.core.llm.ai_usage_log import log_ai_usage

REPORT_KINDS: dict[str, dict[str, str]] = {
    "iteration_report": {
        "prompt_scene": "iteration_report",
        "title_suffix": "迭代自动化测试报告",
        "builtin_kind": "iteration_report",
        "description": "汇总 API/UI/App 多份自动化执行记录、缺陷统计与 AI 结论，适合迭代自动化收尾",
    },
    "functional_report": {
        "prompt_scene": "functional_report",
        "title_suffix": "功能测试报告",
        "builtin_kind": "functional_report",
        "description": "侧重功能范围与手工/功能用例验证，强调功能总结与缺陷分析，不含迭代自动化章节结构",
    },
    "performance_report": {
        "prompt_scene": "performance_report",
        "title_suffix": "性能测试报告",
        "builtin_kind": "performance_report",
        "description": "侧重性能指标、瓶颈与优化建议，缺陷章节从简",
    },
    "test_plan": {
        "prompt_scene": "test_plan",
        "title_suffix": "测试计划",
        "builtin_kind": "test_plan",
        "description": "结合需求与迭代资料生成测试目标、范围、策略与风险，适合迭代启动阶段",
    },
    "test_scheme": {
        "prompt_scene": "test_scheme",
        "title_suffix": "测试方案",
        "builtin_kind": "test_scheme",
        "description": "结合需求与可选测试计划生成方案级说明，含测试类型、策略、环境与准入准出",
    },
}
VALID_REPORT_KINDS = frozenset(REPORT_KINDS.keys())

# 测试计划/方案附录仅保留短摘要，避免整份需求全文灌入 Word
APPENDIX_SUMMARY_MAX_CHARS: dict[str, int] = {
    "test_plan": 2500,
    "test_scheme": 2500,
}


def _appendix_summary(text: str, report_kind: str) -> str:
    body = (text or "").strip()
    if not body:
        return ""
    limit = APPENDIX_SUMMARY_MAX_CHARS.get(report_kind)
    if limit and len(body) > limit:
        return body[:limit] + "\n…（附录摘要已截断，完整资料见资料库）"
    return body


def _normalize_milestone_rows(user_vars: Optional[dict[str, Any]]) -> list[dict[str, str]]:
    raw = (user_vars or {}).get("milestone_rows")
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, str]] = []
    for item in raw[:30]:
        if not isinstance(item, dict):
            continue
        row = {
            "name": str(item.get("name") or "").strip(),
            "start_date": str(item.get("start_date") or "").strip(),
            "end_date": str(item.get("end_date") or "").strip(),
            "owner": str(item.get("owner") or "").strip(),
            "remark": str(item.get("remark") or "").strip(),
        }
        if any(row.values()):
            rows.append(row)
    return rows


def _resolve_knowledge_scope(
    folder_id: Optional[int],
    input_docs: Optional[dict[str, Any]],
) -> tuple[Optional[list[int]], Optional[list[int]]]:
    """返回 (folder_ids, document_ids)。选了文件夹时仅使用 input_docs 中勾选的文档。"""
    if folder_id is not None:
        if input_docs is None:
            return [folder_id], None
        return None, input_docs_to_document_ids(input_docs) or []
    return None, None


async def _source_refs_for_report(
    *,
    project_id: int,
    folder_id: Optional[int],
    folder_obj: AiKnowledgeFolder | None,
    input_docs: Optional[dict[str, Any]],
    knowledge: dict[str, Any],
    template_inspect: dict[str, Any],
    exec_data: dict[str, Any],
) -> list[dict[str, Any]]:
    if folder_id is not None:
        docs = await load_documents_for_refs(project_id, folder_ids=[folder_id])
        doc_by_id = {d.id: d for d in docs}
        refs = build_input_doc_source_refs(
            {},
            folder_name=getattr(folder_obj, "name", "") or "",
            folder_label=getattr(folder_obj, "iteration_label", "") or "",
        )
        role_counts: dict[str, int] = {}
        for role, doc_id in iter_input_doc_selections(input_docs):
            doc = doc_by_id.get(doc_id)
            if not doc:
                continue
            role_counts[role] = role_counts.get(role, 0) + 1
            kind_label = ROLE_LABELS.get(role, role)
            if role_counts[role] > 1:
                kind_label = f"{kind_label} #{role_counts[role]}"
            refs.append(
                {
                    "kind": "document",
                    "kind_label": kind_label,
                    "title": doc.title or doc.file_name or "",
                    "detail": doc.file_name or "",
                    "document_id": doc.id,
                    "role": role,
                }
            )
        refs.append(
            {
                "kind": "template",
                "kind_label": "输出模板",
                "title": template_inspect.get("template_name") or "内置模板",
                "detail": template_inspect.get("source") or "",
            }
        )
        for rec in exec_data.get("exec_records") or []:
            if isinstance(rec, dict):
                refs.append(
                    {
                        "kind": "exec_record",
                        "kind_label": "执行记录",
                        "title": rec.get("name") or "执行记录",
                        "detail": f"{rec.get('report_type') or ''} · 通过率 {rec.get('pass_rate') or 0}%",
                    }
                )
        return refs
    return build_source_refs(
        folder=folder_obj,
        knowledge=knowledge,
        template_inspect=template_inspect,
        exec_data=exec_data,
    )


def _normalize_report_kind(report_kind: Optional[str]) -> str:
    kind = (report_kind or "iteration_report").strip()
    if kind not in VALID_REPORT_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的报告类型: {kind}，可选: {', '.join(sorted(VALID_REPORT_KINDS))}",
        )
    return kind


def _build_report_summary(
    knowledge: dict[str, Any],
    exec_data: dict[str, Any],
    *,
    report_kind: str,
    template_inspect: dict[str, Any],
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = settings or {}
    return {
        "report_kind": report_kind,
        "bug_total": knowledge.get("bug_total") or 0,
        "bug_open_count": knowledge.get("bug_open_count") or 0,
        "bug_closed_count": knowledge.get("bug_closed_count") or 0,
        "pass_rate": (
            None
            if not (exec_data.get("exec_records") or []) and not (exec_data.get("total_cases") or 0)
            else (exec_data.get("pass_rate") if exec_data.get("pass_rate") is not None else 0)
        ),
        "total_cases": exec_data.get("total_cases") or 0,
        "failed_case_count": exec_data.get("failed_case_count") or 0,
        "exec_record_count": len(exec_data.get("exec_records") or []),
        "knowledge_doc_count": len(knowledge.get("refs") or []),
        "template_name": template_inspect.get("template_name"),
        "template_placeholder_count": template_inspect.get("placeholder_count") or 0,
        "template_known_count": template_inspect.get("known_count") or 0,
        "template_empty": bool(template_inspect.get("empty")),
        "knowledge_truncated": bool(knowledge.get("truncated")),
        "knowledge_raw_chars": knowledge.get("raw_total_chars") or 0,
        "bug_stats_row_count": len(build_bug_stats_rows(knowledge)),
        "has_bug_data": bool(knowledge.get("bug_total") or knowledge.get("bug_export_summary")),
        "template_covers_bug": template_covers_bug_data(template_inspect.get("known") or []),
        "mapreduce_on_generate": (
            bool(knowledge.get("truncated"))
            or int(knowledge.get("raw_total_chars") or 0) > int(cfg.get("fulltext_max_chars") or 32000)
        ),
        "context_strategy": cfg.get("context_strategy") or "auto",
    }


async def _resolve_template_bytes(
    project_id: int,
    template_doc_id: Optional[int],
    *,
    report_kind: str = "iteration_report",
) -> tuple[bytes, str, str]:
    """返回 (bytes, file_name, source)，source: uploaded | project_default | builtin。"""
    if template_doc_id:
        doc = await AiKnowledgeDocument.get_or_none(
            id=template_doc_id,
            project_id=project_id,
            is_del=False,
        )
        if not doc:
            raise HTTPException(status_code=404, detail="模板文档不存在")
        if doc.doc_type not in ("report_template", "plan_template", "quality_pptx_template"):
            raise HTTPException(status_code=400, detail="所选文档不是输出模板类型")
        ext = os.path.splitext(doc.file_name or "")[1].lower()
        if doc.doc_type == "quality_pptx_template":
            if ext != ".pptx":
                raise HTTPException(status_code=400, detail="质量回顾模板须为 .pptx 格式")
        elif doc.doc_type == "report_template" and ext != ".docx":
            raise HTTPException(
                status_code=400,
                detail="报告模板须为 .docx（含 Jinja 占位符）。旧版 .doc 请在 Word 中另存为 .docx 后重新上传",
            )
        elif doc.doc_type == "plan_template" and ext != ".docx":
            raise HTTPException(status_code=400, detail="计划/方案模板须为 .docx 格式")
        raw = load_document_source(doc.storage or {}, doc.file_name)
        return raw, doc.file_name, "uploaded"

    from app.modules.knowledge.template_defaults import (
        REPORT_KIND_DOC_TYPES,
        resolve_kind_default_template,
    )

    kind_mode, kind_doc_id = await resolve_kind_default_template(project_id, report_kind)
    if kind_mode == "builtin":
        meta = REPORT_KINDS.get(report_kind) or REPORT_KINDS["iteration_report"]
        content, filename = load_builtin_template_bytes(meta["builtin_kind"])
        return content, filename, "builtin"
    if kind_mode == "doc" and kind_doc_id:
        doc = await AiKnowledgeDocument.get_or_none(
            id=kind_doc_id,
            project_id=project_id,
            is_del=False,
        )
        if doc and doc.doc_type in ("report_template", "plan_template", "quality_pptx_template"):
            ext = os.path.splitext(doc.file_name or "")[1].lower()
            ok = (
                (doc.doc_type == "quality_pptx_template" and ext == ".pptx")
                or (doc.doc_type == "plan_template" and ext == ".docx")
                or (doc.doc_type == "report_template" and ext == ".docx")
            )
            if ok:
                raw = load_document_source(doc.storage or {}, doc.file_name)
                return raw, doc.file_name, "project_kind_default"

    default = await AiKnowledgeDocument.filter(
        project_id=project_id,
        doc_type=REPORT_KIND_DOC_TYPES.get(report_kind, "report_template"),
        is_default_template=True,
        is_del=False,
    ).first()
    if default:
        raw = load_document_source(default.storage or {}, default.file_name)
        return raw, default.file_name, "project_default"

    meta = REPORT_KINDS.get(report_kind) or REPORT_KINDS["iteration_report"]
    content, filename = load_builtin_template_bytes(meta["builtin_kind"])
    return content, filename, "builtin"


async def inspect_report_template(
    project_id: int,
    template_doc_id: Optional[int] = None,
    *,
    report_kind: str = "iteration_report",
) -> dict[str, Any]:
    kind = _normalize_report_kind(report_kind)
    tpl_bytes, tpl_name, source = await _resolve_template_bytes(
        project_id, template_doc_id, report_kind=kind
    )
    ext = os.path.splitext(tpl_name or "")[1].lower()
    if kind == "quality_review" or ext == ".pptx":
        return {
            "template_name": tpl_name,
            "source": source,
            "report_kind": kind,
            "template_format": "pptx",
            "placeholder_count": 0,
            "known_count": 0,
            "unknown_count": 0,
            "empty": False,
            "known": [],
            "unknown": [],
            "has_unknown": False,
            "covers_bug_data": True,
            "missing_bug_hints": [],
            "note": "pptx 由程序按版式填充，不支持 Word 式 {{ 占位符 }}",
        }
    scanned = scan_template_placeholders(tpl_bytes, tpl_name)
    placeholders = set(scanned.get("placeholders") or [])
    cats = await variables_response(project_id, placeholders)
    known = cats.get("known") or []
    unknown = cats.get("unknown") or []
    total = len(placeholders) or len(known) + len(unknown)
    return {
        "template_name": tpl_name,
        "source": source,
        "report_kind": kind,
        "placeholder_count": total,
        "known_count": len(known),
        "unknown_count": len(unknown),
        "empty": total == 0,
        "known": known,
        "unknown": unknown,
        "has_unknown": bool(unknown),
        "covers_bug_data": template_covers_bug_data(known),
        "missing_bug_hints": missing_bug_template_hints(known),
    }


async def preview_report_inputs(
    project_id: int,
    *,
    folder_id: Optional[int] = None,
    template_doc_id: Optional[int] = None,
    document_ids: Optional[list[int]] = None,
    input_docs: Optional[dict[str, Any]] = None,
    exec_records: Optional[list[dict[str, Any]]] = None,
    report_kind: str = "iteration_report",
) -> dict[str, Any]:
    """生成前预览：模板占位符 + 资料/Bug/执行统计（不调用 LLM）。"""
    kind = _normalize_report_kind(report_kind)
    settings = await resolve_knowledge_settings(project_id)
    folder_ids, doc_ids = _resolve_knowledge_scope(folder_id, input_docs)
    if document_ids is not None and doc_ids is None and folder_id is None:
        doc_ids = document_ids
    knowledge = await build_knowledge_context(
        project_id,
        folder_ids=folder_ids,
        document_ids=doc_ids,
        max_chars=int(settings.get("fulltext_max_chars") or 32000),
    )
    exec_data = await _aggregate_exec_records(project_id, exec_records or [])
    template_inspect = await inspect_report_template(
        project_id, template_doc_id, report_kind=kind
    )
    folder_obj = None
    slot_preview: dict[str, Any] = {}
    if folder_id:
        folder_obj = await AiKnowledgeFolder.get_or_none(id=folder_id, project_id=project_id, is_del=False)
        profile = GENERIC_REPORT_SLOT_PROFILES.get(kind, GENERIC_REPORT_SLOT_PROFILES["iteration_report"])
        slot_preview = await build_folder_slot_preview(project_id, folder_id, profile)
    source_refs = await _source_refs_for_report(
        project_id=project_id,
        folder_id=folder_id,
        folder_obj=folder_obj,
        input_docs=input_docs,
        knowledge=knowledge,
        template_inspect=template_inspect,
        exec_data=exec_data,
    )
    return {
        "template": template_inspect,
        "summary": _build_report_summary(
            knowledge,
            exec_data,
            report_kind=kind,
            template_inspect=template_inspect,
            settings=settings,
        ),
        "source_refs": source_refs,
        "input_slots": slot_preview.get("input_slots") or [],
        "default_input_docs": slot_preview.get("default_input_docs") or {},
    }


async def generate_iteration_report(
    project_id: int,
    username: str,
    *,
    folder_id: Optional[int] = None,
    template_doc_id: Optional[int] = None,
    document_ids: Optional[list[int]] = None,
    input_docs: Optional[dict[str, Any]] = None,
    exec_records: Optional[list[dict[str, Any]]] = None,
    ai_config_id: Optional[int] = None,
    title: Optional[str] = None,
    author: Optional[str] = None,
    user_vars: Optional[dict[str, Any]] = None,
    report_kind: Optional[str] = None,
    existing_report: Optional[AiIterationReport] = None,
) -> dict[str, Any]:
    kind = _normalize_report_kind(report_kind)
    kind_meta = REPORT_KINDS[kind]
    prompt_scene = kind_meta["prompt_scene"]

    folder: AiKnowledgeFolder | None = None
    iteration_name = ""
    if folder_id:
        folder = await AiKnowledgeFolder.get_or_none(id=folder_id, project_id=project_id, is_del=False)
        if not folder:
            raise HTTPException(status_code=404, detail="文件夹不存在")
        iteration_name = folder.iteration_label or folder.name

    project = await Project.get_or_none(id=project_id, is_del=False)
    project_name = project.name if project else f"项目{project_id}"

    folder_ids, doc_ids = _resolve_knowledge_scope(folder_id, input_docs)
    if document_ids is not None and doc_ids is None and folder_id is None:
        doc_ids = document_ids

    settings = await resolve_knowledge_settings(project_id)
    knowledge, ctx_meta = await build_llm_knowledge_context(
        project_id,
        folder_ids=folder_ids,
        document_ids=doc_ids,
        settings=settings,
        report_kind=kind,
        ai_config_id=ai_config_id,
        project_name=project_name,
        iteration_name=iteration_name,
        username=username,
    )

    exec_data = await _aggregate_exec_records(project_id, exec_records or [])
    template_inspect = await inspect_report_template(
        project_id, template_doc_id, report_kind=kind
    )
    source_refs = await _source_refs_for_report(
        project_id=project_id,
        folder_id=folder_id,
        folder_obj=folder,
        input_docs=input_docs,
        knowledge=knowledge,
        template_inspect=template_inspect,
        exec_data=exec_data,
    )

    if existing_report:
        report = existing_report
    else:
        report = await AiIterationReport.create(
            project_id=project_id,
            folder_id=folder_id,
            title=title or f"{iteration_name or project_name} {kind_meta['title_suffix']}",
            report_kind=kind,
            config_json={
                "template_doc_id": template_doc_id,
                "document_ids": doc_ids or document_ids,
                "input_docs": input_docs or {},
                "exec_records": exec_records,
                "user_vars": user_vars,
                "report_kind": kind,
            },
            status="generating",
            created_by=username,
        )

    mapreduce_tokens = int((ctx_meta.get("mapreduce") or {}).get("tokens_used") or 0)
    if ctx_meta:
        report.config_json = {
            **(report.config_json or {}),
            "context_meta": ctx_meta,
        }
        await report.save()

    import json as _json

    prompt_ctx = {
        "project_name": project_name,
        "iteration_name": iteration_name,
        "execution_data": _json.dumps(exec_data, ensure_ascii=False, indent=2)[:12000],
        "knowledge_context": (knowledge.get("knowledge_context") or "")[
            : min(int(settings.get("fulltext_max_chars") or 32000), 48000)
        ],
        "bug_summary": knowledge.get("bug_export_summary") or "",
        "bug_total": knowledge.get("bug_total") or 0,
        "bug_open_count": knowledge.get("bug_open_count") or 0,
        "bug_closed_count": knowledge.get("bug_closed_count") or 0,
    }
    try:
        system_prompt, user_prompt = await PromptManager.render(prompt_scene, prompt_ctx)
    except ValueError as e:
        report.status = "failed"
        await report.save()
        raise HTTPException(status_code=500, detail=str(e)) from e

    text_config = await _get_ai_config(ai_config_id, scene=prompt_scene)
    t0 = time.time()
    ai_parsed: dict[str, Any] = {}
    tokens_used = 0
    try:
        llm_resp = await _call_llm(system_prompt, user_prompt, text_config, min_timeout=120, max_retries=1)
        raw = llm_resp.get("content") or ""
        ai_parsed = _extract_json_object(raw)
    except Exception as ex:
        report.status = "failed"
        report.config_json = {**(report.config_json or {}), "error": str(ex)[:500]}
        await report.save()
        await log_ai_usage(
            text_config,
            prompt_scene,
            username=username,
            project_id=project_id,
            tokens_used=0,
            duration_ms=int((time.time() - t0) * 1000),
            status="failed",
            input_summary=f"{kind_meta['title_suffix']} · {iteration_name or project_name}"[:500],
            output_summary=str(ex)[:500],
            report_id=report.id,
            report_kind=kind,
        )
        raise HTTPException(status_code=500, detail=f"LLM 调用失败: {ex}") from ex

    duration_ms = int((time.time() - t0) * 1000)
    main_tokens = int(llm_resp.get("tokens") or 0)
    await log_ai_usage(
        text_config,
        prompt_scene,
        username=username,
        project_id=project_id,
        tokens_used=main_tokens,
        duration_ms=duration_ms,
        input_summary=f"{kind_meta['title_suffix']} · {iteration_name or project_name}"[:500],
        output_summary=str(ai_parsed.get("overview") or ai_parsed.get("ai_conclusion") or "")[:500],
        report_id=report.id,
        report_kind=kind,
    )
    tokens_used = main_tokens + mapreduce_tokens
    report.ai_usage_tokens = tokens_used

    def _ai_field(key: str, fallback: str = "") -> str:
        val = ai_parsed.get(key)
        if isinstance(val, list):
            return "\n".join(f"- {x}" for x in val if x)
        return str(val).strip() if val is not None else fallback

    overview_text = _ai_field("overview")
    test_scope_text = _ai_field("test_scope")
    functional_scope_text = _ai_field("functional_scope", test_scope_text)
    functional_summary_text = _ai_field("functional_summary", _ai_field("ai_conclusion"))

    render_ctx: dict[str, Any] = {
        "project_name": project_name,
        "iteration_name": iteration_name or project_name,
        "report_date": date.today().isoformat(),
        "author": author or username,
        "pass_rate": exec_data["pass_rate"],
        "pass_rate_display": pass_rate_display(exec_data),
        "total_cases": exec_data["total_cases"],
        "failed_case_count": exec_data["failed_case_count"],
        "exec_duration": exec_data["exec_duration"],
        "failed_cases": exec_data["failed_cases"],
        "exec_records": exec_data["exec_records"],
        "knowledge_summary": _appendix_summary(knowledge.get("knowledge_summary") or "", kind),
        "bug_export_summary": knowledge.get("bug_export_summary") or "",
        "bug_total": knowledge.get("bug_total") or 0,
        "bug_open_count": knowledge.get("bug_open_count") or 0,
        "bug_closed_count": knowledge.get("bug_closed_count") or 0,
        "bug_by_severity": _format_counter_text(knowledge.get("bug_by_severity") or {}),
        "bug_by_status": _format_counter_text(knowledge.get("bug_by_status") or {}),
        "bug_by_resolution": _format_counter_text(knowledge.get("bug_by_resolution") or {}),
        "bug_by_opened_by": _format_counter_text(knowledge.get("bug_by_opened_by") or {}),
        "bug_by_assigned_to": _format_counter_text(knowledge.get("bug_by_assigned_to") or {}),
        "bug_by_resolved_by": _format_counter_text(knowledge.get("bug_by_resolved_by") or {}),
        "bug_by_priority": _format_counter_text(knowledge.get("bug_by_priority") or {}),
        "bug_by_module": _format_counter_text(knowledge.get("bug_by_module") or {}),
        "bug_stats_rows": build_bug_stats_rows(knowledge),
        "bug_analysis_text": build_bug_analysis_text(knowledge),
        "bug_analysis_lines": build_bug_analysis_lines(knowledge),
        "bug_detail_rows": build_bug_detail_rows(knowledge.get("bugs") or []),
        "bugs": knowledge.get("bugs") or [],
        "source_refs": source_refs,
        "overview": overview_text,
        "overview_lines": format_multiline_lines(overview_text),
        "test_scope": test_scope_text,
        "test_scope_lines": format_multiline_lines(test_scope_text),
        "test_objectives": _ai_field("test_objectives", overview_text),
        "test_objectives_lines": format_multiline_lines(_ai_field("test_objectives", overview_text)),
        "test_strategy": _ai_field("test_strategy"),
        "test_strategy_lines": format_multiline_lines(_ai_field("test_strategy")),
        "functional_summary": functional_summary_text,
        "functional_summary_lines": format_multiline_lines(functional_summary_text),
        "functional_scope": functional_scope_text,
        "functional_scope_lines": format_multiline_lines(functional_scope_text),
        "performance_summary": _ai_field("performance_summary", _ai_field("ai_conclusion")),
        "performance_summary_lines": format_multiline_lines(
            _ai_field("performance_summary", _ai_field("ai_conclusion"))
        ),
        "performance_metrics": _ai_field("performance_metrics"),
        "performance_metrics_lines": format_multiline_lines(_ai_field("performance_metrics")),
        "ai_conclusion": _ai_field("ai_conclusion"),
        "ai_conclusion_lines": format_multiline_lines(_ai_field("ai_conclusion")),
        "ai_summary": _ai_field("ai_summary", overview_text),
        "ai_risks": _ai_field("ai_risks"),
        "ai_risks_lines": format_multiline_lines(_ai_field("ai_risks")),
        "ai_recommendations": _ai_field("ai_recommendations"),
        "ai_recommendations_lines": format_multiline_lines(_ai_field("ai_recommendations")),
        "tester_name": (user_vars or {}).get("tester_name", ""),
        "approver": (user_vars or {}).get("approver", ""),
        "test_environment": (user_vars or {}).get("test_environment", ""),
        "plan_start_date": (user_vars or {}).get("plan_start_date", ""),
        "plan_end_date": (user_vars or {}).get("plan_end_date", ""),
        "plan_owner": (user_vars or {}).get("plan_owner", ""),
        "milestone_rows": _normalize_milestone_rows(user_vars),
    }
    await apply_custom_defaults(project_id, render_ctx)
    if user_vars:
        render_ctx.update({k: v for k, v in user_vars.items() if k != "milestone_rows"})
        render_ctx["milestone_rows"] = _normalize_milestone_rows(user_vars)

    try:
        tpl_bytes, tpl_name, _ = await _resolve_template_bytes(
            project_id, template_doc_id, report_kind=kind
        )
        out_bytes = render_template(tpl_bytes, tpl_name, render_ctx)
        out_name = f"{report.title}.docx" if tpl_name.endswith(".docx") else f"{report.title}.xlsx"
        storage_meta = save_report_output(project_id, report.id, out_name, out_bytes)
        summary = _build_report_summary(
            knowledge, exec_data, report_kind=kind, template_inspect=template_inspect
        )
        report.file_path = storage_meta.get("file_path")
        report.config_json = {
            **(report.config_json or {}),
            "output_storage": storage_meta,
            "ai_fields": ai_parsed,
            "render_ctx_keys": list(render_ctx.keys()),
            "duration_ms": duration_ms,
            "summary": summary,
            "template_inspect": template_inspect,
            "source_refs": source_refs,
        }
        report.status = "ready"
        await report.save()
    except Exception as ex:
        report.status = "failed"
        report.config_json = {**(report.config_json or {}), "render_error": str(ex)[:500]}
        await report.save()
        raise HTTPException(status_code=500, detail=f"模板渲染失败: {ex}") from ex

    summary = _build_report_summary(
        knowledge, exec_data, report_kind=kind, template_inspect=template_inspect
    )
    return {
        "id": report.id,
        "title": report.title,
        "status": report.status,
        "report_kind": kind,
        "file_path": report.file_path,
        "tokens_used": tokens_used,
        "duration_ms": duration_ms,
        "summary": summary,
        "template_inspect": template_inspect,
        "source_refs": source_refs,
    }


async def list_iteration_reports(
    project_id: int,
    *,
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    from app.core.platform.platform_settings_service import get_knowledge_report_delete_mode

    qs = AiIterationReport.filter(project_id=project_id, is_del=False).order_by("-id")
    total = await qs.count()
    rows = await qs.offset((page - 1) * size).limit(size)
    items = []
    for r in rows:
        cfg = r.config_json if isinstance(r.config_json, dict) else {}
        items.append(
            {
                "id": r.id,
                "title": r.title,
                "report_kind": r.report_kind,
                "status": r.status,
                "folder_id": r.folder_id,
                "file_path": r.file_path,
                "tokens_used": r.ai_usage_tokens,
                "created_by": r.created_by,
                "create_time": r.create_time.isoformat() if r.create_time else None,
                "source_refs": cfg.get("source_refs") or [],
                "bug_workbook_file_name": cfg.get("bug_workbook_file_name") or "",
            }
        )
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": items,
        "delete_mode": await get_knowledge_report_delete_mode(),
    }


async def get_iteration_report_detail(report_id: int, project_id: int) -> dict[str, Any]:
    report = await AiIterationReport.get_or_none(id=report_id, project_id=project_id, is_del=False)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    cfg = report.config_json if isinstance(report.config_json, dict) else {}
    return {
        "id": report.id,
        "title": report.title,
        "status": report.status,
        "report_kind": report.report_kind,
        "file_path": report.file_path,
        "tokens_used": report.ai_usage_tokens,
        "created_by": report.created_by,
        "create_time": report.create_time.isoformat() if report.create_time else None,
        "summary": cfg.get("summary"),
        "source_refs": cfg.get("source_refs") or [],
        "error": cfg.get("error") or cfg.get("render_error"),
        "duration_ms": cfg.get("duration_ms"),
    }


async def retry_iteration_report(report_id: int, project_id: int) -> dict[str, Any]:
    """重试失败的报告生成任务。"""
    report = await AiIterationReport.get_or_none(id=report_id, project_id=project_id, is_del=False)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    if report.status != "failed":
        raise HTTPException(status_code=400, detail="仅失败记录可重试")
    cfg = report.config_json if isinstance(report.config_json, dict) else {}
    cfg = {k: v for k, v in cfg.items() if k not in ("error", "render_error")}
    report.status = "generating"
    report.config_json = cfg
    await report.save()
    kind = report.report_kind or ""
    if kind.startswith("digitech_") or kind == "quality_review":
        try:
            from app.modules.knowledge.packs.digitech.digitech_task_runner import run_digitech_report_task
        except ImportError as ex:
            raise HTTPException(status_code=400, detail="行业定制报告能力未开通，请联系管理员") from ex

        asyncio.create_task(run_digitech_report_task(report.id))
    else:
        asyncio.create_task(_run_iteration_report_task(report.id))
    return {
        "id": report.id,
        "title": report.title,
        "status": report.status,
        "report_kind": report.report_kind,
    }


async def start_iteration_report(
    project_id: int,
    username: str,
    *,
    folder_id: Optional[int] = None,
    template_doc_id: Optional[int] = None,
    document_ids: Optional[list[int]] = None,
    input_docs: Optional[dict[str, Any]] = None,
    exec_records: Optional[list[dict[str, Any]]] = None,
    ai_config_id: Optional[int] = None,
    title: Optional[str] = None,
    author: Optional[str] = None,
    user_vars: Optional[dict[str, Any]] = None,
    report_kind: Optional[str] = None,
) -> dict[str, Any]:
    """创建生成任务并后台执行，立即返回 report id。"""
    kind = _normalize_report_kind(report_kind)
    kind_meta = REPORT_KINDS[kind]

    iteration_name = ""
    if folder_id:
        folder = await AiKnowledgeFolder.get_or_none(id=folder_id, project_id=project_id, is_del=False)
        if not folder:
            raise HTTPException(status_code=404, detail="文件夹不存在")
        iteration_name = folder.iteration_label or folder.name

    project = await Project.get_or_none(id=project_id, is_del=False)
    project_name = project.name if project else f"项目{project_id}"

    report = await AiIterationReport.create(
        project_id=project_id,
        folder_id=folder_id,
        title=title or f"{iteration_name or project_name} {kind_meta['title_suffix']}",
        report_kind=kind,
        config_json={
            "template_doc_id": template_doc_id,
            "document_ids": document_ids,
            "input_docs": input_docs or {},
            "exec_records": exec_records,
            "user_vars": user_vars,
            "report_kind": kind,
            "ai_config_id": ai_config_id,
            "author": author,
            "username": username,
        },
        status="generating",
        created_by=username,
    )
    asyncio.create_task(_run_iteration_report_task(report.id))
    return {
        "id": report.id,
        "title": report.title,
        "status": report.status,
        "report_kind": kind,
    }


async def _run_iteration_report_task(report_id: int) -> None:
    report = await AiIterationReport.get_or_none(id=report_id)
    if not report or report.status != "generating":
        return
    if report.report_kind == "quality_review":
        try:
            from app.modules.knowledge.packs.digitech.digitech_task_runner import run_digitech_report_task
        except ImportError:
            cfg = report.config_json if isinstance(report.config_json, dict) else {}
            report.status = "failed"
            report.config_json = {**cfg, "error": "行业定制报告能力未开通，请联系管理员"}
            await report.save()
            return

        await run_digitech_report_task(report.id)
        return
    cfg = report.config_json if isinstance(report.config_json, dict) else {}
    try:
        await generate_iteration_report(
            report.project_id,
            cfg.get("username") or report.created_by or "",
            folder_id=report.folder_id,
            template_doc_id=cfg.get("template_doc_id"),
            document_ids=cfg.get("document_ids"),
            input_docs=cfg.get("input_docs"),
            exec_records=cfg.get("exec_records"),
            ai_config_id=cfg.get("ai_config_id"),
            title=report.title,
            author=cfg.get("author"),
            user_vars=cfg.get("user_vars"),
            report_kind=report.report_kind,
            existing_report=report,
        )
    except HTTPException as ex:
        detail = ex.detail if isinstance(ex.detail, str) else str(ex.detail)
        cfg = report.config_json if isinstance(report.config_json, dict) else {}
        report.status = "failed"
        report.config_json = {**cfg, "error": detail[:500]}
        await report.save()
        logger.warning("iteration report failed report_id=%s: %s", report_id, detail)
    except Exception as ex:
        logger.exception("iteration report task error report_id=%s", report_id)
        cfg = report.config_json if isinstance(report.config_json, dict) else {}
        report.status = "failed"
        report.config_json = {**cfg, "error": str(ex)[:500]}
        await report.save()


async def get_report_download_bytes(
    report_id: int,
    project_id: int,
    *,
    attachment: str = "main",
) -> tuple[bytes, str]:
    report = await AiIterationReport.get_or_none(id=report_id, project_id=project_id, is_del=False)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    if report.status != "ready":
        raise HTTPException(status_code=400, detail="报告尚未生成完成")
    return load_report_attachment_bytes(report, attachment)


def load_report_attachment_bytes(report: AiIterationReport, attachment: str = "main") -> tuple[bytes, str]:
    """按附件类型读取报告产物（主文件 / Bug 工作簿等）。"""
    cfg = report.config_json if isinstance(report.config_json, dict) else {}
    if attachment == "bug_workbook":
        storage = cfg.get("bug_workbook_storage") or {}
        file_name = cfg.get("bug_workbook_file_name") or ""
        if not storage or not file_name:
            raise HTTPException(status_code=404, detail="Bug 统计文件不存在")
        return load_report_output(storage, file_name), file_name

    storage = cfg.get("output_storage") or {}
    if not storage:
        raise HTTPException(status_code=404, detail="报告文件不存在")
    file_name = cfg.get("output_file_name")
    if not file_name:
        kind = report.report_kind or ""
        if kind in ("digitech_quality", "quality_review"):
            ext = ".pptx"
        elif kind == "digitech_bug_workbook":
            ext = ".xlsx"
        else:
            ext = ".docx"
        file_name = f"{report.title}{ext}"
    return load_report_output(storage, file_name), file_name


async def delete_iteration_report(report_id: int, project_id: int) -> dict[str, Any]:
    from app.core.platform.platform_settings_service import (
        delete_iteration_report_record,
        get_knowledge_report_delete_mode,
    )

    report = await AiIterationReport.get_or_none(id=report_id, project_id=project_id, is_del=False)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    delete_result = await delete_iteration_report_record(report)
    return {
        "id": report_id,
        "delete_result": delete_result,
        "delete_mode": await get_knowledge_report_delete_mode(),
    }


async def validate_document_template(doc_id: int, project_id: int) -> dict[str, Any]:
    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    raw = load_document_source(doc.storage or {}, doc.file_name)
    scanned = scan_template_placeholders(raw, doc.file_name)
    result = await variables_response(project_id, set(scanned.get("placeholders") or []))
    doc.template_schema = result
    await doc.save()
    return result
