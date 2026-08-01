"""资料库 CRUD 与序列化"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from typing import Any, Optional

from fastapi import HTTPException

from app.core.platform.config import KNOWLEDGE_MAX_FILE_MB
from app.models.knowledge import AiKnowledgeDocument, AiKnowledgeFolder
from app.modules.knowledge.constants import (
    ALLOWED_UPLOAD_EXTENSIONS,
    DOC_TYPES,
    PARSE_STATUS_FAILED,
    PARSE_STATUS_PARSING,
    PARSE_STATUS_PENDING,
    PARSE_STATUS_READY,
    TEMPLATE_DOC_TYPES,
)
from app.modules.knowledge.knowledge_ingest import parse_document_content
from app.modules.knowledge.knowledge_storage import load_document_source, save_document_source

logger = logging.getLogger(__name__)


def validate_doc_type(doc_type: str) -> str:
    if doc_type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的文档类型: {doc_type}")
    return doc_type


def validate_upload_file(file_name: str, content: bytes) -> None:
    ext = os.path.splitext(file_name or "")[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式 {ext}，允许: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}",
        )
    max_bytes = KNOWLEDGE_MAX_FILE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail=f"文件超过 {KNOWLEDGE_MAX_FILE_MB}MB 限制")


def folder_to_dict(folder: AiKnowledgeFolder, doc_count: int = 0) -> dict[str, Any]:
    return {
        "id": folder.id,
        "project_id": folder.project_id,
        "name": folder.name,
        "description": folder.description,
        "iteration_label": folder.iteration_label,
        "date_start": folder.date_start.isoformat() if folder.date_start else None,
        "date_end": folder.date_end.isoformat() if folder.date_end else None,
        "sort": folder.sort,
        "doc_count": doc_count,
        "created_by": folder.created_by,
        "create_time": folder.create_time.isoformat() if folder.create_time else None,
        "update_time": folder.update_time.isoformat() if folder.update_time else None,
    }


def _digest_summary(doc: AiKnowledgeDocument) -> dict[str, Any]:
    from app.modules.knowledge.knowledge_digest_cache import get_digest_cache

    cache = get_digest_cache(doc.sections_json)
    text = (cache.get("text") or "").strip() if cache else ""
    status = getattr(doc, "digest_status", None) or "none"
    digest_error = getattr(doc, "digest_error", None)

    if status == "indexing":
        return {
            "digest_status": "indexing",
            "digest_char_count": int(cache.get("digest_char_count") or len(text)) if text else 0,
            "digest_updated_at": cache.get("updated_at") if cache else None,
            "digest_error": None,
        }
    if status == "failed":
        return {
            "digest_status": "failed",
            "digest_char_count": 0,
            "digest_updated_at": None,
            "digest_error": digest_error,
        }
    if text:
        return {
            "digest_status": "ready",
            "digest_char_count": int(cache.get("digest_char_count") or len(text)),
            "digest_updated_at": cache.get("updated_at"),
            "digest_error": None,
        }
    return {
        "digest_status": "none",
        "digest_char_count": 0,
        "digest_updated_at": None,
        "digest_error": digest_error,
    }


def _vector_fields(doc: AiKnowledgeDocument) -> dict[str, Any]:
    from app.modules.knowledge.knowledge_embed_config import normalize_document_embed_mode

    return {
        "embed_mode": normalize_document_embed_mode(getattr(doc, "embed_mode", None)),
        "lexical_index_status": doc.embed_status,
        "vector_status": getattr(doc, "vector_status", None) or "none",
        "vector_model": getattr(doc, "vector_model", None),
        "vector_error": getattr(doc, "vector_error", None),
    }


def document_to_dict(doc: AiKnowledgeDocument) -> dict[str, Any]:
    from app.modules.knowledge.knowledge_sections_read import get_structured_meta

    sections_meta = get_structured_meta(doc.sections_json)
    return {
        "id": doc.id,
        "project_id": doc.project_id,
        "folder_id": doc.folder_id,
        "title": doc.title,
        "doc_type": doc.doc_type,
        "doc_type_label": DOC_TYPES.get(doc.doc_type, doc.doc_type),
        "file_name": doc.file_name,
        "parse_status": doc.parse_status,
        "parse_error": doc.parse_error,
        "char_count": doc.char_count,
        "chunk_count": doc.chunk_count,
        "source_requirement_id": doc.source_requirement_id,
        "embed_status": doc.embed_status,
        "is_default_template": doc.is_default_template,
        "template_schema": doc.template_schema,
        "created_by": doc.created_by,
        "create_time": doc.create_time.isoformat() if doc.create_time else None,
        "update_time": doc.update_time.isoformat() if doc.update_time else None,
        **sections_meta,
        **_digest_summary(doc),
        **_vector_fields(doc),
    }


async def get_folder_or_404(folder_id: int, project_id: int) -> AiKnowledgeFolder:
    folder = await AiKnowledgeFolder.get_or_none(id=folder_id, project_id=project_id, is_del=False)
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    return folder


async def list_folders(project_id: int) -> list[dict[str, Any]]:
    folders = await AiKnowledgeFolder.filter(project_id=project_id, is_del=False).order_by("sort", "-id")
    result = []
    for f in folders:
        cnt = await AiKnowledgeDocument.filter(folder_id=f.id, is_del=False).count()
        result.append(folder_to_dict(f, cnt))
    return result


async def create_folder(
    project_id: int,
    name: str,
    username: str,
    *,
    description: Optional[str] = None,
    iteration_label: Optional[str] = None,
    date_start: Optional[date] = None,
    date_end: Optional[date] = None,
    sort: int = 0,
) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="文件夹名称不能为空")
    folder = await AiKnowledgeFolder.create(
        project_id=project_id,
        name=name,
        description=description,
        iteration_label=iteration_label,
        date_start=date_start,
        date_end=date_end,
        sort=sort,
        created_by=username,
    )
    return folder_to_dict(folder, 0)


async def update_folder(
    folder_id: int,
    project_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    folder = await get_folder_or_404(folder_id, project_id)
    for key in ("name", "description", "iteration_label", "sort"):
        if key in payload and payload[key] is not None:
            setattr(folder, key, payload[key])
    for key in ("date_start", "date_end"):
        if key in payload:
            setattr(folder, key, payload[key])
    await folder.save()
    cnt = await AiKnowledgeDocument.filter(folder_id=folder.id, is_del=False).count()
    return folder_to_dict(folder, cnt)


async def delete_folder(folder_id: int, project_id: int) -> None:
    from app.core.platform.platform_settings_service import (
        DELETE_MODE_PHYSICAL,
        delete_knowledge_document_record,
        get_knowledge_report_delete_mode,
    )

    folder = await get_folder_or_404(folder_id, project_id)
    mode = await get_knowledge_report_delete_mode()
    physical = mode == DELETE_MODE_PHYSICAL
    docs = await AiKnowledgeDocument.filter(
        folder_id=folder_id,
        project_id=project_id,
        is_del=False,
    ).all()
    for doc in docs:
        await delete_knowledge_document_record(doc, permanent=physical)
    if physical:
        await folder.delete()
        return
    folder.is_del = True
    await folder.save()


async def list_documents(
    project_id: int,
    *,
    folder_id: Optional[int] = None,
    doc_type: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    qs = AiKnowledgeDocument.filter(project_id=project_id, is_del=False)
    if folder_id is not None:
        qs = qs.filter(folder_id=folder_id)
    if doc_type:
        qs = qs.filter(doc_type=doc_type)
    if keyword:
        kw = keyword.strip()
        if kw:
            qs = qs.filter(title__icontains=kw)
    from app.core.platform.platform_settings_service import get_knowledge_report_delete_mode

    total = await qs.count()
    items = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [document_to_dict(d) for d in items],
        "delete_mode": await get_knowledge_report_delete_mode(),
    }


async def _schedule_document_postprocess(doc_id: int, project_id: int) -> None:
    try:
        from app.modules.knowledge.knowledge_digest_cache import schedule_document_postprocess
        from app.modules.knowledge.knowledge_project_settings import load_knowledge_project_settings

        ksettings = await load_knowledge_project_settings(project_id)
        schedule_document_postprocess(doc_id, project_id, settings=ksettings)
    except Exception:
        logger.debug("document postprocess schedule skipped doc_id=%s", doc_id, exc_info=True)


async def _parse_document_background(
    doc_id: int,
    project_id: int,
    *,
    image_mode_override: Optional[str] = None,
    username: str = "",
) -> None:
    from app.modules.knowledge.knowledge_image_parse import (
        attach_image_parse_meta,
        parse_document_images_background,
        resolve_effective_image_mode,
        should_schedule_image_parse,
    )
    from app.modules.knowledge.knowledge_project_settings import load_knowledge_project_settings

    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc:
        return
    try:
        content = load_document_source(doc.storage or {}, doc.file_name)
        parsed = parse_document_content(content, doc.file_name, doc_type=doc.doc_type)
        sections_json = parsed.get("sections_json")
        ksettings = await load_knowledge_project_settings(project_id)
        image_mode = resolve_effective_image_mode(ksettings, reparse_override=image_mode_override)
        if isinstance(sections_json, dict):
            loader_meta = None
            meta = sections_json.get("_meta")
            if isinstance(meta, dict) and isinstance(meta.get("loader"), dict):
                loader_meta = meta["loader"]
            sections_json = attach_image_parse_meta(sections_json, loader_meta, mode=image_mode)
            parsed["sections_json"] = sections_json

        doc.parse_status = parsed["parse_status"]
        doc.parse_error = parsed.get("parse_error")
        doc.char_count = parsed.get("char_count") or 0
        doc.chunk_count = parsed.get("chunk_count") or 0
        doc.sections_json = parsed.get("sections_json")
        await doc.save()
        await _schedule_document_postprocess(doc.id, project_id)
        if should_schedule_image_parse(doc.sections_json, image_mode):
            asyncio.create_task(
                parse_document_images_background(
                    doc.id,
                    project_id,
                    reparse_override=image_mode_override,
                    username=username,
                )
            )
    except Exception as ex:
        logger.exception("background parse failed doc_id=%s", doc_id)
        doc.parse_status = PARSE_STATUS_FAILED
        doc.parse_error = str(ex)[:500]
        await doc.save()


async def upload_document(
    project_id: int,
    file_name: str,
    content: bytes,
    doc_type: str,
    username: str,
    *,
    folder_id: Optional[int] = None,
    title: Optional[str] = None,
) -> dict[str, Any]:
    validate_doc_type(doc_type)
    validate_upload_file(file_name, content)
    if folder_id is not None:
        await get_folder_or_404(folder_id, project_id)

    display_title = (title or os.path.splitext(file_name)[0] or "未命名").strip()[:200]

    doc = await AiKnowledgeDocument.create(
        project_id=project_id,
        folder_id=folder_id,
        title=display_title,
        doc_type=doc_type,
        file_name=file_name,
        storage={},
        parse_status=PARSE_STATUS_PENDING,
        created_by=username,
    )

    try:
        storage_meta = save_document_source(project_id, doc.id, file_name, content)
        doc.storage = storage_meta
        doc.parse_status = PARSE_STATUS_PARSING
        await doc.save()
    except Exception as ex:
        doc.parse_status = PARSE_STATUS_FAILED
        doc.parse_error = str(ex)[:500]
        await doc.save()
        raise HTTPException(status_code=500, detail=f"文件保存失败: {ex}") from ex

    asyncio.create_task(_parse_document_background(doc.id, project_id))

    if doc_type in TEMPLATE_DOC_TYPES and doc.is_default_template:
        await AiKnowledgeDocument.filter(
            project_id=project_id,
            doc_type=doc_type,
            is_del=False,
        ).exclude(id=doc.id).update(is_default_template=False)

    result = document_to_dict(doc)
    ext = os.path.splitext(file_name or "")[1].lower()
    if doc_type == "report_template" and ext == ".doc":
        result["template_warning"] = "已保存，但生成 Word 报告须使用 .docx 模板，请将 .doc 在 Word 中另存为 .docx 后重新上传"
    elif doc_type in TEMPLATE_DOC_TYPES and ext == ".doc":
        result["template_warning"] = "已保存；若用于文档生成，建议另存为 .docx"

    return result


async def get_document_detail(doc_id: int, project_id: int) -> dict[str, Any]:
    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return document_to_dict(doc)


async def update_document_embed_mode(doc_id: int, project_id: int, embed_mode: str) -> dict[str, Any]:
    from app.modules.knowledge.knowledge_embed_config import DOCUMENT_EMBED_MODES, normalize_document_embed_mode

    raw = str(embed_mode or "").strip().lower()
    if raw not in DOCUMENT_EMBED_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"无效的 embed_mode，可选: {', '.join(DOCUMENT_EMBED_MODES.keys())}",
        )

    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    mode = normalize_document_embed_mode(raw)
    doc.embed_mode = mode
    if mode in ("lexical_only", "none"):
        doc.vector_status = "none"
        doc.vector_error = None
        doc.vector_model = None
    elif mode == "vector":
        doc.vector_status = "none"
        doc.vector_error = None
        doc.vector_model = None
    await doc.save()
    return document_to_dict(doc)


async def list_document_chunks(
    doc_id: int,
    project_id: int,
    *,
    page: int = 1,
    size: int = 50,
    preview_chars: int = 600,
) -> dict[str, Any]:
    from app.models.knowledge import AiKnowledgeChunk
    from app.modules.knowledge.knowledge_embed import chunk_has_vector, get_chunk_vector

    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    page = max(page, 1)
    size = min(max(size, 1), 100)
    preview_chars = min(max(preview_chars, 120), 2000)
    qs = AiKnowledgeChunk.filter(document_id=doc_id, project_id=project_id)
    total = await qs.count()
    rows = await qs.order_by("chunk_index").offset((page - 1) * size).limit(size)

    items = []
    for row in rows:
        text = row.chunk_text or ""
        vec = get_chunk_vector(row)
        items.append(
            {
                "id": row.id,
                "chunk_index": row.chunk_index,
                "section_title": row.section_title,
                "char_count": row.char_count or len(text),
                "text_preview": text[:preview_chars] + ("…" if len(text) > preview_chars else ""),
                "text": text,
                "has_vector": chunk_has_vector(row),
                "vector_dim": len(vec) if vec else 0,
                "create_time": row.create_time.isoformat() if row.create_time else None,
            }
        )

    return {
        "document_id": doc_id,
        "document_title": doc.title,
        "embed_status": doc.embed_status,
        "lexical_index_status": doc.embed_status,
        "chunk_count": doc.chunk_count or total,
        "total": total,
        "page": page,
        "size": size,
        "items": items,
        **_vector_fields(doc),
    }


async def get_document_preview(doc_id: int, project_id: int, *, max_chars: int = 48000) -> dict[str, Any]:
    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    sections_json = doc.sections_json
    if not sections_json and doc.storage:
        try:
            raw = load_document_source(doc.storage, doc.file_name)
            parsed = parse_document_content(raw, doc.file_name, doc_type=doc.doc_type)
            sections_json = parsed.get("sections_json")
        except Exception:
            sections_json = None

    structured = _build_structured_preview(sections_json, max_chars=max_chars)
    from app.modules.knowledge.knowledge_digest_cache import get_digest_cache
    from app.modules.knowledge.knowledge_image_parse import get_image_parse_details
    from app.modules.knowledge.knowledge_sections_read import get_structured_meta

    digest_cache = get_digest_cache(sections_json) or {}
    digest_text = (digest_cache.get("text") or "").strip()
    digest_summary = _digest_summary(doc)
    return {
        "id": doc.id,
        "title": doc.title,
        "file_name": doc.file_name,
        "doc_type": doc.doc_type,
        "doc_type_label": DOC_TYPES.get(doc.doc_type, doc.doc_type),
        "parse_status": doc.parse_status,
        "parse_error": doc.parse_error,
        "char_count": doc.char_count,
        "embed_status": doc.embed_status,
        "lexical_index_status": doc.embed_status,
        "has_digest": bool(digest_text) or digest_summary.get("digest_status") == "indexing",
        "digest_text": digest_text,
        "digest_char_count": int(digest_cache.get("digest_char_count") or len(digest_text)),
        "digest_updated_at": digest_cache.get("updated_at"),
        **digest_summary,
        **_vector_fields(doc),
        **get_structured_meta(sections_json),
        "image_parse_details": get_image_parse_details(sections_json),
        **structured,
    }


def _build_structured_preview(sections_json: Any, *, max_chars: int = 48000) -> dict[str, Any]:
    from app.modules.knowledge.knowledge_sections_read import (
        iter_tabular_sheets,
        sections_to_text,
        sheet_display_rows,
    )

    empty = {
        "preview_format": "plain",
        "preview_text": "",
        "preview_sections": [],
        "preview_sheets": [],
        "preview_truncated": False,
    }
    if not isinstance(sections_json, dict):
        return empty

    tabular_sheets = iter_tabular_sheets(sections_json)
    if tabular_sheets:
        sheets_out: list[dict[str, Any]] = []
        for sh in tabular_sheets[:8]:
            rows, total_rows = sheet_display_rows(sh, max_rows=30)
            if rows:
                sheets_out.append(
                    {
                        "name": sh.get("name") or "Sheet",
                        "rows": rows,
                        "total_rows": total_rows,
                        "stored_row_count": int(sh.get("stored_row_count") or len(sh.get("rows") or [])),
                        "rows_truncated": bool(sh.get("rows_truncated")),
                    }
                )
        text = sections_to_text(sections_json, max_rows_per_sheet=30, max_sheets=8)
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars] + "\n…（预览已截断）"
        return {
            "preview_format": "sheets",
            "preview_text": text,
            "preview_sections": [],
            "preview_sheets": sheets_out,
            "preview_truncated": truncated,
        }

    sections_out: list[dict[str, str]] = []
    for sec in (sections_json.get("sections") or [])[:80]:
        if not isinstance(sec, dict):
            continue
        title = (sec.get("title") or "").strip()
        body = (sec.get("content") or sec.get("text") or "").strip()
        if title or body:
            sections_out.append({"title": title, "body": body})

    text = sections_to_text(sections_json, max_sections=80)
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars] + "\n…（预览已截断）"
    return {
        "preview_format": "sections" if sections_out else "plain",
        "preview_text": text,
        "preview_sections": sections_out,
        "preview_sheets": [],
        "preview_truncated": truncated,
    }


async def get_document_download_bytes(doc_id: int, project_id: int) -> tuple[bytes, str]:
    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not doc.storage:
        raise HTTPException(status_code=404, detail="源文件不存在")
    content = load_document_source(doc.storage, doc.file_name)
    file_name = doc.file_name or f"document_{doc_id}"
    return content, file_name


async def get_document_image_thumbnails(
    doc_id: int,
    project_id: int,
    *,
    max_edge: int = 320,
) -> dict[str, Any]:
    """从源文件提取嵌入图片并返回缩略图 data URL，供识图明细页展示。"""
    import base64

    from app.modules.ai.document_loader import load_document, make_image_thumbnail

    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not doc.storage:
        raise HTTPException(status_code=404, detail="源文件不存在")
    try:
        content = load_document_source(doc.storage, doc.file_name)
        loaded = load_document(content, doc.file_name or "")
    except Exception as ex:
        raise HTTPException(status_code=400, detail=f"读取文档图片失败: {ex}") from ex

    items: list[dict[str, Any]] = []
    for img in loaded.images or []:
        thumb_bytes, thumb_mime = make_image_thumbnail(img.data, img.mime or "image/jpeg", max_edge=max_edge)
        items.append(
            {
                "index": img.index,
                "display_index": int(img.index) + 1,
                "page": img.page,
                "mime": thumb_mime,
                "data_url": f"data:{thumb_mime};base64,{base64.b64encode(thumb_bytes).decode()}",
            }
        )
    return {"items": items, "total": len(items)}


async def delete_document(doc_id: int, project_id: int) -> str:
    from app.core.platform.platform_settings_service import delete_knowledge_document_record

    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return await delete_knowledge_document_record(doc)


async def reparse_document(
    doc_id: int,
    project_id: int,
    *,
    image_mode: Optional[str] = None,
    username: str = "",
) -> dict[str, Any]:
    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not doc.storage:
        raise HTTPException(status_code=400, detail="源文件不存在，无法重新解析")
    doc.parse_status = PARSE_STATUS_PARSING
    doc.parse_error = None
    await doc.save()
    asyncio.create_task(
        _parse_document_background(
            doc.id,
            project_id,
            image_mode_override=image_mode,
            username=username,
        )
    )
    return document_to_dict(doc)


def _apply_parse_result_to_document(doc: AiKnowledgeDocument, parsed: dict[str, Any]) -> None:
    doc.parse_status = parsed.get("parse_status") or PARSE_STATUS_READY
    doc.parse_error = parsed.get("parse_error")
    doc.char_count = int(parsed.get("char_count") or 0)
    doc.chunk_count = int(parsed.get("chunk_count") or 0)
    doc.sections_json = parsed.get("sections_json")


async def reparse_documents_batch(
    project_id: int,
    *,
    folder_id: Optional[int] = None,
    document_ids: Optional[list[int]] = None,
    image_mode: Optional[str] = None,
    username: str = "",
) -> dict[str, Any]:
    """批量重新解析为 sections_json v2（folder_id 与 document_ids 可组合过滤）。"""
    if folder_id is None and not document_ids:
        raise HTTPException(status_code=400, detail="请指定 folder_id 或 document_ids")

    if folder_id is not None:
        await get_folder_or_404(folder_id, project_id)

    qs = AiKnowledgeDocument.filter(project_id=project_id, is_del=False)
    if folder_id is not None:
        qs = qs.filter(folder_id=folder_id)
    if document_ids:
        qs = qs.filter(id__in=document_ids)

    docs = await qs.order_by("id").all()
    scheduled: list[int] = []
    skipped: list[dict[str, Any]] = []

    for doc in docs:
        if not doc.storage:
            skipped.append({"id": doc.id, "title": doc.title, "reason": "源文件不存在"})
            continue
        doc.parse_status = PARSE_STATUS_PARSING
        doc.parse_error = None
        await doc.save()
        asyncio.create_task(
            _parse_document_background(
                doc.id,
                project_id,
                image_mode_override=image_mode,
                username=username,
            )
        )
        scheduled.append(doc.id)

    return {
        "project_id": project_id,
        "folder_id": folder_id,
        "requested_count": len(docs),
        "scheduled_count": len(scheduled),
        "scheduled_document_ids": scheduled,
        "skipped": skipped,
    }


async def archive_document_from_requirement(
    project_id: int,
    username: str,
    *,
    requirement_id: int,
    folder_id: Optional[int] = None,
    doc_type: str = "requirement",
    title: Optional[str] = None,
    replace_if_exists: bool = False,
) -> dict[str, Any]:
    """将需求文档归档到资料库（复用已解析结构，避免重复解析）。"""
    from app.models.ai import AiRequirement
    from app.modules.ai.requirement_storage import load_requirement_source

    validate_doc_type(doc_type)
    req = await AiRequirement.get_or_none(id=requirement_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    if folder_id is not None:
        await get_folder_or_404(folder_id, project_id)

    existing_qs = AiKnowledgeDocument.filter(
        project_id=project_id,
        source_requirement_id=requirement_id,
        is_del=False,
    )
    if folder_id is not None:
        existing_qs = existing_qs.filter(folder_id=folder_id)
    existing = await existing_qs.first()
    if existing and not replace_if_exists:
        raise HTTPException(status_code=409, detail="该需求已归档到此文件夹，可勾选替换或选择其他文件夹")

    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    display_title = (title or req.name or "需求文档").strip()[:200]
    file_name = meta.get("file_name") or f"{display_title}.md"
    sections = meta.get("sections") or []

    if existing and replace_if_exists:
        doc = existing
        doc.title = display_title
        doc.doc_type = doc_type
        doc.folder_id = folder_id
        doc.file_name = file_name
    else:
        doc = await AiKnowledgeDocument.create(
            project_id=project_id,
            folder_id=folder_id,
            title=display_title,
            doc_type=doc_type,
            file_name=file_name,
            storage={},
            parse_status=PARSE_STATUS_PENDING,
            source_requirement_id=requirement_id,
            created_by=username,
        )

    content_bytes: bytes | None = None
    parsed_file_name = file_name

    if meta.get("storage"):
        try:
            content, src_name = load_requirement_source(meta)
            storage_meta = save_document_source(project_id, doc.id, src_name or file_name, content)
            doc.storage = storage_meta
            doc.file_name = src_name or file_name
            content_bytes = content
            parsed_file_name = src_name or file_name
        except Exception as ex:
            logger.warning("archive copy source failed req=%s: %s", requirement_id, ex)

    if content_bytes is not None:
        parsed = parse_document_content(content_bytes, parsed_file_name, doc_type=doc_type)
    elif (req.original_content or "").strip():
        parsed = parse_document_content(
            req.original_content.encode("utf-8"),
            file_name,
            doc_type=doc_type,
        )
    else:
        from app.modules.knowledge.knowledge_ingest_prose import build_prose_sections_json_v2

        fmt = meta.get("source_type") or req.source_type or "text"
        sections_json = build_prose_sections_json_v2(sections=sections, fmt=fmt)
        parsed = {
            "parse_status": PARSE_STATUS_READY,
            "parse_error": None,
            "char_count": sections_json.get("char_count") or 0,
            "chunk_count": max(len(sections_json.get("sections") or []), 1),
            "sections_json": sections_json,
        }

    _apply_parse_result_to_document(doc, parsed)
    await doc.save()
    await _schedule_document_postprocess(doc.id, project_id)
    result = document_to_dict(doc)
    result["replaced"] = bool(existing and replace_if_exists)
    return result


async def archive_document_from_text(
    project_id: int,
    username: str,
    *,
    title: str,
    content: str,
    folder_id: Optional[int] = None,
    doc_type: str = "summary",
    source_key: Optional[str] = None,
    replace_if_exists: bool = False,
) -> dict[str, Any]:
    """将 Markdown/纯文本归档为资料库文档（如失败分析摘要）。"""
    validate_doc_type(doc_type)
    display_title = (title or "归档文档").strip()[:200]
    body = (content or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="归档内容不能为空")
    if folder_id is not None:
        await get_folder_or_404(folder_id, project_id)

    existing_qs = AiKnowledgeDocument.filter(
        project_id=project_id,
        title=display_title,
        is_del=False,
    )
    if folder_id is not None:
        existing_qs = existing_qs.filter(folder_id=folder_id)
    if source_key:
        existing_qs = existing_qs.filter(file_name=f"__archive__{source_key}.md")
    existing = await existing_qs.first()

    file_name = f"__archive__{source_key}.md" if source_key else f"{display_title}.md"

    if existing and not replace_if_exists:
        raise HTTPException(status_code=409, detail="同来源归档已存在，可勾选替换")

    if existing and replace_if_exists:
        doc = existing
        doc.title = display_title
        doc.doc_type = doc_type
        doc.folder_id = folder_id
        doc.file_name = file_name
    else:
        doc = await AiKnowledgeDocument.create(
            project_id=project_id,
            folder_id=folder_id,
            title=display_title,
            doc_type=doc_type,
            file_name=file_name,
            storage={},
            parse_status=PARSE_STATUS_PENDING,
            created_by=username,
        )

    raw = body.encode("utf-8")
    storage_meta = save_document_source(project_id, doc.id, file_name, raw)
    doc.storage = storage_meta
    parsed = parse_document_content(raw, file_name, doc_type=doc_type)
    _apply_parse_result_to_document(doc, parsed)
    await doc.save()
    await _schedule_document_postprocess(doc.id, project_id)
    result = document_to_dict(doc)
    result["replaced"] = bool(existing and replace_if_exists)
    return result


async def set_default_template(doc_id: int, project_id: int) -> dict[str, Any]:
    doc = await AiKnowledgeDocument.get_or_none(id=doc_id, project_id=project_id, is_del=False)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.doc_type not in TEMPLATE_DOC_TYPES:
        raise HTTPException(status_code=400, detail="仅输出模板类型可设为默认")
    await AiKnowledgeDocument.filter(
        project_id=project_id,
        doc_type=doc.doc_type,
        is_del=False,
    ).update(is_default_template=False)
    doc.is_default_template = True
    await doc.save()
    return document_to_dict(doc)
