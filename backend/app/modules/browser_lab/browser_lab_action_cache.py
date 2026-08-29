"""BL-1 动作缓存存储：CRUD / upsert / 失效 / 命中统计。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.modules.browser_lab.browser_lab_action_cache_core import (
    SCHEMA_VERSION,
    apply_browser_lab_variables,
    assertions_are_usable,
    build_cache_key,
    build_config_fingerprint,
    extract_cacheable_actions,
    extract_final_assertions,
    extract_variable_keys,
    normalize_start_url,
    normalize_tags,
    normalize_task_text,
    sanitize_actions_for_api,
    sanitize_assertions_for_api,
    stringify_runtime_variables,
)
from app.models.ai import BrowserLabActionCache, BrowserLabCase

logger = logging.getLogger(__name__)

DEFAULT_MAX_AGE_DAYS = 30
STATUS_READY = "ready"
STATUS_STALE = "stale"
STATUS_DISABLED = "disabled"


def resolve_cache_options(cfg: dict | None) -> dict[str, Any]:
    cfg = cfg or {}
    on_fail = (cfg.get("on_replay_fail") or "fallback_agent").strip().lower()
    if on_fail not in ("fail", "fallback_agent"):
        on_fail = "fallback_agent"
    return {
        "use_action_cache": bool(cfg.get("use_action_cache", True)),
        "force_refresh_cache": bool(cfg.get("force_refresh_cache", False)),
        "on_replay_fail": on_fail,
        "ignore_query": bool(cfg.get("cache_ignore_query", False)),
        "max_age_days": int(cfg.get("cache_max_age_days") or DEFAULT_MAX_AGE_DAYS),
    }


def parse_env_id(cfg: dict | None) -> int | None:
    raw = (cfg or {}).get("env_id")
    if raw in (None, "", 0, "0"):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def load_browser_lab_runtime_variables(
    *,
    project_id: int,
    env_id: int | None = None,
    extra: dict | None = None,
) -> dict[str, Any]:
    """项目变量 < 环境变量 < 数据工厂标签 < Token 授权缓存 < cfg.variables。"""
    from app.modules.data_tools.tag_service import merge_execution_variables

    merged = await merge_execution_variables(project_id, env_id, extra)
    if project_id and env_id:
        from app.modules.http.api_auth_service import inject_auth_variables

        auth_vars, _err = await inject_auth_variables(
            project_id, env_id, merged, allow_refresh=False
        )
        if auth_vars:
            merged.update(auth_vars)
    return stringify_runtime_variables(merged)


async def resolve_browser_lab_run_context(
    *,
    project_id: int,
    start_url: str,
    task_text: str,
    cfg: dict | None = None,
) -> dict[str, Any]:
    cfg = cfg or {}
    extra = cfg.get("variables") if isinstance(cfg.get("variables"), dict) else None
    env_id = parse_env_id(cfg)
    variables = await load_browser_lab_runtime_variables(
        project_id=project_id,
        env_id=env_id,
        extra=extra,
    )
    return {
        "env_id": env_id,
        "variables": variables,
        "start_url": apply_browser_lab_variables(start_url or "", variables),
        "task_text": apply_browser_lab_variables(task_text or "", variables),
    }


def cache_governance_hint(row: BrowserLabActionCache) -> str:
    if int(row.schema_version or 0) != SCHEMA_VERSION:
        return "缓存版本不兼容，建议强制刷新或清除后重跑"
    if row.status == STATUS_STALE:
        return "缓存已失效，下次执行将走 Agent 并覆盖写入"
    if row.status == STATUS_DISABLED:
        return "缓存已禁用"
    return ""


async def _case_tags(case_id: int | None) -> str:
    if not case_id:
        return ""
    case = await BrowserLabCase.get_or_none(id=case_id, is_del=False)
    return (case.tags or "") if case else ""


async def compute_cache_key_for_task(
    *,
    project_id: int,
    case_id: int | None,
    start_url: str,
    task_text: str,
    tags: str | None = None,
    ignore_query: bool = False,
) -> str:
    resolved_tags = tags if tags is not None else await _case_tags(case_id)
    return build_cache_key(
        project_id=project_id,
        case_id=case_id,
        start_url=start_url,
        task_text=task_text,
        tags=resolved_tags,
        variable_keys=extract_variable_keys(task_text),
        ignore_query=ignore_query,
    )


async def get_ready_cache(
    *,
    project_id: int,
    case_id: int | None,
    start_url: str,
    task_text: str,
    tags: str | None = None,
    ignore_query: bool = False,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> tuple[Optional[BrowserLabActionCache], str]:
    """返回 (row, reason)。reason: ready | cache_miss | cache_stale | cache_expired | schema_mismatch。"""
    from app.modules.browser_lab.browser_lab_action_cache_core import SCHEMA_VERSION

    cache_key = await compute_cache_key_for_task(
        project_id=project_id,
        case_id=case_id,
        start_url=start_url,
        task_text=task_text,
        tags=tags,
        ignore_query=ignore_query,
    )
    row = await BrowserLabActionCache.get_or_none(cache_key=cache_key, project_id=project_id)
    if not row:
        return None, "cache_miss"
    if row.status == STATUS_STALE:
        return None, "cache_stale"
    if row.status == STATUS_DISABLED:
        return None, "cache_miss"
    if row.status != STATUS_READY:
        return None, "cache_miss"
    if int(row.schema_version or 0) != SCHEMA_VERSION:
        return None, "schema_mismatch"
    actions = row.actions_json if isinstance(row.actions_json, list) else []
    assertions = row.assertions_json if isinstance(row.assertions_json, dict) else {}
    if not actions or not assertions_are_usable(assertions):
        return None, "cache_miss"
    if max_age_days > 0 and row.updated_at:
        updated = row.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - updated > timedelta(days=max_age_days):
            row.status = STATUS_STALE
            await row.save(update_fields=["status", "updated_at"])
            return None, "cache_expired"
    return row, "ready"


async def mark_stale_by_key(cache_key: str, *, project_id: int | None = None) -> int:
    """强制刷新：置 stale，保留 hit_count，供后续 upsert 复用同行。"""
    qs = BrowserLabActionCache.filter(cache_key=cache_key)
    if project_id is not None:
        qs = qs.filter(project_id=project_id)
    return await qs.update(status=STATUS_STALE)


async def invalidate_by_key(cache_key: str, *, project_id: int | None = None) -> int:
    qs = BrowserLabActionCache.filter(cache_key=cache_key)
    if project_id is not None:
        qs = qs.filter(project_id=project_id)
    return await qs.delete()


async def delete_case_cache(case_id: int, *, project_id: int | None = None) -> int:
    qs = BrowserLabActionCache.filter(case_id=case_id)
    if project_id is not None:
        qs = qs.filter(project_id=project_id)
    return await qs.delete()


async def upsert_cache_from_step_log(
    *,
    project_id: int,
    case_id: int | None,
    start_url: str,
    task_text: str,
    step_log: list | None,
    source_task_id: int | None = None,
    tags: str | None = None,
    ignore_query: bool = False,
    config_fingerprint: str = "",
    include_weak: bool = False,
    last_agent_tokens: int = 0,
) -> Optional[BrowserLabActionCache]:
    actions = extract_cacheable_actions(
        step_log,
        include_weak=include_weak,
        compress=True,
        task_text=task_text,
    )
    assertions = extract_final_assertions(step_log, start_url=start_url)
    if not actions:
        logger.info("[browser_lab_cache] skip upsert: no cacheable actions task=%s", source_task_id)
        return None
    if not assertions_are_usable(assertions):
        logger.info("[browser_lab_cache] skip upsert: no usable assertions task=%s", source_task_id)
        return None

    # 估算省 token：命中时读取（下划线前缀不参与断言）
    if last_agent_tokens > 0:
        assertions = dict(assertions)
        assertions["_last_agent_tokens"] = int(last_agent_tokens)

    resolved_tags = tags if tags is not None else await _case_tags(case_id)
    variable_keys = extract_variable_keys(task_text)
    cache_key = build_cache_key(
        project_id=project_id,
        case_id=case_id,
        start_url=start_url,
        task_text=task_text,
        tags=resolved_tags,
        variable_keys=variable_keys,
        ignore_query=ignore_query,
    )
    now = datetime.now(timezone.utc)
    defaults = {
        "project_id": project_id,
        "case_id": case_id,
        "start_url": normalize_start_url(start_url, ignore_query=ignore_query)[:500],
        "task_text": normalize_task_text(task_text),
        "tags_json": normalize_tags(resolved_tags),
        "variable_keys_json": variable_keys,
        "actions_json": actions,
        "assertions_json": assertions,
        "status": STATUS_READY,
        "source_task_id": source_task_id,
        "config_fingerprint": (config_fingerprint or "")[:32],
        "schema_version": SCHEMA_VERSION,
        "updated_at": now,
    }
    row = await BrowserLabActionCache.get_or_none(cache_key=cache_key)
    if row:
        # 复用同行：保留 hit_count / last_hit_at，避免全量 save 把并发命中计数写回去
        for k, v in defaults.items():
            setattr(row, k, v)
        await row.save(update_fields=list(defaults.keys()))
        return row
    return await BrowserLabActionCache.create(
        cache_key=cache_key,
        hit_count=0,
        last_hit_at=None,
        created_at=now,
        **defaults,
    )


def cached_token_saved_estimate(row: BrowserLabActionCache) -> int:
    assertions = row.assertions_json if isinstance(row.assertions_json, dict) else {}
    try:
        return max(0, int(assertions.get("_last_agent_tokens") or 0))
    except (TypeError, ValueError):
        return 0


async def mark_cache_hit(row: BrowserLabActionCache) -> None:
    row.hit_count = int(row.hit_count or 0) + 1
    row.last_hit_at = datetime.now(timezone.utc)
    await row.save(update_fields=["hit_count", "last_hit_at", "updated_at"])


def cache_row_to_summary(row: BrowserLabActionCache, *, include_actions: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": row.id,
        "cache_key": row.cache_key,
        "project_id": row.project_id,
        "case_id": row.case_id,
        "start_url": row.start_url,
        "task_text": row.task_text,
        "tags": row.tags_json or [],
        "variable_keys": row.variable_keys_json or [],
        "status": row.status,
        "hit_count": row.hit_count,
        "last_hit_at": row.last_hit_at.isoformat() if row.last_hit_at else None,
        "source_task_id": row.source_task_id,
        "config_fingerprint": row.config_fingerprint or "",
        "schema_version": row.schema_version,
        "actions_count": len(row.actions_json or []) if isinstance(row.actions_json, list) else 0,
        "assertions": sanitize_assertions_for_api(
            row.assertions_json if isinstance(row.assertions_json, dict) else {}
        ),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "hint": cache_governance_hint(row),
        "token_saved_estimate": cached_token_saved_estimate(row),
    }
    if include_actions:
        data["actions"] = sanitize_actions_for_api(
            row.actions_json if isinstance(row.actions_json, list) else []
        )
    return data


async def project_cache_stats(project_id: int) -> dict[str, Any]:
    rows = await BrowserLabActionCache.filter(project_id=project_id).all()
    ready = [r for r in rows if r.status == STATUS_READY]
    total_hits = sum(int(r.hit_count or 0) for r in rows)
    return {
        "project_id": project_id,
        "cache_entries": len(rows),
        "ready_entries": len(ready),
        "total_hits": total_hits,
        "stale_or_disabled": len(rows) - len(ready),
        "top_hits": [
            {
                "id": r.id,
                "case_id": r.case_id,
                "hit_count": r.hit_count,
                "task_text": (r.task_text or "")[:80],
                "last_hit_at": r.last_hit_at.isoformat() if r.last_hit_at else None,
            }
            for r in sorted(rows, key=lambda x: int(x.hit_count or 0), reverse=True)[:10]
        ],
    }


def build_run_fingerprint(*, ai_config_id: int | None, use_vision: bool, max_steps: int, model: str = "") -> str:
    return build_config_fingerprint(
        ai_config_id=ai_config_id,
        use_vision=use_vision,
        max_steps=max_steps,
        model=model,
    )


_RUNTIME_CACHE_KEYS = (
    "cache_status",
    "cache_hit",
    "cache_entry_id",
    "cache_error",
    "cache_actions_count",
    "token_saved_estimate",
    "_cache_fallback_used",
)

# 上次 Runner 执行写入 config_json 的字段；重跑须剥离，否则心跳检测会误用旧时间戳
_RUNNER_RUNTIME_KEYS = (
    "last_runner_heartbeat",
    "dispatch_status",
)


def sanitize_run_config(cfg: dict | None) -> dict[str, Any]:
    """重跑时去掉上次运行写入的缓存/Runner 元数据，避免误标命中或心跳误判。"""
    out = dict(cfg or {})
    for key in (*_RUNTIME_CACHE_KEYS, *_RUNNER_RUNTIME_KEYS):
        out.pop(key, None)
    return out
