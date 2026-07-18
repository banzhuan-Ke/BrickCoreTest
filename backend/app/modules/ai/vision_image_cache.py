"""Vision 读图结果缓存：同项目内相同图片字节 + 相同模型只识图一次。"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

from app.models.ai import AiVisionImageCache

logger = logging.getLogger(__name__)

# 需求文档与资料库读图共用同一 Prompt 模板
VISION_CACHE_SCENE = "requirement_doc_understand"


def compute_image_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_cacheable_vision_text(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return not t.startswith("（读图失败")


async def get_vision_cache(
    *,
    project_id: Optional[int],
    image_hash: str,
    model: str,
    scene: str = VISION_CACHE_SCENE,
) -> Optional[dict[str, Any]]:
    if not project_id or not image_hash or not model:
        return None
    try:
        row = await AiVisionImageCache.get_or_none(
            project_id=project_id,
            image_hash=image_hash,
            scene=scene,
            model=model,
        )
    except Exception as exc:
        logger.warning("[vision_image_cache] lookup failed hash=%s: %s", image_hash[:12], exc)
        return None
    if not row:
        return None
    return {
        "vision_text": row.vision_text,
        "raw_content": row.raw_content or "",
        "tokens_used": int(row.tokens_used or 0),
    }


async def save_vision_cache(
    *,
    project_id: Optional[int],
    image_hash: str,
    model: str,
    vision_text: str,
    raw_content: str = "",
    tokens_used: int = 0,
    scene: str = VISION_CACHE_SCENE,
) -> None:
    if not project_id or not image_hash or not model:
        return
    if not is_cacheable_vision_text(vision_text):
        return
    try:
        await AiVisionImageCache.update_or_create(
            defaults={
                "vision_text": vision_text[:12000],
                "raw_content": (raw_content or "")[:12000],
                "tokens_used": int(tokens_used or 0),
            },
            project_id=project_id,
            image_hash=image_hash,
            scene=scene,
            model=model,
        )
    except Exception as exc:
        logger.warning("[vision_image_cache] save failed hash=%s: %s", image_hash[:12], exc)


async def lookup_vision_result(
    *,
    project_id: Optional[int],
    image_bytes: bytes,
    model: str,
    session_cache: Optional[dict[str, dict[str, Any]]] = None,
    scene: str = VISION_CACHE_SCENE,
) -> Optional[dict[str, Any]]:
    """先查本次任务内存缓存，再查数据库。"""
    if not image_bytes:
        return None
    img_hash = compute_image_hash(image_bytes)
    if session_cache is not None and img_hash in session_cache:
        hit = dict(session_cache[img_hash])
        hit["cache_source"] = "session"
        hit["image_hash"] = img_hash
        return hit

    cached = await get_vision_cache(
        project_id=project_id,
        image_hash=img_hash,
        model=model,
        scene=scene,
    )
    if not cached:
        return None
    cached = dict(cached)
    cached["cache_source"] = "db"
    cached["image_hash"] = img_hash
    if session_cache is not None:
        session_cache[img_hash] = {
            "vision_text": cached["vision_text"],
            "raw_content": cached.get("raw_content") or "",
            "tokens_used": cached.get("tokens_used") or 0,
        }
    return cached


async def store_vision_result(
    *,
    project_id: Optional[int],
    image_bytes: bytes,
    model: str,
    vision_text: str,
    raw_content: str = "",
    tokens_used: int = 0,
    session_cache: Optional[dict[str, dict[str, Any]]] = None,
    scene: str = VISION_CACHE_SCENE,
) -> str:
    img_hash = compute_image_hash(image_bytes)
    payload = {
        "vision_text": vision_text,
        "raw_content": raw_content,
        "tokens_used": int(tokens_used or 0),
    }
    if session_cache is not None:
        session_cache[img_hash] = payload
    await save_vision_cache(
        project_id=project_id,
        image_hash=img_hash,
        model=model,
        scene=scene,
        vision_text=vision_text,
        raw_content=raw_content,
        tokens_used=tokens_used,
    )
    return img_hash
