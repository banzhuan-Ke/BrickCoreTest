"""
需求文档轻量加载器
从 PDF / Word 提取文本与嵌入图片，供 AI 需求用例生成使用
"""
from __future__ import annotations

import io
import logging
import os
import zipfile
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

MAX_IMAGE_EDGE = 4096
MAX_IMAGE_BYTES = 8 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}


@dataclass
class LoadedImage:
    index: int
    mime: str
    data: bytes
    source: str = ""
    page: Optional[int] = None


@dataclass
class DocumentLoadResult:
    text: str
    images: list[LoadedImage] = field(default_factory=list)
    page_count: int = 0
    source_type: str = "text"
    file_name: str = ""
    warnings: list[str] = field(default_factory=list)
    blocks: list[dict] = field(default_factory=list)
    sections: list[dict] = field(default_factory=list)


def _compress_image(data: bytes, mime: str) -> tuple[bytes, str]:
    """压缩图片至规格限制内"""
    try:
        img = Image.open(io.BytesIO(data))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > MAX_IMAGE_EDGE:
            ratio = MAX_IMAGE_EDGE / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        fmt = "PNG" if mime == "image/png" else "JPEG"
        save_mime = "image/png" if fmt == "PNG" else "image/jpeg"
        if fmt == "JPEG" and img.mode == "RGBA":
            img = img.convert("RGB")
        img.save(out, format=fmt, quality=85, optimize=True)
        result = out.getvalue()
        if len(result) > MAX_IMAGE_BYTES:
            # 二次压缩
            img = Image.open(io.BytesIO(result))
            if img.mode != "RGB":
                img = img.convert("RGB")
            out2 = io.BytesIO()
            img.save(out2, format="JPEG", quality=70, optimize=True)
            result = out2.getvalue()
            save_mime = "image/jpeg"
        return result, save_mime
    except Exception as e:
        logger.warning(f"[document_loader] 图片压缩失败: {e}")
        return data, mime


def _load_pdf(content: bytes, file_name: str) -> DocumentLoadResult:
    import fitz  # pymupdf

    result = DocumentLoadResult(text="", source_type="pdf", file_name=file_name)
    doc = fitz.open(stream=content, filetype="pdf")
    result.page_count = doc.page_count
    text_parts: list[str] = []
    img_idx = 0

    for page_num in range(doc.page_count):
        page = doc[page_num]
        page_text = page.get_text().strip()
        if page_text:
            text_parts.append(f"--- 第 {page_num + 1} 页 ---\n{page_text}")

        for img_info in page.get_images(full=True):
            try:
                xref = img_info[0]
                base = doc.extract_image(xref)
                if not base or not base.get("image"):
                    continue
                mime = f"image/{base.get('ext', 'png')}"
                if mime == "image/jpg":
                    mime = "image/jpeg"
                compressed, save_mime = _compress_image(base["image"], mime)
                result.images.append(
                    LoadedImage(
                        index=img_idx,
                        mime=save_mime,
                        data=compressed,
                        source=f"pdf_page_{page_num + 1}",
                        page=page_num + 1,
                    )
                )
                img_idx += 1
            except Exception as e:
                result.warnings.append(f"PDF 第 {page_num + 1} 页图片提取失败: {e}")

    doc.close()
    result.text = "\n\n".join(text_parts)
    return result


def _load_docx(content: bytes, file_name: str) -> DocumentLoadResult:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    result = DocumentLoadResult(text="", source_type="docx", file_name=file_name)
    doc = Document(io.BytesIO(content))
    text_parts: list[str] = []

    for block in doc.element.body:
        tag = block.tag.split("}")[-1] if "}" in block.tag else block.tag
        if tag == "p":
            para = Paragraph(block, doc)
            t = para.text.strip()
            if t:
                text_parts.append(t)
        elif tag == "tbl":
            table = Table(block, doc)
            rows = []
            for row in table.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                rows.append(" | ".join(cells))
            if rows:
                text_parts.append("\n".join(rows))

    result.text = "\n\n".join(text_parts)
    result.page_count = max(1, len(text_parts) // 20)

    # 提取嵌入图片（docx 为 zip）
    img_idx = 0
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
                mime = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                    ".gif": "image/gif",
                    ".bmp": "image/png",
                }.get(ext, "image/png")
                compressed, save_mime = _compress_image(raw, mime)
                result.images.append(
                    LoadedImage(
                        index=img_idx,
                        mime=save_mime,
                        data=compressed,
                        source=media_path,
                    )
                )
                img_idx += 1
    except Exception as e:
        result.warnings.append(f"Word 图片提取失败: {e}")

    return result


def _load_text(content: bytes, file_name: str, source_type: str) -> DocumentLoadResult:
    for encoding in ("utf-8", "gbk", "gb2312", "latin-1"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            text = ""
            continue
    else:
        text = content.decode("utf-8", errors="ignore")

    return DocumentLoadResult(
        text=text.strip(),
        source_type=source_type,
        file_name=file_name,
        page_count=1,
    )


def load_document(content: bytes, file_name: str) -> DocumentLoadResult:
    """根据文件名解析 PDF / Word / 文本（结构化块 + 章节）"""
    from app.core.document_structure import load_document_structured

    return load_document_structured(content, file_name)
