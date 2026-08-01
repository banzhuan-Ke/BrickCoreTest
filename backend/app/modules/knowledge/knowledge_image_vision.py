"""资料库文档图片 Vision 读图（无张数上限，串行处理）。"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Awaitable, Callable, Optional

from app.core.llm.llm_client import LLMClientFactory
from app.core.platform.encryption import decrypt_value
from app.models.ai import AiConfig
from app.modules.ai.ai_prompts import PromptManager
from app.modules.ai.requirement_document import section_text, vision_summary_to_text
from app.modules.ai.vision_image_cache import lookup_vision_result, store_vision_result

logger = logging.getLogger(__name__)

VISION_CONTEXT_MAX_CHARS = 6000


def _extract_json_object(text: str) -> dict:
    if not text:
        return {}
    text = text.strip()
    code_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)
    for block in code_blocks:
        try:
            data = json.loads(block.strip())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


def _find_section_for_image(sections: list[dict], image_index: int) -> Optional[dict]:
    for sec in sections:
        if image_index in (sec.get("image_indices") or []):
            return sec
    return sections[0] if sections else None


async def analyze_one_image_with_vision(
    client: Any,
    vision_config: AiConfig,
    img: dict,
    blocks: list[dict],
    sections: list[dict],
    *,
    system_prompt: str,
    user_template_base: str,
    project_id: Optional[int] = None,
    username: str = "",
    document_id: Optional[int] = None,
    ocr_text_by_index: Optional[dict[int, str]] = None,
    session_cache: Optional[dict[str, dict[str, Any]]] = None,
) -> tuple[str, dict[str, Any], int]:
    """单张 Vision 读图，返回 (vision_text, item_report, tokens)。"""
    ocr_text_by_index = ocr_text_by_index or {}
    idx = img.get("index")
    item: dict[str, Any] = {
        "index": idx,
        "ok": False,
        "tokens": 0,
        "content": "",
        "error": None,
        "section_title": "",
        "skipped": False,
    }
    if idx is None:
        item["error"] = "无效图片索引"
        return "", item, 0

    sec = _find_section_for_image(sections, idx)
    if sec:
        item["section_title"] = sec.get("title") or ""
    ctx = section_text(blocks, sec) if sec else ""
    ocr_hint = (ocr_text_by_index.get(idx) or "").strip()
    if ocr_hint:
        ctx = f"{ctx}\n\n[本地 OCR 参考]\n{ocr_hint}".strip() if ctx.strip() else f"[本地 OCR 参考]\n{ocr_hint}"
    if not ctx.strip():
        ctx = "（该图附近无提取到正文，请仅根据图片内容分析）"
    excerpt = ctx[:VISION_CONTEXT_MAX_CHARS]
    user_text = user_template_base.replace("（见下方章节上下文）", excerpt)

    img_bytes = img.get("data") or b""
    cached = await lookup_vision_result(
        project_id=project_id,
        image_bytes=img_bytes,
        model=vision_config.model,
        session_cache=session_cache,
    )
    if cached:
        item["ok"] = True
        item["cached"] = True
        item["cache_source"] = cached.get("cache_source")
        item["content"] = (cached.get("raw_content") or cached["vision_text"])[:12000]
        return cached["vision_text"], item, 0

    img_t0 = time.time()
    try:
        resp = await client.chat_with_image(
            system_prompt=system_prompt,
            text=user_text,
            image_bytes=img_bytes,
            image_mime=img.get("mime", "image/png"),
            temperature=0.3,
            max_tokens=min(int(vision_config.max_tokens or 4096), 4096),
        )
        item["tokens"] = int(resp.get("tokens") or 0)
        raw_content = resp.get("content", "") or ""
        item["content"] = raw_content[:12000]
        item["ok"] = True
        parsed = _extract_json_object(raw_content)
        if parsed:
            vision_text = vision_summary_to_text(parsed)
        else:
            vision_text = raw_content[:4000]
        await store_vision_result(
            project_id=project_id,
            image_bytes=img_bytes,
            model=vision_config.model,
            vision_text=vision_text,
            raw_content=raw_content,
            tokens_used=item["tokens"],
            session_cache=session_cache,
        )
        if project_id:
            from app.core.llm.ai_usage_log import log_ai_usage

            await log_ai_usage(
                vision_config,
                "knowledge_doc_image_vision",
                username=username,
                project_id=project_id,
                tokens_used=item["tokens"],
                duration_ms=int((time.time() - img_t0) * 1000),
                input_summary=f"资料库文档#{document_id or '-'} · 图片 {idx}"[:500],
                output_summary=(item["content"] or "")[:500],
            )
        return vision_text, item, item["tokens"]
    except Exception as ex:
        logger.warning("[knowledge_image_vision] Vision failed idx=%s: %s", idx, ex)
        err = str(ex)
        item["error"] = err
        if project_id:
            from app.core.llm.ai_usage_log import log_ai_usage

            await log_ai_usage(
                vision_config,
                "knowledge_doc_image_vision",
                username=username,
                project_id=project_id,
                tokens_used=0,
                duration_ms=int((time.time() - img_t0) * 1000),
                status="failed",
                input_summary=f"资料库文档#{document_id or '-'} · 图片 {idx}"[:500],
                output_summary=err[:500],
            )
        return f"（读图失败: {err}）", item, 0


async def analyze_images_with_vision(
    vision_config: AiConfig,
    images: list[dict],
    blocks: list[dict],
    sections: list[dict],
    *,
    project_id: Optional[int] = None,
    username: str = "",
    document_id: Optional[int] = None,
    ocr_text_by_index: Optional[dict[int, str]] = None,
    cancel_check: Optional[Callable[[], Awaitable[bool]]] = None,
    on_image_done: Optional[Callable[[dict[str, Any], str], Awaitable[None]]] = None,
) -> tuple[dict[int, str], int, dict[str, Any]]:
    """返回 (image_index -> 读图文本, tokens, report)。处理全部图片，无张数上限。"""
    ocr_text_by_index = ocr_text_by_index or {}
    report: dict[str, Any] = {
        "skipped": False,
        "config_name": vision_config.name,
        "model": vision_config.model,
        "provider": vision_config.provider,
        "image_total": len(images),
        "images": [],
        "ok_count": 0,
        "fail_count": 0,
        "cache_hit_count": 0,
        "cache_miss_count": 0,
    }
    if not images:
        report["skipped"] = True
        report["message"] = "文档内无图片"
        return {}, 0, report

    api_key = decrypt_value(vision_config.api_key)
    client = LLMClientFactory.create(
        provider=vision_config.provider,
        api_key=api_key,
        api_base=vision_config.api_base,
        model=vision_config.model,
        timeout=max(int(vision_config.timeout or 60), 120),
    )
    if not hasattr(client, "chat_with_image"):
        report["skipped"] = True
        report["message"] = "Vision 客户端不支持读图"
        return {}, 0, report

    system_prompt, user_template_base = await PromptManager.render(
        "requirement_doc_understand",
        {"doc_text_excerpt": "（见下方章节上下文）"},
    )

    vision_text_by_index: dict[int, str] = {}
    total_tokens = 0
    session_cache: dict[str, dict[str, Any]] = {}
    for img in images:
        if cancel_check and await cancel_check():
            report["cancelled"] = True
            break
        idx = img.get("index")
        if idx is None:
            continue
        vision_text, item, tokens = await analyze_one_image_with_vision(
            client,
            vision_config,
            img,
            blocks,
            sections,
            system_prompt=system_prompt,
            user_template_base=user_template_base,
            project_id=project_id,
            username=username,
            document_id=document_id,
            ocr_text_by_index=ocr_text_by_index,
            session_cache=session_cache,
        )
        total_tokens += tokens
        vision_text_by_index[idx] = vision_text
        if item.get("ok"):
            report["ok_count"] += 1
            if item.get("cached"):
                report["cache_hit_count"] += 1
            else:
                report["cache_miss_count"] += 1
        else:
            report["fail_count"] += 1
        report["images"].append(item)
        if on_image_done:
            await on_image_done(item, vision_text)

    report["success"] = report["ok_count"] > 0 and report["fail_count"] == 0
    report["partial"] = report["ok_count"] > 0 and report["fail_count"] > 0
    return vision_text_by_index, total_tokens, report
