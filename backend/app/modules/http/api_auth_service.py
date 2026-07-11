"""
API Token 授权：缓存、刷新、执行前注入变量。
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

from app.core.infra.redis_client import redis_cli
from app.models.http import ApiAuthConfig, ApiDefinition
from app.models.sys import Environment, Project

logger = logging.getLogger(__name__)

REFRESH_LOCK_TTL = 60
REFRESH_WAIT_TIMEOUT = 30
REFRESH_POLL_INTERVAL = 0.3


def _naive_dt(dt: Optional[datetime]) -> Optional[datetime]:
    """统一为 naive datetime，避免 DB 返回 aware 与 now() 相减报错"""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def _now_naive() -> datetime:
    return datetime.now()


DEFAULT_CUSTOM_CODE = '''def auth(context):
    """
    必须返回 dict，key 作为变量名供 ${{key}} 引用。

    context 可用字段：
      - environment_id / project_id / host
      - variables: 项目 global_vars + 环境 global_vars 合并结果

    典型用法：从环境全局变量读取预置 token，或直接返回固定值。
    """
    variables = context.get("variables") or {}
    return {
        "token": variables.get("digi_token") or "在此填写 token 或从 variables 取值",
    }
'''


def auth_config_to_dict(cfg: ApiAuthConfig, env_name: str = "", api_name: str = "") -> dict[str, Any]:
    cache = cfg.cache_data if isinstance(cfg.cache_data, dict) else {}
    expires_at = _naive_dt(cfg.cache_expires_at)
    remaining = None
    if expires_at:
        delta = expires_at - _now_naive()
        remaining = max(0, int(delta.total_seconds() / 60))
    return {
        "id": cfg.id,
        "project_id": cfg.project_id,
        "environment_id": cfg.environment_id,
        "environment_name": env_name,
        "name": cfg.name,
        "auth_type": cfg.auth_type,
        "login_api_id": cfg.login_api_id,
        "login_api_name": api_name,
        "extractors": cfg.extractors or [],
        "custom_code": cfg.custom_code or "",
        "ttl_minutes": cfg.ttl_minutes,
        "refresh_before_minutes": cfg.refresh_before_minutes,
        "refresh_mode": cfg.refresh_mode,
        "is_enabled": cfg.is_enabled,
        "cache_data": cache,
        "cache_expires_at": cfg.cache_expires_at.strftime("%Y-%m-%d %H:%M:%S") if cfg.cache_expires_at else None,
        "cache_remaining_minutes": remaining,
        "last_refresh_time": cfg.last_refresh_time.strftime("%Y-%m-%d %H:%M:%S") if cfg.last_refresh_time else None,
        "last_refresh_error": cfg.last_refresh_error or "",
        "create_by": cfg.create_by,
        "update_by": cfg.update_by or "",
        "create_time": cfg.create_time.strftime("%Y-%m-%d %H:%M:%S") if cfg.create_time else "",
        "update_time": cfg.update_time.strftime("%Y-%m-%d %H:%M:%S") if cfg.update_time else "",
    }


def _cache_needs_refresh(cfg: ApiAuthConfig, now: Optional[datetime] = None) -> bool:
    now = _naive_dt(now) or _now_naive()
    if not cfg.cache_data:
        return True
    expires_at = _naive_dt(cfg.cache_expires_at)
    if not expires_at:
        return True
    refresh_at = expires_at - timedelta(minutes=cfg.refresh_before_minutes or 0)
    return now >= refresh_at


async def _acquire_refresh_lock(config_id: int) -> bool:
    key = f"api_auth_refresh_lock:{config_id}"
    return bool(await redis_cli.set(key, "1", nx=True, ex=REFRESH_LOCK_TTL))


async def _release_refresh_lock(config_id: int) -> None:
    await redis_cli.delete(f"api_auth_refresh_lock:{config_id}")


async def _wait_for_refresh(config_id: int) -> bool:
    deadline = time.monotonic() + REFRESH_WAIT_TIMEOUT
    while time.monotonic() < deadline:
        if not await redis_cli.exists(f"api_auth_refresh_lock:{config_id}"):
            return True
        await asyncio.sleep(REFRESH_POLL_INTERVAL)
    return False


async def _execute_login_api(
    api: ApiDefinition,
    env: Environment,
    extractors: list[dict],
    base_variables: dict[str, Any],
) -> dict[str, Any]:
    from app.core.case.variable_resolver import VariableResolver
    from app.routers.http.utils import (
        build_api_url,
        build_form_data_multipart,
        extract_variables,
        prepare_httpx_headers,
        replace_body_fields_with_detail,
        replace_variables_with_detail,
        resolve_body_fields,
    )

    api_headers = api.headers or {}
    if isinstance(api_headers, list):
        api_headers = {h.get("key", ""): h.get("value", "") for h in api_headers if h.get("key")}

    api_params = api.params or []
    if isinstance(api_params, dict):
        api_params = [{"name": k, "value": v} for k, v in api_params.items()]

    base_url = api.base_url or env.host
    url = build_api_url(base_url, api.path)
    params = {p.get("name", ""): p.get("value", "") for p in api_params if p.get("name")}
    body = api.body or {}
    body_type = api.body_type or "json"
    body_fields = resolve_body_fields([], api.body_fields)

    variables = dict(base_variables or {})
    resolver = VariableResolver(variables)
    url, _ = replace_variables_with_detail(url, variables, "url", resolver=resolver)
    headers, _ = replace_variables_with_detail(api_headers, variables, "headers", resolver=resolver)
    params, _ = replace_variables_with_detail(params, variables, "params", resolver=resolver)
    body, _ = replace_variables_with_detail(body, variables, "body", resolver=resolver)
    body_fields, _ = replace_body_fields_with_detail(body_fields, variables, resolver=resolver)

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        method = api.method.upper()
        kwargs: dict[str, Any] = {"headers": prepare_httpx_headers(headers), "params": params}
        if method in ("POST", "PUT", "PATCH"):
            if body_type in ("json", "xml") and isinstance(body, (dict, list)):
                kwargs["json"] = body
            elif body_type == "form-data":
                from app.core.infra.minio_client import API_FILE_BUCKET
                kwargs["files"] = build_form_data_multipart(body_fields, API_FILE_BUCKET, use_bytes_io=True)
            elif body is not None:
                kwargs["data"] = body
        response = await client.request(method, url, **kwargs)

    try:
        response_body = response.json()
    except Exception:
        response_body = response.text

    if response.status_code >= 400:
        raise RuntimeError(f"登录接口 HTTP {response.status_code}: {str(response_body)[:500]}")

    extracted: dict[str, Any] = {}
    extracted, _ = extract_variables(response_body, extractors or [], headers=response.headers)
    if not extracted:
        raise RuntimeError("登录接口未提取到任何授权变量，请检查提取规则")

    return extracted


def _run_custom_auth(code: str, context: dict[str, Any]) -> dict[str, Any]:
    from RestrictedPython import compile_restricted, safe_builtins, safe_globals
    from RestrictedPython.Guards import guarded_iter_unpack_sequence, safer_getattr
    from RestrictedPython.Eval import default_guarded_getitem, default_guarded_getiter

    local_vars: dict[str, Any] = {"context": dict(context)}
    globals_dict = dict(safe_globals)
    globals_dict["__builtins__"] = safe_builtins
    globals_dict["_getattr_"] = safer_getattr
    globals_dict["_getitem_"] = default_guarded_getitem
    globals_dict["_getiter_"] = default_guarded_getiter
    globals_dict["_iter_unpack_sequence_"] = guarded_iter_unpack_sequence
    globals_dict["_write_"] = lambda obj: obj
    globals_dict["_inplacevar_"] = lambda op, val, expr: val

    compiled = compile_restricted(code, filename="<auth>", mode="exec")
    exec(compiled, globals_dict, local_vars)  # noqa: S102
    auth_fn = local_vars.get("auth")
    if not callable(auth_fn):
        raise RuntimeError("自定义代码必须定义 auth(context) 函数")
    result = auth_fn(context)
    if not isinstance(result, dict):
        raise RuntimeError("auth(context) 必须返回 dict")
    cleaned = {k: v for k, v in result.items() if v is not None}
    if not cleaned:
        raise RuntimeError("auth(context) 返回了空 dict")
    return cleaned


async def preview_auth_config(
    *,
    project_id: int,
    environment_id: int,
    auth_type: str,
    login_api_id: Optional[int] = None,
    extractors: Optional[list[dict]] = None,
    custom_code: Optional[str] = None,
    base_variables: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """调试授权：执行登录/自定义代码并返回变量，不写入缓存"""
    env = await Environment.get_or_none(id=environment_id, project_id=project_id, is_del=False)
    if not env:
        raise RuntimeError("环境不存在")

    from app.core.shared.global_vars_validate import flatten_global_vars

    variables = dict(base_variables or {})
    project = await Project.get_or_none(id=project_id, is_del=False)
    if project and project.global_vars:
        variables = {**flatten_global_vars(project.global_vars), **variables}
    if env.global_vars:
        variables = {**flatten_global_vars(env.global_vars), **variables}

    context = {
        "environment_id": environment_id,
        "project_id": project_id,
        "host": env.host or "",
        "variables": variables,
    }

    if auth_type == "custom_code":
        code = (custom_code or "").strip() or DEFAULT_CUSTOM_CODE
        return _run_custom_auth(code, context)

    if not login_api_id:
        raise RuntimeError("请配置登录接口")
    api = await ApiDefinition.get_or_none(id=login_api_id, is_del=False)
    if not api:
        raise RuntimeError("登录接口不存在")
    return await _execute_login_api(api, env, extractors or [], variables)


async def refresh_auth_config(
    cfg: ApiAuthConfig,
    base_variables: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    env = await Environment.get_or_none(id=cfg.environment_id, is_del=False)
    if not env:
        raise RuntimeError("环境不存在")

    context = {
        "environment_id": cfg.environment_id,
        "project_id": cfg.project_id,
        "host": env.host or "",
        "variables": dict(base_variables or {}),
    }
    from app.core.shared.global_vars_validate import flatten_global_vars

    variables = dict(base_variables or {})
    project = await Project.get_or_none(id=cfg.project_id, is_del=False)
    if project and project.global_vars:
        variables = {**flatten_global_vars(project.global_vars), **variables}
    if env.global_vars:
        variables = {**flatten_global_vars(env.global_vars), **variables}

    if cfg.auth_type == "custom_code":
        code = (cfg.custom_code or "").strip() or DEFAULT_CUSTOM_CODE
        cache_data = _run_custom_auth(code, context)
    else:
        if not cfg.login_api_id:
            raise RuntimeError("请配置登录接口")
        api = await ApiDefinition.get_or_none(id=cfg.login_api_id, is_del=False)
        if not api:
            raise RuntimeError("登录接口不存在")
        cache_data = await _execute_login_api(api, env, cfg.extractors or [], variables)

    now = _now_naive()
    cfg.cache_data = cache_data
    cfg.cache_expires_at = now + timedelta(minutes=cfg.ttl_minutes or 1440)
    cfg.last_refresh_time = now
    cfg.last_refresh_error = None
    await cfg.save(
        update_fields=["cache_data", "cache_expires_at", "last_refresh_time", "last_refresh_error", "update_time"]
    )
    return cache_data


async def ensure_auth_cache(
    cfg: ApiAuthConfig,
    base_variables: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not _cache_needs_refresh(cfg):
        return dict(cfg.cache_data or {})

    got_lock = await _acquire_refresh_lock(cfg.id)
    if got_lock:
        try:
            await cfg.refresh_from_db()
            if not _cache_needs_refresh(cfg):
                return dict(cfg.cache_data or {})
            return await refresh_auth_config(cfg, base_variables)
        finally:
            await _release_refresh_lock(cfg.id)

    waited = await _wait_for_refresh(cfg.id)
    await cfg.refresh_from_db()
    if _cache_needs_refresh(cfg):
        msg = "等待其他执行者刷新授权超时" if not waited else "授权刷新后仍无效"
        raise RuntimeError(msg)
    return dict(cfg.cache_data or {})


async def get_enabled_auth_config(project_id: int, environment_id: int) -> Optional[ApiAuthConfig]:
    return await ApiAuthConfig.filter(
        project_id=project_id,
        environment_id=environment_id,
        is_enabled=True,
        is_del=False,
    ).order_by("-update_time").first()


async def inject_auth_variables(
    project_id: int,
    environment_id: int,
    variables: dict[str, Any],
) -> tuple[dict[str, Any], Optional[str]]:
    """执行前注入授权变量，返回 (auth_vars, error)"""
    cfg = await get_enabled_auth_config(project_id, environment_id)
    if not cfg:
        return {}, None
    try:
        cache = await ensure_auth_cache(cfg, variables)
        return cache, None
    except Exception as e:
        err = str(e)
        cfg.last_refresh_error = err
        await cfg.save(update_fields=["last_refresh_error", "update_time"])
        logger.warning("[api_auth] 刷新失败 config=%s: %s", cfg.id, err)
        return {}, err
