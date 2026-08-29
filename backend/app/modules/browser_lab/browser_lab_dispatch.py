"""Browser Lab 任务派发至 Runner（BL-2 Phase 1）。"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException

from app.core.infra.mq_producer import MQProducer
from app.core.platform import config as settings
from app.models.ai import BrowserLabTask
from app.modules.browser_dispatch import (
    build_internal_token,
    estimate_job_token_ttl_seconds,
    read_headless_from_mapping,
    resolve_platform_base_url_async,
    validate_device_online,
)

logger = logging.getLogger(__name__)

# 桌面执行机（Windows/macOS 有头调试）只保留语言；勿无条件下发 Docker/Linux 沙箱参数，
# 否则 Chromium 会提示「不受支持的命令行标记: --disable-gpu-sandbox」等。
# Linux 云主机 / 平台本机起浏览器（历史 local、未来付费版服务器模式）所需参数由
# Runner 侧按 OS 追加（见 browser_lab_worker + run_env.chromium_launch_args）。
_BROWSER_LAB_CHROME_ARGS = [
    "--lang=zh-CN",
    # 以下为 Linux/Docker 服务器场景保留备忘（勿默认下发）：
    # "--no-sandbox",
    # "--disable-setuid-sandbox",
    # "--disable-dev-shm-usage",
    # "--disable-gpu",
]


def _read_task_platform_base(task: BrowserLabTask) -> str | None:
    cfg = task.config_json if isinstance(task.config_json, dict) else {}
    base = (cfg.get("_platform_base_url") or "").strip().rstrip("/")
    return base or None


def _platform_callback_base(task_id: int, *, platform_base: str) -> str:
    return f"{platform_base.rstrip('/')}/ai/browser-lab/tasks/{task_id}"


def _build_dispatch_options(
    task: BrowserLabTask,
    cfg: dict[str, Any],
    *,
    config: Any,
    scene_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.modules.browser_lab.browser_lab_runner import _resolve_browser_lab_timeouts

    max_steps = int(cfg.get("max_steps") or settings.BROWSER_LAB_DEFAULT_MAX_STEPS)
    max_steps = min(max_steps, settings.BROWSER_LAB_MAX_STEPS_CAP)
    cap = max(0, settings.BROWSER_LAB_MAX_BROWSER_RESTARTS_CAP)
    max_restarts = min(max(0, int(cfg.get("max_browser_restarts") or 0)), cap)
    if not cfg.get("enable_browser_restart"):
        max_restarts = 0
    repeat_cap = max(2, settings.BROWSER_LAB_MAX_REPEAT_STEPS_CAP)
    max_repeat = min(max(2, int(cfg.get("max_repeat_steps") or settings.BROWSER_LAB_MAX_REPEAT_STEPS)), repeat_cap)
    llm_timeout, step_timeout = _resolve_browser_lab_timeouts(config, scene_overrides)
    viewport_w = max(800, settings.BROWSER_LAB_VIEWPORT_WIDTH)
    viewport_h = max(600, settings.BROWSER_LAB_VIEWPORT_HEIGHT)
    from app.modules.ai.browser_use_llm import browser_use_supports_vision

    use_vision = bool(cfg.get("use_vision", True)) and browser_use_supports_vision(config)
    return {
        "max_steps": max_steps,
        "use_vision": use_vision,
        "generate_gif": bool(cfg.get("generate_gif", True)),
        "max_repeat_steps": max_repeat,
        "enable_browser_restart": bool(cfg.get("enable_browser_restart", True)),
        "max_browser_restarts": max_restarts,
        "viewport": {"width": viewport_w, "height": viewport_h},
        "step_timeout": step_timeout,
        "llm_timeout": llm_timeout,
    }


async def build_browser_lab_runner_payload(
    task: BrowserLabTask,
    *,
    config: Any,
    scene_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """组装 MQ run_suite 载荷。"""
    cfg = dict(task.config_json or {})
    device_id = (cfg.get("device_id") or "").strip()
    if not device_id:
        raise HTTPException(status_code=400, detail="Runner 模式须选择在线执行设备")

    callback_base = _platform_callback_base(
        task.id,
        platform_base=await resolve_platform_base_url_async(
            request_base_url=_read_task_platform_base(task),
        ),
    )
    options = _build_dispatch_options(
        task, cfg, config=config, scene_overrides=scene_overrides
    )
    internal_token = build_internal_token(
        job_id=str(task.id),
        project_id=task.project_id,
        task_type="browser_lab",
        ttl_seconds=estimate_job_token_ttl_seconds(
            max_steps=int(options.get("max_steps") or 25),
            step_timeout=int(options.get("step_timeout") or 390),
        ),
    )
    from app.modules.browser_lab.browser_lab_runner import _resolve_browser_lab_timeouts

    llm_timeout, step_timeout = _resolve_browser_lab_timeouts(config, scene_overrides)
    from app.modules.browser_lab.browser_lab_action_cache import resolve_browser_lab_run_context

    run_ctx = await resolve_browser_lab_run_context(
        project_id=task.project_id,
        start_url=task.start_url,
        task_text=task.task_text,
        cfg=cfg,
    )
    options = _build_dispatch_options(
        task, cfg, config=config, scene_overrides=scene_overrides
    )
    options["step_timeout"] = step_timeout
    options["llm_timeout"] = llm_timeout

    return {
        "task_type": "browser_lab",
        "browser_lab_task_id": task.id,
        "project_id": task.project_id,
        "case_id": task.case_id,
        "start_url": run_ctx["start_url"] or task.start_url,
        "task_text": run_ctx["task_text"] or task.task_text,
        "callback_base": callback_base,
        "internal_token": internal_token,
        "llm": {
            "mode": "proxy",
            "base_url": f"{callback_base}/llm/v1",
            "model": config.model,
            "timeout": llm_timeout,
        },
        "options": options,
        "chrome_args": list(_BROWSER_LAB_CHROME_ARGS),
        "ai_config_id": config.id,
    }


async def dispatch_browser_lab_to_runner(
    task: BrowserLabTask,
    *,
    config: Any,
    scene_overrides: dict[str, Any] | None = None,
) -> None:
    """将 Browser Lab Agent 任务投递至 Runner 设备队列。"""
    if not settings.BROWSER_RUN_DISPATCH_ENABLED:
        raise HTTPException(status_code=400, detail="Runner 派发未启用")

    cfg = dict(task.config_json or {})
    device_id = (cfg.get("device_id") or "").strip()
    await validate_device_online(device_id)

    run_suite = await build_browser_lab_runner_payload(
        task, config=config, scene_overrides=scene_overrides
    )
    env_config = {
        "device_id": device_id,
        "headless": read_headless_from_mapping(cfg),
        "browser_type": "chromium",
    }

    mq = MQProducer()
    try:
        mq.send_test_task(env_config, run_suite, device_id)
        logger.info("[browser_lab] dispatched task %s to device %s", task.id, device_id)
    except Exception as exc:
        logger.exception("[browser_lab] MQ dispatch failed task %s", task.id)
        raise HTTPException(status_code=500, detail=f"派发 Runner 任务失败: {exc}") from exc
    finally:
        mq.close()


def send_browser_lab_stop(device_id: str, task_id: int) -> None:
    """向 Runner 发送 browser_lab 停止信令。"""
    did = (device_id or "").strip()
    if not did:
        return
    mq = MQProducer()
    try:
        mq.send_stop_task(did, browser_lab_task_id=task_id)
    except Exception as exc:
        logger.warning("[browser_lab] stop MQ failed task %s: %s", task_id, exc)
    finally:
        mq.close()
