"""
从文档字节解析有序块（Word 优先：段落/标题/表格/图片顺序）
"""
from __future__ import annotations

import io
import logging
import os
import re
import zipfile
from typing import Optional
from xml.etree import ElementTree as ET

from app.modules.ai.document_loader import (
    DocumentLoadResult,
    LoadedImage,
    _compress_image,
    _load_pdf,
    _load_text,
)
from app.modules.ai.requirement_document import blocks_to_sections

logger = logging.getLogger(__name__)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

W = f"{{{W_NS}}}"
A = f"{{{A_NS}}}"
R = f"{{{R_NS}}}"


def _parse_docx_style_index(content: bytes) -> dict[str, dict[str, str]]:
    """解析 word/styles.xml，返回 {styleId: {name, basedOn}}。"""
    index: dict[str, dict[str, str]] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            if "word/styles.xml" not in zf.namelist():
                return index
            styles_root = ET.fromstring(zf.read("word/styles.xml"))
    except Exception as e:
        logger.debug("[document_structure] 读取 styles.xml 失败: %s", e)
        return index

    for st in styles_root.findall(f"{W}style"):
        sid = st.get(f"{W}styleId") or st.get("styleId")
        if not sid:
            continue
        name_el = st.find(f"{W}name")
        name = ""
        if name_el is not None:
            name = (name_el.get(f"{W}val") or name_el.get("val") or "").strip()
        based_el = st.find(f"{W}basedOn")
        based_on = ""
        if based_el is not None:
            based_on = (based_el.get(f"{W}val") or based_el.get("val") or "").strip()
        index[sid] = {"name": name, "basedOn": based_on}
    return index


def _resolve_style_name(style_val: str, style_index: dict[str, dict[str, str]]) -> str:
    """将段落 pStyle 的 styleId 解析为样式名（沿 basedOn 向上查找）。"""
    if not style_val:
        return ""
    visited: set[str] = set()
    current = style_val.strip()
    fallback = current
    while current and current not in visited:
        visited.add(current)
        info = style_index.get(current) or {}
        name = (info.get("name") or "").strip()
        if name:
            return name
        current = (info.get("basedOn") or "").strip()
    return fallback


def _heading_level_from_label(label: str) -> int:
    if not label:
        return 0
    s = label.strip()
    m = re.match(r"(?:Heading|heading)\s*(\d+)", s, re.I)
    if m:
        return int(m.group(1))
    if "子标题" in s:
        return 0
    m2 = re.search(r"标题\s*(\d+)", s)
    if m2:
        return int(m2.group(1))
    if "标题" in s:
        return 1
    return 0


def _heading_level_from_style(
    style_val: str,
    style_index: Optional[dict[str, dict[str, str]]] = None,
) -> int:
    if not style_val:
        return 0
    s = style_val.strip()
    if not style_index:
        return _heading_level_from_label(s)

    visited: set[str] = set()
    current = s
    while current and current not in visited:
        visited.add(current)
        info = style_index.get(current) or {}
        name = (info.get("name") or "").strip()
        if name:
            level = _heading_level_from_label(name)
            if level:
                return level
        current = (info.get("basedOn") or "").strip()
    return _heading_level_from_label(s)


def _load_docx_structured(content: bytes, file_name: str) -> DocumentLoadResult:
    """按 document.xml 顺序解析段落、表格、嵌入图"""
    result = DocumentLoadResult(text="", source_type="docx", file_name=file_name)
    blocks: list[dict] = []
    images: list[LoadedImage] = []
    img_idx = 0
    block_seq = 0
    style_index = _parse_docx_style_index(content)

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            rels_map: dict[str, str] = {}
            if "word/_rels/document.xml.rels" in zf.namelist():
                rels_root = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
                for rel in rels_root:
                    rid = rel.get("Id")
                    target = rel.get("Target")
                    if rid and target:
                        rels_map[rid] = target

            media_cache: dict[str, tuple[bytes, str]] = {}

            def _read_image(embed_id: str) -> Optional[int]:
                nonlocal img_idx
                target = rels_map.get(embed_id)
                if not target:
                    return None
                path = target if target.startswith("word/") else f"word/{target.lstrip('/')}"
                if path not in zf.namelist():
                    path2 = f"word/{os.path.basename(target)}"
                    if path2 in zf.namelist():
                        path = path2
                    else:
                        return None
                if path in media_cache:
                    _, mime = media_cache[path]
                else:
                    raw = zf.read(path)
                    ext = os.path.splitext(path)[1].lower()
                    mime = {
                        ".png": "image/png",
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".webp": "image/webp",
                        ".gif": "image/gif",
                    }.get(ext, "image/png")
                    compressed, save_mime = _compress_image(raw, mime)
                    media_cache[path] = (compressed, save_mime)
                    raw = compressed
                    mime = save_mime
                compressed, save_mime = media_cache[path]
                images.append(
                    LoadedImage(
                        index=img_idx,
                        mime=save_mime,
                        data=compressed,
                        source=path,
                    )
                )
                idx = img_idx
                img_idx += 1
                return idx

            doc_root = ET.fromstring(zf.read("word/document.xml"))
            body = doc_root.find(f"{W}body")
            if body is None:
                raise ValueError("Word 文档 body 为空")

            for child in body:
                tag = child.tag
                if tag == f"{W}p":
                    p_texts = []
                    for t_node in child.iter(f"{W}t"):
                        if t_node.text:
                            p_texts.append(t_node.text)
                    text = "".join(p_texts).strip()

                    level = 0
                    p_pr = child.find(f"{W}pPr")
                    if p_pr is not None:
                        p_style = p_pr.find(f"{W}pStyle")
                        if p_style is not None:
                            level = _heading_level_from_style(
                                p_style.get(f"{W}val") or p_style.get("val") or "",
                                style_index,
                            )

                    for blip in child.iter(f"{A}blip"):
                        embed = blip.get(f"{R}embed") or blip.get("embed")
                        if embed:
                            image_index = _read_image(embed)
                            if image_index is not None:
                                block_seq += 1
                                blocks.append({
                                    "id": f"b{block_seq}",
                                    "type": "image",
                                    "image_index": image_index,
                                    "anchor": f"文档图 {image_index + 1}",
                                })

                    if text:
                        block_seq += 1
                        blocks.append({
                            "id": f"b{block_seq}",
                            "type": "heading" if level else "paragraph",
                            "level": level,
                            "text": text,
                        })

                elif tag == f"{W}tbl":
                    rows_text = []
                    for row in child.findall(f".//{W}tr"):
                        cells = []
                        for cell in row.findall(f".//{W}tc"):
                            cell_texts = []
                            for t_node in cell.iter(f"{W}t"):
                                if t_node.text:
                                    cell_texts.append(t_node.text)
                            cells.append("".join(cell_texts).strip().replace("\n", " "))
                        if any(cells):
                            rows_text.append(" | ".join(cells))
                    if rows_text:
                        block_seq += 1
                        blocks.append({
                            "id": f"b{block_seq}",
                            "type": "paragraph",
                            "text": "\n".join(rows_text),
                        })

    except Exception as e:
        logger.warning(f"[document_structure] Word 结构化解析失败，回退简单模式: {e}")
        return _load_docx_fallback(content, file_name)

    # 若 XML 未解析到图，回退 zip media
    if not images:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                media_files = sorted(
                    n for n in zf.namelist()
                    if n.startswith("word/media/") and not n.endswith("/")
                )
                for media_path in media_files:
                    ext = os.path.splitext(media_path)[1].lower()
                    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"):
                        continue
                    raw = zf.read(media_path)
                    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(
                        ext, "image/png"
                    )
                    compressed, save_mime = _compress_image(raw, mime)
                    images.append(
                        LoadedImage(index=img_idx, mime=save_mime, data=compressed, source=media_path)
                    )
                    block_seq += 1
                    blocks.append({
                        "id": f"b{block_seq}",
                        "type": "image",
                        "image_index": img_idx,
                        "anchor": f"附录图 {img_idx + 1}",
                    })
                    img_idx += 1
        except Exception as e:
            result.warnings.append(f"Word 图片提取失败: {e}")

    result.images = images
    result.text = _blocks_plain_text(blocks)
    result.page_count = max(1, len([b for b in blocks if b.get("type") != "image"]) // 25)
    result.blocks = blocks
    result.sections = blocks_to_sections(blocks, "docx")
    return result


def _load_docx_fallback(content: bytes, file_name: str) -> DocumentLoadResult:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    result = DocumentLoadResult(text="", source_type="docx", file_name=file_name)
    style_index = _parse_docx_style_index(content)
    doc = Document(io.BytesIO(content))
    blocks: list[dict] = []
    block_seq = 0
    for element in doc.element.body:
        tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
        if tag == "p":
            para = Paragraph(element, doc)
            t = para.text.strip()
            if not t:
                continue
            level = 0
            try:
                style_id = para.style.style_id if para.style is not None else ""
                style_name = para.style.name if para.style is not None else ""
                level = _heading_level_from_style(style_id or style_name, style_index)
                if not level and style_name:
                    level = _heading_level_from_style(style_name)
            except Exception:
                pass
            block_seq += 1
            blocks.append({
                "id": f"b{block_seq}",
                "type": "heading" if level else "paragraph",
                "level": level,
                "text": t,
            })
        elif tag == "tbl":
            table = Table(element, doc)
            rows = []
            for row in table.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                rows.append(" | ".join(cells))
            if rows:
                block_seq += 1
                blocks.append({"id": f"b{block_seq}", "type": "paragraph", "text": "\n".join(rows)})

    img_idx = 0
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for media_path in sorted(
                n for n in zf.namelist()
                if n.startswith("word/media/") and not n.endswith("/")
            ):
                ext = os.path.splitext(media_path)[1].lower()
                if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"):
                    continue
                raw = zf.read(media_path)
                mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(
                    ext, "image/png"
                )
                compressed, save_mime = _compress_image(raw, mime)
                result.images.append(
                    LoadedImage(index=img_idx, mime=save_mime, data=compressed, source=media_path)
                )
                block_seq += 1
                blocks.append({
                    "id": f"b{block_seq}",
                    "type": "image",
                    "image_index": img_idx,
                    "anchor": f"附录图 {img_idx + 1}",
                })
                img_idx += 1
    except Exception as e:
        result.warnings.append(f"Word 图片提取失败: {e}")

    result.text = _blocks_plain_text(blocks)
    result.page_count = max(1, len(blocks) // 20)
    result.blocks = blocks
    result.sections = blocks_to_sections(blocks, "docx")
    return result


def _load_pdf_structured(content: bytes, file_name: str) -> DocumentLoadResult:
    result = _load_pdf(content, file_name)
    blocks: list[dict] = []
    block_seq = 0
    import fitz

    doc = fitz.open(stream=content, filetype="pdf")
    img_by_page_source = {}
    for img in result.images:
        img_by_page_source[img.source] = img

    for page_num in range(doc.page_count):
        page = doc[page_num]
        page_no = page_num + 1
        page_text = page.get_text().strip()
        if page_text:
            block_seq += 1
            blocks.append({
                "id": f"b{block_seq}",
                "type": "paragraph",
                "text": page_text,
                "page": page_no,
            })
        for img in result.images:
            if img.page == page_no:
                block_seq += 1
                blocks.append({
                    "id": f"b{block_seq}",
                    "type": "image",
                    "image_index": img.index,
                    "page": page_no,
                    "anchor": f"第 {page_no} 页",
                })
    doc.close()

    result.blocks = blocks
    result.sections = blocks_to_sections(blocks, "pdf")
    return result


def _load_md_structured(content: bytes, file_name: str) -> DocumentLoadResult:
    result = _load_text(content, file_name, "md")
    blocks: list[dict] = []
    block_seq = 0
    for line in result.text.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        m = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        block_seq += 1
        if m:
            blocks.append({
                "id": f"b{block_seq}",
                "type": "heading",
                "level": len(m.group(1)),
                "text": m.group(2).strip(),
            })
        else:
            blocks.append({"id": f"b{block_seq}", "type": "paragraph", "text": line.strip()})
    result.blocks = blocks
    result.sections = blocks_to_sections(blocks, "md")
    return result


def _blocks_plain_text(blocks: list[dict]) -> str:
    parts = []
    for b in blocks:
        if b.get("type") in ("paragraph", "heading"):
            t = (b.get("text") or "").strip()
            if t:
                parts.append(t)
    return "\n\n".join(parts)


def load_document_structured(content: bytes, file_name: str) -> DocumentLoadResult:
    ext = os.path.splitext(file_name or "")[1].lower()
    if ext == ".pdf":
        return _load_pdf_structured(content, file_name)
    if ext in (".docx",):
        return _load_docx_structured(content, file_name)
    if ext == ".doc":
        raise ValueError("暂不支持旧版 .doc，请另存为 .docx")
    if ext in (".txt", ".md"):
        return _load_md_structured(content, file_name)
    raise ValueError(f"不支持的格式: {ext}")
