"""按报告类型的项目默认输出模板映射"""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import HTTPException

from app.models.knowledge import AiKnowledgeDocument
from app.modules.knowledge.default_templates import BUILTIN_TEMPLATE_CATALOG, load_builtin_template_bytes
from app.modules.knowledge.knowledge_project_settings import load_knowledge_project_settings, save_knowledge_project_settings
from app.modules.knowledge.knowledge_storage import load_document_source
from app.modules.knowledge.template_registry import categorize_variables, template_covers_bug_data
from app.modules.knowledge.template_render import scan_template_placeholders

REPORT_KIND_DOC_TYPES: dict[str, str] = {
    "iteration_report": "report_template",
    "functional_report": "report_template",
    "performance_report": "report_template",
    "test_plan": "plan_template",
    "test_scheme": "plan_template",
}

BUG_RELEVANT_REPORT_KINDS = frozenset({"iteration_report", "functional_report", "performance_report"})

KindResolution = Literal["unset", "builtin", "doc"]


def _valid_report_kinds() -> frozenset[str]:
    from app.modules.knowledge.iteration_report import VALID_REPORT_KINDS

    return VALID_REPORT_KINDS


def _report_kinds_meta() -> dict[str, dict[str, str]]:
    from app.modules.knowledge.iteration_report import REPORT_KINDS

    return REPORT_KINDS


def normalize_default_template_by_kind(raw: Any) -> dict[str, Optional[int]]:
    valid = _valid_report_kinds()
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Optional[int]] = {}
    for kind in valid:
        if kind not in raw:
            continue
        val = raw[kind]
        if val is None or val == "":
            out[kind] = None
            continue
        try:
            doc_id = int(val)
        except (TypeError, ValueError):
            continue
        if doc_id > 0:
            out[kind] = doc_id
    return out


async def resolve_kind_default_template(
    project_id: int,
    report_kind: str,
) -> tuple[KindResolution, Optional[int]]:
    settings = await load_knowledge_project_settings(project_id)
    mapping = normalize_default_template_by_kind(settings.get("default_template_by_kind"))
    if report_kind not in mapping:
        return "unset", None
    doc_id = mapping[report_kind]
    if doc_id is None:
        return "builtin", None
    return "doc", doc_id


async def _inspect_template_doc(
    project_id: int,
    doc: AiKnowledgeDocument,
) -> dict[str, Any]:
    from app.modules.knowledge.template_registry import categorize_variables_for_project

    raw = load_document_source(doc.storage or {}, doc.file_name)
    scanned = scan_template_placeholders(raw, doc.file_name)
    placeholders = set(scanned.get("placeholders") or [])
    cats = await categorize_variables_for_project(project_id, placeholders)
    known = cats.get("known") or []
    unknown = cats.get("unknown") or []
    total = len(placeholders) or len(known) + len(unknown)
    return {
        "template_doc_id": doc.id,
        "template_name": doc.title or doc.file_name,
        "file_name": doc.file_name,
        "source": "uploaded",
        "placeholder_count": total,
        "known_count": len(known),
        "unknown_count": len(unknown),
        "empty": total == 0,
        "known": known,
        "unknown": unknown,
        "covers_bug_data": template_covers_bug_data(known),
    }


async def _inspect_builtin_template(report_kind: str) -> dict[str, Any]:
    from app.modules.knowledge.default_templates import (
        BUILTIN_TEMPLATE_CATALOG,
        PPTX_BUILTIN_TEMPLATE_CATALOG,
        is_pptx_builtin_kind,
        load_builtin_template_bytes,
    )

    report_kinds = _report_kinds_meta()
    meta = report_kinds.get(report_kind) or report_kinds["iteration_report"]
    builtin_kind = meta["builtin_kind"]

    if is_pptx_builtin_kind(builtin_kind):
        content, filename = load_builtin_template_bytes(builtin_kind)
        pptx_meta = PPTX_BUILTIN_TEMPLATE_CATALOG.get(builtin_kind) or {}
        return {
            "template_doc_id": None,
            "template_name": pptx_meta.get("filename") or filename,
            "file_name": filename,
            "source": "builtin",
            "template_format": "pptx",
            "placeholder_count": 0,
            "known_count": 0,
            "unknown_count": 0,
            "empty": False,
            "known": [],
            "unknown": [],
            "covers_bug_data": True,
            "note": "pptx 由程序按版式填充，不支持 Word 式 {{ 占位符 }}",
            "size_bytes": len(content),
        }

    content, filename = load_builtin_template_bytes(builtin_kind)
    scanned = scan_template_placeholders(content, filename)
    placeholders = set(scanned.get("placeholders") or [])
    cats = categorize_variables(placeholders)
    known = cats.get("known") or []
    unknown = cats.get("unknown") or []
    total = len(placeholders) or len(known) + len(unknown)
    catalog = BUILTIN_TEMPLATE_CATALOG.get(builtin_kind) or {}
    return {
        "template_doc_id": None,
        "template_name": catalog.get("filename") or filename,
        "file_name": filename,
        "source": "builtin",
        "placeholder_count": total,
        "known_count": len(known),
        "unknown_count": len(unknown),
        "empty": total == 0,
        "known": known,
        "unknown": unknown,
        "covers_bug_data": template_covers_bug_data(known),
    }


async def _effective_template_inspect(
    project_id: int,
    report_kind: str,
    *,
    configured_doc_id: Optional[int] | str = "unset",
) -> dict[str, Any]:
    if configured_doc_id != "unset" and configured_doc_id is None:
        inspect = await _inspect_builtin_template(report_kind)
        inspect["effective_source"] = "project_kind_builtin"
        return inspect

    doc_id: Optional[int] = None
    source_chain: list[str] = []

    if configured_doc_id != "unset" and isinstance(configured_doc_id, int):
        doc_id = configured_doc_id
        source_chain.append("project_kind_default")
    else:
        legacy = await AiKnowledgeDocument.filter(
            project_id=project_id,
            doc_type=REPORT_KIND_DOC_TYPES.get(report_kind, "report_template"),
            is_default_template=True,
            is_del=False,
        ).first()
        if legacy:
            doc_id = legacy.id
            source_chain.append("legacy_global_default")

    if doc_id:
        doc = await AiKnowledgeDocument.get_or_none(
            id=doc_id,
            project_id=project_id,
            is_del=False,
        )
        expected_type = REPORT_KIND_DOC_TYPES.get(report_kind, "report_template")
        if doc and doc.doc_type == expected_type:
            inspect = await _inspect_template_doc(project_id, doc)
            inspect["effective_source"] = source_chain[0] if source_chain else "uploaded"
            return inspect

    inspect = await _inspect_builtin_template(report_kind)
    inspect["effective_source"] = "builtin"
    return inspect


async def list_default_template_mappings(project_id: int) -> dict[str, Any]:
    settings = await load_knowledge_project_settings(project_id)
    mapping = normalize_default_template_by_kind(settings.get("default_template_by_kind"))
    report_kinds = _report_kinds_meta()

    report_templates = await AiKnowledgeDocument.filter(
        project_id=project_id,
        doc_type="report_template",
        is_del=False,
    ).order_by("-is_default_template", "-id")
    plan_templates = await AiKnowledgeDocument.filter(
        project_id=project_id,
        doc_type="plan_template",
        is_del=False,
    ).order_by("-is_default_template", "-id")
    quality_templates = await AiKnowledgeDocument.filter(
        project_id=project_id,
        doc_type="quality_pptx_template",
        is_del=False,
    ).order_by("-is_default_template", "-id")

    def _doc_option(doc: AiKnowledgeDocument) -> dict[str, Any]:
        return {
            "id": doc.id,
            "title": doc.title,
            "file_name": doc.file_name,
            "is_default_template": doc.is_default_template,
        }

    items: list[dict[str, Any]] = []
    for kind, meta in report_kinds.items():
        configured = mapping.get(kind, "unset")
        configured_doc_id: Optional[int] | str = configured if kind in mapping else "unset"
        effective = await _effective_template_inspect(
            project_id,
            kind,
            configured_doc_id=configured_doc_id,
        )
        doc_type = REPORT_KIND_DOC_TYPES.get(kind, "report_template")
        if doc_type == "quality_pptx_template":
            candidates = quality_templates
        elif doc_type == "report_template":
            candidates = report_templates
        else:
            candidates = plan_templates
        items.append(
            {
                "report_kind": kind,
                "label": meta["title_suffix"],
                "description": meta.get("description") or "",
                "doc_type": doc_type,
                "configured_template_doc_id": configured if kind in mapping else None,
                "configured_mode": (
                    "builtin"
                    if kind in mapping and mapping[kind] is None
                    else ("uploaded" if kind in mapping and mapping[kind] else "unset")
                ),
                "effective": effective,
                "candidates": [_doc_option(d) for d in candidates],
                "needs_bug_placeholders": kind in BUG_RELEVANT_REPORT_KINDS,
            }
        )

    return {
        "items": items,
        "default_template_by_kind": {k: mapping[k] for k in sorted(mapping.keys())},
    }


async def save_default_template_mappings(
    project_id: int,
    updates: dict[str, Any],
) -> dict[str, Any]:
    valid_kinds = _valid_report_kinds()
    report_kinds = _report_kinds_meta()
    if not isinstance(updates, dict):
        raise HTTPException(status_code=400, detail="mappings 须为对象")
    current = await load_knowledge_project_settings(project_id)
    mapping = normalize_default_template_by_kind(current.get("default_template_by_kind"))

    for kind, val in updates.items():
        if kind not in valid_kinds:
            raise HTTPException(status_code=400, detail=f"不支持的报告类型: {kind}")
        if val is None or val == "" or val == 0:
            mapping[kind] = None
            continue
        if val == "unset":
            mapping.pop(kind, None)
            continue
        try:
            doc_id = int(val)
        except (TypeError, ValueError) as ex:
            raise HTTPException(status_code=400, detail=f"{kind} 的模板 id 无效") from ex
        expected_type = REPORT_KIND_DOC_TYPES.get(kind, "report_template")
        doc = await AiKnowledgeDocument.get_or_none(
            id=doc_id,
            project_id=project_id,
            is_del=False,
        )
        if not doc:
            raise HTTPException(status_code=404, detail=f"模板文档不存在: {doc_id}")
        if doc.doc_type != expected_type:
            raise HTTPException(
                status_code=400,
                detail=f"{report_kinds[kind]['title_suffix']}须使用 {expected_type} 类型模板",
            )
        ext = (doc.file_name or "").lower()
        if expected_type == "quality_pptx_template":
            if not ext.endswith(".pptx"):
                raise HTTPException(status_code=400, detail="质量回顾模板须为 .pptx 格式")
        elif expected_type in ("report_template", "plan_template") and not ext.endswith(".docx"):
            raise HTTPException(status_code=400, detail="输出模板须为 .docx 格式")
        mapping[kind] = doc_id

    saved = await save_knowledge_project_settings(
        project_id,
        {"default_template_by_kind": mapping},
    )
    return normalize_default_template_by_kind(saved.get("default_template_by_kind"))
