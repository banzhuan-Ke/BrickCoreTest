"""表格旁路问答编排"""
from __future__ import annotations

from typing import Any, Optional

from app.models.knowledge import AiKnowledgeDocument
from app.modules.knowledge.knowledge_qa_classify import classify_qa_question
from app.modules.knowledge.knowledge_qa_tabular_exec import execute_tabular_plan, format_tabular_answer
from app.modules.knowledge.knowledge_qa_tabular_parse import parse_tabular_query
from app.modules.knowledge.knowledge_retrieve import load_documents_for_qa_scope
from app.modules.knowledge.knowledge_sections_read import is_sections_json_v2, iter_tabular_sheets
from app.modules.knowledge.knowledge_tabular_profiles import field_display_label


def _is_tabular_doc(doc: AiKnowledgeDocument) -> bool:
    sj = doc.sections_json if isinstance(doc.sections_json, dict) else {}
    if not is_sections_json_v2(sj):
        return False
    structured = sj.get("structured") if isinstance(sj.get("structured"), dict) else {}
    if structured.get("kind") == "tabular":
        return True
    return bool(iter_tabular_sheets(sj))


async def _resolve_tabular_doc(
    project_id: int,
    *,
    folder_ids: Optional[list[int]] = None,
    document_ids: Optional[list[int]] = None,
) -> tuple[Optional[AiKnowledgeDocument], Optional[str]]:
    docs = await load_documents_for_qa_scope(
        project_id,
        folder_ids=folder_ids,
        document_ids=document_ids,
    )
    tabular = [d for d in docs if _is_tabular_doc(d)]
    if not tabular:
        return None, "scope内无 v2 表格文档"

    if document_ids and len(document_ids) == 1:
        wanted_id = int(document_ids[0])
        specified = next((d for d in docs if int(d.id) == wanted_id), None)
        if not specified:
            return None, f"指定文档 #{wanted_id} 不在范围内"
        if not _is_tabular_doc(specified):
            return None, "指定文档不是 v2 表格，无法做精确统计"
        return specified, None

    if len(tabular) == 1:
        return tabular[0], None
    return None, "范围内有多份表格文档，请指定 1 份 Excel/CSV"


async def try_tabular_qa(
    project_id: int,
    *,
    query: str,
    folder_ids: Optional[list[int]] = None,
    document_ids: Optional[list[int]] = None,
) -> Optional[dict[str, Any]]:
    classification = classify_qa_question(query)
    qtype = classification.get("question_type")
    if qtype not in ("stat", "coverage", "mixed"):
        return None

    doc, scope_reason = await _resolve_tabular_doc(
        project_id,
        folder_ids=folder_ids,
        document_ids=document_ids,
    )
    if not doc:
        if qtype in ("stat", "coverage"):
            return {
                "tabular_fallback": True,
                "tabular_fallback_reason": scope_reason or "无法确定唯一表格文档",
                "answer_path": "rag",
            }
        return None

    plan = parse_tabular_query(query, doc)
    if not plan:
        return {
            "tabular_fallback": True,
            "tabular_fallback_reason": "未能解析出有效的表格过滤条件",
            "answer_path": "rag",
            "question_type": qtype,
        }

    sections_json = doc.sections_json if isinstance(doc.sections_json, dict) else {}
    try:
        result = execute_tabular_plan(plan, sections_json)
    except Exception as ex:
        return {
            "tabular_fallback": True,
            "tabular_fallback_reason": f"表格执行失败: {ex}",
            "answer_path": "rag",
            "question_type": qtype,
        }

    if result.get("error"):
        return {
            "tabular_fallback": True,
            "tabular_fallback_reason": result.get("error"),
            "answer_path": "rag",
            "question_type": qtype,
        }

    answer = format_tabular_answer(plan, result)
    flt = plan.filters[0] if plan.filters else None
    basis: dict[str, Any] = {
        "document_id": doc.id,
        "document_title": doc.title,
        "profile": plan.profile,
        "sheet_name": plan.sheet_name,
        "matched_count": result.get("matched_count"),
        "total_rows": result.get("total_rows"),
        "stored_row_count": result.get("stored_row_count"),
        "rows_truncated": result.get("rows_truncated"),
    }
    if flt:
        basis["field_label"] = field_display_label(plan.profile, flt.field, flt.column)
        basis["filter"] = f"{flt.column} = {flt.value}"

    return {
        "strategy": "structured_tabular",
        "answer_path": "structured_tabular",
        "answer": answer,
        "question_type": qtype,
        "tabular_basis": basis,
        "matched_rows_preview": result.get("matched_rows_preview") or [],
        "group_by_result": result.get("group_by_result"),
        "tabular_fallback": False,
        "context_text": answer,
        "doc_count": 1,
        "hit_count": int(result.get("matched_count") or 0),
    }
