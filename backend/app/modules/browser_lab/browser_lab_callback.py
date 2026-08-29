"""Browser Lab Runner 回调事件处理。"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from tortoise.transactions import in_transaction

from app.core.platform import config as settings
from app.core.platform.datetime_utils import now_app
from app.models.ai import BrowserLabTask
from app.modules.browser_lab.browser_lab_media import is_browser_lab_object_key
from app.modules.browser_lab.browser_lab_runner import ensure_browser_lab_dir, _task_dir

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"done", "failed", "stopped"})


def _is_task_terminal(status: str | None) -> bool:
    return (status or "").strip().lower() in _TERMINAL_STATUSES


def _count_step_events(log: list) -> int:
    return len([e for e in log if e.get("type") == "step"])


def _touch_runner_activity(task: BrowserLabTask) -> None:
    cfg = dict(task.config_json or {})
    cfg["last_runner_heartbeat"] = datetime.now(timezone.utc).isoformat()
    task.config_json = cfg


async def append_browser_lab_callback_event(task_id: int, event: dict[str, Any]) -> Optional[BrowserLabTask]:
    task = await BrowserLabTask.get_or_none(id=task_id)
    if not task:
        return None
    log = list(task.step_log or [])
    log.append(event)
    task.step_log = log
    task.steps_count = _count_step_events(log)
    await task.save(update_fields=["step_log", "steps_count"])
    return task


async def upsert_browser_lab_step_event(task_id: int, step_evt: dict[str, Any]) -> Optional[BrowserLabTask]:
    """同 index 的步骤事件 upsert（bootstrap 可被后续 Agent 步覆盖展示）。"""
    async with in_transaction():
        task = await BrowserLabTask.select_for_update().get_or_none(id=task_id)
        if not task:
            return None
        idx = step_evt.get("index")
        log = list(task.step_log or [])
        replaced = False
        if idx is not None:
            for i, evt in enumerate(log):
                if evt.get("type") == "step" and evt.get("index") == idx:
                    log[i] = step_evt
                    replaced = True
                    break
        if not replaced:
            log.append(step_evt)
        task.step_log = log
        task.steps_count = _count_step_events(log)
        _touch_runner_activity(task)
        await task.save(update_fields=["step_log", "steps_count", "config_json"])
        return task


_MAX_GIF_B64_CHARS = 3_000_000


async def save_step_screenshot(task_id: int, step_index: int, screenshot_b64: str) -> Optional[str]:
    if not screenshot_b64:
        return None
    try:
        raw = base64.b64decode(screenshot_b64)
        ensure_browser_lab_dir()
        filename = f"step_{int(step_index):03d}.jpg"
        path = _task_dir(task_id) / filename
        path.write_bytes(raw)
        return filename
    except Exception as exc:
        logger.warning("[browser_lab] callback screenshot save failed: %s", exc)
        return None


async def handle_browser_lab_runner_callback(
    task: BrowserLabTask,
    event: str,
    payload: dict[str, Any],
) -> BrowserLabTask:
    """处理 Runner 上报的 step / heartbeat / done / fail / stopped。"""
    event = (event or "").strip().lower()
    payload = payload or {}
    task_id = task.id

    if event == "heartbeat":
        if _is_task_terminal(task.status):
            return task
        cfg = dict(task.config_json or {})
        cfg["last_runner_heartbeat"] = datetime.now(timezone.utc).isoformat()
        task.config_json = cfg
        await task.save(update_fields=["config_json"])
        return task

    # step / 终态回调：Runner 仍在跑时 GET 可能已误标 failed，必须继续合并步骤并允许 done 覆盖
    if event not in ("step", "done", "fail", "stopped", "error"):
        logger.warning("[browser_lab] unknown runner callback event: %s", event)
        return task

    if event == "step":
        screenshot_file = None
        b64 = payload.get("screenshot_b64")
        incoming_file = (payload.get("screenshot_file") or "").strip()
        if incoming_file and is_browser_lab_object_key(incoming_file):
            screenshot_file = incoming_file
        elif b64:
            screenshot_file = await save_step_screenshot(
                task_id, int(payload.get("index") or 0), str(b64)
            )
        step_evt = {
            "type": "step",
            "index": payload.get("index"),
            "url": payload.get("url") or "",
            "title": payload.get("title") or "",
            "thinking": (payload.get("thinking") or "")[:2000],
            "next_goal": (payload.get("next_goal") or "")[:1000],
            "memory": (payload.get("memory") or "")[:1000],
            "actions": payload.get("actions") or [],
            "screenshot_file": screenshot_file or payload.get("screenshot_file"),
            "step_status": (payload.get("step_status") or "ok").strip() or "ok",
            "runner": True,
        }
        await upsert_browser_lab_step_event(task_id, step_evt)
        task = await BrowserLabTask.get(id=task_id)
        if task.status == "pending":
            task.status = "running"
            if not task.started_at:
                task.started_at = now_app()
            await task.save(update_fields=["status", "started_at"])
        return task

    task = await BrowserLabTask.get(id=task_id)
    summary = (payload.get("result_summary") or payload.get("summary") or "").strip()
    error_message = (payload.get("error_message") or payload.get("message") or "").strip()
    runner_tokens = int(payload.get("tokens_used") or 0)

    if event == "done":
        task.status = "done"
        task.result_summary = (summary or "执行结束")[:8000]
        task.error_message = None
    elif event == "stopped":
        task.status = "stopped"
        task.result_summary = summary or "用户已停止"
        task.error_message = error_message or "用户已停止"
    else:
        task.status = "failed"
        task.error_message = (error_message or summary or "执行失败")[:4000]
        task.result_summary = (summary or task.error_message or "执行失败")[:8000]

    from app.modules.browser_lab.browser_lab_usage import resolve_browser_lab_tokens

    tokens = resolve_browser_lab_tokens(task, runner_reported=runner_tokens)
    task.tokens_used = tokens
    task.finished_at = now_app()
    task.engine = "browser_use_runner"

    gif_rel = (payload.get("gif_path") or "").strip()
    gif_b64 = payload.get("gif_b64")
    if gif_b64:
        try:
            raw_text = str(gif_b64)
            if len(raw_text) <= _MAX_GIF_B64_CHARS:
                raw = base64.b64decode(raw_text)
                ensure_browser_lab_dir()
                path = _task_dir(task_id) / "replay.gif"
                path.write_bytes(raw)
                task.gif_path = f"browser_lab/{task_id}/replay.gif"
            else:
                logger.warning(
                    "[browser_lab] gif_b64 too large (%s chars), skip save task=%s",
                    len(raw_text),
                    task_id,
                )
        except Exception as exc:
            logger.warning("[browser_lab] runner gif save failed: %s", exc)
    elif gif_rel:
        task.gif_path = gif_rel.lstrip("/")
    elif payload.get("gif_omitted"):
        logger.info("[browser_lab] task=%s gif omitted by runner", task_id)

    log = list(task.step_log or [])
    if event == "error":
        log.append({"type": "error", "message": task.error_message or "执行失败"})
    log = [e for e in log if e.get("type") != "done"]
    log.append(
        {
            "type": "done",
            "status": task.status,
            "summary": task.result_summary or "",
            "tokens_used": tokens,
        }
    )
    task.step_log = log
    task.steps_count = _count_step_events(log)
    _touch_runner_activity(task)
    await task.save()

    from app.modules.browser_lab.browser_lab_action_cache_runtime import (
        finish_browser_lab_side_effects,
        maybe_upsert_action_cache,
    )

    cfg = task.config_json or {}
    ai_config_id = cfg.get("ai_config_id") or task.ai_config_id
    try:
        from app.modules.ai.ai_scene_config import resolve_config_for_scene

        config = await resolve_config_for_scene("browser_lab", ai_config_id)
        await finish_browser_lab_side_effects(
            task,
            username=task.created_by or "",
            config=config,
            tokens=tokens,
        )
    except Exception as exc:
        logger.warning("[browser_lab] runner callback usage side effects: %s", exc)
    try:
        from app.modules.ai.ai_scene_config import resolve_config_for_scene

        config = await resolve_config_for_scene("browser_lab", ai_config_id)
        await maybe_upsert_action_cache(
            task,
            cfg=cfg,
            model_name=config.model or "",
        )
    except Exception as exc:
        logger.warning("[browser_lab] runner callback cache upsert: %s", exc)
    return task
