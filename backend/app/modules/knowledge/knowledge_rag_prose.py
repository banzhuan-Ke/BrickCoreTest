"""prose 文档章节感知 RAG 分块"""
from __future__ import annotations

from typing import Any

from app.modules.knowledge.knowledge_context_mapreduce import split_text_chunks


def build_prose_chunk_specs(
    sections: list[dict[str, Any]],
    *,
    chunk_chars: int = 1800,
) -> list[dict[str, Any]]:
    """按 section 边界切分；单节超长时在段落处再切。"""
    specs: list[dict[str, Any]] = []
    for sec_idx, sec in enumerate(sections):
        if not isinstance(sec, dict):
            continue
        title = (sec.get("title") or "正文").strip()
        body = (sec.get("content") or sec.get("text") or "").strip()
        if not body and not title:
            continue
        prefix = f"## {title}\n" if title else ""
        full_piece = f"{prefix}{body}".strip()
        page = sec.get("page")
        level = int(sec.get("level") or 1)

        if len(full_piece) <= chunk_chars:
            pieces = [full_piece]
        else:
            inner = split_text_chunks(body, chunk_size=max(chunk_chars - len(prefix) - 2, 400), overlap=200)
            pieces = [f"{prefix}{p}".strip() if p else prefix.strip() for p in inner if p.strip()]

        for part_idx, text in enumerate(pieces):
            if not text:
                continue
            meta: dict[str, Any] = {
                "section_index": sec_idx,
                "section_level": level,
                "section_part": part_idx,
            }
            if page is not None:
                meta["page"] = page
            specs.append(
                {
                    "text": text,
                    "section_title": title[:200],
                    "meta": meta,
                }
            )
    return specs
