"""资料库文档图片解析：入库/reparse 阶段 OCR + 可选 Vision，后台串行处理全部图片。"""
from __future__ import annotations

import copy
import logging
from typing import Any, Optional

from fastapi import HTTPException

from app.models.knowledge import AiKnowledgeDocument
from app.modules.ai.document_loader import load_document
from app.modules.knowledge.constants import KNOWLEDGE_INGEST_MAX_PROSE_CHARS
from app.modules.knowledge.knowledge_image_ocr import ocr_image, rapidocr_available
from app.modules.knowledge.knowledge_ingest_prose import (
    _apply_prose_size_guard,
    _build_outline,
    _normalize_section,
    _sections_to_fulltext,
)
from app.modules.knowledge.knowledge_project_settings import load_knowledge_project_settings
from app.modules.knowledge.knowledge_storage import load_document_source

logger = logging.getLogger(__name__)

IMAGE_PARSE_OFF = "off"
IMAGE_PARSE_OCR = "ocr"
IMAGE_PARSE_VISION = "vision"
IMAGE_PARSE_OCR_THEN_VISION = "ocr_then_vision"

IMAGE_PARSE_STATUS_PENDING = "pending"
IMAGE_PARSE_STATUS_PARSING = "parsing"
IMAGE_PARSE_STATUS_READY = "ready"
IMAGE_PARSE_STATUS_PARTIAL = "partial"
IMAGE_PARSE_STATUS_SKIPPED = "skipped"
IMAGE_PARSE_STATUS_FAILED = "failed"
IMAGE_PARSE_STATUS_CANCELLED = "cancelled"

MIN_IMAGE_EDGE = 10
OCR_ENGINE_LABEL = "RapidOCR（PP-OCR 本地文档 OCR）"


def normalize_image_parse_mode(raw: Any) -> str:
    mode = str(raw or IMAGE_PARSE_OCR).strip().lower()
    if mode in (IMAGE_PARSE_OFF, IMAGE_PARSE_OCR, IMAGE_PARSE_VISION, IMAGE_PARSE_OCR_THEN_VISION):
        return mode
    return IMAGE_PARSE_OCR


def resolve_effective_image_mode(
    settings: dict[str, Any],
    *,
    reparse_override: Optional[str] = None,
) -> str:
    """reparse_override: default | enhanced | off"""
    if reparse_override == "off":
        return IMAGE_PARSE_OFF
    if reparse_override == "enhanced":
        cfg_mode = normalize_image_parse_mode(settings.get("knowledge_image_parse_mode"))
        if cfg_mode in (IMAGE_PARSE_VISION, IMAGE_PARSE_OCR_THEN_VISION):
            return cfg_mode
        return IMAGE_PARSE_OCR_THEN_VISION
    return normalize_image_parse_mode(settings.get("knowledge_image_parse_mode"))


def _strip_section_buffers(sections: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for sec in sections or []:
        if not isinstance(sec, dict):
            continue
        item = {k: v for k, v in sec.items() if k != "_text_buf"}
        cleaned.append(item)
    return cleaned


def section_interleaved_text(
    blocks: list[dict],
    section: dict,
    image_text_by_index: dict[int, str],
) -> str:
    """按 block 顺序输出章节正文（含图片识别文本）。"""
    block_map = {b.get("id"): b for b in blocks if b.get("id")}
    parts: list[str] = []
    for bid in section.get("block_ids") or []:
        blk = block_map.get(bid)
        if not blk:
            continue
        if blk.get("type") == "image":
            idx = blk.get("image_index")
            anchor = blk.get("anchor") or (f"第 {blk.get('page')} 页" if blk.get("page") else "")
            label = f"[图-{idx + 1 if idx is not None else '?'}]"
            if anchor:
                label += f" ({anchor})"
            vtext = image_text_by_index.get(idx, "") if idx is not None else ""
            if vtext:
                parts.append(f"{label}\n{vtext}")
            else:
                parts.append(f"{label}（识图进行中或未识别）")
        else:
            t = (blk.get("text") or "").strip()
            if t:
                parts.append(t)
    return "\n\n".join(parts).strip()


def merge_image_text(*, ocr_text: str = "", vision_text: str = "") -> str:
    ocr_text = (ocr_text or "").strip()
    vision_text = (vision_text or "").strip()
    if vision_text and is_low_quality_ocr_text(ocr_text):
        return vision_text
    if ocr_text and vision_text:
        return f"[OCR]\n{ocr_text}\n\n[读图理解]\n{vision_text}"
    return vision_text or ocr_text


def is_low_quality_ocr_text(text: str) -> bool:
    """过滤明显无效的 OCR 片段（如单字噪声），避免污染入库正文。"""
    t = (text or "").strip()
    if not t:
        return True
    if len(t) == 1:
        return True
    if len(t) <= 3 and all(not (ch.isalnum() or "\u4e00" <= ch <= "\u9fff") for ch in t):
        return True
    return False


def build_image_text_map(
    *,
    ocr_by_index: dict[int, str],
    vision_by_index: dict[int, str],
) -> dict[int, str]:
    indices = set(ocr_by_index) | set(vision_by_index)
    out: dict[int, str] = {}
    for idx in sorted(indices):
        merged = merge_image_text(
            ocr_text=ocr_by_index.get(idx, ""),
            vision_text=vision_by_index.get(idx, ""),
        )
        if merged:
            out[idx] = merged
    return out


def prepare_loader_meta_from_result(result: Any) -> Optional[dict[str, Any]]:
    image_count = len(getattr(result, "images", None) or [])
    blocks = getattr(result, "blocks", None) or []
    raw_sections = _strip_section_buffers(getattr(result, "sections", None) or [])
    if image_count <= 0:
        return None
    return {
        "blocks": blocks,
        "sections": raw_sections,
        "image_count": image_count,
    }


def compact_loader_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """持久化时仅保留 loader.image_count，避免 blocks 撑大 JSON 拖慢数据库。"""
    out = dict(meta)
    loader = out.get("loader")
    if isinstance(loader, dict):
        cnt = int(loader.get("image_count") or 0)
        if cnt > 0:
            out["loader"] = {"image_count": cnt}
        else:
            out.pop("loader", None)
    return out


def attach_image_parse_meta(
    sections_json: dict[str, Any],
    loader_meta: Optional[dict[str, Any]],
    *,
    mode: str = IMAGE_PARSE_OCR,
) -> dict[str, Any]:
    payload = copy.deepcopy(sections_json)
    meta = dict(payload.get("_meta") or {})
    if not loader_meta or int(loader_meta.get("image_count") or 0) <= 0:
        meta.pop("loader", None)
        meta.pop("image_parse", None)
        payload["_meta"] = meta or None
        if payload.get("_meta") is None:
            payload.pop("_meta", None)
        return payload

    meta["loader"] = {
        "image_count": int(loader_meta.get("image_count") or 0),
    }
    if mode == IMAGE_PARSE_OFF:
        meta["image_parse"] = {
            "status": IMAGE_PARSE_STATUS_SKIPPED,
            "mode": mode,
            "total": meta["loader"]["image_count"],
            "completed": 0,
            "ocr_engine": "rapidocr" if rapidocr_available() else "unavailable",
        }
    else:
        meta["image_parse"] = {
            "status": IMAGE_PARSE_STATUS_PENDING,
            "mode": mode,
            "total": meta["loader"]["image_count"],
            "completed": 0,
            "ocr_ok": 0,
            "vision_ok": 0,
            "ocr_engine": "rapidocr" if rapidocr_available() else "unavailable",
            "items": [],
        }
    payload["_meta"] = meta
    return payload


def rebuild_sections_with_image_text(
    sections_json: dict[str, Any],
    image_text_by_index: dict[int, str],
    *,
    blocks: Optional[list[dict]] = None,
    raw_sections: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """用识图结果重建 sections / fulltext / outline / char_count。"""
    payload = copy.deepcopy(sections_json)
    meta = payload.get("_meta") or {}
    loader = meta.get("loader") or {}
    use_blocks = blocks if blocks is not None else (loader.get("blocks") or [])
    use_sections = raw_sections if raw_sections is not None else (loader.get("sections") or [])
    v2_sections = payload.get("sections") or []
    warnings = list(payload.get("parse_warnings") or [])

    updated: list[dict[str, Any]] = []
    for i, sec in enumerate(v2_sections):
        if not isinstance(sec, dict):
            continue
        raw = use_sections[i] if i < len(use_sections) else None
        if raw and use_blocks:
            body = section_interleaved_text(use_blocks, raw, image_text_by_index)
        else:
            body = (sec.get("content") or "").strip()
        updated.append(
            _normalize_section(
                title=sec.get("title") or "正文",
                content=body,
                level=int(sec.get("level") or 1),
                page=sec.get("page"),
            )
        )

    if not updated:
        updated = v2_sections

    updated, fulltext = _apply_prose_size_guard(
        updated,
        max_chars=KNOWLEDGE_INGEST_MAX_PROSE_CHARS,
        warnings=warnings,
    )
    outline = _build_outline(updated)
    payload["sections"] = updated
    payload["fulltext"] = fulltext
    payload["char_count"] = len(fulltext)
    payload["parse_warnings"] = warnings
    payload["chunk_count"] = max(len(updated), 1 if fulltext else 0)
    structured = payload.get("structured")
    if isinstance(structured, dict):
        structured = {**structured, "outline": outline}
        payload["structured"] = structured
    return payload


def get_image_parse_summary(sections_json: Any) -> dict[str, Any]:
    if not isinstance(sections_json, dict):
        return {}
    meta = sections_json.get("_meta")
    if not isinstance(meta, dict):
        return {}
    ip = meta.get("image_parse")
    return ip if isinstance(ip, dict) else {}


def _clip_preview(text: str, max_len: int = 800) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def _image_dimensions(data: bytes) -> tuple[int, int]:
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(data))
        return int(img.size[0]), int(img.size[1])
    except Exception:
        return 0, 0


def image_too_small_for_recognition(data: bytes, min_edge: int = MIN_IMAGE_EDGE) -> bool:
    w, h = _image_dimensions(data)
    if w <= 0 or h <= 0:
        return True
    return w < min_edge or h < min_edge


async def is_image_parse_cancelled(doc_id: int, project_id: int) -> bool:
    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc:
        return True
    sections_json = doc.sections_json if isinstance(doc.sections_json, dict) else {}
    ip = (sections_json.get("_meta") or {}).get("image_parse") or {}
    return bool(ip.get("cancel_requested"))


def _resolve_row_status(
    *,
    enabled: bool,
    done_ok: Optional[bool],
    explicit_status: Optional[str],
    job_running: bool,
    is_current: bool,
) -> Optional[str]:
    if not enabled:
        return None
    if explicit_status:
        return explicit_status
    if done_ok is True:
        return "success"
    if job_running:
        if is_current:
            return "processing"
        return "pending"
    if done_ok is False:
        return "failed"
    return "pending"


IMAGE_PARSE_MODE_LABELS: dict[str, str] = {
    IMAGE_PARSE_OFF: "关闭",
    IMAGE_PARSE_OCR: "本地 OCR",
    IMAGE_PARSE_VISION: "Vision 读图",
    IMAGE_PARSE_OCR_THEN_VISION: "OCR + Vision",
}


def build_image_parse_results(
    images: list[dict],
    *,
    ocr_by_index: dict[int, str],
    vision_by_index: dict[int, str],
    vision_report: Optional[dict[str, Any]] = None,
    ocr_items: Optional[list[dict[str, Any]]] = None,
    run_ocr: bool = False,
    run_vision: bool = False,
    job_running: bool = False,
    current_phase: Optional[str] = None,
    current_index: Optional[int] = None,
) -> list[dict[str, Any]]:
    """构建每张图片的识图明细，供文档详情页展示。"""
    vision_items_by_idx: dict[Any, dict[str, Any]] = {}
    if isinstance(vision_report, dict) and isinstance(vision_report.get("images"), list):
        for vi in vision_report["images"]:
            if isinstance(vi, dict) and vi.get("index") is not None:
                vision_items_by_idx[vi["index"]] = vi

    ocr_items_by_idx: dict[Any, dict[str, Any]] = {}
    for oi in ocr_items or []:
        if isinstance(oi, dict) and oi.get("index") is not None:
            ocr_items_by_idx[oi["index"]] = oi

    results: list[dict[str, Any]] = []
    for img in images:
        idx = img.get("index")
        if idx is None:
            continue
        ocr_item = ocr_items_by_idx.get(idx, {})
        vision_item = vision_items_by_idx.get(idx, {})
        merged = merge_image_text(
            ocr_text=ocr_by_index.get(idx, ""),
            vision_text=vision_by_index.get(idx, ""),
        )
        ocr_ok = bool(ocr_by_index.get(idx)) if run_ocr else None
        if run_ocr and ocr_item.get("ocr_skipped"):
            ocr_ok = False
        vision_ok = bool(vision_item.get("ok")) if run_vision else None
        if run_vision and vision_item.get("skipped"):
            vision_ok = False
        ocr_status = _resolve_row_status(
            enabled=run_ocr,
            done_ok=ocr_ok if ocr_item or not job_running else None,
            explicit_status=ocr_item.get("ocr_status"),
            job_running=job_running,
            is_current=current_phase == "ocr" and current_index == idx,
        )
        ocr_low_quality = bool(run_ocr and ocr_by_index.get(idx) and is_low_quality_ocr_text(ocr_by_index.get(idx, "")))
        if run_ocr and ocr_item.get("ocr_skipped"):
            ocr_status = "skipped"
        elif run_ocr and ocr_item.get("ocr_error") and not job_running:
            ocr_status = "failed"
        elif ocr_low_quality and vision_by_index.get(idx):
            ocr_status = "skipped"
        vision_status = _resolve_row_status(
            enabled=run_vision,
            done_ok=vision_ok if vision_item or not job_running else None,
            explicit_status=vision_item.get("vision_status"),
            job_running=job_running,
            is_current=current_phase == "vision" and current_index == idx,
        )
        if run_vision and vision_item.get("skipped"):
            vision_status = "skipped"
        elif run_vision and vision_item.get("error") and not job_running and not vision_item.get("ok"):
            vision_status = "failed"
        results.append(
            {
                "index": idx,
                "display_index": int(idx) + 1,
                "page": img.get("page"),
                "section_title": (vision_item.get("section_title") or ocr_item.get("section_title") or "").strip(),
                "ocr_ok": ocr_ok if not ocr_low_quality else False,
                "ocr_status": ocr_status,
                "ocr_low_quality": ocr_low_quality,
                "ocr_preview": _clip_preview(ocr_by_index.get(idx, ""), 400) if run_ocr and not ocr_low_quality else "",
                "ocr_error": (ocr_item.get("ocr_error") or "").strip() or None,
                "vision_ok": vision_ok,
                "vision_status": vision_status,
                "vision_preview": _clip_preview(vision_by_index.get(idx, ""), 800) if run_vision else "",
                "vision_error": (vision_item.get("error") or "").strip() or None,
                "merged_preview": _clip_preview(merged, 1000),
                "has_result": bool(merged),
            }
        )
    return results


def get_image_parse_details(sections_json: Any) -> dict[str, Any]:
    """API 返回：识图汇总 + 每张图 OCR/Vision 预览。"""
    ip = get_image_parse_summary(sections_json)
    total = int(ip.get("total") or 0)
    if total <= 0:
        return {"summary": {}, "items": [], "has_full_results": False}

    mode = str(ip.get("mode") or "")
    summary = {
        key: ip.get(key)
        for key in (
            "status",
            "mode",
            "total",
            "completed",
            "ocr_ok",
            "vision_ok",
            "ocr_engine",
            "vision_skipped",
            "vision_message",
            "vision_report",
            "error",
        )
        if key in ip
    }
    summary["mode_label"] = IMAGE_PARSE_MODE_LABELS.get(mode, mode or "—")
    summary["job_running"] = summary.get("status") == IMAGE_PARSE_STATUS_PARSING
    if summary.get("ocr_engine") in ("rapidocr", "ddddocr"):
        summary["ocr_engine_label"] = ip.get("ocr_engine_label") or OCR_ENGINE_LABEL
    else:
        summary["ocr_engine_label"] = ip.get("ocr_engine_label") or summary.get("ocr_engine") or "—"
    if summary.get("ocr_engine") == "skipped":
        summary["ocr_engine_label"] = ip.get("ocr_engine_label") or "已跳过本地 OCR"

    stored = ip.get("results")
    if isinstance(stored, list) and stored:
        return {"summary": summary, "items": stored, "has_full_results": not summary["job_running"]}

    fallback: list[dict[str, Any]] = []
    for oi in ip.get("items") or []:
        if not isinstance(oi, dict) or oi.get("index") is None:
            continue
        idx = oi.get("index")
        job_running = summary["job_running"]
        fallback.append(
            {
                "index": idx,
                "display_index": int(idx) + 1,
                "page": oi.get("page"),
                "section_title": oi.get("section_title") or "",
                "ocr_ok": oi.get("ocr_ok"),
                "ocr_status": oi.get("ocr_status") or ("pending" if job_running else None),
                "ocr_preview": oi.get("ocr_preview") or "",
                "ocr_error": oi.get("ocr_error"),
                "vision_ok": None if job_running else oi.get("vision_ok"),
                "vision_status": "pending" if job_running else oi.get("vision_status"),
                "vision_preview": "",
                "vision_error": None,
                "merged_preview": oi.get("ocr_preview") or "",
                "has_result": bool(oi.get("ocr_ok")),
            }
        )
    return {
        "summary": summary,
        "items": fallback,
        "has_full_results": False,
        "partial_only": bool(fallback),
    }


def should_schedule_image_parse(sections_json: Any, mode: str) -> bool:
    if mode == IMAGE_PARSE_OFF:
        return False
    summary = get_image_parse_summary(sections_json)
    total = int(summary.get("total") or 0)
    status = summary.get("status")
    return total > 0 and status in (IMAGE_PARSE_STATUS_PENDING, IMAGE_PARSE_STATUS_PARSING)


async def _resolve_vision_config(settings: dict[str, Any]):
    from app.modules.ai.ai_scene_config import resolve_vision_config

    config_id = settings.get("knowledge_doc_vision_ai_config_id")
    if config_id:
        return await resolve_vision_config(int(config_id), scene="requirement_doc_understand")
    return await resolve_vision_config(None, scene="requirement_doc_understand")


async def _resolve_run_ocr_and_vision(mode: str, settings: dict[str, Any]) -> tuple[bool, bool, Optional[Any]]:
    """解析是否执行本地 OCR 与 Vision。"""
    run_vision = mode in (IMAGE_PARSE_VISION, IMAGE_PARSE_OCR_THEN_VISION)
    run_ocr = mode in (IMAGE_PARSE_OCR, IMAGE_PARSE_OCR_THEN_VISION)
    vision_config = None
    if run_vision:
        vision_config = await _resolve_vision_config(settings)
        if vision_config is None:
            run_vision = False
    return run_ocr, run_vision, vision_config


async def _persist_image_parse_doc(
    doc: AiKnowledgeDocument,
    sections_json: dict[str, Any],
    meta: dict[str, Any],
    ip: dict[str, Any],
    *,
    blocks: list[dict],
    raw_sections: list[dict],
    images: list[dict],
    ocr_by_index: dict[int, str],
    vision_by_index: dict[int, str],
    ocr_items: list[dict[str, Any]],
    vision_report: dict[str, Any],
    run_ocr: bool,
    run_vision: bool,
    job_running: bool,
    current_phase: Optional[str] = None,
    current_index: Optional[int] = None,
) -> dict[str, Any]:
    ip["results"] = build_image_parse_results(
        images,
        ocr_by_index=ocr_by_index,
        vision_by_index=vision_by_index,
        vision_report=vision_report if run_vision else None,
        ocr_items=ocr_items,
        run_ocr=run_ocr,
        run_vision=run_vision,
        job_running=job_running,
        current_phase=current_phase,
        current_index=current_index,
    )
    meta["image_parse"] = ip
    meta["loader"] = {"image_count": len(images)}
    image_text = build_image_text_map(ocr_by_index=ocr_by_index, vision_by_index=vision_by_index)
    sections_json = rebuild_sections_with_image_text(
        sections_json,
        image_text,
        blocks=blocks,
        raw_sections=raw_sections,
    )
    sections_json["_meta"] = compact_loader_meta(meta)
    doc.sections_json = sections_json
    doc.char_count = int(sections_json.get("char_count") or 0)
    doc.chunk_count = max(len(sections_json.get("sections") or []), 1)
    await doc.save()
    return sections_json


async def parse_document_images_background(
    doc_id: int,
    project_id: int,
    *,
    reparse_override: Optional[str] = None,
    username: str = "",
) -> None:
    """后台串行处理文档内全部图片（无张数上限）。"""
    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc or not doc.storage:
        return
    username = (username or "").strip() or (getattr(doc, "created_by", None) or "").strip()

    settings = await load_knowledge_project_settings(project_id)
    mode = resolve_effective_image_mode(settings, reparse_override=reparse_override)
    sections_json = doc.sections_json if isinstance(doc.sections_json, dict) else {}
    if not should_schedule_image_parse(sections_json, mode) and mode != IMAGE_PARSE_OFF:
        summary = get_image_parse_summary(sections_json)
        if int(summary.get("total") or 0) <= 0:
            return

    if mode == IMAGE_PARSE_OFF:
        meta = dict((sections_json.get("_meta") or {}))
        ip = dict(meta.get("image_parse") or {})
        ip["status"] = IMAGE_PARSE_STATUS_SKIPPED
        ip["mode"] = mode
        meta["image_parse"] = ip
        sections_json = {**sections_json, "_meta": meta}
        doc.sections_json = sections_json
        await doc.save()
        return

    try:
        content = load_document_source(doc.storage or {}, doc.file_name)
        loaded = load_document(content, doc.file_name or "")
    except Exception as ex:
        logger.exception("[knowledge_image_parse] reload doc=%s failed", doc_id)
        meta = dict((sections_json.get("_meta") or {}))
        ip = dict(meta.get("image_parse") or {})
        ip.update({"status": IMAGE_PARSE_STATUS_FAILED, "error": str(ex)[:500]})
        meta["image_parse"] = ip
        doc.sections_json = {**sections_json, "_meta": meta}
        await doc.save()
        return

    images = [
        {"index": img.index, "mime": img.mime, "data": img.data, "page": img.page}
        for img in (loaded.images or [])
    ]
    loader = (sections_json.get("_meta") or {}).get("loader") or {}
    blocks = loader.get("blocks") or loaded.blocks or []
    raw_sections = loader.get("sections") or _strip_section_buffers(loaded.sections or [])

    meta = dict((sections_json.get("_meta") or {}))
    ip = dict(meta.get("image_parse") or {})
    ip.update(
        {
            "status": IMAGE_PARSE_STATUS_PARSING,
            "mode": mode,
            "total": len(images),
            "completed": 0,
            "ocr_ok": 0,
            "vision_ok": 0,
            "ocr_engine": "rapidocr" if rapidocr_available() else "unavailable",
            "items": [],
            "cancel_requested": False,
            "current_phase": None,
            "current_index": None,
        }
    )
    meta["image_parse"] = ip
    meta["loader"] = {"image_count": len(images)}
    sections_json = {**sections_json, "_meta": compact_loader_meta(meta)}
    doc.sections_json = sections_json
    await doc.save()

    ocr_concurrency = max(1, int(settings.get("knowledge_image_ocr_concurrency") or 1))
    run_ocr, run_vision, vision_config = await _resolve_run_ocr_and_vision(mode, settings)
    ocr_engine_label = OCR_ENGINE_LABEL if rapidocr_available() else "unavailable"
    ip["ocr_engine_label"] = ocr_engine_label
    meta["image_parse"] = ip
    sections_json["_meta"] = compact_loader_meta(meta)
    doc.sections_json = sections_json
    await doc.save()

    ocr_by_index: dict[int, str] = {}
    vision_by_index: dict[int, str] = {}
    items: list[dict[str, Any]] = []
    vision_report: dict[str, Any] = {"images": [], "ok_count": 0, "fail_count": 0}
    cancelled = False

    if run_ocr:
        ip["current_phase"] = "ocr"
        for img in images:
            if await is_image_parse_cancelled(doc_id, project_id):
                cancelled = True
                break
            idx = img.get("index")
            if idx is None:
                continue
            ip["current_index"] = idx
            item: dict[str, Any] = {"index": idx, "page": img.get("page")}
            data = img.get("data") or b""
            if image_too_small_for_recognition(data):
                w, h = _image_dimensions(data)
                item.update(
                    {
                        "ocr_ok": False,
                        "ocr_skipped": True,
                        "ocr_status": "skipped",
                        "ocr_error": f"图片尺寸过小（{w}×{h}，需宽高均 ≥ {MIN_IMAGE_EDGE}px），已跳过 OCR",
                    }
                )
            else:
                text, err = await ocr_image(data, concurrency=ocr_concurrency)
                if text:
                    ocr_by_index[idx] = text
                    item.update(
                        {
                            "ocr_ok": True,
                            "ocr_status": "success",
                            "ocr_preview": text[:200],
                        }
                    )
                else:
                    item.update(
                        {
                            "ocr_ok": False,
                            "ocr_status": "failed",
                            "ocr_error": (err or "OCR 无有效结果")[:200],
                        }
                    )
            items.append(item)
            ip["completed"] = len(items)
            ip["ocr_ok"] = len(ocr_by_index)
            ip["items"] = items[-30:]
            sections_json = await _persist_image_parse_doc(
                doc,
                sections_json,
                meta,
                ip,
                blocks=blocks,
                raw_sections=raw_sections,
                images=images,
                ocr_by_index=ocr_by_index,
                vision_by_index=vision_by_index,
                ocr_items=items,
                vision_report=vision_report,
                run_ocr=run_ocr,
                run_vision=run_vision,
                job_running=True,
                current_phase="ocr",
                current_index=idx,
            )
            meta = sections_json.get("_meta") or meta
            ip = meta.get("image_parse") or ip

    run_vision_effective = run_vision and not cancelled
    if run_vision_effective:
        if vision_config is None:
            ip["vision_skipped"] = True
            ip["vision_message"] = "未配置 Vision 模型"
            if not run_ocr:
                warnings = list(sections_json.get("parse_warnings") or [])
                warnings.append("未配置 Vision 模型，图片未识图入库")
                sections_json["parse_warnings"] = warnings
            run_vision_effective = False
        else:
            from app.modules.knowledge.knowledge_image_vision import analyze_images_with_vision

            ip["current_phase"] = "vision"

            async def _on_vision_image(item: dict[str, Any], vision_text: str) -> None:
                nonlocal sections_json, meta, ip
                idx = item.get("index")
                if idx is None:
                    return
                if item.get("skipped"):
                    vision_by_index[idx] = ""
                else:
                    vision_by_index[idx] = vision_text
                ip["vision_ok"] = sum(
                    1
                    for v in vision_by_index.values()
                    if v and not str(v).startswith("（读图失败")
                )
                ip["completed"] = max(int(ip.get("completed") or 0), len(items) + len(vision_by_index))
                ip["current_index"] = idx
                sections_json = await _persist_image_parse_doc(
                    doc,
                    sections_json,
                    meta,
                    ip,
                    blocks=blocks,
                    raw_sections=raw_sections,
                    images=images,
                    ocr_by_index=ocr_by_index,
                    vision_by_index=vision_by_index,
                    ocr_items=items,
                    vision_report=vision_report,
                    run_ocr=run_ocr,
                    run_vision=True,
                    job_running=True,
                    current_phase="vision",
                    current_index=idx,
                )
                meta = sections_json.get("_meta") or meta
                ip = meta.get("image_parse") or ip

            skipped_reports: list[dict[str, Any]] = []
            vision_images = []
            for img in images:
                idx = img.get("index")
                if idx is None:
                    continue
                if image_too_small_for_recognition(img.get("data") or b""):
                    w, h = _image_dimensions(img.get("data") or b"")
                    skip_item = {
                        "index": idx,
                        "ok": False,
                        "skipped": True,
                        "error": f"图片尺寸过小（{w}×{h}，需宽高均 ≥ {MIN_IMAGE_EDGE}px），已跳过 Vision",
                        "section_title": "",
                    }
                    skipped_reports.append(skip_item)
                    await _on_vision_image(skip_item, "")
                else:
                    vision_images.append(img)

            if vision_images:
                vmap, _tokens, batch_report = await analyze_images_with_vision(
                    vision_config,
                    vision_images,
                    blocks,
                    raw_sections,
                    project_id=project_id,
                    username=username,
                    document_id=doc_id,
                    ocr_text_by_index=ocr_by_index,
                    cancel_check=lambda: is_image_parse_cancelled(doc_id, project_id),
                    on_image_done=_on_vision_image,
                )
                vision_by_index.update(vmap)
                if batch_report.get("cancelled"):
                    cancelled = True
                vision_report = {
                    "images": skipped_reports + list(batch_report.get("images") or []),
                    "ok_count": len(skipped_reports) * 0 + int(batch_report.get("ok_count") or 0),
                    "fail_count": len(skipped_reports) + int(batch_report.get("fail_count") or 0),
                    "partial": batch_report.get("partial"),
                }
            elif skipped_reports:
                vision_report = {
                    "images": skipped_reports,
                    "ok_count": 0,
                    "fail_count": len(skipped_reports),
                    "partial": False,
                }
            ip["vision_report"] = {
                "ok_count": vision_report.get("ok_count"),
                "fail_count": vision_report.get("fail_count"),
                "partial": vision_report.get("partial"),
            }

    ip["results"] = build_image_parse_results(
        images,
        ocr_by_index=ocr_by_index,
        vision_by_index=vision_by_index,
        vision_report=vision_report if run_vision else None,
        ocr_items=items,
        run_ocr=run_ocr,
        run_vision=run_vision_effective,
        job_running=False,
    )

    if cancelled:
        ip["status"] = IMAGE_PARSE_STATUS_CANCELLED
    else:
        fail_n = len(images) - len(build_image_text_map(ocr_by_index=ocr_by_index, vision_by_index=vision_by_index))
        if fail_n > 0 and len(images) > 0:
            ip["status"] = IMAGE_PARSE_STATUS_PARTIAL
        else:
            ip["status"] = IMAGE_PARSE_STATUS_READY if images else IMAGE_PARSE_STATUS_SKIPPED
    ip["completed"] = len(images)
    ip["current_phase"] = None
    ip["current_index"] = None
    ip["cancel_requested"] = False
    meta["image_parse"] = ip
    meta["loader"] = {"image_count": len(images)}
    image_text = build_image_text_map(ocr_by_index=ocr_by_index, vision_by_index=vision_by_index)
    sections_json = rebuild_sections_with_image_text(
        sections_json,
        image_text,
        blocks=blocks,
        raw_sections=raw_sections,
    )
    sections_json["_meta"] = compact_loader_meta(meta)
    doc.sections_json = sections_json
    doc.char_count = int(sections_json.get("char_count") or 0)
    doc.chunk_count = max(len(sections_json.get("sections") or []), 1)
    await doc.save()

    if cancelled:
        return

    try:
        from app.modules.knowledge.knowledge_digest_cache import schedule_document_postprocess

        schedule_document_postprocess(doc_id, project_id, settings=settings)
    except Exception:
        logger.debug("[knowledge_image_parse] postprocess schedule skipped doc=%s", doc_id, exc_info=True)


async def request_stop_image_parse(doc_id: int, project_id: int) -> dict[str, Any]:
    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    sections_json = doc.sections_json if isinstance(doc.sections_json, dict) else {}
    meta = dict(sections_json.get("_meta") or {})
    ip = dict(meta.get("image_parse") or {})
    if ip.get("status") != IMAGE_PARSE_STATUS_PARSING:
        raise HTTPException(status_code=400, detail="当前没有进行中的识图任务")
    ip["cancel_requested"] = True
    meta["image_parse"] = ip
    sections_json["_meta"] = meta
    doc.sections_json = sections_json
    await doc.save()
    return {"doc_id": doc_id, "cancel_requested": True}


async def reparse_document_image_background(
    doc_id: int,
    project_id: int,
    image_index: int,
    *,
    username: str = "",
    scope: str = "auto",
) -> None:
    """单张图片重新识图：scope=auto|ocr|vision|all"""
    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc or not doc.storage:
        return
    username = (username or "").strip() or (getattr(doc, "created_by", None) or "").strip()
    settings = await load_knowledge_project_settings(project_id)
    mode = normalize_image_parse_mode(settings.get("knowledge_image_parse_mode"))
    sections_json = doc.sections_json if isinstance(doc.sections_json, dict) else {}

    try:
        content = load_document_source(doc.storage or {}, doc.file_name)
        loaded = load_document(content, doc.file_name or "")
    except Exception as ex:
        logger.exception("[knowledge_image_parse] single reparse reload doc=%s failed", doc_id)
        return

    target = next((img for img in (loaded.images or []) if img.index == image_index), None)
    if target is None:
        return

    img = {"index": target.index, "mime": target.mime, "data": target.data, "page": target.page}
    loader = (sections_json.get("_meta") or {}).get("loader") or {}
    blocks = loader.get("blocks") or loaded.blocks or []
    raw_sections = loader.get("sections") or _strip_section_buffers(loaded.sections or [])

    if scope == "vision":
        run_ocr, run_vision = False, mode in (IMAGE_PARSE_VISION, IMAGE_PARSE_OCR_THEN_VISION)
        vision_config = await _resolve_vision_config(settings) if run_vision else None
        run_vision = bool(vision_config)
    elif scope == "ocr":
        run_ocr = mode in (IMAGE_PARSE_OCR, IMAGE_PARSE_OCR_THEN_VISION)
        run_vision, vision_config = False, None
    else:
        run_ocr, run_vision, vision_config = await _resolve_run_ocr_and_vision(mode, settings)

    meta = dict(sections_json.get("_meta") or {})
    ip = dict(meta.get("image_parse") or {})
    existing_results = list(ip.get("results") or [])

    ocr_by_index: dict[int, str] = {}
    vision_by_index: dict[int, str] = {}
    for r in existing_results:
        if not isinstance(r, dict) or r.get("index") is None:
            continue
        idx = r["index"]
        if idx == image_index:
            continue
        if r.get("ocr_ok") and r.get("ocr_preview"):
            ocr_by_index[idx] = r.get("ocr_preview") or ""
        vp = r.get("vision_preview") or ""
        if r.get("vision_ok") and vp:
            vision_by_index[idx] = vp
        elif vp and not str(vp).startswith("（读图失败"):
            vision_by_index[idx] = vp

    ocr_items = [dict(x) for x in (ip.get("items") or []) if isinstance(x, dict)]
    ocr_item_by_idx = {x.get("index"): x for x in ocr_items if x.get("index") is not None}
    vision_report: dict[str, Any] = {"images": list((ip.get("vision_report") or {}).get("images") or [])}

    ip["single_reparse_index"] = image_index
    ip["status"] = IMAGE_PARSE_STATUS_PARSING
    meta["image_parse"] = ip
    sections_json["_meta"] = meta
    doc.sections_json = sections_json
    await doc.save()

    idx = image_index
    item = dict(ocr_item_by_idx.get(idx) or {"index": idx, "page": img.get("page")})
    data = img.get("data") or b""

    if run_ocr:
        if image_too_small_for_recognition(data):
            w, h = _image_dimensions(data)
            ocr_by_index.pop(idx, None)
            item.update(
                {
                    "ocr_ok": False,
                    "ocr_skipped": True,
                    "ocr_status": "skipped",
                    "ocr_error": f"图片尺寸过小（{w}×{h}），已跳过 OCR",
                    "ocr_preview": "",
                }
            )
        else:
            text, err = await ocr_image(data, concurrency=max(1, int(settings.get("knowledge_image_ocr_concurrency") or 1)))
            if text:
                ocr_by_index[idx] = text
                item.update({"ocr_ok": True, "ocr_status": "success", "ocr_preview": text[:200], "ocr_error": None})
            else:
                ocr_by_index.pop(idx, None)
                item.update(
                    {
                        "ocr_ok": False,
                        "ocr_status": "failed",
                        "ocr_error": (err or "OCR 无有效结果")[:200],
                        "ocr_preview": "",
                    }
                )
        ocr_item_by_idx[idx] = item
        ocr_items = list(ocr_item_by_idx.values())

    if run_vision:
        vision_config = await _resolve_vision_config(settings)
        if vision_config is None:
            item["vision_error"] = "未配置 Vision 模型"
        elif image_too_small_for_recognition(data):
            w, h = _image_dimensions(data)
            vision_by_index.pop(idx, None)
            vitem = {
                "index": idx,
                "ok": False,
                "skipped": True,
                "error": f"图片尺寸过小（{w}×{h}），已跳过 Vision",
            }
            vision_report["images"] = [v for v in vision_report.get("images") or [] if v.get("index") != idx] + [vitem]
        else:
            from app.modules.knowledge.knowledge_image_vision import analyze_one_image_with_vision
            from app.core.llm.llm_client import LLMClientFactory
            from app.core.platform.encryption import decrypt_value
            from app.modules.ai.ai_prompts import PromptManager

            api_key = decrypt_value(vision_config.api_key)
            client = LLMClientFactory.create(
                provider=vision_config.provider,
                api_key=api_key,
                api_base=vision_config.api_base,
                model=vision_config.model,
                timeout=max(int(vision_config.timeout or 60), 120),
            )
            system_prompt, user_template_base = await PromptManager.render(
                "requirement_doc_understand",
                {"doc_text_excerpt": "（见下方章节上下文）"},
            )
            vision_text, vitem, _tokens = await analyze_one_image_with_vision(
                client,
                vision_config,
                img,
                blocks,
                raw_sections,
                system_prompt=system_prompt,
                user_template_base=user_template_base,
                project_id=project_id,
                username=username,
                document_id=doc_id,
                ocr_text_by_index=ocr_by_index,
            )
            vision_by_index[idx] = vision_text
            vision_report["images"] = [v for v in vision_report.get("images") or [] if v.get("index") != idx] + [vitem]

    images_all = [
        {"index": i.index, "mime": i.mime, "data": i.data, "page": i.page} for i in (loaded.images or [])
    ]
    new_rows = build_image_parse_results(
        [img],
        ocr_by_index=ocr_by_index,
        vision_by_index=vision_by_index,
        vision_report=vision_report if run_vision else None,
        ocr_items=[item],
        run_ocr=run_ocr or bool(ocr_by_index.get(image_index)),
        run_vision=run_vision,
        job_running=False,
    )
    by_idx = {r.get("index"): r for r in existing_results if isinstance(r, dict)}
    if new_rows:
        by_idx[image_index] = new_rows[0]
    ip["results"] = [by_idx.get(i["index"]) for i in images_all if by_idx.get(i["index"]) is not None]
    ip.pop("single_reparse_index", None)
    ip["ocr_ok"] = sum(1 for r in ip["results"] if r.get("ocr_ok"))
    ip["vision_ok"] = sum(1 for r in ip["results"] if r.get("vision_ok"))
    if ip.get("status") == IMAGE_PARSE_STATUS_PARSING:
        ip["status"] = (
            IMAGE_PARSE_STATUS_PARTIAL
            if any(not r.get("has_result") for r in ip["results"])
            else IMAGE_PARSE_STATUS_READY
        )
    meta["image_parse"] = ip
    sections_json["_meta"] = meta
    image_text = build_image_text_map(ocr_by_index=ocr_by_index, vision_by_index=vision_by_index)
    sections_json = rebuild_sections_with_image_text(sections_json, image_text)
    doc.sections_json = sections_json
    doc.char_count = int(sections_json.get("char_count") or 0)
    doc.chunk_count = max(len(sections_json.get("sections") or []), 1)
    await doc.save()

    try:
        from app.modules.knowledge.knowledge_digest_cache import schedule_document_postprocess

        schedule_document_postprocess(doc_id, project_id, settings=settings)
    except Exception:
        logger.debug("[knowledge_image_parse] single reparse postprocess skipped doc=%s", doc_id, exc_info=True)


def schedule_reparse_document_image(
    doc_id: int,
    project_id: int,
    image_index: int,
    *,
    username: str = "",
    scope: str = "auto",
) -> None:
    import asyncio

    asyncio.create_task(
        reparse_document_image_background(
            doc_id,
            project_id,
            image_index,
            username=username,
            scope=scope,
        )
    )
