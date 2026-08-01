"""报告生成用资料上下文编排：摘要缓存 / RAG / Map-Reduce / 截断"""
from __future__ import annotations

from typing import Any, Optional

from app.models.knowledge import AiKnowledgeDocument
from app.modules.knowledge.knowledge_context import build_knowledge_context, load_documents_for_refs
from app.modules.knowledge.knowledge_digest_cache import build_context_from_digest_cache
from app.modules.knowledge.knowledge_context_mapreduce import (
    maybe_mapreduce_knowledge_context,
    should_mapreduce_knowledge,
)
from app.modules.knowledge.knowledge_rag import build_rag_query, retrieve_rag_context


async def build_llm_knowledge_context(
    project_id: int,
    *,
    folder_ids: Optional[list[int]] = None,
    document_ids: Optional[list[int]] = None,
    settings: dict[str, Any],
    report_kind: str = "iteration_report",
    ai_config_id: Optional[int] = None,
    project_name: str = "",
    iteration_name: str = "",
    username: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    返回 (knowledge_dict, meta)。
    meta 记录 context_source: digest_cache | rag | mapreduce | truncate
    """
    max_chars = int(settings.get("fulltext_max_chars") or 32000)
    strategy = str(settings.get("context_strategy") or "auto").strip().lower()
    meta: dict[str, Any] = {"context_source": "truncate", "strategy": strategy}

    knowledge = await build_knowledge_context(
        project_id,
        folder_ids=folder_ids,
        document_ids=document_ids,
        max_chars=max_chars,
    )

    docs = await load_documents_for_refs(
        project_id,
        folder_ids=folder_ids,
        document_ids=document_ids,
    )
    # 排除 Bug 导出（统计已由 knowledge 解析，正文不必送入叙述 LLM）
    from app.modules.knowledge.knowledge_context import _is_bug_export_candidate

    text_docs = [d for d in docs if not _is_bug_export_candidate(d)]

    def _apply_text(text: str, source: str, extra: Optional[dict] = None) -> dict[str, Any]:
        knowledge["knowledge_context"] = text
        knowledge["knowledge_summary"] = text[:8000]
        meta["context_source"] = source
        if extra:
            meta.update(extra)
        return knowledge

    # 1) 摘要缓存
    if strategy in ("auto",) and settings.get("digest_cache_enabled"):
        cached = await build_context_from_digest_cache(
            text_docs,
            min_chars=int(settings.get("digest_cache_min_chars") or 12000),
            max_chars=max_chars,
        )
        if cached:
            return _apply_text(cached["text"], "digest_cache", cached), meta

    need_expand = bool(knowledge.get("truncated")) or int(knowledge.get("raw_total_chars") or 0) > max_chars
    if not need_expand:
        meta["context_source"] = "fulltext"
        return knowledge, meta

    # 2) RAG
    if strategy in ("auto", "rag") and settings.get("rag_enabled") and text_docs:
        doc_ids = [d.id for d in text_docs]
        query = build_rag_query(
            report_kind=report_kind,
            iteration_name=iteration_name,
            project_name=project_name,
        )
        rag = await retrieve_rag_context(
            project_id,
            doc_ids,
            query=query,
            top_k=int(settings.get("rag_top_k") or 12),
            max_chars=max_chars,
        )
        if (rag.get("text") or "").strip() and int(rag.get("hit_count") or 0) > 0:
            return _apply_text(rag["text"], "rag", rag), meta

    # 3) Map-Reduce
    map_enabled = settings.get("mapreduce_enabled", True)
    if strategy in ("auto", "mapreduce") and map_enabled:
        if should_mapreduce_knowledge(knowledge, settings):
            mr = await maybe_mapreduce_knowledge_context(
                knowledge,
                text_docs,
                ai_config_id=ai_config_id,
                project_name=project_name,
                iteration_name=iteration_name,
                report_kind=report_kind if settings.get("mapreduce_by_report_kind", True) else "",
                settings=settings,
                project_id=project_id,
                username=username,
            )
            if mr:
                meta["mapreduce"] = {
                    "chunk_count": mr.get("chunk_count"),
                    "doc_count": mr.get("doc_count"),
                    "tokens_used": mr.get("tokens_used"),
                }
                meta["context_source"] = "mapreduce"
                return _apply_text(mr["text"], "mapreduce", meta.get("mapreduce")), meta

    # 4) truncate fallback
    meta["context_source"] = "truncate"
    return knowledge, meta
