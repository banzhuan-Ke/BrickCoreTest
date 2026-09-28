"""MCP 管理写操作：默认模型 / API Key / 测试通知 / 环境变量 / 设备 / 成员 / 质量门禁。

高危操作一律 preview → confirm；密钥脱敏，不回传明文。
"""
from __future__ import annotations

from typing import Any, Optional

from app.core.integration.mcp_confirm import consume_confirm_token, create_confirm_token
from app.core.platform.permissions import (
    AI_CONFIG_EDIT,
    AI_CONFIG_VIEW,
    DEVICE_EDIT,
    ENVIRONMENT_EDIT,
    NOTIFICATION_CONFIG_EDIT,
    PROJECT_SETTINGS_EDIT,
    PROJECT_SETTINGS_VIEW,
)
from app.core.platform.project_access import (
    ALL_PROJECT_ROLES,
    PROJECT_ROLE_MANAGER,
    PROJECT_ROLE_MEMBER,
    PROJECT_ROLE_OWNER,
    PROJECT_ROLE_VIEWER,
)
from app.mcp.auth import McpAuthContext, ensure_any_permission, ensure_permission
from app.mcp.tools_ai_notify import _mask_ai_config, _mask_notify_channel_config


def _require_login_user(ctx: McpAuthContext, *, op: str) -> None:
    """高危写操作禁止纯 MCP API Key：须登录用户 JWT（可审计到具体人）。"""
    if ctx.is_api_key or not ctx.user_id:
        raise ValueError(f"{op} 须使用登录用户 JWT，不支持仅凭 MCP API Key 执行")


def _clip(text: Any, limit: int = 200) -> str:
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


async def _require_project(ctx: McpAuthContext, project_id: int, *, min_role: str = PROJECT_ROLE_VIEWER) -> int:
    from brickcore_assist.skills.access import require_project_access

    return await require_project_access(ctx, int(project_id), min_role=min_role)


async def _await_route(coro):
    from fastapi import HTTPException

    try:
        return await coro
    except HTTPException as exc:
        raise ValueError(_http_detail(exc)) from exc


def _unwrap(resp: Any) -> Any:
    data = getattr(resp, "data", None)
    if data is not None:
        return data
    if isinstance(resp, dict) and "data" in resp:
        return resp.get("data")
    return resp


def _device_safe(device: Any) -> dict[str, Any]:
    return {
        "id": getattr(device, "id", None),
        "name": getattr(device, "name", None),
        "ip": getattr(device, "ip", None),
        "system": getattr(device, "system", None),
        "status": getattr(device, "status", None),
        "hostname": getattr(device, "hostname", None) or "",
        "version": getattr(device, "version", None) or "",
        "runner_client_version": getattr(device, "runner_client_version", None) or "",
        "runner_engine_types": list(getattr(device, "runner_engine_types", None) or []),
    }


# ---------- AI 配置写 ----------


async def tool_preview_set_default_ai_config(ctx: McpAuthContext, config_id: int) -> dict[str, Any]:
    """预览将指定 LLM 配置设为平台默认。"""
    ensure_permission(ctx, AI_CONFIG_EDIT)
    from app.models.ai import AiConfig

    config = await AiConfig.get_or_none(id=int(config_id), is_del=False)
    if not config:
        raise ValueError("AI 配置不存在")
    impact = {
        "config_id": config.id,
        "name": config.name,
        "model": config.model,
        "provider": config.provider,
        "was_default": bool(config.is_default),
        "warning": "将取消其它配置的默认标记，并把本配置设为平台默认模型",
    }
    token = await create_confirm_token(
        "set_default_ai_config",
        {"config_id": int(config.id)},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_set_default_ai_config 并传入 confirm_token",
    }


async def tool_confirm_set_default_ai_config(
    ctx: McpAuthContext,
    confirm_token: str,
    config_id: int,
) -> dict[str, Any]:
    ensure_permission(ctx, AI_CONFIG_EDIT)
    payload = await consume_confirm_token(confirm_token, "set_default_ai_config", ctx.username)
    if int(payload.get("config_id") or 0) != int(config_id):
        raise ValueError("config_id 与确认 Token 不匹配")

    from app.routers.ai.config import set_default_config

    resp = await _await_route(set_default_config(int(config_id), user_info=_ctx_user_info(ctx)))
    data = _unwrap(resp)
    return {"ok": True, "config": data}


async def tool_preview_update_ai_config_api_key(
    ctx: McpAuthContext,
    config_id: int,
    api_key: str,
) -> dict[str, Any]:
    """预览更新 LLM 配置的 API Key（确认后才写入；Key 不明文回显）。"""
    _require_login_user(ctx, op="更新 AI API Key")
    ensure_permission(ctx, AI_CONFIG_EDIT)
    from app.models.ai import AiConfig

    config = await AiConfig.get_or_none(id=int(config_id), is_del=False)
    if not config:
        raise ValueError("AI 配置不存在")
    key = (api_key or "").strip()
    if not key:
        raise ValueError("api_key 不能为空")
    if "****" in key:
        raise ValueError("请传入完整 API Key，不要传脱敏占位符")
    impact = {
        "config_id": config.id,
        "name": config.name,
        "model": config.model,
        "api_key_preview": (key[:4] + "****" + key[-4:]) if len(key) > 8 else "****",
        "warning": "将覆盖该配置的 API Key（加密存储）",
    }
    token = await create_confirm_token(
        "update_ai_config_api_key",
        {"config_id": int(config.id), "api_key": key},
        ctx.username,
        seal_keys=["api_key"],
    )
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_update_ai_config_api_key 并传入 confirm_token（无需再传 api_key）",
    }


async def tool_confirm_update_ai_config_api_key(
    ctx: McpAuthContext,
    confirm_token: str,
    config_id: int,
) -> dict[str, Any]:
    """确认更新 API Key；密钥仅从 Token 取出，不接受客户端再传明文。"""
    _require_login_user(ctx, op="更新 AI API Key")
    ensure_permission(ctx, AI_CONFIG_EDIT)
    payload = await consume_confirm_token(confirm_token, "update_ai_config_api_key", ctx.username)
    if int(payload.get("config_id") or 0) != int(config_id):
        raise ValueError("config_id 与确认 Token 不匹配")
    key = (payload.get("api_key") or "").strip()
    if not key or "****" in key:
        raise ValueError("确认 Token 中缺少有效 api_key，请重新 preview")

    from app.routers.ai.config import update_config
    from app.schemas.ai import AiConfigUpdate

    item = AiConfigUpdate(api_key=key)
    resp = await _await_route(update_config(int(config_id), item, user_info=_ctx_user_info(ctx)))
    data = _unwrap(resp)
    if hasattr(data, "api_key") or hasattr(data, "id"):
        try:
            from app.models.ai import AiConfig

            cfg = await AiConfig.get_or_none(id=int(config_id), is_del=False)
            return {"ok": True, "config": _mask_ai_config(cfg) if cfg else data}
        except Exception:
            pass
    return {"ok": True, "config": data}


# ---------- 测试通知 ----------


async def tool_preview_test_notification_config(
    ctx: McpAuthContext,
    config_id: int,
) -> dict[str, Any]:
    """预览向通知渠道发送一条测试消息。"""
    ensure_permission(ctx, NOTIFICATION_CONFIG_EDIT)
    from app.models.sys import NotificationConfig, Project

    cfg = await NotificationConfig.get_or_none(id=int(config_id))
    if not cfg:
        raise ValueError("通知配置不存在")
    await _require_project(ctx, int(cfg.project_id), min_role=PROJECT_ROLE_MEMBER)
    project = await Project.get_or_none(id=cfg.project_id)
    impact = {
        "config_id": cfg.id,
        "project_id": cfg.project_id,
        "project_name": project.name if project else "",
        "channel_type": cfg.channel_type,
        "channel": _mask_notify_channel_config(cfg.channel_type, cfg.config if isinstance(cfg.config, dict) else {}),
        "warning": "将向该渠道发送一条真实测试消息",
    }
    token = await create_confirm_token(
        "test_notification_config",
        {"config_id": int(cfg.id), "project_id": int(cfg.project_id)},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_test_notification_config 并传入 confirm_token",
    }


async def tool_confirm_test_notification_config(
    ctx: McpAuthContext,
    confirm_token: str,
    config_id: int,
) -> dict[str, Any]:
    ensure_permission(ctx, NOTIFICATION_CONFIG_EDIT)
    payload = await consume_confirm_token(confirm_token, "test_notification_config", ctx.username)
    if int(payload.get("config_id") or 0) != int(config_id):
        raise ValueError("config_id 与确认 Token 不匹配")
    from app.models.sys import NotificationConfig
    from app.routers.sys.notifications import test_notification_config

    cfg = await NotificationConfig.get_or_none(id=int(config_id))
    if not cfg:
        raise ValueError("通知配置不存在")
    await _require_project(ctx, int(cfg.project_id), min_role=PROJECT_ROLE_MEMBER)
    await _await_route(test_notification_config(int(config_id)))
    return {"ok": True, "config_id": int(config_id), "message": "测试消息已发送"}


# ---------- 环境变量批量 ----------


async def tool_preview_batch_env_vars(
    ctx: McpAuthContext,
    project_id: int,
    mode: str,
    keys: list[str],
    target_env_ids: Optional[list[int]] = None,
    source_env_id: Optional[int] = None,
    default_values: Optional[dict] = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    """预览跨环境批量增删/同步变量（不回显变量值）。"""
    ensure_permission(ctx, ENVIRONMENT_EDIT)
    pid = await _require_project(ctx, project_id, min_role=PROJECT_ROLE_MEMBER)
    mode_s = (mode or "").strip()
    if mode_s not in ("add_keys", "delete_keys", "sync_values"):
        raise ValueError("mode 须为 add_keys / delete_keys / sync_values")
    key_list = [str(k).strip() for k in (keys or []) if str(k).strip()]
    if not key_list:
        raise ValueError("keys 不能为空")
    if len(key_list) > 50:
        raise ValueError("单次最多 50 个变量名")
    # 默认值不进 impact 明文；仅记键名
    impact = {
        "project_id": pid,
        "mode": mode_s,
        "keys": key_list,
        "target_env_ids": [int(x) for x in (target_env_ids or [])],
        "source_env_id": int(source_env_id) if source_env_id else None,
        "overwrite": bool(overwrite),
        "default_value_keys": list((default_values or {}).keys())[:50],
        "warning": "将修改目标环境的 global_vars；delete/sync 可能覆盖已有值",
    }
    defaults = default_values or {}
    if not isinstance(defaults, dict):
        raise ValueError("default_values 须为对象")
    if len(defaults) > 50:
        raise ValueError("default_values 单次最多 50 个键")
    for dk, dv in defaults.items():
        if len(str(dk)) > 128:
            raise ValueError("default_values 键名过长")
        if len(str(dv) if dv is not None else "") > 8000:
            raise ValueError(f"default_values[{dk}] 值过长（最多 8000 字符）")
    token = await create_confirm_token(
        "batch_env_vars",
        {
            "project_id": pid,
            "mode": mode_s,
            "keys": key_list,
            "target_env_ids": [int(x) for x in (target_env_ids or [])],
            "source_env_id": int(source_env_id) if source_env_id else None,
            "default_values": defaults,
            "overwrite": bool(overwrite),
        },
        ctx.username,
        seal_keys=["default_values"],
    )
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_batch_env_vars 并传入 confirm_token",
    }


async def tool_confirm_batch_env_vars(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    mode: str,
    keys: list[str],
    target_env_ids: Optional[list[int]] = None,
    source_env_id: Optional[int] = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    """确认批量改环境变量；执行参数一律取自 Token，客户端仅作身份核对。"""
    ensure_permission(ctx, ENVIRONMENT_EDIT)
    pid = await _require_project(ctx, project_id, min_role=PROJECT_ROLE_MEMBER)
    payload = await consume_confirm_token(confirm_token, "batch_env_vars", ctx.username)
    if int(payload.get("project_id") or 0) != pid:
        raise ValueError("project_id 与确认 Token 不匹配")
    if (payload.get("mode") or "") != (mode or "").strip():
        raise ValueError("mode 与确认 Token 不匹配")
    tok_keys = [str(k).strip() for k in (payload.get("keys") or []) if str(k).strip()]
    if tok_keys != [str(k).strip() for k in (keys or []) if str(k).strip()]:
        raise ValueError("keys 与确认 Token 不匹配")
    tok_targets = [int(x) for x in (payload.get("target_env_ids") or [])]
    if tok_targets != [int(x) for x in (target_env_ids or [])]:
        raise ValueError("target_env_ids 与确认 Token 不匹配")
    tok_source = payload.get("source_env_id")
    if (int(tok_source) if tok_source is not None else None) != (
        int(source_env_id) if source_env_id else None
    ):
        raise ValueError("source_env_id 与确认 Token 不匹配")
    if bool(payload.get("overwrite", True)) != bool(overwrite):
        raise ValueError("overwrite 与确认 Token 不匹配")

    from app.routers.sys.envs import EnvBatchVarsBody, batch_env_vars

    body = EnvBatchVarsBody(
        project_id=pid,
        mode=(payload.get("mode") or "").strip(),
        keys=tok_keys,
        target_env_ids=tok_targets,
        source_env_id=int(tok_source) if tok_source is not None else None,
        default_values=payload.get("default_values") or {},
        overwrite=bool(payload.get("overwrite", True)),
    )
    result = await _await_route(batch_env_vars(body, user_info=_ctx_user_info(ctx)))
    return {"ok": True, "result": result}


# ---------- 设备 ----------


async def tool_preview_register_device(
    ctx: McpAuthContext,
    device_id: str,
    name: str,
    ip: str,
    system: str,
    username: str = "",
    version: str = "",
    hostname: str = "",
) -> dict[str, Any]:
    """预览登记 Runner 设备基础信息（不改在线状态、不覆盖 Runner 元数据）。"""
    ensure_permission(ctx, DEVICE_EDIT)
    from app.models.sys import Device

    did = (device_id or "").strip()
    if not did:
        raise ValueError("device_id 必填")
    if not (name or "").strip() or not (ip or "").strip() or not (system or "").strip():
        raise ValueError("name / ip / system 必填")
    existing = await Device.get_or_none(id=did, is_del=False)
    impact = {
        "device_id": did,
        "name": _clip(name, 80),
        "ip": _clip(ip, 64),
        "system": _clip(system, 40),
        "username": _clip(username or ctx.username, 40),
        "exists": bool(existing),
        "warning": (
            "将仅更新 name/ip/system/hostname/version/username，不改状态与 Runner 引擎元数据"
            if existing
            else "将新建设备记录，状态为「离线」（须 Runner 自行上线）"
        ),
    }
    token = await create_confirm_token(
        "register_device",
        {
            "id": did,
            "name": (name or "").strip(),
            "ip": (ip or "").strip(),
            "system": (system or "").strip(),
            "username": (username or ctx.username or "").strip() or "mcp",
            "version": (version or "").strip(),
            "hostname": (hostname or "").strip(),
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_register_device 并传入 confirm_token",
    }


async def tool_confirm_register_device(
    ctx: McpAuthContext,
    confirm_token: str,
    device_id: str,
) -> dict[str, Any]:
    ensure_permission(ctx, DEVICE_EDIT)
    payload = await consume_confirm_token(confirm_token, "register_device", ctx.username)
    if (payload.get("id") or "") != (device_id or "").strip():
        raise ValueError("device_id 与确认 Token 不匹配")

    from app.models.sys import Device
    from app.modules.runner.runner_device_control import STOPPED_STATUS

    did = payload["id"]
    device = await Device.get_or_none(id=did, is_del=False)
    if device and device.status == STOPPED_STATUS:
        raise ValueError("设备已被管理员停止，请在 Runner 客户端重新上线")
    fields = {
        "name": payload.get("name") or "",
        "ip": payload.get("ip") or "",
        "system": payload.get("system") or "",
        "username": payload.get("username") or "mcp",
        "version": payload.get("version") or "",
        "hostname": payload.get("hostname") or "",
    }
    if device:
        # 只改基础展示字段，绝不覆盖 status / runner_* / app_* / toolchain
        device.update_from_dict(fields)
        await device.save(update_fields=list(fields.keys()) + ["update_time"])
    else:
        device = await Device.create(
            id=did,
            **fields,
            status="离线",
        )
    return {"ok": True, "device": _device_safe(device)}


async def tool_preview_delete_device(ctx: McpAuthContext, device_id: str) -> dict[str, Any]:
    """预览删除（逻辑删除）Runner 设备。"""
    _require_login_user(ctx, op="删除设备")
    ensure_permission(ctx, DEVICE_EDIT)
    from app.models.sys import Device

    did = (device_id or "").strip()
    device = await Device.get_or_none(id=did, is_del=False)
    if not device:
        raise ValueError("设备不存在或已被删除")
    impact = {
        "device_id": device.id,
        "name": device.name,
        "status": device.status,
        "warning": "将逻辑删除设备并清理 MQ 队列 / 吊销中间件凭证；Runner 需重新上线",
    }
    token = await create_confirm_token("delete_device", {"device_id": did}, ctx.username)
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_delete_device 并传入 confirm_token",
    }


async def tool_confirm_delete_device(
    ctx: McpAuthContext,
    confirm_token: str,
    device_id: str,
) -> dict[str, Any]:
    _require_login_user(ctx, op="删除设备")
    ensure_permission(ctx, DEVICE_EDIT)
    payload = await consume_confirm_token(confirm_token, "delete_device", ctx.username)
    if (payload.get("device_id") or "") != (device_id or "").strip():
        raise ValueError("device_id 与确认 Token 不匹配")
    from app.routers.sys.devices import delete_device

    await _await_route(delete_device((device_id or "").strip(), user_info=_ctx_user_info(ctx)))
    return {"ok": True, "device_id": (device_id or "").strip(), "deleted": True}


# ---------- 项目成员 ----------


async def tool_preview_add_project_member(
    ctx: McpAuthContext,
    project_id: int,
    user_id: int,
    role: str = "member",
) -> dict[str, Any]:
    """预览添加项目成员（不可直接设为 owner）。"""
    pid = await _require_project(ctx, project_id, min_role=PROJECT_ROLE_MANAGER)
    role_s = (role or "member").strip() or PROJECT_ROLE_MEMBER
    if role_s not in ALL_PROJECT_ROLES:
        raise ValueError(f"无效的项目角色，可选: {[r for r in ALL_PROJECT_ROLES if r != PROJECT_ROLE_OWNER]}")
    if role_s == PROJECT_ROLE_OWNER:
        raise ValueError("请使用 preview_transfer_project_owner 转让负责人")
    from fastapi import HTTPException

    from app.core.platform.project_access import assert_project_access
    from app.models.sys import ProjectMember, User

    try:
        my_role = await assert_project_access(_ctx_user_info(ctx), pid, min_role=PROJECT_ROLE_MANAGER)
    except HTTPException as exc:
        raise ValueError(_http_detail(exc)) from exc
    if role_s == PROJECT_ROLE_MANAGER and my_role != PROJECT_ROLE_OWNER:
        raise ValueError("仅项目负责人可添加项目管理员")

    user = await User.get_or_none(id=int(user_id), is_del=False)
    if not user:
        raise ValueError("用户不存在")
    existing = await ProjectMember.get_or_none(project_id=pid, user_id=int(user_id), is_del=False)
    if existing:
        raise ValueError("该用户已是项目成员")
    impact = {
        "project_id": pid,
        "user_id": int(user_id),
        "username": user.username,
        "role": role_s,
        "warning": "将把该用户加入项目",
    }
    token = await create_confirm_token(
        "add_project_member",
        {"project_id": pid, "user_id": int(user_id), "role": role_s},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_add_project_member 并传入 confirm_token",
    }


async def tool_confirm_add_project_member(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    user_id: int,
    role: str = "member",
) -> dict[str, Any]:
    pid = await _require_project(ctx, project_id, min_role=PROJECT_ROLE_MANAGER)
    payload = await consume_confirm_token(confirm_token, "add_project_member", ctx.username)
    if int(payload.get("project_id") or 0) != pid:
        raise ValueError("project_id 与确认 Token 不匹配")
    if int(payload.get("user_id") or 0) != int(user_id):
        raise ValueError("user_id 与确认 Token 不匹配")
    tok_role = (payload.get("role") or "member").strip()
    if tok_role != (role or "member").strip():
        raise ValueError("role 与确认 Token 不匹配")

    from app.routers.sys.project_members import add_member
    from app.schemas.sys import AddProjectMemberForm

    item = AddProjectMemberForm(user_id=int(payload["user_id"]), role=tok_role)
    member = await _await_route(add_member(pid, item, user_info=_ctx_user_info(ctx)))
    data = member.model_dump() if hasattr(member, "model_dump") else dict(member)
    return {"ok": True, "member": data}


async def tool_preview_remove_project_member(
    ctx: McpAuthContext,
    project_id: int,
    member_id: int,
) -> dict[str, Any]:
    """预览移除项目成员（member 行 id，不是 user_id）。"""
    pid = await _require_project(ctx, project_id, min_role=PROJECT_ROLE_MANAGER)
    from app.models.sys import ProjectMember

    row = await ProjectMember.get_or_none(id=int(member_id), project_id=pid, is_del=False)
    if not row:
        raise ValueError("成员不存在")
    if row.role == PROJECT_ROLE_OWNER:
        raise ValueError("不可移除项目负责人，请先转让负责人")
    if ctx.user_id and int(row.user_id) == int(ctx.user_id):
        raise ValueError("不能移除自己，请联系其他管理员")
    await row.fetch_related("user")
    impact = {
        "project_id": pid,
        "member_id": row.id,
        "user_id": row.user_id,
        "username": getattr(row.user, "username", "") if row.user else "",
        "role": row.role,
        "warning": "将软删除该项目成员关系",
    }
    token = await create_confirm_token(
        "remove_project_member",
        {"project_id": pid, "member_id": int(row.id)},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_remove_project_member 并传入 confirm_token",
    }


async def tool_confirm_remove_project_member(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    member_id: int,
) -> dict[str, Any]:
    pid = await _require_project(ctx, project_id, min_role=PROJECT_ROLE_MANAGER)
    payload = await consume_confirm_token(confirm_token, "remove_project_member", ctx.username)
    if int(payload.get("project_id") or 0) != pid:
        raise ValueError("project_id 与确认 Token 不匹配")
    if int(payload.get("member_id") or 0) != int(member_id):
        raise ValueError("member_id 与确认 Token 不匹配")
    from app.routers.sys.project_members import remove_member

    await _await_route(remove_member(pid, int(member_id), user_info=_ctx_user_info(ctx)))
    return {"ok": True, "member_id": int(member_id), "removed": True}


async def tool_preview_transfer_project_owner(
    ctx: McpAuthContext,
    project_id: int,
    user_id: int,
) -> dict[str, Any]:
    """预览转让项目负责人（仅当前 owner 可操作；须登录 JWT）。"""
    _require_login_user(ctx, op="转让项目负责人")
    pid = await _require_project(ctx, project_id, min_role=PROJECT_ROLE_OWNER)
    from app.models.sys import ProjectMember, User

    target = await ProjectMember.get_or_none(project_id=pid, user_id=int(user_id), is_del=False)
    if not target:
        raise ValueError("目标用户不是项目成员，请先添加为成员")
    user = await User.get_or_none(id=int(user_id), is_del=False)
    impact = {
        "project_id": pid,
        "new_owner_user_id": int(user_id),
        "new_owner_username": user.username if user else "",
        "warning": "当前负责人将降为项目管理员，目标用户成为新负责人",
    }
    token = await create_confirm_token(
        "transfer_project_owner",
        {"project_id": pid, "user_id": int(user_id)},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_transfer_project_owner 并传入 confirm_token",
    }


async def tool_confirm_transfer_project_owner(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
    user_id: int,
) -> dict[str, Any]:
    _require_login_user(ctx, op="转让项目负责人")
    pid = await _require_project(ctx, project_id, min_role=PROJECT_ROLE_OWNER)
    payload = await consume_confirm_token(confirm_token, "transfer_project_owner", ctx.username)
    if int(payload.get("project_id") or 0) != pid:
        raise ValueError("project_id 与确认 Token 不匹配")
    if int(payload.get("user_id") or 0) != int(user_id):
        raise ValueError("user_id 与确认 Token 不匹配")
    from app.routers.sys.project_members import transfer_owner
    from app.schemas.sys import TransferProjectOwnerForm

    result = await _await_route(
        transfer_owner(pid, TransferProjectOwnerForm(user_id=int(user_id)), user_info=_ctx_user_info(ctx))
    )
    return {"ok": True, "result": result}


# ---------- 质量门禁 ----------


async def tool_get_quality_gate_settings(ctx: McpAuthContext, project_id: int) -> dict[str, Any]:
    """读取项目质量门禁阈值（无扩展包时返回默认值 + premium_required）。"""
    ensure_any_permission(ctx, PROJECT_SETTINGS_VIEW, AI_CONFIG_VIEW)
    pid = await _require_project(ctx, project_id)
    from app.modules.test_management.premium_gateway import tm_premium_ready
    from app.modules.test_management.tm_premium_defaults import DEFAULT_QUALITY_RULES

    if not tm_premium_ready():
        return {**DEFAULT_QUALITY_RULES, "premium_required": True, "project_id": pid}
    from app.modules.test_management.tm_quality_gate_settings import load_tm_quality_gate_settings

    data = await load_tm_quality_gate_settings(pid)
    return {**(data or {}), "project_id": pid}


async def tool_preview_update_quality_gate_settings(
    ctx: McpAuthContext,
    project_id: int,
    required_completion_min: Optional[float] = None,
    required_pass_rate_min: Optional[float] = None,
    blocker_open_max: Optional[int] = None,
    critical_open_max: Optional[int] = None,
    high_risk_without_result_max: Optional[int] = None,
) -> dict[str, Any]:
    """预览更新质量门禁阈值。"""
    ensure_any_permission(ctx, PROJECT_SETTINGS_EDIT, AI_CONFIG_EDIT)
    pid = await _require_project(ctx, project_id, min_role=PROJECT_ROLE_MEMBER)
    updates = {}
    if required_completion_min is not None:
        updates["required_completion_min"] = float(required_completion_min)
    if required_pass_rate_min is not None:
        updates["required_pass_rate_min"] = float(required_pass_rate_min)
    if blocker_open_max is not None:
        updates["blocker_open_max"] = int(blocker_open_max)
    if critical_open_max is not None:
        updates["critical_open_max"] = int(critical_open_max)
    if high_risk_without_result_max is not None:
        updates["high_risk_without_result_max"] = int(high_risk_without_result_max)
    if not updates:
        raise ValueError("请至少提供一个要更新的阈值字段")
    impact = {
        "project_id": pid,
        "updates": updates,
        "warning": "将更新项目质量门禁阈值（需测试管理扩展包）",
    }
    token = await create_confirm_token(
        "update_quality_gate",
        {"project_id": pid, "updates": updates},
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": token,
        "expires_in_seconds": 300,
        "next_step": "调用 confirm_update_quality_gate_settings 并传入 confirm_token",
    }


async def tool_confirm_update_quality_gate_settings(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
) -> dict[str, Any]:
    ensure_any_permission(ctx, PROJECT_SETTINGS_EDIT, AI_CONFIG_EDIT)
    pid = await _require_project(ctx, project_id, min_role=PROJECT_ROLE_MEMBER)
    payload = await consume_confirm_token(confirm_token, "update_quality_gate", ctx.username)
    if int(payload.get("project_id") or 0) != pid:
        raise ValueError("project_id 与确认 Token 不匹配")
    updates = payload.get("updates") or {}
    if not isinstance(updates, dict) or not updates:
        raise ValueError("确认 Token 中缺少 updates")

    from app.routers.sys.project_settings import QualityGateSettingsBody, update_quality_gate_settings

    body = QualityGateSettingsBody(**{k: v for k, v in updates.items() if v is not None})
    resp = await _await_route(
        update_quality_gate_settings(body, project_id=pid, user_info=_ctx_user_info(ctx))
    )
    return {"ok": True, "settings": _unwrap(resp)}
