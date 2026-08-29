"""单页 DOM 抓取派发至 Runner（同步等待回传）。"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException

from app.core.infra.mq_producer import MQProducer
from app.core.platform import config as settings
from app.modules.browser_dispatch import (
    build_internal_token,
    resolve_platform_base_url_async,
    validate_device_online,
)
from app.modules.ui import page_fetch_bridge

logger = logging.getLogger(__name__)

_DEFAULT_FETCH_TIMEOUT = 20
_WAIT_BUFFER_SECONDS = 25


async def fetch_page_structure_via_runner(
    *,
    url: str,
    device_id: str | None,
    project_id: int | None = None,
    request_base_url: str | None = None,
    timeout: int = _DEFAULT_FETCH_TIMEOUT,
    headless: bool = True,
) -> Optional[dict[str, Any]]:
    """
    经 Runner 抓取页面元素结构；成功返回 {title,url,elements,status_code}，失败返回 None。
    """
    target = (url or "").strip()
    if not target.startswith(("http://", "https://")):
        logger.warning("[page_fetch] 无效 URL: %s", url)
        return None

    if not settings.BROWSER_RUN_DISPATCH_ENABLED:
        raise HTTPException(status_code=400, detail="Runner 派发未启用（BROWSER_RUN_DISPATCH_ENABLED=0）")

    await validate_device_online(device_id)
    did = (device_id or "").strip()
    platform_base = await resolve_platform_base_url_async(request_base_url=request_base_url)
    request_id = page_fetch_bridge.new_request_id()
    fetch_timeout = max(5, min(int(timeout or _DEFAULT_FETCH_TIMEOUT), 60))
    wait_timeout = float(fetch_timeout + _WAIT_BUFFER_SECONDS)

    callback_base = f"{platform_base.rstrip('/')}/ai/generate/page-fetch/{request_id}"
    internal_token = build_internal_token(
        job_id=request_id,
        project_id=int(project_id or 0),
        task_type="page_fetch",
        ttl_seconds=max(120, int(wait_timeout) + 60),
    )
    run_suite = {
        "task_type": "page_fetch",
        "request_id": request_id,
        "page_url": target,
        "timeout": fetch_timeout,
        "callback_base": callback_base,
        "internal_token": internal_token,
        "project_id": int(project_id or 0),
    }
    env_config = {
        "device_id": did,
        "headless": bool(headless),
        "browser_type": "chromium",
    }

    await page_fetch_bridge.register_wait(request_id)
    mq = MQProducer()
    try:
        mq.send_test_task(env_config, run_suite, did)
        logger.info("[page_fetch] dispatched request_id=%s device=%s url=%s", request_id, did, target)
    except Exception as exc:
        await page_fetch_bridge.cancel(request_id)
        logger.exception("[page_fetch] MQ dispatch failed")
        raise HTTPException(status_code=500, detail=f"派发页面抓取任务失败: {exc}") from exc
    finally:
        mq.close()

    result = await page_fetch_bridge.wait_result(request_id, timeout=wait_timeout)
    if result is None:
        logger.warning("[page_fetch] timeout request_id=%s", request_id)
        return None

    if not result.get("ok"):
        logger.warning(
            "[page_fetch] runner failed request_id=%s err=%s",
            request_id,
            (result.get("error") or "")[:200],
        )
        return None

    page = result.get("page") if isinstance(result.get("page"), dict) else None
    if not page:
        return None
    return {
        "title": page.get("title") or "",
        "url": page.get("url") or target,
        "elements": page.get("elements") or [],
        "status_code": int(page.get("status_code") or 0),
    }
