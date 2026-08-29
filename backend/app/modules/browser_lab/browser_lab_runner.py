"""Browser Lab 任务编排：仅派发至 Runner，平台不启动浏览器。"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Optional

from app.core.platform import config as settings
from app.core.platform.datetime_utils import now_app
from app.models.ai import BrowserLabTask

logger = logging.getLogger(__name__)

_run_semaphore = asyncio.Semaphore(max(1, settings.BROWSER_LAB_MAX_CONCURRENT))
_stop_flags: dict[int, bool] = {}


def request_stop(task_id: int) -> None:
    _stop_flags[task_id] = True


def _should_stop(task_id: int) -> bool:
    return _stop_flags.get(task_id, False)


def _resolve_browser_lab_timeouts(config, scene_overrides: dict | None = None) -> tuple[int, int]:
    overrides = scene_overrides or {}
    base_timeout = overrides.get("timeout") or config.timeout or 180
    llm_timeout = max(120, int(base_timeout))
    step_timeout = max(settings.BROWSER_LAB_STEP_TIMEOUT, llm_timeout + 90)
    return llm_timeout, step_timeout


def _task_dir(task_id: int) -> Path:
    root = Path(settings.BROWSER_LAB_DIR)
    root.mkdir(parents=True, exist_ok=True)
    path = root / str(task_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def _append_step_event(task_id: int, event: dict[str, Any]) -> None:
    task = await BrowserLabTask.get_or_none(id=task_id)
    if not task:
        return
    log = list(task.step_log or [])
    log.append(event)
    task.step_log = log
    task.steps_count = len([e for e in log if e.get("type") == "step"])
    await task.save(update_fields=["step_log", "steps_count"])


async def _fail_task(task_id: int, message: str) -> None:
    task = await BrowserLabTask.get_or_none(id=task_id)
    if not task:
        return
    task.status = "failed"
    task.error_message = (message or "执行失败")[:4000]
    task.finished_at = now_app()
    await task.save()
    await _append_step_event(task_id, {"type": "error", "message": task.error_message})


async def run_browser_lab_task(task_id: int, username: str = "") -> None:
    """将 Browser Lab 任务派发至 Runner（平台不运行 browser-use / Playwright）。"""
    async with _run_semaphore:
        task = await BrowserLabTask.get_or_none(id=task_id)
        if not task:
            return

        from app.modules.ai.ai_scene_config import get_scene_llm_overrides, resolve_config_for_scene
        from app.modules.browser_dispatch import validate_device_online

        ai_config_id = (task.config_json or {}).get("ai_config_id")
        try:
            config = await resolve_config_for_scene("browser_lab", ai_config_id)
            scene_overrides = await get_scene_llm_overrides("browser_lab")
        except Exception as exc:
            await _fail_task(task_id, str(exc))
            _stop_flags.pop(task_id, None)
            return

        cfg = dict(task.config_json or {})
        device_id = (cfg.get("device_id") or "").strip()

        if _should_stop(task_id):
            task.status = "stopped"
            task.error_message = "用户已停止"
            task.finished_at = now_app()
            await task.save()
            await _append_step_event(
                task_id,
                {"type": "done", "status": "stopped", "summary": "用户已停止"},
            )
            _stop_flags.pop(task_id, None)
            return

        if not settings.BROWSER_RUN_DISPATCH_ENABLED:
            await _fail_task(
                task_id,
                "Runner 派发未启用，请在环境变量设置 BROWSER_RUN_DISPATCH_ENABLED=1",
            )
            _stop_flags.pop(task_id, None)
            return

        if not device_id:
            await _fail_task(task_id, "请选择在线 Runner 执行设备")
            _stop_flags.pop(task_id, None)
            return

        try:
            await validate_device_online(device_id)
        except Exception as exc:
            await _fail_task(task_id, str(exc))
            _stop_flags.pop(task_id, None)
            return

        task.status = "running"
        task.started_at = now_app()
        task.ai_config_id = config.id
        cfg["run_mode"] = "runner"
        cfg.pop("last_runner_heartbeat", None)
        cfg.pop("dispatch_status", None)
        task.config_json = cfg
        await task.save(update_fields=["status", "started_at", "ai_config_id", "config_json"])

        from app.modules.browser_lab.browser_lab_dispatch import dispatch_browser_lab_to_runner

        try:
            llm_timeout, step_timeout = _resolve_browser_lab_timeouts(config, scene_overrides)
            await dispatch_browser_lab_to_runner(
                task,
                config=config,
                scene_overrides=scene_overrides,
            )
            cfg = dict(task.config_json or {})
            cfg["dispatch_status"] = "runner"
            cfg["step_timeout"] = step_timeout
            cfg["llm_timeout"] = llm_timeout
            task.config_json = cfg
            task.engine = "browser_use_runner"
            await task.save(update_fields=["config_json", "engine"])
        except Exception as exc:
            logger.exception("[browser_lab] runner dispatch failed task %s", task_id)
            await _fail_task(task_id, str(exc))
        finally:
            _stop_flags.pop(task_id, None)


def ensure_browser_lab_dir() -> None:
    os.makedirs(settings.BROWSER_LAB_DIR, exist_ok=True)
