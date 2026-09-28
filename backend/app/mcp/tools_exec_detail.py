"""MCP Wave C：鉴权配置 / 接口调试 / 执行详情（脱敏截断）。"""
from __future__ import annotations

import json
from typing import Any, Optional

from app.core.integration.mcp_confirm import consume_confirm_token, create_confirm_token
from app.core.platform.encryption import mask_key
from app.core.platform.permissions import (
    API_AUTH_EDIT,
    API_AUTH_VIEW,
    API_MANAGE_EDIT,
    API_RECORD_VIEW,
    APP_RECORD_VIEW,
    PERF_RECORD_VIEW,
    UI_RECORD_VIEW,
)
from app.core.platform.project_access import PROJECT_ROLE_MEMBER, PROJECT_ROLE_VIEWER
from app.mcp.auth import McpAuthContext, ensure_permission
from app.models.app import AppCaseExecution
from app.models.http import ApiAuthConfig, ApiDefinition, ApiRunRecord
from app.models.perf import PerfRecord
from app.models.sys import Environment, Project
from app.models.ui import UiCaseExecution
from app.modules.http.api_auth_service import auth_config_to_dict, preview_auth_config, refresh_auth_config


def _clip(text: Any, limit: int = 400) -> str:
    s = ("" if text is None else str(text)).strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _http_detail(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, str) and detail.strip():
        return detail
    return str(exc)


def _mask_secret_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    if len(text) <= 8:
        return "****"
    return mask_key(text)


def _mask_cache_data(cache: dict | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (cache or {}).items():
        out[str(k)] = _mask_secret_value(v)
    return out


def _json_clip(value: Any, limit: int = 800) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        try:
            text = json.dumps(value, ensure_ascii=False)
        except Exception:
            text = str(value)
        if len(text) <= limit:
            return value
        return _clip(text, limit)
    return _clip(value, limit)


async def _require_project(ctx: McpAuthContext, project_id: int, *, member: bool = False) -> int:
    from brickcore_assist.skills.access import require_project_access

    return await require_project_access(
        ctx,
        int(project_id),
        min_role=PROJECT_ROLE_MEMBER if member else PROJECT_ROLE_VIEWER,
    )


def _auth_summary(cfg: ApiAuthConfig, *, env_name: str = "", api_name: str = "") -> dict[str, Any]:
    raw = auth_config_to_dict(cfg, env_name, api_name)
    return {
        "id": raw["id"],
        "project_id": raw["project_id"],
        "environment_id": raw["environment_id"],
        "environment_name": raw.get("environment_name") or "",
        "name": raw["name"],
        "auth_type": raw["auth_type"],
        "login_api_id": raw.get("login_api_id"),
        "login_api_name": raw.get("login_api_name") or "",
        "extractors": raw.get("extractors") or [],
        "ttl_minutes": raw.get("ttl_minutes"),
        "refresh_before_minutes": raw.get("refresh_before_minutes"),
        "refresh_mode": raw.get("refresh_mode"),
        "is_enabled": raw.get("is_enabled"),
        "cache_data": _mask_cache_data(raw.get("cache_data") if isinstance(raw.get("cache_data"), dict) else {}),
        "cache_expires_at": raw.get("cache_expires_at"),
        "cache_remaining_minutes": raw.get("cache_remaining_minutes"),
        "last_refresh_time": raw.get("last_refresh_time"),
        "last_refresh_error": _clip(raw.get("last_refresh_error"), 300),
        "has_custom_code": bool((raw.get("custom_code") or "").strip()),
        "update_time": raw.get("update_time"),
    }


# ---------- 鉴权配置 ----------


async def tool_list_api_auth_configs(
    ctx: McpAuthContext,
    project_id: int,
    environment_id: Optional[int] = None,
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目 Token 授权配置（缓存 token 已脱敏）。"""
    ensure_permission(ctx, API_AUTH_VIEW)
    pid = await _require_project(ctx, project_id)
    page = max(int(page or 1), 1)
    size = min(max(int(size or 20), 1), 50)
    qs = ApiAuthConfig.filter(project_id=pid, is_del=False)
    if environment_id:
        qs = qs.filter(environment_id=int(environment_id))
    kw = (keyword or "").strip()
    if kw:
        qs = qs.filter(name__icontains=kw)
    total = await qs.count()
    rows = await qs.order_by("-update_time").offset((page - 1) * size).limit(size)
    items = []
    for cfg in rows:
        env = await Environment.get_or_none(id=cfg.environment_id)
        api_name = ""
        if cfg.login_api_id:
            api = await ApiDefinition.get_or_none(id=cfg.login_api_id)
            api_name = api.name if api else ""
        items.append(_auth_summary(cfg, env_name=env.name if env else "", api_name=api_name))
    return {"total": total, "page": page, "size": size, "items": items}


async def tool_get_api_auth_config(
    ctx: McpAuthContext,
    project_id: int,
    config_id: int,
) -> dict[str, Any]:
    """获取单个授权配置详情（token 脱敏，不返回自定义代码全文）。"""
    ensure_permission(ctx, API_AUTH_VIEW)
    pid = await _require_project(ctx, project_id)
    cfg = await ApiAuthConfig.get_or_none(id=int(config_id), project_id=pid, is_del=False)
    if not cfg:
        raise ValueError("授权配置不存在或不属于当前项目")
    env = await Environment.get_or_none(id=cfg.environment_id)
    api_name = ""
    if cfg.login_api_id:
        api = await ApiDefinition.get_or_none(id=cfg.login_api_id)
        api_name = api.name if api else ""
    return _auth_summary(cfg, env_name=env.name if env else "", api_name=api_name)


async def tool_preview_test_api_auth_config(
    ctx: McpAuthContext,
    project_id: int,
    config_id: int,
) -> dict[str, Any]:
    """预览调试授权配置（试跑登录/自定义代码，成功后写入缓存）。"""
    ensure_permission(ctx, API_AUTH_EDIT)
    pid = await _require_project(ctx, project_id, member=True)
    cfg = await ApiAuthConfig.get_or_none(id=int(config_id), project_id=pid, is_del=False)
    if not cfg:
        raise ValueError("授权配置不存在或不属于当前项目")
    impact = {
        "project_id": pid,
        "config_id": cfg.id,
        "name": cfg.name,
        "auth_type": cfg.auth_type,
        "environment_id": cfg.environment_id,
        "warning": "将按当前配置试跑授权，成功后写入缓存 token（可能调用真实登录接口）",
    }
    confirm_token = await create_confirm_token(
        "test_api_auth_config",
        {"project_id": pid, "config_id": int(cfg.id)},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_test_api_auth_config 并传入 confirm_token",
    }


async def tool_confirm_test_api_auth_config(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    config_id: int,
) -> dict[str, Any]:
    ensure_permission(ctx, API_AUTH_EDIT)
    payload = await consume_confirm_token(confirm_token, "test_api_auth_config", ctx.username)
    if int(payload.get("project_id") or 0) != int(project_id):
        raise ValueError("project_id 与确认 Token 不匹配")
    if int(payload.get("config_id") or 0) != int(config_id):
        raise ValueError("config_id 与确认 Token 不匹配")
    pid = await _require_project(ctx, int(payload["project_id"]), member=True)
    cfg = await ApiAuthConfig.get_or_none(id=int(payload["config_id"]), project_id=pid, is_del=False)
    if not cfg:
        raise ValueError("授权配置不存在或不属于当前项目")
    env = await Environment.get_or_none(id=cfg.environment_id, project_id=pid, is_del=False)
    if not env:
        raise ValueError("环境不存在")
    base_vars = dict(env.global_vars or {})
    project = await Project.get_or_none(id=pid, is_del=False)
    if project and project.global_vars:
        base_vars = {**project.global_vars, **base_vars}
    from app.modules.http.api_auth_service import persist_auth_preview_cache
    from app.routers.http.auth_config import _normalize_auth_extractors

    try:
        variables = await preview_auth_config(
            project_id=pid,
            environment_id=cfg.environment_id,
            auth_type=cfg.auth_type,
            login_api_id=cfg.login_api_id,
            extractors=_normalize_auth_extractors(cfg.extractors),
            custom_code=cfg.custom_code,
            base_variables=base_vars,
        )
        await persist_auth_preview_cache(cfg, variables)
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    return {
        "config_id": cfg.id,
        "cache_written": True,
        "variables": _mask_cache_data(variables if isinstance(variables, dict) else {}),
        "message": "调试成功，已写入授权缓存",
        "usage_hint": "执行用例时在 Header/Body 中使用 ${{变量名}}",
    }


async def tool_preview_refresh_api_auth_token(
    ctx: McpAuthContext,
    project_id: int,
    config_id: int,
) -> dict[str, Any]:
    """预览立即刷新授权 token。"""
    ensure_permission(ctx, API_AUTH_EDIT)
    pid = await _require_project(ctx, project_id, member=True)
    cfg = await ApiAuthConfig.get_or_none(id=int(config_id), project_id=pid, is_del=False)
    if not cfg:
        raise ValueError("授权配置不存在或不属于当前项目")
    impact = {
        "project_id": pid,
        "config_id": cfg.id,
        "name": cfg.name,
        "warning": "将立即刷新授权缓存（可能调用真实登录接口）",
    }
    confirm_token = await create_confirm_token(
        "refresh_api_auth_token",
        {"project_id": pid, "config_id": int(cfg.id)},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_refresh_api_auth_token 并传入 confirm_token",
    }


async def tool_confirm_refresh_api_auth_token(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    config_id: int,
) -> dict[str, Any]:
    ensure_permission(ctx, API_AUTH_EDIT)
    payload = await consume_confirm_token(confirm_token, "refresh_api_auth_token", ctx.username)
    if int(payload.get("project_id") or 0) != int(project_id):
        raise ValueError("project_id 与确认 Token 不匹配")
    if int(payload.get("config_id") or 0) != int(config_id):
        raise ValueError("config_id 与确认 Token 不匹配")
    pid = await _require_project(ctx, int(payload["project_id"]), member=True)
    cfg = await ApiAuthConfig.get_or_none(id=int(payload["config_id"]), project_id=pid, is_del=False)
    if not cfg:
        raise ValueError("授权配置不存在或不属于当前项目")
    env = await Environment.get_or_none(id=cfg.environment_id, is_del=False)
    base_vars = dict(env.global_vars or {}) if env else {}
    project = await Project.get_or_none(id=cfg.project_id, is_del=False)
    if project and project.global_vars:
        base_vars = {**project.global_vars, **base_vars}
    try:
        cache = await refresh_auth_config(cfg, base_vars)
    except Exception as exc:
        cfg.last_refresh_error = str(exc)
        await cfg.save(update_fields=["last_refresh_error", "update_time"])
        raise ValueError(str(exc)) from exc
    return {
        "config_id": cfg.id,
        "cache_data": _mask_cache_data(cache if isinstance(cache, dict) else {}),
        "message": "刷新成功",
    }


# ---------- 接口调试 ----------


async def tool_preview_debug_api_definition(
    ctx: McpAuthContext,
    project_id: int,
    api_id: int,
    env_id: Optional[int] = None,
) -> dict[str, Any]:
    """预览单次接口调试（按接口定义发送真实请求；需确认）。"""
    ensure_permission(ctx, API_MANAGE_EDIT)
    pid = await _require_project(ctx, project_id, member=True)
    api = await ApiDefinition.get_or_none(id=int(api_id), project_id=pid)
    if not api:
        # soft-delete field may not exist on all editions; fall back
        api = await ApiDefinition.get_or_none(id=int(api_id))
        if not api or int(getattr(api, "project_id", 0) or 0) != pid:
            raise ValueError("接口定义不存在或不属于当前项目")
    env_name = ""
    if env_id:
        env = await Environment.get_or_none(id=int(env_id), project_id=pid, is_del=False)
        if not env:
            raise ValueError("环境不存在或不属于当前项目")
        env_name = env.name or ""
    impact = {
        "project_id": pid,
        "api_id": api.id,
        "name": api.name,
        "method": api.method,
        "path": api.path,
        "env_id": int(env_id) if env_id else None,
        "env_name": env_name,
        "warning": "将按接口定义向真实环境发送一次调试请求",
    }
    confirm_token = await create_confirm_token(
        "debug_api_definition",
        {"project_id": pid, "api_id": int(api.id), "env_id": int(env_id) if env_id else None},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_debug_api_definition 并传入 confirm_token",
    }


async def tool_confirm_debug_api_definition(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    api_id: int,
    env_id: Optional[int] = None,
) -> dict[str, Any]:
    from fastapi import HTTPException

    from app.routers.http.apis import debug_api
    from app.schemas.http import ApiDebugRequest

    ensure_permission(ctx, API_MANAGE_EDIT)
    payload = await consume_confirm_token(confirm_token, "debug_api_definition", ctx.username)
    if int(payload.get("project_id") or 0) != int(project_id):
        raise ValueError("project_id 与确认 Token 不匹配")
    if int(payload.get("api_id") or 0) != int(api_id):
        raise ValueError("api_id 与确认 Token 不匹配")
    tok_env = payload.get("env_id")
    if env_id is not None and int(tok_env or 0) != int(env_id):
        raise ValueError("env_id 与确认 Token 不匹配")

    pid = await _require_project(ctx, int(payload["project_id"]), member=True)
    api = await ApiDefinition.get_or_none(id=int(payload["api_id"]))
    if not api or int(getattr(api, "project_id", 0) or 0) != pid:
        raise ValueError("接口定义不存在或不属于当前项目")

    path = (api.path or "").strip()
    base = (api.base_url or "").strip().rstrip("/")
    if path.startswith(("http://", "https://")):
        url = path
    elif base:
        url = f"{base}/{path.lstrip('/')}" if path else base
    else:
        url = path

    req = ApiDebugRequest(
        method=(api.method or "GET").upper(),
        url=url or "/",
        headers=api.headers if isinstance(api.headers, list) else [],
        global_header_policy=api.global_header_policy if isinstance(api.global_header_policy, dict) else {},
        params=api.params if isinstance(api.params, list) else [],
        body=api.body,
        body_type=api.body_type or "json",
        body_fields=api.body_fields if isinstance(api.body_fields, list) else [],
        env_id=int(tok_env) if tok_env else None,
        project_id=pid,
    )
    try:
        raw = await debug_api(req)
    except HTTPException as exc:
        raise ValueError(_http_detail(exc)) from exc

    data = raw if isinstance(raw, dict) else {}
    headers = data.get("headers") if isinstance(data.get("headers"), dict) else {}
    # 脱敏常见鉴权头
    safe_headers = {}
    for k, v in list(headers.items())[:30]:
        lk = str(k).lower()
        if any(x in lk for x in ("authorization", "token", "cookie", "secret", "api-key", "apikey")):
            safe_headers[str(k)] = "****"
        else:
            safe_headers[str(k)] = _clip(v, 120)
    return {
        "api_id": api.id,
        "status_code": data.get("status_code"),
        "time_ms": data.get("time"),
        "size": data.get("size"),
        "headers": safe_headers,
        "body": _json_clip(data.get("body"), 1200),
        "request_url": _clip((data.get("request") or {}).get("url") if isinstance(data.get("request"), dict) else url, 400),
        "message": "调试完成",
    }


# 兼容规划名：debug_api_definition 作为「建议 confirm」的别名入口说明
async def tool_debug_api_definition(
    ctx: McpAuthContext,
    project_id: int,
    api_id: int,
    env_id: Optional[int] = None,
) -> dict[str, Any]:
    """兼容入口：等价于 preview_debug_api_definition（必须再 confirm）。"""
    return await tool_preview_debug_api_definition(ctx, project_id, api_id, env_id)


# ---------- 执行详情 ----------


async def tool_get_api_case_execution_detail(
    ctx: McpAuthContext,
    project_id: int,
    record_id: int,
) -> dict[str, Any]:
    """获取接口用例执行详情摘要（请求/响应/断言已截断）。"""
    ensure_permission(ctx, API_RECORD_VIEW)
    pid = await _require_project(ctx, project_id)
    rec = await ApiRunRecord.get_or_none(id=int(record_id)).prefetch_related("case", "project")
    if not rec:
        raise ValueError("接口执行记录不存在")
    rec_pid = int(getattr(rec, "project_id", 0) or (rec.project.id if rec.project else 0) or 0)
    if rec_pid != pid:
        raise ValueError("执行记录不属于当前项目")
    assertions = rec.assertions_result if isinstance(rec.assertions_result, list) else []
    assertion_summary = []
    for a in assertions[:20]:
        if not isinstance(a, dict):
            continue
        assertion_summary.append(
            {
                "name": _clip(a.get("name") or a.get("type") or a.get("assert_type"), 80),
                "passed": a.get("passed") if "passed" in a else a.get("success"),
                "message": _clip(a.get("message") or a.get("error") or a.get("msg"), 200),
            }
        )
    req_headers = rec.request_headers if isinstance(rec.request_headers, dict) else {}
    safe_req_headers = {
        str(k): ("****" if any(x in str(k).lower() for x in ("authorization", "token", "cookie", "secret")) else _clip(v, 100))
        for k, v in list(req_headers.items())[:20]
    }
    return {
        "id": rec.id,
        "type": "api_case",
        "project_id": rec_pid or pid,
        "case_id": rec.case_id,
        "case_name": rec.case.name if rec.case else "",
        "status": rec.status,
        "request_method": rec.request_method,
        "request_url": _clip(rec.request_url, 500),
        "request_headers": safe_req_headers,
        "request_body": _json_clip(rec.request_body, 800),
        "response_status": rec.response_status,
        "response_time_ms": rec.response_time,
        "response_body": _json_clip(rec.response_body, 1200),
        "assertions": assertion_summary,
        "assertion_count": len(assertions),
        "error_msg": _clip(rec.error_msg, 500),
        "run_by": rec.run_by,
        "start_time": rec.start_time.isoformat() if rec.start_time else None,
        "end_time": rec.end_time.isoformat() if rec.end_time else None,
        "report_url": f"/api-module/report/{rec.id}?type=case",
    }


async def tool_get_ui_case_execution_detail(
    ctx: McpAuthContext,
    project_id: int,
    record_id: int,
) -> dict[str, Any]:
    """获取 Web UI 用例执行详情摘要（失败步骤 / 截图提示）。"""
    ensure_permission(ctx, UI_RECORD_VIEW)
    pid = await _require_project(ctx, project_id)
    rec = await UiCaseExecution.get_or_none(id=int(record_id), is_del=False).prefetch_related("case")
    if not rec:
        raise ValueError("Web UI 用例执行记录不存在")
    case = rec.case
    case_pid = int(getattr(case, "project_id", 0) or 0) if case else 0
    if not case or case_pid != pid:
        raise ValueError("执行记录不属于当前项目")
    from app.modules.ui.ui_result_extract import extract_ui_case_failure_summary, normalize_result_data

    summary = extract_ui_case_failure_summary(getattr(rec, "result_data", None))
    rd = normalize_result_data(getattr(rec, "result_data", None))
    steps = rd.get("steps") if isinstance(rd.get("steps"), list) else []
    key_steps = []
    for s in steps[:15]:
        if not isinstance(s, dict):
            continue
        key_steps.append(
            {
                "keyword": _clip(s.get("keyword") or s.get("desc"), 80),
                "status": s.get("status") or s.get("result"),
                "message": _clip(s.get("message") or s.get("error"), 160),
            }
        )
    screenshot = None
    failed_idx = summary.get("failed_step_index")
    if failed_idx and isinstance(failed_idx, int) and 0 < failed_idx <= len(steps):
        fs = steps[failed_idx - 1]
        if isinstance(fs, dict):
            screenshot = fs.get("screenshot") or fs.get("image")
    if not screenshot:
        screenshot = rd.get("img") or rd.get("img_url")
    return {
        "id": rec.id,
        "type": "ui_case",
        "project_id": case_pid or pid,
        "case_id": rec.case_id,
        "case_name": case.name if case else summary.get("case_name") or "",
        "status": rec.status,
        "username": rec.username,
        "start_time": rec.start_time.isoformat() if rec.start_time else None,
        "error_hint": _clip(summary.get("error_hint"), 500),
        "failed_step_index": summary.get("failed_step_index"),
        "failed_step_keyword": _clip(summary.get("failed_step_keyword"), 120),
        "failed_step_desc": _clip(summary.get("failed_step_desc"), 200),
        "log_error_excerpt": _clip(summary.get("log_error_excerpt"), 400),
        "has_screenshot": bool(summary.get("has_screenshot") or screenshot),
        "screenshot_url": _clip(screenshot, 300) if screenshot else None,
        "key_steps": key_steps,
        "step_count": len(steps),
        "report_url": f"/record/report/suite/{rec.suite_execution_id}" if rec.suite_execution_id else None,
    }


async def tool_get_app_case_execution_detail(
    ctx: McpAuthContext,
    project_id: int,
    record_id: int,
) -> dict[str, Any]:
    """获取 App 用例执行详情摘要。"""
    ensure_permission(ctx, APP_RECORD_VIEW)
    pid = await _require_project(ctx, project_id)
    rec = await AppCaseExecution.get_or_none(id=int(record_id), is_del=False).prefetch_related("case")
    if not rec:
        raise ValueError("App 用例执行记录不存在")
    case = rec.case
    case_pid = int(getattr(case, "project_id", 0) or 0) if case else 0
    if not case or case_pid != pid:
        raise ValueError("执行记录不属于当前项目")
    rd = rec.result_data if isinstance(rec.result_data, dict) else {}
    steps = rd.get("steps") if isinstance(rd.get("steps"), list) else []
    error = rd.get("error") or rd.get("error_msg") or rd.get("message") or ""
    key_steps = []
    for s in steps[:15]:
        if not isinstance(s, dict):
            continue
        key_steps.append(
            {
                "keyword": _clip(s.get("keyword") or s.get("desc"), 80),
                "status": s.get("status") or s.get("result"),
                "message": _clip(s.get("message") or s.get("error"), 160),
            }
        )
    return {
        "id": rec.id,
        "type": "app_case",
        "project_id": case_pid or pid,
        "case_id": rec.case_id,
        "case_name": case.name if case else "",
        "status": rec.status,
        "username": rec.username,
        "start_time": rec.start_time.isoformat() if rec.start_time else None,
        "error_hint": _clip(error, 500),
        "key_steps": key_steps,
        "step_count": len(steps),
        "has_device_apm": bool(rec.device_apm_summary),
        "report_url": (
            f"/app-record/report/suite/{rec.suite_execution_id}" if rec.suite_execution_id else None
        ),
    }


async def tool_get_perf_record_detail(
    ctx: McpAuthContext,
    project_id: int,
    record_id: int,
) -> dict[str, Any]:
    """获取压测执行记录摘要（不含明细时序大数据）。"""
    ensure_permission(ctx, PERF_RECORD_VIEW)
    pid = await _require_project(ctx, project_id)
    rec = await PerfRecord.get_or_none(id=int(record_id)).prefetch_related("scene")
    if not rec:
        raise ValueError("压测执行记录不存在")
    if int(rec.project_id or 0) != pid:
        raise ValueError("执行记录不属于当前项目")
    return {
        "id": rec.id,
        "type": "perf",
        "project_id": pid,
        "scene_id": rec.scene_id,
        "scene_name": rec.scene.name if rec.scene else "",
        "status": rec.status,
        "qps": rec.qps,
        "avg_response_time": rec.avg_response_time,
        "median_response_time": getattr(rec, "median_response_time", None),
        "p90_response_time": getattr(rec, "p90_response_time", None),
        "error_rate": rec.error_rate,
        "total_requests": rec.total_requests,
        "duration": rec.duration,
        "run_by": rec.run_by,
        "started_at": rec.started_at.isoformat() if rec.started_at else None,
        "ended_at": rec.ended_at.isoformat() if getattr(rec, "ended_at", None) else None,
        "report_url": f"/perf-report/{rec.id}",
    }


async def _assert_report_in_project(pid: int, rtype: str, record_id: int) -> None:
    """套件/计划报告没有用例级 project 校验，这里按记录所属项目拦截。"""
    from app.models.app import AppPlanExecution, AppSuiteExecution
    from app.models.http import ApiPlanRunRecord, ApiSuiteRunRecord
    from app.models.ui import UiPlanExecution

    rid = int(record_id)
    rec_pid = 0
    if rtype in ("api_suite", "suite"):
        rec = await ApiSuiteRunRecord.get_or_none(id=rid)
        if not rec:
            raise ValueError("接口套件执行记录不存在")
        rec_pid = int(getattr(rec, "project_id", 0) or 0)
    elif rtype in ("api_plan", "plan"):
        rec = await ApiPlanRunRecord.get_or_none(id=rid)
        if not rec:
            raise ValueError("接口测试计划执行记录不存在")
        rec_pid = int(getattr(rec, "project_id", 0) or 0)
    elif rtype in ("ui_plan", "ui_task"):
        rec = await UiPlanExecution.get_or_none(id=rid, is_del=False)
        if not rec:
            raise ValueError("UI 测试计划执行记录不存在")
        rec_pid = int(getattr(rec, "project_id", 0) or 0)
    elif rtype in ("app_plan", "app_task"):
        rec = await AppPlanExecution.get_or_none(id=rid, is_del=False)
        if not rec:
            raise ValueError("App 计划执行记录不存在")
        rec_pid = int(getattr(rec, "project_id", 0) or 0)
    elif rtype == "app_suite":
        rec = await AppSuiteExecution.get_or_none(id=rid, is_del=False).prefetch_related("suite")
        if not rec:
            raise ValueError("App 套件执行记录不存在")
        suite = rec.suite
        rec_pid = int(getattr(suite, "project_id", 0) or 0) if suite else 0
    else:
        raise ValueError(
            "record_type 支持 api_case / ui_case / app_case / perf / api_suite / api_plan / ui_plan / app_plan / app_suite"
        )
    if rec_pid != pid:
        raise ValueError("执行记录不属于当前项目")


async def tool_get_execution_report(
    ctx: McpAuthContext,
    project_id: int,
    record_type: str,
    record_id: int,
) -> dict[str, Any]:
    """获取执行报告链接与摘要（api_suite/api_plan/api_case/ui_plan/ui_case/app_*/perf）。"""
    from app.mcp.tools import tool_get_execution_record

    rtype = (record_type or "").strip().lower()
    pid = await _require_project(ctx, project_id)

    # 先走已有摘要工具；单用例细节补充用 detail 工具
    if rtype in ("api_case", "api_case_execution"):
        detail = await tool_get_api_case_execution_detail(ctx, project_id, record_id)
        return {
            "record_type": "api_case",
            "record_id": record_id,
            "report_url": detail.get("report_url"),
            "summary": detail,
        }
    if rtype in ("ui_case", "ui_case_execution", "web_ui_case"):
        detail = await tool_get_ui_case_execution_detail(ctx, project_id, record_id)
        return {
            "record_type": "ui_case",
            "record_id": record_id,
            "report_url": detail.get("report_url"),
            "summary": detail,
        }
    if rtype in ("app_case", "app_case_execution"):
        detail = await tool_get_app_case_execution_detail(ctx, project_id, record_id)
        return {
            "record_type": "app_case",
            "record_id": record_id,
            "report_url": detail.get("report_url"),
            "summary": detail,
        }
    if rtype in ("perf", "perf_record"):
        detail = await tool_get_perf_record_detail(ctx, project_id, record_id)
        return {
            "record_type": "perf",
            "record_id": record_id,
            "report_url": detail.get("report_url"),
            "summary": detail,
        }

    await _assert_report_in_project(pid, rtype, record_id)
    summary = await tool_get_execution_record(ctx, rtype, record_id)
    report_url = None
    if rtype in ("api_suite", "suite"):
        report_url = f"/api-module/report/{record_id}?type=suite"
    elif rtype in ("api_plan", "plan"):
        report_url = f"/api-module/report/{record_id}?type=plan"
    elif rtype in ("ui_plan", "ui_task"):
        report_url = f"/record/report/task/{record_id}"
    elif rtype in ("app_plan", "app_task"):
        report_url = f"/app-record/report/plan/{record_id}"
    elif rtype in ("app_suite",):
        report_url = f"/app-record/report/suite/{record_id}"
    return {
        "record_type": summary.get("type") or rtype,
        "record_id": record_id,
        "report_url": report_url,
        "summary": summary,
    }
