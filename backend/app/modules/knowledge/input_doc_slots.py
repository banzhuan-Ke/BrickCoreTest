"""报告/方案生成 — 输入文档槽位（按文件类型手动选择）"""
from __future__ import annotations

from typing import Any, Optional

from app.models.knowledge import AiKnowledgeDocument
from app.modules.knowledge.constants import DOC_TYPES
from app.modules.knowledge.knowledge_context import load_documents_for_refs, _is_bug_export_candidate

try:
    from app.modules.knowledge.packs.digitech.doc_classifier import classify_digitech_doc
except ImportError:  # CE / 未打包行业扩展时
    def classify_digitech_doc(doc: AiKnowledgeDocument) -> Optional[str]:  # type: ignore[misc]
        return None

# 同一迭代可有多份文档的类型（如多份 PRD/需求）
MULTI_SELECT_ROLES = frozenset({"requirement"})

ROLE_LABELS: dict[str, str] = {
    "iteration_plan": "迭代计划",
    "test_plan": "测试计划",
    "bug_export": "Bug 导出",
    "task_export": "任务导出",
    "dev_hours_export": "开发工时单",
    "case_export": "用例导出",
    "requirement": "需求文档",
    "summary": "测试总结",
    "scheme_template": "方案模板",
    "report_template": "报告模板",
    "quality_pptx_template": "质量回顾模板",
}

DIGITECH_SLOT_PROFILES: dict[str, list[tuple[str, bool]]] = {
    "scheme": [
        ("iteration_plan", True),
        ("test_plan", False),
        ("case_export", False),
    ],
    "report": [
        ("iteration_plan", True),
        ("bug_export", True),
        ("test_plan", False),
        ("case_export", False),
    ],
    "quality": [
        ("bug_export", True),
        ("task_export", False),
        ("dev_hours_export", False),
    ],
    "bug_workbook": [
        ("bug_export", True),
    ],
}

GENERIC_REPORT_SLOT_PROFILES: dict[str, list[tuple[str, bool]]] = {
    "iteration_report": [
        ("iteration_plan", False),
        ("test_plan", False),
        ("bug_export", False),
        ("requirement", False),
        ("task_export", False),
        ("summary", False),
    ],
    "functional_report": [
        ("requirement", False),
        ("test_plan", False),
        ("bug_export", False),
    ],
    "performance_report": [
        ("test_plan", False),
        ("summary", False),
        ("bug_export", False),
    ],
    "test_plan": [
        ("requirement", False),
        ("iteration_plan", False),
        ("case_export", False),
    ],
    "test_scheme": [
        ("requirement", False),
        ("iteration_plan", False),
        ("test_plan", False),
        ("case_export", False),
    ],
}


def _detect_doc_role(doc: AiKnowledgeDocument) -> str:
    digitech_role = classify_digitech_doc(doc)
    if digitech_role:
        return digitech_role
    if doc.doc_type in DOC_TYPES and doc.doc_type != "other":
        return doc.doc_type
    fn = (doc.file_name or "").lower()
    title = (doc.title or "").lower()
    if any(h in fn or h in title for h in ("需求", "prd", "requirement", "spec")):
        return "requirement"
    if _is_bug_export_candidate(doc):
        return "bug_export"
    return "other"


def _doc_payload(doc: AiKnowledgeDocument, *, role: str) -> dict[str, Any]:
    return {
        "id": doc.id,
        "title": doc.title,
        "file_name": doc.file_name,
        "doc_type": doc.doc_type,
        "doc_type_label": DOC_TYPES.get(doc.doc_type or "", doc.doc_type or ""),
        "detected_role": role,
        "role_label": ROLE_LABELS.get(role, role),
    }


async def list_folder_documents(project_id: int, folder_id: int) -> list[dict[str, Any]]:
    docs = await load_documents_for_refs(project_id, folder_ids=[folder_id])
    items = [_doc_payload(doc, role=_detect_doc_role(doc)) for doc in docs]
    items.sort(key=lambda x: (x.get("detected_role") or "other", x.get("title") or ""))
    return items


def _candidates_for_role(docs: list[AiKnowledgeDocument], role: str) -> list[AiKnowledgeDocument]:
    matched = [d for d in docs if _detect_doc_role(d) == role]
    if matched:
        return matched
    if role in DOC_TYPES:
        return [d for d in docs if (d.doc_type or "") == role]
    return []


def build_slot_options(
    docs: list[AiKnowledgeDocument],
    profile: list[tuple[str, bool]],
) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for role, required in profile:
        candidates = _candidates_for_role(docs, role)
        multiple = role in MULTI_SELECT_ROLES
        if multiple:
            default_ids = [c.id for c in candidates]
            default_id = default_ids[0] if len(default_ids) == 1 else None
        else:
            default_ids = []
            default_id = candidates[0].id if candidates else None
        slots.append(
            {
                "key": role,
                "label": ROLE_LABELS.get(role, role),
                "required": required,
                "multiple": multiple,
                "default_id": default_id,
                "default_ids": default_ids,
                "candidates": [_doc_payload(d, role=_detect_doc_role(d)) for d in candidates],
            }
        )
    return slots


def missing_required_slots(slots: list[dict[str, Any]], input_docs: dict[str, Any] | None) -> list[str]:
    selected = input_docs or {}
    missing: list[str] = []
    for slot in slots:
        if not slot.get("required"):
            continue
        key = slot["key"]
        val = selected.get(key)
        if slot.get("multiple"):
            if not (val or slot.get("default_ids")):
                missing.append(key)
            continue
        doc_id = val or slot.get("default_id")
        if not doc_id:
            missing.append(key)
    return missing


def resolve_selected_doc(
    docs: list[AiKnowledgeDocument],
    role: str,
    input_docs: dict[str, int] | None,
    default_doc: AiKnowledgeDocument | None,
) -> Optional[AiKnowledgeDocument]:
    if input_docs and role in input_docs:
        doc_id = input_docs[role]
        for doc in docs:
            if doc.id == doc_id:
                return doc
        return None
    return default_doc


def input_docs_to_document_ids(input_docs: dict[str, Any] | None) -> list[int] | None:
    if not input_docs:
        return None
    ids: list[int] = []
    for val in input_docs.values():
        if val is None:
            continue
        if isinstance(val, list):
            ids.extend(int(v) for v in val if v)
        else:
            ids.append(int(val))
    return ids or None


def iter_input_doc_selections(input_docs: dict[str, Any] | None) -> list[tuple[str, int]]:
    """展开 input_docs 为 (role, document_id) 列表，支持多选。"""
    if not input_docs:
        return []
    pairs: list[tuple[str, int]] = []
    for role, val in input_docs.items():
        if val is None:
            continue
        if isinstance(val, list):
            for doc_id in val:
                if doc_id:
                    pairs.append((role, int(doc_id)))
        else:
            pairs.append((role, int(val)))
    return pairs


def build_input_doc_source_refs(
    docs_by_role: dict[str, AiKnowledgeDocument | None],
    *,
    folder_name: str = "",
    folder_label: str = "",
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if folder_name:
        refs.append(
            {
                "kind": "folder",
                "kind_label": "迭代文件夹",
                "title": folder_name,
                "detail": folder_label,
            }
        )
    for role, doc in docs_by_role.items():
        if doc is None:
            continue
        refs.append(
            {
                "kind": "document",
                "kind_label": ROLE_LABELS.get(role, role),
                "title": doc.title or doc.file_name or "",
                "detail": doc.file_name or "",
                "document_id": doc.id,
                "role": role,
            }
        )
    return refs


async def build_folder_slot_preview(
    project_id: int,
    folder_id: int,
    profile: list[tuple[str, bool]],
) -> dict[str, Any]:
    docs = await load_documents_for_refs(project_id, folder_ids=[folder_id])
    slots = build_slot_options(docs, profile)
    defaults: dict[str, Any] = {}
    for slot in slots:
        if slot.get("multiple"):
            if slot.get("default_ids"):
                defaults[slot["key"]] = list(slot["default_ids"])
        elif slot.get("default_id"):
            defaults[slot["key"]] = slot["default_id"]
    return {
        "folder_documents": [_doc_payload(d, role=_detect_doc_role(d)) for d in docs],
        "input_slots": slots,
        "default_input_docs": defaults,
        "missing_required": missing_required_slots(slots, defaults),
    }
