"""资料库文档图片本地 OCR（RapidOCR / PP-OCR ONNX，2G 友好，可选依赖）。"""
from __future__ import annotations

import asyncio
import io
import logging
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

MAX_OCR_EDGE = 1920

_ocr_instance: object | None = None
_ocr_unavailable: bool = False
_ocr_init_error: str | None = None
_ocr_semaphore: asyncio.Semaphore | None = None


def rapidocr_available() -> bool:
    if _ocr_unavailable:
        return False
    try:
        _ensure_cv2()
        from rapidocr import RapidOCR  # noqa: F401

        return True
    except ImportError:
        return False


def _format_import_error(ex: ImportError) -> str:
    msg = str(ex)
    if "libGL" in msg:
        return f"缺少 libGL 系统库（需重建 backend 镜像）: {msg}"
    if "cv2" in msg:
        return f"缺少 opencv (cv2)，Docker 需 opencv-python-headless: {msg}"
    return msg


def _ensure_cv2() -> None:
    import cv2  # noqa: F401


def _load_rapidocr():
    global _ocr_instance, _ocr_unavailable, _ocr_init_error
    if _ocr_instance is not None:
        return _ocr_instance
    if _ocr_unavailable:
        return None
    try:
        _ensure_cv2()
        from rapidocr import RapidOCR

        _ocr_instance = RapidOCR()
        return _ocr_instance
    except ImportError as ex:
        _ocr_init_error = _format_import_error(ex)
        logger.warning("[knowledge_image_ocr] RapidOCR import failed: %s", ex)
        _ocr_unavailable = True
        return None
    except Exception as ex:
        _ocr_init_error = str(ex)
        logger.warning("[knowledge_image_ocr] RapidOCR init failed: %s", ex, exc_info=True)
        _ocr_unavailable = True
        return None


def ocr_unavailable_reason() -> str:
    if _ocr_init_error:
        return f"RapidOCR 不可用: {_ocr_init_error}"
    return "RapidOCR 未安装（需重建 backend 镜像: docker compose build --no-cache backend）"


def _get_semaphore(concurrency: int = 1) -> asyncio.Semaphore:
    global _ocr_semaphore
    if _ocr_semaphore is None:
        _ocr_semaphore = asyncio.Semaphore(max(1, int(concurrency or 1)))
    return _ocr_semaphore


def _prepare_image_bytes(image_bytes: bytes, *, max_edge: int = MAX_OCR_EDGE) -> bytes:
    """缩过大图，降低 2G 服务器 OCR 内存峰值。"""
    if not image_bytes:
        return image_bytes
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("RGB")
            w, h = img.size
            limit = max(64, int(max_edge or MAX_OCR_EDGE))
            if max(w, h) > limit:
                ratio = limit / max(w, h)
                img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        return image_bytes


def _extract_text_from_result(result: object) -> str:
    txts = getattr(result, "txts", None)
    if not txts:
        return ""
    lines: list[str] = []
    for item in txts:
        text = str(item or "").strip()
        if text:
            lines.append(text)
    return "\n".join(lines).strip()


def ocr_image_sync(image_bytes: bytes) -> tuple[str, Optional[str]]:
    """同步 OCR，返回 (text, error)。"""
    ocr = _load_rapidocr()
    if ocr is None:
        return "", ocr_unavailable_reason()
    if not image_bytes:
        return "", "空图片"
    try:
        prepared = _prepare_image_bytes(image_bytes)
        result = ocr(prepared)
        text = _extract_text_from_result(result)
        if text:
            return text, None
        return "", "OCR 未识别到文字"
    except Exception as ex:
        return "", str(ex)


async def ocr_image(image_bytes: bytes, *, concurrency: int = 1) -> tuple[str, Optional[str]]:
    sem = _get_semaphore(concurrency)
    async with sem:
        return await asyncio.to_thread(ocr_image_sync, image_bytes)
