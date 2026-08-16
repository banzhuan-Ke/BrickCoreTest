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


def expected_auth_variable_names(cfg: ApiAuthConfig) -> list[str]:
    """从提取器配置得到执行时应收齐的变量名（自定义代码无固定名，返回空列表）。"""
    names: list[str] = []
    for raw in cfg.extractors or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _cache_has_expected_keys(cfg: ApiAuthConfig) -> bool:
    cache = cfg.cache_data if isinstance(cfg.cache_data, dict) else {}
    if not cache:
        return False
    expected = expected_auth_variable_names(cfg)
    if not expected:
        # 自定义代码：只要缓存非空即可
        return any(v not in (None, "") for v in cache.values())
    for key in expected:
        val = cache.get(key)
        if val is None or val == "":
            return False
    return True


def _cache_needs_refresh(cfg: ApiAuthConfig, now: Optional[datetime] = None) -> bool:
    now = _naive_dt(now) or _now_naive()
    if not _cache_has_expected_keys(cfg):
        return True
    expires_at = _naive_dt(cfg.cache_expires_at)
    if not expires_at:
        return True
    refresh_at = expires_at - timedelta(minutes=cfg.refresh_before_minutes or 0)
    return now >= refresh_at


async def _acquire_refresh_lock(config_id: int) -> bool:
    key = f"api_auth_refresh_lock:{config_id}"
    try:
        return bool(await redis_cli.set(key, "1", nx=True, ex=REFRESH_LOCK_TTL))
    except Exception as e:
        logger.warning("[api_auth] 获取刷新锁失败 config=%s: %s，改为直接刷新", config_id, e)
        return True


async def _release_refresh_lock(config_id: int) -> None:
    try:
        await redis_cli.delete(f"api_auth_refresh_lock:{config_id}")
    except Exception as e:
        logger.warning("[api_auth] 释放刷新锁失败 config=%s: %s", config_id, e)


async def _wait_for_refresh(config_id: int) -> bool:
    deadline = time.monotonic() + REFRESH_WAIT_TIMEOUT
    while time.monotonic() < deadline:
        try:
            if not await redis_cli.exists(f"api_auth_refresh_lock:{config_id}"):
                return True
        except Exception:
            return False
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
    if not _cache_needs_refresh(cfg):
        return dict(cfg.cache_data or {})
    # 等待其他执行者超时/失败后仍无效：自行刷新，避免用例静默拿不到 token
    logger.warning(
        "[api_auth] 锁等待后缓存仍无效 config=%s waited=%s，改为本进程刷新",
        cfg.id,
        waited,
    )
    return await refresh_auth_config(cfg, base_variables)


async def get_enabled_auth_config(project_id: int, environment_id: int) -> Optional[ApiAuthConfig]:
    try:
        pid = int(project_id)
        eid = int(environment_id)
    except (TypeError, ValueError):
        return None
    return await ApiAuthConfig.filter(
        project_id=pid,
        environment_id=eid,
        is_enabled=True,
        is_del=False,
    ).order_by("-update_time").first()


async def inject_auth_variables(
    project_id: int,
    environment_id: int,
    variables: dict[str, Any],
    *,
    allow_refresh: bool = True,
) -> tuple[dict[str, Any], Optional[str]]:
    """注入授权变量，返回 (auth_vars, error)。

    allow_refresh=False 时仅读取已有缓存，不触发登录刷新（供变量预览等轻量接口）。
    """
    cfg = await get_enabled_auth_config(project_id, environment_id)
    if not cfg:
        logger.info(
            "[api_auth] 未找到启用中的授权配置 project_id=%s environment_id=%s",
            project_id,
            environment_id,
        )
        return {}, None

    if not allow_refresh:
        cache = dict(cfg.cache_data or {}) if isinstance(cfg.cache_data, dict) else {}
        cleaned = {k: v for k, v in cache.items() if v not in (None, "")}
        if not cleaned:
            hint = f"授权「{cfg.name}」暂无可用缓存，预览不自动登录；请到 Token 授权页「刷新」或「调试」"
            if cfg.last_refresh_error:
                hint = f"{hint}（最近错误：{cfg.last_refresh_error}）"
            return {}, hint
        if _cache_needs_refresh(cfg):
            return cleaned, (
                f"授权「{cfg.name}」缓存将过期或缺少提取键，预览仅展示当前缓存；"
                "用例执行时会自动刷新"
            )
        return cleaned, None

    try:
        cache = await ensure_auth_cache(cfg, variables)
        if not isinstance(cache, dict):
            cache = {}
        # 接口登录：缓存缺提取器变量名时再刷一次，避免旧 key（如 token）挡住 token1
        expected = expected_auth_variable_names(cfg)
        if expected and any(k not in cache or cache.get(k) in (None, "") for k in expected):
            cache = await refresh_auth_config(cfg, variables)
        if not cache:
            return {}, f"授权「{cfg.name}」缓存为空，请检查提取规则或点击「刷新」"
        return cache, None
    except Exception as e:
        err = str(e)
        cfg.last_refresh_error = err
        await cfg.save(update_fields=["last_refresh_error", "update_time"])
        logger.warning("[api_auth] 刷新失败 config=%s: %s", cfg.id, err)
        return {}, err


async def persist_auth_preview_cache(
    cfg: ApiAuthConfig,
    cache_data: dict[str, Any],
) -> dict[str, Any]:
    """将调试得到的变量写入缓存，便于立刻被用例执行注入。"""
    cleaned = {k: v for k, v in (cache_data or {}).items() if v is not None and v != ""}
    if not cleaned:
        raise RuntimeError("调试结果为空，无法写入缓存")
    now = _now_naive()
    cfg.cache_data = cleaned
    cfg.cache_expires_at = now + timedelta(minutes=cfg.ttl_minutes or 1440)
    cfg.last_refresh_time = now
    cfg.last_refresh_error = None
    await cfg.save(
        update_fields=["cache_data", "cache_expires_at", "last_refresh_time", "last_refresh_error", "update_time"]
    )
    return cleaned


async def prepare_api_runtime_variables(
    project_id: int | None,
    environment_id: int | None,
    extra: Optional[dict[str, Any]] = None,
    *,
    inject_auth: bool = True,
    allow_auth_refresh: bool = True,
) -> tuple[dict[str, Any], Optional[str], list[str]]:
    """合并项目/环境/数据工厂变量，并按需注入 Token 授权缓存。

    返回 (variables, auth_error, auth_injected_keys)。
    allow_auth_refresh=False 时只读授权缓存，不发起登录（变量预览用）。
    """
    from app.modules.data_tools.tag_service import merge_execution_variables

    variables = await merge_execution_variables(project_id, environment_id, extra)
    auth_err: Optional[str] = None
    auth_keys: list[str] = []
    if inject_auth and project_id and environment_id:
        auth_vars, auth_err = await inject_auth_variables(
            project_id,
            environment_id,
            variables,
            allow_refresh=allow_auth_refresh,
        )
        if auth_vars:
            auth_keys = list(auth_vars.keys())
            variables.update(auth_vars)
    return variables, auth_err, auth_keys
