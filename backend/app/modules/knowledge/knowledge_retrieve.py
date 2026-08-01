"""资料库 RAG 检索 — 对外 API 与助手工具共用"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException

from app.models.knowledge import AiKnowledgeChunk, AiKnowledgeDocument
from app.modules.knowledge.knowledge_context import build_knowledge_context, load_documents_for_refs
from app.modules.knowledge.knowledge_embed import (
    chunk_has_vector,
    cosine_dense,
    embed_query_vector,
    get_chunk_vector,
    get_lexical_tf,
)
from app.modules.knowledge.knowledge_embed_config import normalize_retrieve_strategy
from app.modules.knowledge.knowledge_project_settings import (
    is_vector_embed_active,
    load_knowledge_project_settings,
)
from app.modules.knowledge.knowledge_rag import _cosine, _term_freq, tokenize


def resolve_qa_scope(
    folder_ids: Optional[list[int]] = None,
    document_ids: Optional[list[int]] = None,
) -> tuple[str, list[int]]:
    """问答检索范围：指定文档时仅搜这些文档；否则按文件夹；都未选则搜项目全部资料。"""
    doc_ids = [int(x) for x in (document_ids or []) if x]
    fids = [int(x) for x in (folder_ids or []) if x]
    if doc_ids:
        return "documents", doc_ids
    if fids:
        return "folders", fids
    return "all", []


async def load_documents_for_qa_scope(
    project_id: int,
    *,
    folder_ids: Optional[list[int]] = None,
    document_ids: Optional[list[int]] = None,
) -> list[AiKnowledgeDocument]:
    kind, ids = resolve_qa_scope(folder_ids, document_ids)
    if kind == "documents":
        return await load_documents_for_refs(project_id, document_ids=ids)
    if kind == "folders":
        return await load_documents_for_refs(project_id, folder_ids=ids)
    return list(await AiKnowledgeDocument.filter(project_id=project_id, is_del=False).order_by("id"))


async def _chunks_for_docs(project_id: int, document_ids: list[int]) -> list[AiKnowledgeChunk]:
    return list(
        await AiKnowledgeChunk.filter(
            project_id=project_id,
            document_id__in=document_ids,
        ).order_by("document_id", "chunk_index")
    )


async def _doc_ids_have_vectors(project_id: int, document_ids: list[int]) -> bool:
    chunks = await _chunks_for_docs(project_id, document_ids)
    return any(chunk_has_vector(ch) for ch in chunks)


def _normalize_scores(scored: list[tuple[float, AiKnowledgeChunk]]) -> list[tuple[float, AiKnowledgeChunk]]:
    if not scored:
        return []
    max_score = max(s for s, _ in scored) or 1.0
    return [(s / max_score, ch) for s, ch in scored]


def build_rag_context_text(
    chunk_rows: list[dict[str, Any]],
    *,
    query: str,
    strategy_label: str,
    max_chars: int,
) -> dict[str, Any]:
    """将检索分块拼成 LLM 上下文，[来源N] 与前端引用卡片序号一致。"""
    parts: list[str] = []
    total = 0
    block_truncated = False
    for i, row in enumerate(chunk_rows, start=1):
        block = (
            f"--- [来源{i}] 《{row['title']}》#{(row.get('chunk_index') or 0) + 1} "
            f"(相关度 {row.get('score')}) ---\n{row.get('text') or ''}"
        )
        sep_len = 2 if parts else 0
        if total + sep_len + len(block) > max_chars:
            remain = max_chars - total - sep_len
            if remain > 300:
                parts.append(block[:remain] + "\n…")
                block_truncated = True
            break
        parts.append(block)
        total += sep_len + len(block)
    prefix = f"【RAG 检索·{strategy_label}】查询：{query[:120]}\n\n"
    context = prefix + "\n\n".join(parts)
    used = len(parts)
    return {
        "context_text": context.strip(),
        "context_chunk_count": used,
        "context_truncated": block_truncated or used < len(chunk_rows),
        "context_chars": len(context.strip()),
    }


async def _build_chunk_rows(
    scored: list[tuple[float, AiKnowledgeChunk]],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    hits = scored[:top_k]
    doc_titles: dict[int, str] = {}
    result: list[dict[str, Any]] = []
    for score, ch in hits:
        if ch.document_id not in doc_titles:
            doc = await AiKnowledgeDocument.get_or_none(id=ch.document_id)
            doc_titles[ch.document_id] = doc.title if doc else f"文档#{ch.document_id}"
        result.append(
            {
                "document_id": ch.document_id,
                "title": doc_titles[ch.document_id],
                "chunk_index": ch.chunk_index,
                "score": round(score, 4),
                "text": ch.chunk_text,
            }
        )
    return result


async def _score_chunks_lexical(
    project_id: int,
    document_ids: list[int],
    query: str,
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    q_vec = _term_freq(tokenize(query))
    chunks = await _chunks_for_docs(project_id, document_ids)

    scored: list[tuple[float, AiKnowledgeChunk]] = []
    for ch in chunks:
        score = _cosine(q_vec, get_lexical_tf(ch))
        if score > 0:
            scored.append((score, ch))

    scored.sort(key=lambda x: x[0], reverse=True)
    return await _build_chunk_rows(scored, top_k=top_k)


async def _score_chunks_vector(
    project_id: int,
    document_ids: list[int],
    query_vector: list[float],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    chunks = await _chunks_for_docs(project_id, document_ids)
    scored: list[tuple[float, AiKnowledgeChunk]] = []
    for ch in chunks:
        vec = get_chunk_vector(ch)
        if not vec:
            continue
        score = cosine_dense(query_vector, vec)
        if score > 0:
            scored.append((score, ch))

    scored.sort(key=lambda x: x[0], reverse=True)
    return await _build_chunk_rows(scored, top_k=top_k)


async def _score_chunks_hybrid(
    project_id: int,
    document_ids: list[int],
    query: str,
    query_vector: list[float],
    *,
    top_k: int,
    lexical_weight: float,
) -> list[dict[str, Any]]:
    q_vec = _term_freq(tokenize(query))
    chunks = await _chunks_for_docs(project_id, document_ids)
    w_lex = min(max(float(lexical_weight), 0.0), 1.0)
    w_vec = 1.0 - w_lex

    lexical_scores: list[tuple[float, AiKnowledgeChunk]] = []
    vector_scores: list[tuple[float, AiKnowledgeChunk]] = []
    for ch in chunks:
        lex = _cosine(q_vec, get_lexical_tf(ch))
        if lex > 0:
            lexical_scores.append((lex, ch))
        vec = get_chunk_vector(ch)
        if vec:
            vscore = cosine_dense(query_vector, vec)
            if vscore > 0:
                vector_scores.append((vscore, ch))

    lex_norm = {id(ch): s for s, ch in _normalize_scores(lexical_scores)}
    vec_norm = {id(ch): s for s, ch in _normalize_scores(vector_scores)}

    combined: dict[int, tuple[float, AiKnowledgeChunk]] = {}
    for ch in chunks:
        key = id(ch)
        score = w_lex * lex_norm.get(key, 0.0) + w_vec * vec_norm.get(key, 0.0)
        if score > 0:
            combined[key] = (score, ch)

    scored = sorted(combined.values(), key=lambda x: x[0], reverse=True)
    return await _build_chunk_rows(scored, top_k=top_k)


def _resolve_effective_strategy(
    requested: str,
    *,
    has_vectors: bool,
    vector_active: bool,
) -> str:
    strategy = normalize_retrieve_strategy(requested)
    if strategy in ("vector", "hybrid") and not has_vectors:
        return "lexical"
    if strategy == "vector" and not vector_active:
        return "lexical"
    if strategy == "hybrid" and not vector_active:
        return "lexical"
    return strategy


async def retrieve_knowledge(
    project_id: int,
    *,
    query: str,
    folder_ids: Optional[list[int]] = None,
    document_ids: Optional[list[int]] = None,
    top_k: int = 12,
    max_chars: int = 32000,
    strategy: Optional[str] = None,
) -> dict[str, Any]:
    """按 query 检索资料库，支持词法 / 向量 / 混合策略。"""
    q = (query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query 不能为空")

    top_k = min(max(top_k, 1), 30)
    max_chars = min(max(max_chars, 500), 64000)

    settings = await load_knowledge_project_settings(project_id)
    scope_kind, _scope_ids = resolve_qa_scope(folder_ids, document_ids)
    docs = await load_documents_for_qa_scope(
        project_id,
        folder_ids=folder_ids,
        document_ids=document_ids,
    )
    doc_ids = [d.id for d in docs]
    if not doc_ids:
        return {
            "query": q,
            "strategy": "none",
            "doc_count": 0,
            "hit_count": 0,
            "chunks": [],
            "context_text": "",
            "message": "未找到可检索的文档，请检查文件夹或文档 ID",
        }

    indexed = await AiKnowledgeChunk.filter(project_id=project_id, document_id__in=doc_ids).exists()
    if indexed:
        has_vectors = await _doc_ids_have_vectors(project_id, doc_ids)
        vector_active = is_vector_embed_active(settings)
        eff_strategy = _resolve_effective_strategy(
            strategy or settings.get("retrieve_strategy"),
            has_vectors=has_vectors,
            vector_active=vector_active,
        )

        chunk_rows: list[dict[str, Any]] = []
        if eff_strategy == "lexical":
            chunk_rows = await _score_chunks_lexical(project_id, doc_ids, q, top_k=top_k)
        elif eff_strategy == "vector":
            q_vec = await embed_query_vector(q, project_settings=settings, project_id=project_id)
            chunk_rows = await _score_chunks_vector(project_id, doc_ids, q_vec, top_k=top_k)
        else:
            q_vec = await embed_query_vector(q, project_settings=settings, project_id=project_id)
            chunk_rows = await _score_chunks_hybrid(
                project_id,
                doc_ids,
                q,
                q_vec,
                top_k=top_k,
                lexical_weight=float(settings.get("hybrid_lexical_weight") or 0.4),
            )

        if chunk_rows:
            label = {"lexical": "词法", "vector": "向量", "hybrid": "混合"}.get(eff_strategy, eff_strategy)
            ctx_meta = build_rag_context_text(
                chunk_rows,
                query=q,
                strategy_label=label,
                max_chars=max_chars,
            )
            return {
                "query": q,
                "strategy": eff_strategy,
                "doc_count": len(docs),
                "hit_count": len(chunk_rows),
                "scope_kind": scope_kind,
                "chunks": chunk_rows,
                **ctx_meta,
            }

    ctx = await build_knowledge_context(
        project_id,
        folder_ids=None,
        document_ids=[d.id for d in docs] if docs else None,
        max_chars=max_chars,
    )
    ktext = (ctx.get("knowledge_context") or "").strip()
    refs = ctx.get("refs") or []
    chunks = [
        {
            "document_id": r.get("document_id"),
            "title": r.get("title"),
            "chunk_index": 0,
            "score": None,
            "text": ktext[:max_chars] if len(refs) == 1 else f"（全文引用）《{r.get('title')}》",
        }
        for r in refs[:top_k]
    ]
    fallback_strategy = "fulltext" if ktext else "none"
    return {
        "query": q,
        "strategy": fallback_strategy,
        "doc_count": len(docs),
        "hit_count": len(refs) if ktext else 0,
        "scope_kind": scope_kind,
        "chunks": chunks,
        "context_text": ktext,
        "truncated": bool(ctx.get("truncated")),
        "context_truncated": bool(ctx.get("truncated")),
        "bug_export_summary": ctx.get("bug_export_summary") or "",
    }
