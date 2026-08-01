"""prose 文档增强问答：narrow_fulltext / section_first / layered_rag"""
from __future__ import annotations

import re
from typing import Any, Optional

from app.models.knowledge import AiKnowledgeDocument
from app.modules.knowledge.knowledge_qa_classify import classify_qa_question
from app.modules.knowledge.knowledge_qa_section_match import pick_sections_for_query
from app.modules.knowledge.knowledge_retrieve import load_documents_for_qa_scope, retrieve_knowledge
from app.modules.knowledge.knowledge_sections_read import is_sections_json_v2

NARROW_FULLTEXT_MAX_CHARS = 32000
NARROW_MAX_DOCS = 3


def _is_prose_doc(doc: AiKnowledgeDocument) -> bool:
    sj = doc.sections_json if isinstance(doc.sections_json, dict) else {}
    if not is_sections_json_v2(sj):
        return False
    structured = sj.get("structured") if isinstance(sj.get("structured"), dict) else {}
    return structured.get("kind") == "prose" or bool(sj.get("sections"))


def _prose_docs_in_scope(docs: list[AiKnowledgeDocument]) -> list[AiKnowledgeDocument]:
    return [d for d in docs if _is_prose_doc(d)]


def _prose_doc_char_count(doc: AiKnowledgeDocument) -> int:
    sj = doc.sections_json if isinstance(doc.sections_json, dict) else {}
    fulltext = (sj.get("fulltext") or "").strip()
    if fulltext:
        return len(fulltext)
    total = 0
    for sec in sj.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        total += len((sec.get("content") or sec.get("text") or ""))
        total += len((sec.get("title") or ""))
    return total


def _build_narrow_context(docs: list[AiKnowledgeDocument]) -> tuple[str, list[dict[str, Any]], bool]:
    parts: list[str] = []
    sections_used: list[dict[str, Any]] = []
    truncated = False
    total = 0

    for doc in docs[:NARROW_MAX_DOCS]:
        sj = doc.sections_json if isinstance(doc.sections_json, dict) else {}
        fulltext = (sj.get("fulltext") or "").strip()
        if fulltext:
            block = f"--- 《{doc.title}》 ---\n{fulltext}"
        else:
            sec_parts = []
            for sec in sj.get("sections") or []:
                if not isinstance(sec, dict):
                    continue
                title = (sec.get("title") or "").strip()
                body = (sec.get("content") or "").strip()
                sec_parts.append(f"## {title}\n{body}" if title else body)
            block = f"--- 《{doc.title}》 ---\n" + "\n\n".join(sec_parts)

        if total + len(block) > NARROW_FULLTEXT_MAX_CHARS:
            remain = NARROW_FULLTEXT_MAX_CHARS - total
            if remain > 200:
                parts.append(block[:remain] + "\n…（全文已截断）")
                truncated = True
            break
        parts.append(block)
        total += len(block)
        sections_used.append({"document_id": doc.id, "title": doc.title, "mode": "fulltext"})

    return "\n\n".join(parts).strip(), sections_used, truncated


def _build_section_context(
    doc: AiKnowledgeDocument,
    query: str,
    *,
    max_chars: int = 32000,
) -> tuple[str, list[dict[str, Any]], bool]:
    sj = doc.sections_json if isinstance(doc.sections_json, dict) else {}
    sections = sj.get("sections") or []
    picked = pick_sections_for_query(query, sections, top_n=5)
    if not picked:
        return "", [], False

    parts: list[str] = []
    used: list[dict[str, Any]] = []
    truncated = False
    total = 0
    header = f"--- 《{doc.title}》章节命中 ---\n"
    total += len(header)

    for sec in picked:
        title = (sec.get("title") or "章节").strip()
        body = (sec.get("content") or "").strip()
        block = f"## {title}\n{body}"
        if total + len(block) + 2 > max_chars:
            remain = max_chars - total - 2
            if remain > 200:
                parts.append(block[:remain] + "\n…（章节内容已截断）")
                item = {"document_id": doc.id, "title": title, "mode": "section", "truncated": True}
                if sec.get("page") is not None:
                    item["page"] = sec["page"]
                used.append(item)
                truncated = True
            break
        parts.append(block)
        total += len(block) + 2
        item = {"document_id": doc.id, "title": title, "mode": "section"}
        if sec.get("page") is not None:
            item["page"] = sec["page"]
        used.append(item)

    if not parts:
        return "", [], False
    return header + "\n\n".join(parts), used, truncated


def _resolve_section_target(
    prose_docs: list[AiKnowledgeDocument],
    *,
    document_ids: Optional[list[int]] = None,
) -> tuple[Optional[AiKnowledgeDocument], Optional[str]]:
    if document_ids and len(document_ids) == 1:
        wanted_id = int(document_ids[0])
        target = next((d for d in prose_docs if int(d.id) == wanted_id), None)
        if not target:
            return None, f"指定文档 #{wanted_id} 不是 v2 长文档"
        return target, None
    if len(prose_docs) == 1:
        return prose_docs[0], None
    return None, "范围内有多份长文档，章节定位请指定 1 份 Word/PDF"


async def try_prose_enhanced_qa(
    project_id: int,
    *,
    query: str,
    folder_ids: Optional[list[int]] = None,
    document_ids: Optional[list[int]] = None,
    top_k: int = 12,
    max_chars: int = 32000,
    strategy: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    docs = await load_documents_for_qa_scope(
        project_id,
        folder_ids=folder_ids,
        document_ids=document_ids,
    )
    prose_docs = _prose_docs_in_scope(docs)
    if not prose_docs:
        return None

    classification = classify_qa_question(query)
    qtype = classification.get("question_type")
    narrow_limit = min(max_chars, NARROW_FULLTEXT_MAX_CHARS)

    # 策略 A：窄范围全文
    if len(prose_docs) <= NARROW_MAX_DOCS and qtype in ("semantic", "coverage"):
        total_chars = sum(_prose_doc_char_count(doc) for doc in prose_docs)
        if total_chars <= narrow_limit:
            context, sections_used, truncated = _build_narrow_context(prose_docs)
            if context:
                return {
                    "strategy": "prose_fulltext",
                    "answer_path": "prose_fulltext",
                    "context_text": context,
                    "context_truncated": truncated,
                    "prose_basis": {
                        "document_ids": [d.id for d in prose_docs],
                        "total_chars": total_chars,
                        "sections_used": sections_used,
                        "context_mode": "narrow_fulltext",
                    },
                    "doc_count": len(prose_docs),
                    "hit_count": len(sections_used),
                    "question_type": qtype,
                }

    # 策略 B：章节优先
    if qtype == "locate" or re_locate_hint(query):
        target, scope_reason = _resolve_section_target(prose_docs, document_ids=document_ids)
        if target:
            context, sections_used, truncated = _build_section_context(target, query, max_chars=max_chars)
            if context.strip() and sections_used:
                return {
                    "strategy": "prose_section",
                    "answer_path": "prose_section",
                    "context_text": context,
                    "context_truncated": truncated,
                    "prose_basis": {
                        "document_ids": [target.id],
                        "sections_used": sections_used,
                        "context_mode": "section_first",
                        "scope_note": scope_reason,
                    },
                    "doc_count": 1,
                    "hit_count": len(sections_used),
                    "question_type": qtype,
                }

    # 策略 C：分层 RAG（仅 prose 文档范围）
    prose_ids = [d.id for d in prose_docs]
    retrieval = await retrieve_knowledge(
        project_id,
        query=query,
        document_ids=prose_ids,
        top_k=top_k,
        max_chars=max_chars,
        strategy=strategy,
    )
    if retrieval.get("context_text"):
        return {
            **retrieval,
            "strategy": retrieval.get("strategy") or "lexical",
            "answer_path": "layered_rag",
            "prose_basis": {
                "document_ids": prose_ids,
                "context_mode": "layered_rag",
                "sections_used": [],
            },
            "question_type": qtype,
        }
    return None


def re_locate_hint(query: str) -> bool:
    return bool(re.search(r"(哪一?章|哪一节|测试范围|讲了什么|说了什么)", query or ""))
