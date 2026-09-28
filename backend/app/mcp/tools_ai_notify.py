"""MCP Wave B：AI 配置 / 用量 / 站内信 / 通知（只读优先 + 连通性 confirm）。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

from app.core.integration.mcp_confirm import consume_confirm_token, create_confirm_token
from app.core.platform.encryption import mask_key
from app.core.platform.permissions import (
    AI_CONFIG_VIEW,
    AI_TEST_EXECUTE,
    AI_TEST_VIEW,
    NOTIFICATION_CONFIG_VIEW,
    NOTIFICATION_LOG_VIEW,
)
from app.core.platform.project_access import PROJECT_ROLE_VIEWER
from app.mcp.auth import McpAuthContext, ensure_any_permission, ensure_permission
from app.models.ai import AiConfig
from app.models.sys import NotificationConfig, NotificationLog


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


def _ctx_user_info(ctx: McpAuthContext) -> dict[str, Any]:
    return {
        "id": ctx.user_id,
        "username": ctx.username or "",
        "is_superuser": bool(ctx.is_superuser or ctx.is_api_key),
        "is_api_key": bool(ctx.is_api_key),
    }


def _mask_ai_config(config: AiConfig) -> dict[str, Any]:
    from app.routers.ai.config import _mask_config

    return _mask_config(config)


def _mask_notify_channel_config(channel_type: str, raw: dict | None) -> dict[str, Any]:
    data = dict(raw or {})
    out: dict[str, Any] = {}
    if channel_type == "email":
        out["recipients"] = list(data.get("recipients") or [])[:20]
        return out
    url = str(data.get("webhook_url") or "").strip()
    if url:
        parts = urlsplit(url)
        if parts.scheme and parts.netloc:
            out["webhook_url"] = urlunsplit((parts.scheme, parts.netloc, "", "", "")) + "/***"
        else:
            out["webhook_url"] = "****"
    # 不回传 secret / token / password
    for key in ("secret", "sign", "token", "password", "access_token"):
        if data.get(key):
            out[key] = "****"
    return out


def _mask_cache_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value)
    if len(text) <= 8:
        return "****"
    return mask_key(text)


# ---------- AI 配置 ----------


async def tool_list_ai_configs(
    ctx: McpAuthContext,
    page: int = 1,
    size: int = 50,
    keyword: str = "",
) -> dict[str, Any]:
    """列出平台 LLM 配置（API Key 已脱敏）。"""
    ensure_permission(ctx, AI_CONFIG_VIEW)
    page = max(int(page or 1), 1)
    size = min(max(int(size or 50), 1), 100)
    qs = AiConfig.filter(is_del=False)
    kw = (keyword or "").strip()
    if kw:
        from tortoise.expressions import Q

        qs = qs.filter(Q(name__icontains=kw) | Q(model__icontains=kw) | Q(provider__icontains=kw))
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [_mask_ai_config(c) for c in rows],
    }


async def tool_get_ai_config(ctx: McpAuthContext, config_id: int) -> dict[str, Any]:
    """获取单个 LLM 配置详情（含 supports_vision；Key 脱敏）。"""
    ensure_permission(ctx, AI_CONFIG_VIEW)
    config = await AiConfig.get_or_none(id=int(config_id), is_del=False)
    if not config:
        raise ValueError("AI 配置不存在")
    return _mask_ai_config(config)


async def tool_list_ai_config_select_options(ctx: McpAuthContext) -> dict[str, Any]:
    """列出可用于执行/分析的已启用模型选项（含 supports_vision）。"""
    ensure_any_permission(ctx, AI_TEST_EXECUTE, AI_CONFIG_VIEW)
    configs = await AiConfig.filter(is_del=False, is_enabled=True).order_by("-is_default", "-id")
    return {
        "items": [
            {
                "id": c.id,
                "name": c.name,
                "model": c.model,
                "provider": c.provider,
                "supports_vision": bool(getattr(c, "supports_vision", False)),
                "is_default": c.is_default,
                "is_enabled": c.is_enabled,
            }
            for c in configs
        ]
    }


async def tool_list_ai_scene_bindings(ctx: McpAuthContext) -> dict[str, Any]:
    """列出 AI 场景与模型绑定（只读）。"""
    ensure_permission(ctx, AI_CONFIG_VIEW)
    from app.modules.ai.ai_scene_config import list_scene_bindings

    data = await list_scene_bindings()
    return data if isinstance(data, dict) else {"bindings": data}


async def tool_preview_test_ai_config(
    ctx: McpAuthContext,
    config_id: int,
    project_id: Optional[int] = None,
) -> dict[str, Any]:
    """预览测试 LLM 连通性（会消耗少量 Token；需确认）。"""
    ensure_any_permission(ctx, AI_CONFIG_VIEW, AI_TEST_EXECUTE)
    config = await AiConfig.get_or_none(id=int(config_id), is_del=False)
    if not config:
        raise ValueError("AI 配置不存在")
    impact = {
        "config_id": config.id,
        "name": config.name,
        "provider": config.provider,
        "model": config.model,
        "supports_vision": bool(getattr(config, "supports_vision", False)),
        "project_id": int(project_id) if project_id else None,
        "warning": "将向该模型发送一条极短连通性探测，可能消耗少量 Token",
    }
    confirm_token = await create_confirm_token(
        "test_ai_config",
        {"config_id": int(config.id), "project_id": int(project_id) if project_id else None},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_test_ai_config 并传入 confirm_token",
    }


async def tool_confirm_test_ai_config(
    ctx: McpAuthContext,
    confirm_token: str,
    config_id: int,
    project_id: Optional[int] = None,
) -> dict[str, Any]:
    ensure_any_permission(ctx, AI_CONFIG_VIEW, AI_TEST_EXECUTE)
    payload = await consume_confirm_token(confirm_token, "test_ai_config", ctx.username)
    if int(payload.get("config_id") or 0) != int(config_id):
        raise ValueError("config_id 与确认 Token 不匹配")
    tok_pid = payload.get("project_id")
    if project_id is not None and int(tok_pid or 0) != int(project_id):
        raise ValueError("project_id 与确认 Token 不匹配")

    from fastapi import HTTPException

    from app.routers.ai.config import test_config

    user_info = _ctx_user_info(ctx)
    if tok_pid:
        user_info["project_id"] = int(tok_pid)
        user_info["current_project_id"] = int(tok_pid)
    try:
        resp = await test_config(int(payload["config_id"]), user_info=user_info)
    except HTTPException as exc:
        raise ValueError(_http_detail(exc)) from exc

    data = getattr(resp, "data", None)
    if data is None and isinstance(resp, dict):
        data = resp.get("data")
    code = getattr(resp, "code", None)
    if code is None and isinstance(resp, dict):
        code = resp.get("code")
    message = getattr(resp, "message", None) or ""
    result = dict(data or {}) if isinstance(data, dict) else {"raw": data}
    result["config_id"] = int(payload["config_id"])
    if int(code or 200) >= 400:
        result["connected"] = False
        result["message"] = message or "连通性测试失败"
    else:
        result.setdefault("connected", True)
        result["message"] = message or "连通性测试成功"
    # 绝不回传明文 key
    result.pop("api_key", None)
    return result


async def tool_get_ai_usage_logs(
    ctx: McpAuthContext,
    project_id: Optional[int] = None,
    days: int = 7,
    scene: str = "",
    status: str = "",
    page: int = 1,
    size: int = 20,
    include_summary: bool = True,
) -> dict[str, Any]:
    """查询 AI 用量摘要与近期记录（不含完整 Prompt）。"""
    ensure_permission(ctx, AI_TEST_VIEW)
    if project_id:
        from brickcore_assist.skills.access import require_project_access

        await require_project_access(ctx, int(project_id), min_role=PROJECT_ROLE_VIEWER)

    days = min(max(int(days or 7), 1), 90)
    page = max(int(page or 1), 1)
    size = min(max(int(size or 20), 1), 50)
    date_from = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=days - 1
    )

    from app.routers.ai.usage_logs import _build_usage_queryset, _row_to_dict, usage_logs_summary

    qs = _build_usage_queryset(
        project_id=int(project_id) if project_id else None,
        scene=(scene or "").strip() or None,
        status=(status or "").strip() or None,
        date_from=date_from,
    )
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    items = []
    for row in rows:
        d = _row_to_dict(row)
        items.append(
            {
                "id": d.get("id"),
                "scene": d.get("scene"),
                "scene_label": d.get("scene_label"),
                "username": d.get("username"),
                "project_id": d.get("project_id"),
                "project_name": d.get("project_name"),
                "model": d.get("model"),
                "provider": d.get("provider"),
                "tokens_used": d.get("tokens_used"),
                "duration_ms": d.get("duration_ms"),
                "status": d.get("status"),
                "path_label": d.get("path_label"),
                "input_summary": _clip(d.get("input_summary"), 200),
                "output_summary": _clip(d.get("output_summary"), 200),
                "create_time": d.get("create_time"),
            }
        )

    out: dict[str, Any] = {
        "days": days,
        "total": total,
        "page": page,
        "size": size,
        "items": items,
    }
    if include_summary:
        from fastapi import HTTPException

        try:
            summary_resp = await usage_logs_summary(
                project_id=int(project_id) if project_id else None,
                days=days,
            )
            summary = getattr(summary_resp, "data", None)
            if summary is None and isinstance(summary_resp, dict):
                summary = summary_resp.get("data")
            out["summary"] = summary
        except HTTPException as exc:
            out["summary_error"] = _http_detail(exc)
        except Exception as exc:
            out["summary_error"] = str(exc)
    return out


# ---------- 站内信 ----------


async def tool_list_inbox_messages(
    ctx: McpAuthContext,
    project_id: Optional[int] = None,
    unread_only: bool = False,
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出当前用户站内信（需 TM 扩展包；无包返回空列表提示）。"""
    if not ctx.user_id:
        raise ValueError("站内信需要登录用户身份（API Key 无用户 ID 时不可用）")
    page = max(int(page or 1), 1)
    size = min(max(int(size or 20), 1), 50)
    from app.modules.test_management.premium_gateway import tm_premium_ready

    if not tm_premium_ready():
        return {
            "total": 0,
            "page": page,
            "size": size,
            "items": [],
            "premium_required": True,
            "message": "站内信需要测试管理扩展包",
        }
    from app.modules.test_management import assignment_notify_service as svc

    data = await svc.list_inbox(
        user_id=int(ctx.user_id),
        project_id=int(project_id) if project_id else None,
        unread_only=bool(unread_only),
        page=page,
        size=size,
    )
    if isinstance(data, dict):
        items = data.get("data") or data.get("items") or []
        return {
            "total": data.get("total", len(items)),
            "page": data.get("page", page),
            "size": data.get("size", size),
            "items": items,
        }
    return {"total": 0, "page": page, "size": size, "items": []}


async def tool_get_inbox_unread_count(
    ctx: McpAuthContext,
    project_id: Optional[int] = None,
) -> dict[str, Any]:
    """获取当前用户未读站内信数量。"""
    if not ctx.user_id:
        raise ValueError("站内信需要登录用户身份（API Key 无用户 ID 时不可用）")
    from app.modules.test_management.premium_gateway import tm_premium_ready

    if not tm_premium_ready():
        return {"count": 0, "premium_required": True}
    from app.modules.test_management import assignment_notify_service as svc

    count = await svc.unread_count(
        user_id=int(ctx.user_id),
        project_id=int(project_id) if project_id else None,
    )
    return {"count": int(count or 0)}


async def tool_get_inbox_preferences(ctx: McpAuthContext) -> dict[str, Any]:
    """获取当前用户通知偏好（只读）。"""
    if not ctx.user_id:
        raise ValueError("站内信需要登录用户身份（API Key 无用户 ID 时不可用）")
    from app.modules.test_management.premium_gateway import tm_premium_ready
    from app.modules.test_management.tm_premium_defaults import DEFAULT_USER_NOTIFY_PREFS

    if not tm_premium_ready():
        return {**DEFAULT_USER_NOTIFY_PREFS, "premium_required": True}
    from app.modules.test_management.user_notify_prefs import load_user_notify_prefs

    return await load_user_notify_prefs(int(ctx.user_id))


async def tool_preview_mark_inbox_read(
    ctx: McpAuthContext,
    notification_id: int,
) -> dict[str, Any]:
    """预览将单条站内信标为已读。"""
    if not ctx.user_id:
        raise ValueError("站内信需要登录用户身份")
    from app.modules.test_management.premium_gateway import tm_premium_ready

    if not tm_premium_ready():
        raise ValueError("站内信需要测试管理扩展包")
    impact = {
        "notification_id": int(notification_id),
        "warning": "确认后将该条站内信标记为已读",
    }
    confirm_token = await create_confirm_token(
        "mark_inbox_read",
        {"notification_id": int(notification_id), "user_id": int(ctx.user_id)},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_mark_inbox_read 并传入 confirm_token",
    }


async def tool_confirm_mark_inbox_read(
    ctx: McpAuthContext,
    confirm_token: str,
    notification_id: int,
) -> dict[str, Any]:
    if not ctx.user_id:
        raise ValueError("站内信需要登录用户身份")
    payload = await consume_confirm_token(confirm_token, "mark_inbox_read", ctx.username)
    if int(payload.get("notification_id") or 0) != int(notification_id):
        raise ValueError("notification_id 与确认 Token 不匹配")
    if int(payload.get("user_id") or 0) != int(ctx.user_id):
        raise ValueError("用户身份与确认 Token 不匹配")
    from app.modules.test_management.premium_gateway import tm_premium_ready

    if not tm_premium_ready():
        raise ValueError("站内信需要测试管理扩展包")
    from app.modules.test_management import assignment_notify_service as svc

    ok = await svc.mark_read(notification_id=int(notification_id), user_id=int(ctx.user_id))
    if not ok:
        raise ValueError("通知不存在")
    return {"ok": True, "notification_id": int(notification_id), "message": "已标记为已读"}


async def tool_preview_mark_inbox_all_read(
    ctx: McpAuthContext,
    project_id: Optional[int] = None,
) -> dict[str, Any]:
    """预览将站内信全部标为已读。"""
    if not ctx.user_id:
        raise ValueError("站内信需要登录用户身份")
    from app.modules.test_management.premium_gateway import tm_premium_ready

    if not tm_premium_ready():
        raise ValueError("站内信需要测试管理扩展包")
    impact = {
        "project_id": int(project_id) if project_id else None,
        "warning": "确认后将当前用户（可选项目范围）未读站内信全部标为已读",
    }
    confirm_token = await create_confirm_token(
        "mark_inbox_all_read",
        {
            "user_id": int(ctx.user_id),
            "project_id": int(project_id) if project_id else None,
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_mark_inbox_all_read 并传入 confirm_token",
    }


async def tool_confirm_mark_inbox_all_read(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: Optional[int] = None,
) -> dict[str, Any]:
    if not ctx.user_id:
        raise ValueError("站内信需要登录用户身份")
    payload = await consume_confirm_token(confirm_token, "mark_inbox_all_read", ctx.username)
    if int(payload.get("user_id") or 0) != int(ctx.user_id):
        raise ValueError("用户身份与确认 Token 不匹配")
    tok_pid = payload.get("project_id")
    if project_id is not None and int(tok_pid or 0) != int(project_id):
        raise ValueError("project_id 与确认 Token 不匹配")
    from app.modules.test_management.premium_gateway import tm_premium_ready

    if not tm_premium_ready():
        raise ValueError("站内信需要测试管理扩展包")
    from app.modules.test_management import assignment_notify_service as svc

    updated = await svc.mark_all_read(
        user_id=int(ctx.user_id),
        project_id=int(tok_pid) if tok_pid else None,
    )
    return {"updated": int(updated or 0), "message": f"已标记 {int(updated or 0)} 条为已读"}


# ---------- 通知配置 / 日志 ----------


async def tool_list_notification_configs(
    ctx: McpAuthContext,
    project_id: int,
) -> dict[str, Any]:
    """列出项目通知渠道配置（Webhook / 收件人已脱敏）。"""
    ensure_permission(ctx, NOTIFICATION_CONFIG_VIEW)
    from brickcore_assist.skills.access import require_project_access

    pid = await require_project_access(ctx, int(project_id), min_role=PROJECT_ROLE_VIEWER)
    configs = await NotificationConfig.filter(project_id=pid).all()
    items = []
    for cfg in configs:
        items.append(
            {
                "id": cfg.id,
                "project_id": cfg.project_id,
                "channel_type": cfg.channel_type,
                "enabled": cfg.enabled,
                "api_alert_on_failure": getattr(cfg, "api_alert_on_failure", True),
                "ui_alert_on_failure": getattr(cfg, "ui_alert_on_failure", True),
                "perf_alert_on_failure": getattr(cfg, "perf_alert_on_failure", True),
                "app_alert_on_failure": getattr(cfg, "app_alert_on_failure", True),
                "api_auto_push_report": bool(
                    getattr(cfg, "api_suite_auto_push_report", False)
                    or getattr(cfg, "api_plan_auto_push_report", False)
                    or getattr(cfg, "api_auto_push_report", False)
                ),
                "ui_auto_push_report": bool(
                    getattr(cfg, "ui_suite_auto_push_report", False)
                    or getattr(cfg, "ui_plan_auto_push_report", False)
                    or getattr(cfg, "ui_auto_push_report", False)
                ),
                "app_auto_push_report": bool(
                    getattr(cfg, "app_suite_auto_push_report", False)
                    or getattr(cfg, "app_plan_auto_push_report", False)
                    or getattr(cfg, "app_auto_push_report", False)
                ),
                "perf_auto_push_report": bool(getattr(cfg, "perf_auto_push_report", False)),
                "tm_assignment_notify": bool(getattr(cfg, "tm_assignment_notify", True)),
                "config": _mask_notify_channel_config(cfg.channel_type, cfg.config),
            }
        )
    return {"project_id": pid, "items": items, "total": len(items)}


async def tool_list_notification_logs(
    ctx: McpAuthContext,
    project_id: int,
    channel_type: str = "",
    notify_type: str = "",
    status: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出项目通知推送记录。"""
    ensure_permission(ctx, NOTIFICATION_LOG_VIEW)
    from brickcore_assist.skills.access import require_project_access

    pid = await require_project_access(ctx, int(project_id), min_role=PROJECT_ROLE_VIEWER)
    page = max(int(page or 1), 1)
    size = min(max(int(size or 20), 1), 50)
    qs = NotificationLog.filter(project_id=pid).order_by("-id")
    if (channel_type or "").strip():
        qs = qs.filter(channel_type=channel_type.strip())
    if (notify_type or "").strip():
        qs = qs.filter(notify_type=notify_type.strip())
    if (status or "").strip():
        qs = qs.filter(status=status.strip())
    total = await qs.count()
    rows = await qs.offset((page - 1) * size).limit(size)
    items = []
    for item in rows:
        create_time = item.create_time
        if hasattr(create_time, "strftime"):
            create_time = create_time.strftime("%Y-%m-%d %H:%M:%S")
        items.append(
            {
                "id": item.id,
                "project_id": item.project_id,
                "channel_type": item.channel_type,
                "notify_type": item.notify_type,
                "title": _clip(item.title, 200),
                "status": item.status,
                "error_msg": _clip(item.error_msg, 300),
                "related_id": item.related_id,
                "related_type": item.related_type,
                "recipients": item.recipients if isinstance(item.recipients, list) else [],
                "create_time": create_time,
            }
        )
    return {"total": total, "page": page, "size": size, "items": items}
