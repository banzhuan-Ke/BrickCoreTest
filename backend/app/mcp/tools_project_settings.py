"""MCP Wave E / M4：项目设置、环境、设备、成员（只读，脱敏）。"""
from __future__ import annotations

from typing import Any, Optional

from app.core.platform.permissions import (
    AI_CONFIG_VIEW,
    DEVICE_VIEW,
    PROJECT_SETTINGS_VIEW,
    PROJECT_VIEW,
)
from app.core.platform.project_access import PROJECT_ROLE_LABELS, PROJECT_ROLE_VIEWER
from app.core.shared.global_vars_validate import is_secret_key
from app.core.shared.ui_env_exec_strategy import (
    DEFAULT_TIMEOUT_SCALE,
    parse_ui_action_settle_ms,
    parse_ui_nav_wait_until,
    parse_ui_timeout_scale,
)
from app.mcp.auth import McpAuthContext, ensure_any_permission, ensure_permission
from app.models.sys import Device, Environment, Project, ProjectMember
from app.modules.ai.ai_project_settings import load_ai_project_settings
from app.modules.ui.ui_debug_steps import get_env_default_start_url

_ONLINE_STATUS = frozenset({"在线", "执行中"})
_HEADER_SECRET_HINTS = ("authorization", "token", "cookie", "secret", "api-key", "apikey")


def _clip(text: Any, limit: int = 200) -> str:
    s = "" if text is None else str(text)
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    return iso() if callable(iso) else _clip(value, 40)


async def _require_project(ctx: McpAuthContext, project_id: int) -> int:
    from brickcore_assist.skills.access import require_project_access

    return await require_project_access(ctx, int(project_id), min_role=PROJECT_ROLE_VIEWER)


def _ensure_settings_view(ctx: McpAuthContext) -> None:
    ensure_any_permission(ctx, PROJECT_SETTINGS_VIEW, AI_CONFIG_VIEW)


def _mask_var_value(key: str, raw: Any) -> dict[str, Any]:
    description = ""
    secret = is_secret_key(key)
    value: Any = raw
    if isinstance(raw, dict) and "value" in raw:
        value = raw.get("value")
        description = str(raw.get("description") or "")
        secret = secret or bool(raw.get("secret"))
    if secret:
        return {"value": "****", "secret": True, "description": _clip(description, 80)}
    return {"value": _clip(value, 200), "secret": False, "description": _clip(description, 80)}


def _mask_headers(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items[:40]:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "")
        low = key.lower()
        secret = is_secret_key(key) or any(hint in low for hint in _HEADER_SECRET_HINTS)
        out.append(
            {
                "key": key,
                "value": "****" if secret else _clip(item.get("value"), 160),
                "enabled": item.get("enabled", True) is not False,
                "secret": secret,
            }
        )
    return out


def _device_summary(device: Device) -> dict[str, Any]:
    engines = device.runner_engine_types if isinstance(device.runner_engine_types, list) else ["web"]
    status = device.status or "离线"
    toolchain = device.toolchain_status if isinstance(device.toolchain_status, dict) else {}
    return {
        "id": device.id,
        "name": device.name or device.hostname or device.id,
        "ip": device.ip,
        "hostname": device.hostname or "",
        "system": device.system,
        "status": status,
        "is_online": status in _ONLINE_STATUS,
        "is_stopped": status == "已停止",
        "version": device.version or "",
        "runner_client_version": device.runner_client_version or "",
        "runner_last_heartbeat": _iso(device.runner_last_heartbeat),
        "runner_engine_types": engines or ["web"],
        "app_udid": (device.app_udid or "").strip(),
        "app_connection": (device.app_connection or "").strip(),
        "app_platform": (device.app_platform or "").strip(),
        "toolchain_status": toolchain,
        "update_time": _iso(device.update_time),
    }


def _timeout_hint(settings: dict[str, Any]) -> dict[str, Any]:
    seconds = settings.get("debug_max_step_timeout_seconds")
    return {
        "debug_max_step_timeout_seconds": seconds,
        "note": (
            f"交互调试单步最大超时 {seconds} 秒；"
            "正式执行仍用步骤自身超时，环境可另设 UI 超时倍率 __ui_timeout_scale"
        ),
    }


async def tool_get_project_settings_overview(
    ctx: McpAuthContext,
    project_id: int,
) -> dict[str, Any]:
    """项目设置概览：当前项目、执行策略摘要、调试超时。"""
    _ensure_settings_view(ctx)
    pid = await _require_project(ctx, project_id)
    project = await Project.get_or_none(id=pid, is_del=False)
    if not project:
        raise ValueError("项目不存在")
    settings = await load_ai_project_settings(pid)
    rc = settings.get("requirement_case") if isinstance(settings.get("requirement_case"), dict) else {}
    return {
        "project_id": pid,
        "project_name": project.name,
        "scope": "project",
        "sections": {
            "execution": True,
            "notification": True,
            "test_notify": True,
            "quality_gate": True,
        },
        "execution_summary": {
            "locator_heal_enabled": settings.get("locator_heal_enabled"),
            "ai_act_enabled": settings.get("ai_act_enabled"),
            "failure_analysis_enabled": settings.get("failure_analysis_enabled"),
            "auto_count_enabled_default": rc.get("auto_count_enabled_default"),
            "auto_count_min_floor": rc.get("auto_count_min_floor"),
            "auto_count_max_cap": rc.get("auto_count_max_cap"),
            "fixed_count_hard_max": rc.get("fixed_count_hard_max"),
        },
        "timeouts": _timeout_hint(settings),
        "navigate": "/project-settings?tab=execution",
    }


async def tool_get_project_execution_settings(
    ctx: McpAuthContext,
    project_id: int,
) -> dict[str, Any]:
    """获取项目执行设置（含调试单步超时；不含密钥）。"""
    _ensure_settings_view(ctx)
    pid = await _require_project(ctx, project_id)
    project = await Project.get_or_none(id=pid, is_del=False)
    if not project:
        raise ValueError("项目不存在")
    settings = await load_ai_project_settings(pid)
    return {
        "project_id": pid,
        "project_name": project.name,
        "settings": settings,
        "timeouts": _timeout_hint(settings),
        "navigate": "/project-settings?tab=execution",
    }


async def tool_get_environment_detail(
    ctx: McpAuthContext,
    project_id: int,
    env_id: int,
) -> dict[str, Any]:
    """获取环境详情：地址、脱敏变量、UI 超时倍率。"""
    ensure_permission(ctx, PROJECT_VIEW)
    pid = await _require_project(ctx, project_id)
    env = await Environment.get_or_none(id=int(env_id), project_id=pid, is_del=False)
    if not env:
        raise ValueError("环境不存在或不属于当前项目")
    raw_vars = env.global_vars if isinstance(env.global_vars, dict) else {}
    variables = {str(k): _mask_var_value(str(k), v) for k, v in list(raw_vars.items())[:80]}
    scale = parse_ui_timeout_scale(raw_vars)
    return {
        "id": env.id,
        "project_id": pid,
        "name": env.name,
        "host": env.host,
        "username": env.username,
        "default_start_url": _clip(get_env_default_start_url(raw_vars), 300),
        "ui_exec_strategy": {
            "timeout_scale": scale,
            "timeout_scale_is_default": scale == DEFAULT_TIMEOUT_SCALE,
            "nav_wait_until": parse_ui_nav_wait_until(raw_vars),
            "action_settle_ms": parse_ui_action_settle_ms(raw_vars),
        },
        "variables": variables,
        "variable_count": len(raw_vars),
        "default_headers": _mask_headers(env.default_headers),
        "update_time": _iso(env.update_time),
        "note": "正式 Web UI 步骤超时会再乘 timeout_scale；密钥类变量已脱敏",
    }


async def tool_list_devices(
    ctx: McpAuthContext,
    project_id: Optional[int] = None,
    status: str = "",
    keyword: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """列出 Runner 设备（含在线状态；不含连接凭证）。"""
    ensure_permission(ctx, DEVICE_VIEW)
    if project_id is not None:
        await _require_project(ctx, project_id)
    status_text = (status or "").strip()
    query = Device.filter(is_del=False)
    if status_text:
        query = query.filter(status=status_text)
    rows = await query.order_by("-update_time").limit(200)
    needle = (keyword or "").strip().lower()
    items = []
    for device in rows:
        summary = _device_summary(device)
        if needle:
            blob = " ".join(
                [
                    str(summary.get("id") or ""),
                    str(summary.get("name") or ""),
                    str(summary.get("ip") or ""),
                    str(summary.get("hostname") or ""),
                ]
            ).lower()
            if needle not in blob:
                continue
        items.append(summary)
    page_no = max(1, int(page or 1))
    page_size = min(50, max(1, int(size or 20)))
    start = (page_no - 1) * page_size
    return {
        "project_id": int(project_id) if project_id is not None else None,
        "items": items[start : start + page_size],
        "total": len(items),
        "page": page_no,
        "size": page_size,
        "online_count": sum(1 for item in items if item.get("is_online")),
        "note": "Runner 为全局资源；不返回 MQ/Redis 凭证",
    }


async def tool_get_device_detail(
    ctx: McpAuthContext,
    device_id: str,
    project_id: Optional[int] = None,
) -> dict[str, Any]:
    """获取单台 Runner 设备详情（在线、心跳、引擎能力）。"""
    ensure_permission(ctx, DEVICE_VIEW)
    if project_id is not None:
        await _require_project(ctx, project_id)
    device_key = (device_id or "").strip()
    if not device_key:
        raise ValueError("device_id 必填")
    device = await Device.get_or_none(id=device_key, is_del=False)
    if not device:
        raise ValueError("设备不存在或已被删除")
    detail = _device_summary(device)
    detail["project_id"] = int(project_id) if project_id is not None else None
    return detail


async def tool_list_project_members(
    ctx: McpAuthContext,
    project_id: int,
) -> dict[str, Any]:
    """列出项目成员与角色（不含邮箱、手机号）。"""
    ensure_permission(ctx, PROJECT_VIEW)
    pid = await _require_project(ctx, project_id)
    rows = await (
        ProjectMember.filter(project_id=pid, is_del=False)
        .order_by("-id")
        .prefetch_related("user", "invited_by")
    )
    items = []
    for row in rows[:200]:
        user = row.user
        invited = row.invited_by
        items.append(
            {
                "id": row.id,
                "user_id": row.user_id,
                "username": user.username if user else "",
                "nickname": user.nickname if user else "",
                "role": row.role,
                "role_label": PROJECT_ROLE_LABELS.get(row.role, row.role),
                "invited_by_username": invited.username if invited else "",
                "create_time": _iso(row.create_time),
            }
        )
    return {"project_id": pid, "total": len(rows), "items": items}
