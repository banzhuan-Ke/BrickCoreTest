"""MCP 接入信息 API（供首页看板 MCP 卡片与平台配置使用）"""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.auth import get_current_username, is_authenticated, require_permissions
from app.core.config import MCP_HTTP_PATH
from app.core.mcp_config_service import (
    get_mcp_config_for_admin,
    get_mcp_runtime_config,
    resolve_public_base_url,
    save_mcp_config,
)
from app.core.permissions import MCP_CONFIG_EDIT, MCP_CONFIG_VIEW
from app.mcp.server import MCP_DANGEROUS_OPS, MCP_TOOL_GROUPS, build_client_config, get_registered_tool_count

router = APIRouter(prefix="/mcp", tags=["MCP"], dependencies=[Depends(is_authenticated)])


class McpConfigForm(BaseModel):
    enabled: bool = True
    base_url: str = Field(default="", description="平台对外访问地址")
    api_key: Optional[str] = Field(default=None, description="留空表示不修改已有密钥")


async def _build_info_payload(request: Request) -> dict:
    cfg = await get_mcp_runtime_config()
    base = resolve_public_base_url(cfg, str(request.base_url).rstrip("/"))
    endpoint = f"{base}{MCP_HTTP_PATH}" if base else MCP_HTTP_PATH
    return {
        "enabled": cfg.enabled,
        "endpoint": endpoint,
        "http_path": MCP_HTTP_PATH,
        "has_api_key": bool(cfg.api_key),
        "config_source": cfg.source,
        "transport": "streamable-http",
        "auth_hint": "Authorization: Bearer <JWT 或 MCP API Key>，也可使用 X-MCP-API-Key 头",
        "tool_count": get_registered_tool_count(),
        "tool_groups": list(MCP_TOOL_GROUPS),
        "client_config": build_client_config(base or "http://localhost:8000", cfg.api_key),
        "dangerous_ops": list(MCP_DANGEROUS_OPS),
    }


@router.get("/info", summary="MCP 接入信息")
async def get_mcp_info(request: Request):
    return await _build_info_payload(request)


@router.get(
    "/config",
    summary="获取 MCP 平台配置",
    dependencies=[Depends(require_permissions(MCP_CONFIG_VIEW))],
)
async def get_mcp_config():
    data = await get_mcp_config_for_admin()
    data["http_path"] = MCP_HTTP_PATH
    data["http_path_note"] = "接入路径仍由部署环境变量 MCP_HTTP_PATH 控制，修改后需同步 Nginx"
    return data


@router.put(
    "/config",
    summary="保存 MCP 平台配置",
    dependencies=[Depends(require_permissions(MCP_CONFIG_EDIT))],
)
async def update_mcp_config(item: McpConfigForm, username: str = Depends(get_current_username)):
    data = await save_mcp_config(
        enabled=item.enabled,
        base_url=item.base_url,
        api_key=item.api_key,
        username=username,
    )
    data["http_path"] = MCP_HTTP_PATH
    return data
