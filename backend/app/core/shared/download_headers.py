"""下载响应 Content-Disposition（兼容中文文件名）。"""
from __future__ import annotations

import re
from urllib.parse import quote


def sanitize_download_basename(name: str, *, fallback: str = "report", max_len: int = 80) -> str:
    """去掉路径非法字符，供附件文件名使用。"""
    s = (name or "").strip()
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", s)
    s = re.sub(r"\s+", " ", s).strip(" ._")
    if not s:
        s = fallback
    if len(s) > max_len:
        s = s[:max_len].rstrip(" ._")
    return s or fallback


def content_disposition_attachment(filename: str, *, ascii_fallback: str) -> dict[str, str]:
    """RFC 5987：filename 用 ASCII 兜底，filename* 用 UTF-8 真名。"""
    utf8_name = sanitize_download_basename(filename, fallback=ascii_fallback)
    ascii_name = sanitize_download_basename(ascii_fallback, fallback="download.bin")
    # ASCII fallback 仅保留可打印 ASCII，避免部分浏览器解析失败
    ascii_name = re.sub(r"[^\x20-\x7E]", "_", ascii_name) or "download.bin"
    return {
        "Content-Disposition": (
            f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(utf8_name)}"
        )
    }
