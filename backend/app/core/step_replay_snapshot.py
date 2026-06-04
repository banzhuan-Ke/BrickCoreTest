"""
编辑页自愈：回放用例前置步骤后抓取页面 snapshot
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.page_fetcher import SmartPageExplorer, capture_accessibility_snapshot

logger = logging.getLogger(__name__)

SKIP_METHODS = frozenset({"close", "close_page", "save_page_img"})


def _resolve_start_url(steps: list, fallback_url: str = "") -> str:
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("method") == "open_url":
            url = (step.get("params") or {}).get("url") or ""
            if url.strip():
                return url.strip()
    return (fallback_url or "").strip() or "about:blank"


async def capture_snapshot_after_replay(
    steps: list,
    through_index: int,
    fallback_url: str = "",
) -> dict[str, Any]:
    """
    执行 steps[0:through_index] 后抓取无障碍树 snapshot。
    through_index=3 表示执行第 1～3 步（不含 index 3）。
    """
    if through_index <= 0:
        return {"success": False, "reason": "无需回放或回放步数为 0，请填写页面 URL 或增大回放步数"}

    pre_steps = [s for s in steps[:through_index] if isinstance(s, dict)]
    if not pre_steps:
        return {"success": False, "reason": "回放步骤为空"}

    start_url = _resolve_start_url(pre_steps, fallback_url)
    explorer = SmartPageExplorer(
        start_url=start_url,
        description="locator-heal-replay",
        max_rounds=1,
        timeout=30,
    )
    await explorer._init_browser()

    try:
        if start_url and start_url != "about:blank":
            try:
                await explorer.page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.warning(f"[step_replay] 初始导航失败: {e}")

        for i, step in enumerate(pre_steps):
            method = (step.get("method") or "").strip()
            if method in ("open_browser",):
                continue
            if method in SKIP_METHODS:
                continue
            if method == "open_url" and i > 0:
                pass
            success, error = await explorer._execute_step(step)
            if not success:
                return {
                    "success": False,
                    "reason": f"回放第 {i + 1} 步「{step.get('desc') or method}」失败: {error}",
                    "failed_step_index": i,
                }

        snap_text, snap_type = await capture_accessibility_snapshot(explorer.page)
        if not snap_text:
            return {"success": False, "reason": "回放成功但未能抓取页面 snapshot"}

        return {
            "success": True,
            "accessibility_snapshot": snap_text,
            "snapshot_type": snap_type,
            "page_url": explorer.page.url,
            "replayed_steps": through_index,
        }
    except Exception as e:
        logger.error(f"[step_replay] 回放异常: {e}", exc_info=True)
        return {"success": False, "reason": f"回放异常: {e}"}
    finally:
        await explorer._close()
