"""browser-use GIF 补丁：中文字体 + 缩小叠加字号。"""
from __future__ import annotations

import logging
import os
import platform
from functools import wraps
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Debian/Ubuntu fonts-noto-cjk、fonts-wqy-zenhei 常见路径
_CJK_FONT_PATHS: list[str] = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    # Windows 本地开发
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "msyh.ttc"),
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "msyhbd.ttc"),
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "simhei.ttf"),
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "simsun.ttc"),
    *[
        p.strip()
        for p in os.environ.get("BROWSER_LAB_GIF_FONT", "").split(os.pathsep)
        if p.strip()
    ],
]

# browser-use 默认 title_font_size=56，叠加中文偏大
_GIF_FONT_SIZE = int(os.getenv("BROWSER_LAB_GIF_FONT_SIZE", "24"))
_GIF_TITLE_FONT_SIZE = int(os.getenv("BROWSER_LAB_GIF_TITLE_FONT_SIZE", "32"))
_GIF_MARGIN = int(os.getenv("BROWSER_LAB_GIF_MARGIN", "28"))

_patch_applied = False


def _pick_cjk_font_path() -> str | None:
    for path in _CJK_FONT_PATHS:
        if path and os.path.isfile(path):
            return path
    return None


def apply_browser_use_gif_cjk_patch() -> None:
    """GIF 生成：缩小叠加字号，Linux Docker 优先用 CJK 字体。"""
    global _patch_applied
    if _patch_applied:
        return

    cjk_path = _pick_cjk_font_path()
    if not cjk_path:
        logger.warning(
            "[browser_lab] 未找到中文字体，GIF 叠加文字可能显示为方框；"
            "请确认 Docker 已安装 fonts-noto-cjk / fonts-wqy-zenhei"
        )

    from PIL import ImageFont
    import browser_use.agent.gif as gif_mod

    orig_truetype = ImageFont.truetype
    orig_create = gif_mod.create_history_gif

    @wraps(orig_create)
    def create_history_gif_patched(*args: Any, **kwargs: Any):
        kwargs.setdefault("font_size", _GIF_FONT_SIZE)
        kwargs.setdefault("title_font_size", _GIF_TITLE_FONT_SIZE)
        kwargs.setdefault("goal_font_size", _GIF_TITLE_FONT_SIZE - 2)
        kwargs.setdefault("margin", _GIF_MARGIN)

        def truetype_patched(font: Any, size: int, *args2: Any, **kwargs2: Any):
            if cjk_path:
                try:
                    return orig_truetype(cjk_path, size, *args2, **kwargs2)
                except OSError:
                    pass
            try:
                return orig_truetype(font, size, *args2, **kwargs2)
            except OSError as ex:
                if cjk_path:
                    raise OSError(f"cannot open font {font!r} or CJK fallback {cjk_path}") from ex
                raise

        ImageFont.truetype = truetype_patched  # type: ignore[method-assign]
        try:
            return orig_create(*args, **kwargs)
        finally:
            ImageFont.truetype = orig_truetype  # type: ignore[method-assign]

    gif_mod.create_history_gif = create_history_gif_patched  # type: ignore[method-assign]
    _patch_applied = True
    logger.info(
        "[browser_lab] GIF 补丁已启用 font=%s title=%s cjk=%s (%s)",
        _GIF_FONT_SIZE,
        _GIF_TITLE_FONT_SIZE,
        cjk_path or "none",
        platform.system(),
    )


def ensure_replay_gif(task_text: str, history: Any, output_path: str | Path) -> bool:
    """从 Agent history 生成 replay.gif；已存在则跳过。"""
    path = Path(output_path)
    if path.exists():
        return True
    if history is None:
        return False
    try:
        apply_browser_use_gif_cjk_patch()
        from browser_use.agent.gif import create_history_gif

        create_history_gif(
            task=task_text or "browser lab task",
            history=history,
            output_path=str(path),
        )
        if path.exists():
            logger.info("[browser_lab] replay GIF generated at %s", path)
            return True
    except Exception as ex:
        logger.warning("[browser_lab] replay GIF generation failed: %s", ex)
    return False
