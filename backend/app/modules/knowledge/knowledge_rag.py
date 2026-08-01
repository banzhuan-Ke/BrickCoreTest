"""资料库 RAG：分块索引 + 关键词检索（无需外部 Embedding API）"""
from __future__ import annotations

import asyncio
import logging
import math
import re
from typing import Any, Optional

from app.models.knowledge import AiKnowledgeChunk, AiKnowledgeDocument
from app.modules.knowledge.knowledge_context_mapreduce import extract_document_full_text, split_text_chunks

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[a-zA-Z][a-zA-Z0-9_]{2,}|\d{2,}")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _term_freq(tokens: list[str]) -> dict[str, float]:
    counts: dict[str, float] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0.0) + 1.0
    total = float(len(tokens)) or 1.0
    return {k: v / total for k, v in counts.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in set(a) | set(b))
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


REPORT_KIND_QUERY_TERMS: dict[str, list[str]] = {
    "iteration_report": ["迭代", "测试", "执行", "缺陷", "bug", "通过率", "总结", "范围"],
    "functional_report": ["功能", "模块", "验收", "用例", "缺陷", "回归", "测试"],
    "performance_report": ["性能", "响应", "并发", "tps", "瓶颈", "压测", "指标"],
    "test_plan": ["测试计划", "目标", "范围", "策略", "里程碑", "资源", "环境", "需求"],
    "test_scheme": ["测试方案", "策略", "类型", "环境", "风险", "准入", "准出", "组织"],
}


def build_rag_query(
    *,
    report_kind: str = "iteration_report",
    iteration_name: str = "",
    project_name: str = "",
    extra_terms: Optional[list[str]] = None,
) -> str:
    terms = list(REPORT_KIND_QUERY_TERMS.get(report_kind, REPORT_KIND_QUERY_TERMS["iteration_report"]))
    if iteration_name:
        terms.extend(tokenize(iteration_name))
    if project_name:
        terms.extend(tokenize(project_name))
    if extra_terms:
        terms.extend(extra_terms)
    return " ".join(dict.fromkeys(terms))


def infer_chunk_section_title(piece: str) -> Optional[str]:
    """从分块文本推断章节标题（Word ## 标题或 xlsx 表名）。"""
    text = (piece or "").strip()
    if not text:
        return None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            title = s[3:].strip()
            return title[:200] if title else None
        if s.startswith("# ") and not s.startswith("## "):
            title = s[2:].strip()
            return title[:200] if title else None
    m = re.match(r"^\[([^\]]+)\]", text)
    if m:
        name = m.group(1).strip()
        if name:
            return name[:200]
    return None


async def index_document_chunks(
    doc: AiKnowledgeDocument,
    *,
    chunk_chars: int = 1800,
) -> int:
    """重建单文档 RAG 分块索引。v2 按 structured.kind 分支，v1 走全文盲切。"""
    from app.modules.knowledge.knowledge_rag_prose import build_prose_chunk_specs
    from app.modules.knowledge.knowledge_rag_tabular import build_tabular_chunk_specs
    from app.modules.knowledge.knowledge_sections_read import is_sections_json_v2

    doc.embed_status = "indexing"
    doc.vector_status = "none"
    doc.vector_model = None
    doc.vector_error = None
    await doc.save()

    await AiKnowledgeChunk.filter(document_id=doc.id).delete()

    chunk_specs: list[dict[str, Any]] = []
    sections_json = doc.sections_json if isinstance(doc.sections_json, dict) else {}

    if is_sections_json_v2(sections_json):
        structured = sections_json.get("structured") if isinstance(sections_json.get("structured"), dict) else {}
        kind = structured.get("kind")
        if kind == "tabular" and sections_json.get("sheets"):
            chunk_specs = build_tabular_chunk_specs(sections_json["sheets"])
        elif kind == "prose" and sections_json.get("sections"):
            chunk_specs = build_prose_chunk_specs(sections_json["sections"], chunk_chars=chunk_chars)

    if not chunk_specs:
        full = extract_document_full_text(doc)
        if not full.strip():
            doc.embed_status = "none"
            await doc.save()
            return 0
        for piece in split_text_chunks(full, chunk_size=chunk_chars, overlap=min(200, chunk_chars // 5)):
            chunk_specs.append(
                {
                    "text": piece,
                    "section_title": infer_chunk_section_title(piece),
                    "meta": {},
                }
            )

    rows: list[AiKnowledgeChunk] = []
    for idx, spec in enumerate(chunk_specs):
        text = str(spec.get("text") or "").strip()
        if not text:
            continue
        tokens = tokenize(text)
        meta = spec.get("meta") if isinstance(spec.get("meta"), dict) else {}
        rows.append(
            AiKnowledgeChunk(
                document_id=doc.id,
                project_id=doc.project_id,
                chunk_index=idx,
                section_title=(spec.get("section_title") or infer_chunk_section_title(text)),
                chunk_text=text,
                char_count=len(text),
                embedding={"kind": "lexical", "tf": _term_freq(tokens), **meta},
                embedding_model="lexical_v1",
            )
        )
    if rows:
        await AiKnowledgeChunk.bulk_create(rows)
    doc.embed_status = "ready" if rows else "none"
    doc.chunk_count = len(rows)
    await doc.save()
    return len(rows)


def _chunk_lexical_tf(ch: AiKnowledgeChunk) -> dict[str, float]:
    emb = ch.embedding if isinstance(ch.embedding, dict) else {}
    tf = emb.get("tf")
    if isinstance(tf, dict):
        return {str(k): float(v) for k, v in tf.items()}
    return _term_freq(tokenize(ch.chunk_text or ""))


async def retrieve_rag_context(
    project_id: int,
    document_ids: list[int],
    *,
    query: str,
    top_k: int = 12,
    max_chars: int = 32000,
) -> dict[str, Any]:
    """检索最相关分块并拼接为上下文。"""
    if not document_ids:
        return {"text": "", "chunk_count": 0, "hit_count": 0}

    q_tokens = tokenize(query)
    q_vec = _term_freq(q_tokens)
    chunks = await AiKnowledgeChunk.filter(
        project_id=project_id,
        document_id__in=document_ids,
    ).order_by("document_id", "chunk_index")

    scored: list[tuple[float, AiKnowledgeChunk]] = []
    for ch in chunks:
        score = _cosine(q_vec, _chunk_lexical_tf(ch))
        if score > 0:
            scored.append((score, ch))

    scored.sort(key=lambda x: x[0], reverse=True)
    hits = scored[:top_k]

    parts: list[str] = []
    total = 0
    doc_titles: dict[int, str] = {}
    for score, ch in hits:
        doc_id = ch.document_id
        if doc_id not in doc_titles:
            doc = await AiKnowledgeDocument.get_or_none(id=doc_id)
            doc_titles[doc_id] = doc.title if doc else f"文档#{doc_id}"
        label = doc_titles[doc_id]
        block = f"--- 《{label}》RAG#{ch.chunk_index + 1} (相关度 {score:.2f}) ---\n{ch.chunk_text}"
        if total + len(block) > max_chars:
            remain = max_chars - total
            if remain > 300:
                parts.append(block[:remain] + "\n…")
            break
        parts.append(block)
        total += len(block)

    text = "\n\n".join(parts)
    header = f"【RAG 检索摘要】查询：{query[:120]}；命中 {len(hits)} 块。\n\n"
    return {
        "text": (header + text).strip(),
        "chunk_count": len(hits),
        "hit_count": len(hits),
        "indexed_chunks": len(chunks),
    }


async def _reindex_document_rag_background(
    doc_id: int,
    project_id: int,
    *,
    username: str = "",
    settings: Optional[dict[str, Any]] = None,
) -> None:
    """后台重建词法索引，并按策略链式触发向量索引。"""
    from app.modules.knowledge.knowledge_embed import chain_vector_index_after_lexical, will_chain_vector_index

    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc:
        return
    cfg = settings or {}
    try:
        await index_document_chunks(
            doc,
            chunk_chars=int(cfg.get("rag_chunk_chars") or 1800),
        )
        doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
        if not doc:
            return
        if will_chain_vector_index(doc, cfg):
            doc.vector_status = "indexing"
            doc.vector_error = None
            await doc.save()
            await chain_vector_index_after_lexical(doc, settings=cfg, username=username)
    except Exception as ex:
        logger.exception("[rag] background reindex doc=%s failed: %s", doc_id, ex)
        doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
        if doc and doc.embed_status == "indexing":
            doc.embed_status = "none"
            await doc.save()


def schedule_reindex_document_rag(
    doc_id: int,
    project_id: int,
    *,
    username: str = "",
    settings: Optional[dict[str, Any]] = None,
) -> None:
    asyncio.create_task(
        _reindex_document_rag_background(
            doc_id,
            project_id,
            username=username,
            settings=settings,
        )
    )


def schedule_reindex_document_all(
    doc_id: int,
    project_id: int,
    *,
    username: str = "",
    settings: Optional[dict[str, Any]] = None,
) -> None:
    schedule_reindex_document_rag(
        doc_id,
        project_id,
        username=username,
        settings=settings,
    )
