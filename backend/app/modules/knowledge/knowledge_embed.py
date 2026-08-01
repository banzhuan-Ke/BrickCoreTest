"""资料库向量 Embedding 管线"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Any, Optional

from fastapi import HTTPException
from openai import AsyncOpenAI

from app.core.llm.ai_usage_log import log_ai_usage
from app.core.llm.embed_providers import resolve_embed_api_base
from app.core.llm.llm_invoke import is_retryable_llm_error
from app.core.platform.config import KNOWLEDGE_EMBED_MAX_CHUNKS_PER_JOB
from app.core.platform.encryption import decrypt_value
from app.models.ai import AiConfig
from app.models.knowledge import AiKnowledgeChunk, AiKnowledgeDocument
from app.modules.ai.ai_scene_config import resolve_config_for_scene
from app.modules.knowledge.knowledge_embed_config import (
    document_should_vector_embed,
    effective_embed_batch_size,
    normalize_embed_provider,
    resolve_embed_dimensions,
    resolve_embed_provider_model,
)
from app.modules.knowledge.knowledge_project_settings import is_vector_embed_active
from app.modules.knowledge.knowledge_rag import _term_freq, tokenize

logger = logging.getLogger(__name__)

SCENE = "knowledge_embed"
MAX_RETRIES = 2


def get_lexical_tf(ch: AiKnowledgeChunk) -> dict[str, float]:
    emb = ch.embedding if isinstance(ch.embedding, dict) else {}
    tf = emb.get("tf")
    if isinstance(tf, dict):
        return {str(k): float(v) for k, v in tf.items()}
    return _term_freq(tokenize(ch.chunk_text or ""))


def get_chunk_vector(ch: AiKnowledgeChunk) -> Optional[list[float]]:
    vec = getattr(ch, "vector_json", None)
    if isinstance(vec, list) and vec:
        return [float(x) for x in vec]
    emb = ch.embedding if isinstance(ch.embedding, dict) else {}
    raw = emb.get("vector")
    if isinstance(raw, list) and raw:
        return [float(x) for x in raw]
    return None


def chunk_has_vector(ch: AiKnowledgeChunk) -> bool:
    return get_chunk_vector(ch) is not None


def cosine_dense(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


async def _pick_config_by_provider(provider: str) -> Optional[AiConfig]:
    key = normalize_embed_provider(provider)
    return (
        await AiConfig.filter(provider=key, is_enabled=True, is_del=False)
        .order_by("-is_default", "-id")
        .first()
    )


async def _load_embed_config_by_id(config_id: int) -> Optional[Any]:
    from app.models.ai import AiEmbedConfig

    return await AiEmbedConfig.get_or_none(id=config_id, is_del=False, is_enabled=True)


async def _load_default_embed_config() -> Optional[Any]:
    from app.models.ai import AiEmbedConfig

    return (
        await AiEmbedConfig.filter(is_del=False, is_enabled=True)
        .order_by("-is_default", "-id")
        .first()
    )


async def resolve_embed_ai_config(project_settings: dict[str, Any]) -> tuple[Any, str]:
    embed_config_id = project_settings.get("vector_embed_config_id")
    if embed_config_id:
        row = await _load_embed_config_by_id(int(embed_config_id))
        if row:
            return row, (row.model or "").strip()

    default_row = await _load_default_embed_config()
    if default_row:
        return default_row, (default_row.model or "").strip()

    provider, embed_model = resolve_embed_provider_model(project_settings)
    config_id = project_settings.get("vector_embed_ai_config_id")
    if config_id:
        config = await resolve_config_for_scene(SCENE, int(config_id))
    else:
        config = await resolve_config_for_scene(SCENE, None)
        if normalize_embed_provider(config.provider) != provider:
            alt = await _pick_config_by_provider(provider)
            if alt:
                config = alt
    return config, embed_model


async def embed_texts(
    texts: list[str],
    *,
    config: Any,
    model: str,
    project_id: Optional[int] = None,
    username: str = "",
    max_retries: int = MAX_RETRIES,
    dimensions: Optional[int] = None,
    client: Optional[AsyncOpenAI] = None,
) -> list[list[float]]:
    if not texts:
        return []
    clean = [t if t else " " for t in texts]
    owns_client = client is None
    if client is None:
        api_key = decrypt_value(config.api_key)
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=resolve_embed_api_base(config),
            timeout=max(int(config.timeout or 60), 120),
        )
    create_kwargs: dict[str, Any] = {"model": model, "input": clean}
    if dimensions is not None:
        create_kwargs["dimensions"] = dimensions
    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        t0 = time.perf_counter()
        try:
            resp = await client.embeddings.create(**create_kwargs)
            duration_ms = int((time.perf_counter() - t0) * 1000)
            ordered = sorted(resp.data, key=lambda d: d.index)
            vectors = [item.embedding for item in ordered]
            tokens = int(resp.usage.total_tokens) if resp.usage else 0
            await log_ai_usage(
                config,
                SCENE,
                project_id=project_id,
                username=username,
                tokens_used=tokens,
                duration_ms=duration_ms,
                input_summary=f"embed {len(texts)} chunks model={model}",
                output_summary=f"vectors={len(vectors)} dim={len(vectors[0]) if vectors else 0}",
            )
            return vectors
        except Exception as ex:
            last_err = ex
            if attempt < max_retries and is_retryable_llm_error(ex):
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            await log_ai_usage(
                config,
                SCENE,
                project_id=project_id,
                username=username,
                duration_ms=int((time.perf_counter() - t0) * 1000),
                status="failed",
                input_summary=f"embed {len(texts)} chunks model={model}",
                output_summary=str(ex)[:240],
            )
            raise
    if last_err:
        raise last_err
    return []


async def embed_query_vector(
    query: str,
    *,
    project_settings: dict[str, Any],
    project_id: Optional[int] = None,
    username: str = "",
) -> list[float]:
    config, model = await resolve_embed_ai_config(project_settings)
    dimensions = resolve_embed_dimensions(config, model)
    vectors = await embed_texts(
        [query],
        config=config,
        model=model,
        project_id=project_id,
        username=username,
        dimensions=dimensions,
    )
    return vectors[0] if vectors else []


async def maybe_index_document_vectors(
    doc: AiKnowledgeDocument,
    *,
    settings: Optional[dict[str, Any]] = None,
    username: str = "",
) -> int:
    settings = settings or {}
    if not is_vector_embed_active(settings):
        return 0
    if not document_should_vector_embed(
        doc_type=doc.doc_type,
        embed_mode=getattr(doc, "embed_mode", "inherit") or "inherit",
        project_settings=settings,
    ):
        return 0
    try:
        return await index_document_vectors(doc, settings=settings, username=username)
    except Exception as ex:
        logger.warning("[vector_embed] doc=%s failed: %s", doc.id, ex)
        return 0


async def index_document_vectors(
    doc: AiKnowledgeDocument,
    *,
    settings: Optional[dict[str, Any]] = None,
    force: bool = False,
    username: str = "",
) -> int:
    from app.modules.knowledge.knowledge_project_settings import load_knowledge_project_settings

    settings = settings or await load_knowledge_project_settings(doc.project_id)
    active = is_vector_embed_active(settings)
    should = document_should_vector_embed(
        doc_type=doc.doc_type,
        embed_mode=getattr(doc, "embed_mode", "inherit") or "inherit",
        project_settings=settings,
    )
    if not force and (not active or not should):
        doc.vector_status = "none"
        doc.vector_error = None
        doc.vector_model = None
        await doc.save()
        return 0
    if not active:
        raise HTTPException(status_code=400, detail="平台或项目未开启向量 Embedding")
    # force=True：用户手动「重建向量」，不校验文档 embed_mode / doc_type 策略

    chunk_list = list(await AiKnowledgeChunk.filter(document_id=doc.id).order_by("chunk_index"))
    if not chunk_list:
        doc.vector_status = "failed"
        doc.vector_error = "请先建立词法分块索引"
        await doc.save()
        raise HTTPException(status_code=400, detail="请先建立词法分块索引")

    if len(chunk_list) > KNOWLEDGE_EMBED_MAX_CHUNKS_PER_JOB:
        raise HTTPException(
            status_code=400,
            detail=(
                f"分块数 {len(chunk_list)} 超过单次上限 {KNOWLEDGE_EMBED_MAX_CHUNKS_PER_JOB}，"
                "请调大 KNOWLEDGE_EMBED_MAX_CHUNKS_PER_JOB 或拆分文档"
            ),
        )

    config, model = await resolve_embed_ai_config(settings)
    dimensions = resolve_embed_dimensions(config, model)
    effective_username = (username or "").strip() or (getattr(doc, "created_by", None) or "").strip()
    doc.vector_status = "indexing"
    doc.vector_error = None
    await doc.save()

    batch_size = effective_embed_batch_size(config)
    api_key = decrypt_value(config.api_key)
    client = AsyncOpenAI(
        api_key=api_key,
            base_url=resolve_embed_api_base(config),
        timeout=max(int(config.timeout or 60), 120),
    )
    try:
        total = 0
        for i in range(0, len(chunk_list), batch_size):
            batch = chunk_list[i : i + batch_size]
            texts = [c.chunk_text or " " for c in batch]
            vectors = await embed_texts(
                texts,
                config=config,
                model=model,
                project_id=doc.project_id,
                username=effective_username,
                dimensions=dimensions,
                client=client,
            )
            for ch, vec in zip(batch, vectors):
                ch.vector_json = vec
                emb = dict(ch.embedding) if isinstance(ch.embedding, dict) else {}
                emb["kind"] = "hybrid"
                emb["vector"] = vec
                emb["vector_model"] = model
                emb["vector_dim"] = len(vec)
                ch.embedding = emb
                ch.embedding_model = "lexical+vector"
            await AiKnowledgeChunk.bulk_update(
                batch,
                fields=["vector_json", "embedding", "embedding_model"],
            )
            total += len(batch)

        doc.vector_status = "ready"
        doc.vector_model = model
        doc.vector_error = None
        await doc.save()
        return total
    except HTTPException:
        doc.vector_status = "failed"
        await doc.save()
        raise
    except Exception as ex:
        doc.vector_status = "failed"
        doc.vector_error = str(ex)[:500]
        await doc.save()
        raise HTTPException(status_code=502, detail=f"向量 Embedding 失败：{ex}") from ex


async def chain_vector_index_after_lexical(
    doc: AiKnowledgeDocument,
    *,
    settings: Optional[dict[str, Any]] = None,
    username: str = "",
) -> dict[str, Any]:
    """词法索引完成后，按项目/文档策略尝试重建向量（失败不阻断词法结果）。"""
    from app.modules.knowledge.knowledge_embed_config import document_should_vector_embed
    from app.modules.knowledge.knowledge_project_settings import load_knowledge_project_settings

    settings = settings or await load_knowledge_project_settings(doc.project_id)
    out: dict[str, Any] = {
        "vector_chained": False,
        "vector_count": 0,
        "vector_status": getattr(doc, "vector_status", None) or "none",
        "vector_error": None,
    }
    if not is_vector_embed_active(settings):
        return out
    if not document_should_vector_embed(
        doc_type=doc.doc_type,
        embed_mode=getattr(doc, "embed_mode", "inherit") or "inherit",
        project_settings=settings,
    ):
        return out
    try:
        count = await index_document_vectors(doc, settings=settings, force=False, username=username)
        out["vector_chained"] = True
        out["vector_count"] = count
        out["vector_status"] = doc.vector_status
        out["vector_error"] = doc.vector_error
    except HTTPException as ex:
        out["vector_error"] = str(ex.detail)[:240]
        out["vector_status"] = getattr(doc, "vector_status", None) or "failed"
        logger.warning("[vector_embed] chain after lexical doc=%s failed: %s", doc.id, ex.detail)
    except Exception as ex:
        out["vector_error"] = str(ex)[:240]
        out["vector_status"] = getattr(doc, "vector_status", None) or "failed"
        logger.warning("[vector_embed] chain after lexical doc=%s failed: %s", doc.id, ex)
    return out


def will_chain_vector_index(
    doc: AiKnowledgeDocument,
    settings: dict[str, Any],
) -> bool:
    """判断词法索引完成后是否应继续走向量索引。"""
    if not is_vector_embed_active(settings):
        return False
    return document_should_vector_embed(
        doc_type=doc.doc_type,
        embed_mode=getattr(doc, "embed_mode", "inherit") or "inherit",
        project_settings=settings,
    )


async def _chain_vector_index_background(
    doc_id: int,
    project_id: int,
    *,
    username: str = "",
    settings: Optional[dict[str, Any]] = None,
) -> None:
    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc:
        return
    try:
        await chain_vector_index_after_lexical(doc, settings=settings, username=username)
    except Exception as ex:
        logger.exception("[vector_embed] background chain doc=%s failed: %s", doc_id, ex)


async def _index_document_vectors_background(
    doc_id: int,
    project_id: int,
    *,
    username: str = "",
    settings: Optional[dict[str, Any]] = None,
    force: bool = False,
) -> None:
    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc:
        return
    try:
        await index_document_vectors(doc, settings=settings, force=force, username=username)
    except HTTPException as ex:
        detail = ex.detail if isinstance(ex.detail, str) else str(ex.detail)
        logger.warning("[vector_embed] background index doc=%s failed: %s", doc_id, detail)
        doc.vector_status = "failed"
        doc.vector_error = detail[:500]
        await doc.save()
    except Exception as ex:
        logger.exception("[vector_embed] background index doc=%s failed: %s", doc_id, ex)
        doc.vector_status = "failed"
        doc.vector_error = str(ex)[:500]
        await doc.save()


def schedule_chain_vector_index_after_lexical(
    doc_id: int,
    project_id: int,
    *,
    username: str = "",
    settings: Optional[dict[str, Any]] = None,
) -> None:
    asyncio.create_task(
        _chain_vector_index_background(
            doc_id,
            project_id,
            username=username,
            settings=settings,
        )
    )


def schedule_index_document_vectors(
    doc_id: int,
    project_id: int,
    *,
    username: str = "",
    settings: Optional[dict[str, Any]] = None,
    force: bool = False,
) -> None:
    asyncio.create_task(
        _index_document_vectors_background(
            doc_id,
            project_id,
            username=username,
            settings=settings,
            force=force,
        )
    )
