"""文档 AI 摘要缓存（上传/重解析后异步生成，报告生成时复用）"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from app.core.llm.ai_usage_log import log_ai_usage

from app.models.knowledge import AiKnowledgeChunk, AiKnowledgeDocument
from app.modules.knowledge.constants import PARSE_STATUS_FAILED, PARSE_STATUS_READY
from app.modules.knowledge.knowledge_context_mapreduce import (
    _digest_from_llm_response,
    extract_document_full_text,
)

logger = logging.getLogger(__name__)

META_KEY = "_platform_meta"
DIGEST_KEY = "digest_cache"
CACHE_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_digest_cache(sections_json: Any) -> Optional[dict[str, Any]]:
    if not isinstance(sections_json, dict):
        return None
    meta = sections_json.get(META_KEY)
    if not isinstance(meta, dict):
        return None
    cache = meta.get(DIGEST_KEY)
    return cache if isinstance(cache, dict) else None


def set_digest_cache(sections_json: Any, cache: dict[str, Any]) -> dict[str, Any]:
    base = dict(sections_json) if isinstance(sections_json, dict) else {}
    meta = dict(base.get(META_KEY) or {})
    meta[DIGEST_KEY] = cache
    base[META_KEY] = meta
    return base


def is_digest_cache_valid(doc: AiKnowledgeDocument, min_chars: int) -> bool:
    cache = get_digest_cache(doc.sections_json)
    if not cache or not (cache.get("text") or "").strip():
        return False
    source_chars = int(cache.get("source_char_count") or 0)
    if source_chars and abs(source_chars - int(doc.char_count or 0)) > max(500, source_chars * 0.05):
        return False
    if int(doc.char_count or 0) < min_chars:
        return False
    return int(cache.get("version") or 0) == CACHE_VERSION


async def resolve_document_text_for_digest(doc: AiKnowledgeDocument) -> str:
    """优先从源文件提取正文；失败时回退到已索引分块。"""
    full = extract_document_full_text(doc).strip()
    if full:
        return full
    chunks = await AiKnowledgeChunk.filter(document_id=doc.id).order_by("chunk_index")
    parts = [(c.chunk_text or "").strip() for c in chunks if (c.chunk_text or "").strip()]
    return "\n\n".join(parts)


async def _mapreduce_single_text_for_digest(
    *,
    doc: AiKnowledgeDocument,
    full: str,
    ai_config_id: Optional[int],
    project_name: str,
    chunk_chars: int,
    max_chars: int,
    username: str,
) -> str:
    """单文档长文 Map-Reduce（含 Bug 导出等，不走报告侧 skip 逻辑）。"""
    from app.modules.knowledge.knowledge_context_mapreduce import (
        _digest_one_chunk,
        _merge_digests,
        split_text_chunks,
    )

    label = f"《{doc.title}》({doc.doc_type})"
    chunks = split_text_chunks(full, chunk_size=chunk_chars)
    if not chunks:
        return ""
    digests: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        digest, _tok = await _digest_one_chunk(
            ai_config_id=ai_config_id,
            project_name=project_name,
            iteration_name=doc.title or "",
            doc_label=label,
            chunk_index=idx,
            chunk_total=len(chunks),
            chunk_text=chunk,
            digest_focus="提炼 Bug/任务/需求要点、模块范围、测试关注点与风险，勿编造。",
            project_id=doc.project_id,
            username=username or doc.created_by or "",
        )
        if digest.strip():
            digests.append(digest.strip())
    if not digests:
        return ""
    merged, _merge_tokens = await _merge_digests(
        ai_config_id=ai_config_id,
        project_name=project_name,
        iteration_name=doc.title or "",
        digests=digests,
        output_limit=max_chars,
        project_id=doc.project_id,
        username=username or doc.created_by or "",
    )
    return (merged or "").strip()[:max_chars]


async def build_single_document_digest(
    doc: AiKnowledgeDocument,
    *,
    source_text: Optional[str] = None,
    ai_config_id: Optional[int] = None,
    project_name: str = "",
    chunk_chars: int = 10000,
    max_chars: int = 8000,
    username: str = "",
) -> str:
    """为单文档生成摘要文本。"""
    full = (source_text if source_text is not None else extract_document_full_text(doc)).strip()
    if not full:
        return ""

    if len(full) <= chunk_chars:
        from app.modules.ai.ai_prompts import PromptManager
        from app.routers.ai.generate import _call_llm, _get_ai_config

        ctx = {
            "project_name": project_name or f"项目{doc.project_id}",
            "iteration_name": doc.title or "",
            "doc_label": f"《{doc.title}》({doc.doc_type})",
            "chunk_index": 1,
            "chunk_total": 1,
            "chunk_text": full[: chunk_chars * 2],
            "digest_focus": "提炼全文核心：需求要点、模块范围、测试关注点、风险与依赖。",
        }
        system_prompt, user_prompt = await PromptManager.render("knowledge_chunk_digest", ctx)
        config = await _get_ai_config(ai_config_id, scene="knowledge_chunk_digest")
        t0 = time.time()
        resp = await _call_llm(system_prompt, user_prompt, config, min_timeout=90, max_retries=1)
        text = _digest_from_llm_response(resp.get("content") or "")
        tokens = int(resp.get("tokens") or 0)
        duration_ms = int((time.time() - t0) * 1000)
        await log_ai_usage(
            config,
            "knowledge_chunk_digest",
            username=username or doc.created_by or "",
            project_id=doc.project_id,
            tokens_used=tokens,
            duration_ms=duration_ms,
            input_summary=f"《{doc.title}》({doc.doc_type}) · 摘要缓存"[:500],
            output_summary=text[:500],
            document_id=doc.id,
        )
        return text[:max_chars]

    return await _mapreduce_single_text_for_digest(
        doc=doc,
        full=full,
        ai_config_id=ai_config_id,
        project_name=project_name or f"项目{doc.project_id}",
        chunk_chars=chunk_chars,
        max_chars=max_chars,
        username=username,
    )


async def save_document_digest_cache(
    doc_id: int,
    project_id: int,
    *,
    ai_config_id: Optional[int] = None,
    settings: Optional[dict[str, Any]] = None,
    force: bool = False,
) -> tuple[bool, str]:
    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc:
        return False, "文档不存在"
    if doc.parse_status == PARSE_STATUS_FAILED:
        err = (doc.parse_error or "").strip()
        fail_msg = f"文档解析失败{('：' + err) if err else ''}，请先「重新解析」"
        await _mark_digest_failed(doc, fail_msg)
        return False, fail_msg
    if doc.parse_status != PARSE_STATUS_READY:
        fail_msg = "文档尚未解析完成，请稍候或点击「重新解析」"
        await _mark_digest_failed(doc, fail_msg)
        return False, fail_msg

    cfg = settings or {}
    min_chars = int(cfg.get("digest_cache_min_chars") or 12000)
    char_count = int(doc.char_count or 0)
    if not force and char_count < min_chars:
        return False, (
            f"文档约 {char_count} 字，低于自动摘要阈值 {min_chars} 字；"
            "短文档生成报告时直接全文引用，无需单独摘要。"
        )

    source_text = await resolve_document_text_for_digest(doc)
    if not source_text.strip():
        fail_msg = "无法读取文档正文（源文件可能已丢失），请重新上传或点击「重新解析」"
        await _mark_digest_failed(doc, fail_msg)
        return False, fail_msg

    try:
        from app.models.sys import Project

        project = await Project.get_or_none(id=project_id, is_del=False)
        project_name = project.name if project else f"项目{project_id}"
        text = await build_single_document_digest(
            doc,
            source_text=source_text,
            ai_config_id=ai_config_id,
            project_name=project_name,
            chunk_chars=int(cfg.get("mapreduce_chunk_chars") or 10000),
            max_chars=min(int(cfg.get("fulltext_max_chars") or 32000) // 2, 16000),
            username=doc.created_by or "",
        )
        if not text:
            fail_msg = (
                "AI 未返回有效摘要，请前往 AI 测试 → AI 模型配置，"
                "在「场景绑定」中为「资料分块提炼」指定可用的大语言模型。"
            )
            await _mark_digest_failed(doc, fail_msg)
            return False, fail_msg
        cache = {
            "text": text,
            "source_char_count": max(char_count, len(source_text)),
            "digest_char_count": len(text),
            "updated_at": _utc_now_iso(),
            "version": CACHE_VERSION,
        }
        doc.sections_json = set_digest_cache(doc.sections_json, cache)
        doc.digest_status = "ready"
        doc.digest_error = None
        await doc.save()
        return True, ""
    except HTTPException as ex:
        detail = ex.detail if isinstance(ex.detail, str) else str(ex.detail)
        await _mark_digest_failed(doc, detail)
        raise
    except Exception as ex:
        logger.warning("[digest_cache] doc=%s failed: %s", doc_id, ex)
        fail_msg = f"AI 摘要生成失败：{ex}"
        await _mark_digest_failed(doc, fail_msg)
        return False, fail_msg


async def _mark_digest_failed(doc: AiKnowledgeDocument, err: str) -> None:
    doc.digest_status = "failed"
    doc.digest_error = (err or "")[:500]
    await doc.save()


async def _rebuild_document_digest_background(
    doc_id: int,
    project_id: int,
    *,
    ai_config_id: Optional[int] = None,
    settings: Optional[dict[str, Any]] = None,
) -> None:
    try:
        await save_document_digest_cache(
            doc_id,
            project_id,
            ai_config_id=ai_config_id,
            settings=settings,
            force=True,
        )
    except HTTPException as ex:
        detail = ex.detail if isinstance(ex.detail, str) else str(ex.detail)
        doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
        if doc:
            await _mark_digest_failed(doc, detail)
        logger.warning("[digest_cache] background doc=%s failed: %s", doc_id, detail)
    except Exception as ex:
        logger.exception("[digest_cache] background doc=%s failed: %s", doc_id, ex)
        doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
        if doc:
            await _mark_digest_failed(doc, str(ex))


def schedule_rebuild_document_digest(
    doc_id: int,
    project_id: int,
    *,
    ai_config_id: Optional[int] = None,
    settings: Optional[dict[str, Any]] = None,
) -> None:
    asyncio.create_task(
        _rebuild_document_digest_background(
            doc_id,
            project_id,
            ai_config_id=ai_config_id,
            settings=settings,
        )
    )


def schedule_document_postprocess(
    doc_id: int,
    project_id: int,
    *,
    settings: dict[str, Any],
    ai_config_id: Optional[int] = None,
) -> None:
    """上传/重解析后：摘要缓存 + RAG 索引（后台任务）。"""

    async def _job() -> None:
        doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
        if not doc:
            return
        if settings.get("rag_enabled") and settings.get("rag_reindex_on_upload"):
            try:
                from app.modules.knowledge.knowledge_rag import index_document_chunks

                await index_document_chunks(
                    doc,
                    chunk_chars=int(settings.get("rag_chunk_chars") or 1800),
                )
            except Exception as ex:
                logger.warning("[rag] index doc=%s failed: %s", doc_id, ex)
        if settings.get("vector_embed_on_upload"):
            try:
                from app.modules.knowledge.knowledge_embed import maybe_index_document_vectors

                await maybe_index_document_vectors(doc, settings=settings)
            except Exception as ex:
                logger.warning("[vector_embed] postprocess doc=%s failed: %s", doc_id, ex)
        if settings.get("digest_cache_enabled") and settings.get("digest_cache_on_upload"):
            if int(doc.char_count or 0) >= int(settings.get("digest_cache_min_chars") or 12000):
                doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
                if doc:
                    doc.digest_status = "indexing"
                    doc.digest_error = None
                    await doc.save()
                await save_document_digest_cache(
                    doc_id,
                    project_id,
                    ai_config_id=ai_config_id,
                    settings=settings,
                    force=False,
                )

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_job())
    except RuntimeError:
        asyncio.run(_job())


async def build_context_from_digest_cache(
    docs: list[AiKnowledgeDocument],
    *,
    min_chars: int,
    max_chars: int,
) -> Optional[dict[str, Any]]:
    """若资料均可命中摘要缓存或短文档全文，则拼接返回。"""
    if not docs:
        return None
    parts: list[str] = []
    total = 0
    used_cache = 0
    for doc in docs:
        char_count = int(doc.char_count or 0)
        if char_count >= min_chars:
            if not is_digest_cache_valid(doc, min_chars):
                return None
            cache = get_digest_cache(doc.sections_json) or {}
            text = (cache.get("text") or "").strip()
            if not text:
                return None
            block = f"--- 《{doc.title}》摘要缓存 ---\n{text}"
            used_cache += 1
        else:
            from app.modules.knowledge.knowledge_context_mapreduce import extract_document_full_text

            text = extract_document_full_text(doc).strip()
            if not text:
                continue
            block = f"--- 《{doc.title}》 ---\n{text}"
        if total + len(block) > max_chars:
            remain = max_chars - total
            if remain > 200:
                parts.append(block[:remain] + "\n…")
            break
        parts.append(block)
        total += len(block)
    if not parts:
        return None
    header = "【文档摘要缓存】"
    if used_cache:
        header += f"含 {used_cache} 份预生成摘要；"
    header += "供报告生成参考。\n\n"
    return {
        "text": header + "\n\n".join(parts),
        "source": "digest_cache",
        "doc_count": len(docs),
        "cached_doc_count": used_cache,
    }
