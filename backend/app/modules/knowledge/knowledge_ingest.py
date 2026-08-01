"""资料库文档解析（sections_json v2 全量入库）"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.modules.knowledge.constants import (
    PARSE_STATUS_FAILED,
    PARSE_STATUS_READY,
    SECTIONS_JSON_VERSION_V2,
)
from app.modules.knowledge.knowledge_ingest_prose import parse_prose_v2
from app.modules.knowledge.knowledge_ingest_tabular import parse_tabular_v2
from app.modules.knowledge.knowledge_structured_profiles import (
    build_tabular_structured,
    detect_tabular_profile,
)

logger = logging.getLogger(__name__)


def _build_v2_sections_json(
    *,
    fmt: str,
    char_count: int,
    parse_warnings: list[str],
    body: dict[str, Any],
    structured: Optional[dict[str, Any]] = None,
    fulltext: Optional[str] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": SECTIONS_JSON_VERSION_V2,
        "format": fmt,
        "char_count": char_count,
        "parse_warnings": parse_warnings,
    }
    payload.update(body)
    if fulltext is not None:
        payload["fulltext"] = fulltext
    if structured is not None:
        payload["structured"] = structured
    return payload


def parse_document_content(
    content: bytes,
    file_name: str,
    *,
    doc_type: Optional[str] = None,
) -> dict[str, Any]:
    """解析上传文件，返回 char_count / sections_json v2 / chunk_count / parse_error。"""
    ext = (file_name or "").rsplit(".", 1)[-1].lower() if "." in (file_name or "") else ""
    try:
        if ext in ("xlsx", "xls", "csv"):
            tabular = parse_tabular_v2(content, file_name, ext)
            parse_warnings = list(tabular.get("parse_warnings") or [])
            profile = detect_tabular_profile(file_name, doc_type)
            structured = build_tabular_structured(profile, content, file_name)
            sections_json = _build_v2_sections_json(
                fmt=tabular["format"],
                char_count=int(tabular.get("char_count") or 0),
                parse_warnings=parse_warnings,
                body={"sheets": tabular["sheets"]},
                structured=structured,
            )
            data = {
                "char_count": tabular.get("char_count") or 0,
                "sections_json": sections_json,
                "chunk_count": tabular.get("chunk_count") or 0,
            }
        elif ext in ("docx", "pdf", "md", "txt", "doc", "ppt", "pptx"):
            if ext == "doc":
                try:
                    prose = parse_prose_v2(content, file_name, ext)
                except Exception as doc_ex:
                    logger.warning("[knowledge_ingest] .doc pymupdf failed: %s", doc_ex)
                    raise ValueError(
                        "无法解析旧版 .doc，请在 Word 中「另存为 .docx」后重新上传"
                    ) from doc_ex
            elif ext == "ppt":
                try:
                    prose = parse_prose_v2(content, file_name, ext)
                except Exception as ppt_ex:
                    logger.warning("[knowledge_ingest] .ppt pymupdf failed: %s", ppt_ex)
                    raise ValueError(
                        "无法解析旧版 .ppt，请在 PowerPoint 中「另存为 .pptx」后重新上传"
                    ) from ppt_ex
            else:
                prose = parse_prose_v2(content, file_name, ext)

            parse_warnings = list(prose.get("parse_warnings") or [])
            loader_meta = prose.pop("loader_meta", None)
            structured = prose.pop("structured", {"kind": "prose", "outline": []})
            sections_json = _build_v2_sections_json(
                fmt=prose["format"],
                char_count=int(prose.get("char_count") or 0),
                parse_warnings=parse_warnings,
                body={
                    k: prose[k]
                    for k in ("sections", "page_count")
                    if k in prose
                },
                structured=structured,
                fulltext=prose.get("fulltext") or "",
            )
            if loader_meta:
                sections_json["_meta"] = {
                    "loader": {
                        "image_count": int(loader_meta.get("image_count") or 0),
                    }
                }
            data = {
                "char_count": prose.get("char_count") or 0,
                "sections_json": sections_json,
                "chunk_count": prose.get("chunk_count") or 0,
            }
        else:
            data = {
                "char_count": len(content),
                "sections_json": {
                    "version": SECTIONS_JSON_VERSION_V2,
                    "format": ext or "bin",
                    "parse_warnings": [],
                },
                "chunk_count": 0,
            }
        return {**data, "parse_status": PARSE_STATUS_READY, "parse_error": None}
    except Exception as ex:
        logger.warning("[knowledge_ingest] parse failed file=%s err=%s", file_name, ex)
        return {
            "char_count": 0,
            "sections_json": None,
            "chunk_count": 0,
            "parse_status": PARSE_STATUS_FAILED,
            "parse_error": str(ex)[:500],
        }
