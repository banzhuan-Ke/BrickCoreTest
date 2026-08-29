"""BL-1：runner 侧动作缓存编排（查缓存 / 回放 / 写缓存）。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from app.models.ai import BrowserLabCase, BrowserLabTask

logger = logging.getLogger(__name__)

_TASK_FINISH_FIELDS = [
    "status",
    "error_message",
    "result_summary",
    "tokens_used",
    "engine",
    "finished_at",
    "config_json",
]


async def finish_browser_lab_side_effects(
    task: BrowserLabTask,
    *,
    username: str,
    config: Any,
    tokens: int = 0,
) -> None:
    if task.case_id:
        case = await BrowserLabCase.get_or_none(id=task.case_id, is_del=False)
        if case:
            case.run_count = int(case.run_count or 0) + 1
            case.last_run_at = task.finished_at
            case.last_status = task.status
            await case.save(update_fields=["run_count", "last_run_at", "last_status"])

    from app.modules.browser_lab.browser_lab_usage import ensure_browser_lab_usage_logged

    if int(tokens or 0) > 0 and int(task.tokens_used or 0) < int(tokens):
        task.tokens_used = int(tokens)
        await task.save(update_fields=["tokens_used"])

    await ensure_browser_lab_usage_logged(
        task,
        config=config,
        tokens=tokens,
        username=username,
    )


async def merge_task_cache_meta(task: BrowserLabTask, **meta: Any) -> BrowserLabTask:
    cfg = dict(task.config_json or {})
    cfg.update(meta)
    task.config_json = cfg
    await task.save(update_fields=["config_json"])
    return task


def _is_user_stop(ex: Exception, task_id: int, should_stop: Callable[[int], bool]) -> bool:
    if should_stop(task_id):
        return True
    return "用户已停止" in str(ex)


async def try_action_cache_path(
    task: BrowserLabTask,
    *,
    task_id: int,
    username: str,
    config: Any,
    cfg: dict[str, Any],
    append_step: Callable,
    should_stop: Callable[[int], bool],
    clear_stop: Callable[[int], None],
) -> str:
    """返回 hit（已收尾）/ miss / fallback。"""
    from app.modules.browser_lab.browser_lab_action_cache import (
        cached_token_saved_estimate,
        compute_cache_key_for_task,
        get_ready_cache,
        mark_cache_hit,
        mark_stale_by_key,
        resolve_browser_lab_run_context,
        resolve_cache_options,
    )
    from app.modules.browser_lab.browser_lab_action_cache_core import (
        extract_variable_keys,
        unresolved_value_from_keys,
    )
    from app.modules.browser_lab.browser_lab_cache_replay import replay_cached_actions

    opts = resolve_cache_options(cfg)
    if not opts["use_action_cache"]:
        await merge_task_cache_meta(task, cache_status="disabled", cache_hit=False)
        return "miss"

    if opts["force_refresh_cache"]:
        cache_key = await compute_cache_key_for_task(
            project_id=task.project_id,
            case_id=task.case_id,
            start_url=task.start_url,
            task_text=task.task_text,
            ignore_query=opts["ignore_query"],
        )
        # 置 stale 保留 hit_count，后续 Agent 成功 upsert 复用同行
        await mark_stale_by_key(cache_key, project_id=task.project_id)
        await merge_task_cache_meta(task, cache_status="force_refresh", cache_hit=False)
        return "miss"

    row, lookup_reason = await get_ready_cache(
        project_id=task.project_id,
        case_id=task.case_id,
        start_url=task.start_url,
        task_text=task.task_text,
        ignore_query=opts["ignore_query"],
        max_age_days=opts["max_age_days"],
    )
    if not row:
        await merge_task_cache_meta(
            task,
            cache_status=lookup_reason or "cache_miss",
            cache_hit=False,
        )
        return "miss"

    actions = row.actions_json if isinstance(row.actions_json, list) else []
    run_ctx = await resolve_browser_lab_run_context(
        project_id=task.project_id,
        start_url=task.start_url,
        task_text=task.task_text,
        cfg=cfg,
    )
    variables = run_ctx["variables"]
    resolved_start = run_ctx["start_url"] or task.start_url
    missing_vars = unresolved_value_from_keys(actions, variables)
    missing_vars.extend(
        k for k in extract_variable_keys(resolved_start) if k not in missing_vars
    )
    if missing_vars:
        await merge_task_cache_meta(
            task,
            cache_status="cache_missing_vars",
            cache_hit=False,
            cache_entry_id=row.id,
            cache_error=f"缺少变量: {','.join(missing_vars[:8])}",
        )
        if opts["on_replay_fail"] == "fail":
            task = await BrowserLabTask.get(id=task_id)
            cfg2 = dict(task.config_json or {})
            cfg2["cache_status"] = "cache_missing_vars"
            cfg2["cache_hit"] = False
            cfg2["cache_entry_id"] = row.id
            task.config_json = cfg2
            task.status = "failed"
            task.error_message = f"缓存无法回放，缺少变量: {','.join(missing_vars[:8])}"[:4000]
            task.result_summary = task.error_message
            task.tokens_used = 0
            task.finished_at = datetime.now(timezone.utc)
            await task.save(update_fields=_TASK_FINISH_FIELDS)
            await append_step(
                task_id,
                {
                    "type": "done",
                    "status": "failed",
                    "summary": task.error_message,
                    "error_message": task.error_message,
                    "tokens_used": 0,
                    "cache_status": "cache_missing_vars",
                    "cache_hit": False,
                },
            )
            await finish_browser_lab_side_effects(task, username=username, config=config, tokens=0)
            clear_stop(task_id)
            return "hit"
        return "miss"

    await append_step(
        task_id,
        {
            "type": "step",
            "index": 0,
            "url": resolved_start,
            "title": "",
            "next_goal": "命中动作缓存，开始零 token 回放…",
            "actions": [],
            "cache_replay": True,
        },
    )

    async def on_step(event: dict[str, Any]) -> None:
        await append_step(task_id, event)

    try:
        result = await replay_cached_actions(
            start_url=resolved_start,
            actions=actions,
            assertions=row.assertions_json if isinstance(row.assertions_json, dict) else {},
            variables=variables,
            on_step=on_step,
            should_stop=lambda: should_stop(task_id),
            schema_version=row.schema_version,
        )
        if should_stop(task_id):
            raise RuntimeError("用户已停止")
        await mark_cache_hit(row)
        saved_tokens = cached_token_saved_estimate(row)
        task = await BrowserLabTask.get(id=task_id)
        task.status = "done"
        task.result_summary = (result.get("message") or "动作缓存回放成功")[:8000]
        task.error_message = None
        task.tokens_used = 0
        task.engine = "action_cache"
        task.finished_at = datetime.now(timezone.utc)
        cfg2 = dict(task.config_json or {})
        cfg2["cache_status"] = "cache_hit"
        cfg2["cache_hit"] = True
        cfg2["cache_entry_id"] = row.id
        cfg2["token_saved_estimate"] = saved_tokens
        task.config_json = cfg2
        await task.save(update_fields=_TASK_FINISH_FIELDS)
        await append_step(
            task_id,
            {
                "type": "done",
                "status": task.status,
                "summary": task.result_summary or "",
                "error_message": task.error_message or "",
                "tokens_used": 0,
                "cache_status": "cache_hit",
                "cache_hit": True,
                "token_saved_estimate": saved_tokens,
            },
        )
        await finish_browser_lab_side_effects(task, username=username, config=config, tokens=0)
        clear_stop(task_id)
        return "hit"
    except Exception as ex:
        logger.warning("[browser_lab] cache replay failed task=%s: %s", task_id, ex)
        task = await BrowserLabTask.get(id=task_id)
        if _is_user_stop(ex, task_id, should_stop):
            cfg2 = dict(task.config_json or {})
            cfg2["cache_status"] = "stopped"
            cfg2["cache_hit"] = False
            cfg2["cache_entry_id"] = row.id
            task.config_json = cfg2
            task.status = "stopped"
            task.error_message = "用户已停止"
            task.result_summary = "用户已停止"
            task.tokens_used = 0
            task.finished_at = datetime.now(timezone.utc)
            await task.save(update_fields=_TASK_FINISH_FIELDS)
            await append_step(
                task_id,
                {
                    "type": "done",
                    "status": "stopped",
                    "summary": "用户已停止",
                    "error_message": "用户已停止",
                    "tokens_used": 0,
                    "cache_status": "stopped",
                    "cache_hit": False,
                },
            )
            await finish_browser_lab_side_effects(task, username=username, config=config, tokens=0)
            clear_stop(task_id)
            return "hit"

        # 不可用 type=error：前端 SSE 会当成终态断开，导致降级 Agent 的实时日志丢失
        await append_step(
            task_id,
            {
                "type": "step",
                "index": 0,
                "url": task.start_url,
                "title": "",
                "next_goal": f"缓存回放失败，准备降级 Agent：{ex}",
                "actions": [],
                "cache_replay": True,
                "cache_status": "cache_replay_failed",
            },
        )
        await merge_task_cache_meta(
            task,
            cache_status="cache_replay_failed",
            cache_hit=False,
            cache_entry_id=row.id,
            cache_error=str(ex)[:500],
        )
        if opts["on_replay_fail"] == "fallback_agent" and not cfg.get("_cache_fallback_used"):
            cfg3 = dict(task.config_json or {})
            cfg3["_cache_fallback_used"] = True
            task.config_json = cfg3
            await task.save(update_fields=["config_json"])
            return "fallback"

        task.status = "failed"
        task.error_message = f"缓存回放失败: {ex}"[:4000]
        task.result_summary = task.error_message
        task.tokens_used = 0
        task.finished_at = datetime.now(timezone.utc)
        await task.save(update_fields=_TASK_FINISH_FIELDS)
        await append_step(
            task_id,
            {
                "type": "done",
                "status": "failed",
                "summary": task.error_message,
                "error_message": task.error_message,
                "tokens_used": 0,
                "cache_status": "cache_replay_failed",
            },
        )
        await finish_browser_lab_side_effects(task, username=username, config=config, tokens=0)
        clear_stop(task_id)
        return "hit"


async def maybe_upsert_action_cache(
    task: BrowserLabTask,
    *,
    cfg: dict[str, Any],
    model_name: str = "",
) -> None:
    if task.status != "done":
        return
    from app.modules.browser_lab.browser_lab_action_cache import (
        build_run_fingerprint,
        resolve_cache_options,
        upsert_cache_from_step_log,
    )

    opts = resolve_cache_options(cfg)
    if not opts["use_action_cache"]:
        return
    try:
        row = await upsert_cache_from_step_log(
            project_id=task.project_id,
            case_id=task.case_id,
            start_url=task.start_url,
            task_text=task.task_text,
            step_log=task.step_log,
            source_task_id=task.id,
            ignore_query=opts["ignore_query"],
            config_fingerprint=build_run_fingerprint(
                ai_config_id=task.ai_config_id,
                use_vision=bool(cfg.get("use_vision", True)),
                max_steps=int(cfg.get("max_steps") or 0),
                model=model_name,
            ),
            include_weak=False,
            last_agent_tokens=int(task.tokens_used or 0),
        )
        if row:
            status = (task.config_json or {}).get("cache_status") or "cache_written"
            if status == "cache_replay_failed":
                status = "cache_refreshed"
            elif status in (
                "cache_miss",
                "force_refresh",
                "cache_expired",
                "cache_stale",
                "schema_mismatch",
                "cache_missing_vars",
                None,
                "",
            ):
                status = "cache_written"
            await merge_task_cache_meta(
                task,
                cache_status=status,
                cache_entry_id=row.id,
                cache_actions_count=len(row.actions_json or [])
                if isinstance(row.actions_json, list)
                else 0,
                token_saved_estimate=0,
            )
            logger.info("[browser_lab] action cache upserted task=%s entry=%s", task.id, row.id)
    except Exception as ex:
        logger.warning("[browser_lab] action cache upsert failed: %s", ex)
