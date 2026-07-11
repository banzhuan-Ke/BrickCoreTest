"""MCP 认证上下文解析"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.core.platform.auth import verify_token
from app.core.integration.mcp_config_service import get_mcp_runtime_config
from app.models.sys import User


@dataclass
class McpAuthContext:
    username: str
    user_id: Optional[int] = None
    is_api_key: bool = False
    is_superuser: bool = False
    permissions: set[str] = field(default_factory=set)


async def resolve_mcp_auth(headers: dict[str, str]) -> McpAuthContext:
    """从 HTTP 头解析 MCP 调用身份（API Key 或 JWT）"""
    runtime = await get_mcp_runtime_config()
    if not runtime.enabled:
        raise ValueError("MCP Server 已在平台配置中关闭")

    configured_key = (runtime.api_key or "").strip()
    api_key = (headers.get("x-mcp-api-key") or headers.get("X-MCP-API-Key") or "").strip()
    auth_header = (headers.get("authorization") or headers.get("Authorization") or "").strip()

    bearer = ""
    if auth_header.lower().startswith("bearer "):
        bearer = auth_header[7:].strip()

    if configured_key and (api_key == configured_key or bearer == configured_key):
        return McpAuthContext(username="mcp-api", is_api_key=True, is_superuser=True)

    token = bearer or api_key
    if not token:
        raise ValueError("未提供认证信息，请设置 Authorization: Bearer <JWT 或 MCP API Key>")

    if configured_key and token == configured_key:
        return McpAuthContext(username="mcp-api", is_api_key=True, is_superuser=True)

    data = verify_token(token)
    user = await User.get_or_none(id=data.get("id"), is_del=False).prefetch_related("roles")
    if not user:
        raise ValueError("用户不存在或已被删除")
    if not user.is_active:
        raise ValueError("用户已被停用")

    from app.core.platform.permissions import get_user_permissions

    perms = set(await get_user_permissions(user))
    return McpAuthContext(
        username=user.username,
        user_id=user.id,
        is_superuser=bool(user.is_superuser),
        permissions=perms,
    )


def ensure_permission(ctx: McpAuthContext, *perms: str) -> None:
    if ctx.is_api_key or ctx.is_superuser:
        return
    if not set(perms).issubset(ctx.permissions):
        raise ValueError(f"权限不足，需要: {', '.join(perms)}")


def ensure_any_permission(ctx: McpAuthContext, *perms: str) -> None:
    if ctx.is_api_key or ctx.is_superuser:
        return
    if not perms:
        return
    if not any(p in ctx.permissions for p in perms):
        raise ValueError(f"权限不足，需要以下权限之一: {', '.join(perms)}")
