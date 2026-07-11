"""MCP 平台配置读取（DB 优先，环境变量兜底）"""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.core.platform.config import BASE_URL as ENV_BASE_URL
from app.core.platform.config import MCP_API_KEY as ENV_MCP_API_KEY
from app.core.platform.config import MCP_ENABLED as ENV_MCP_ENABLED
from app.core.platform.encryption import decrypt_value, encrypt_value, mask_key
from app.core.infra.redis_client import redis_cli
from app.models.sys import SystemMcpConfig

CACHE_KEY = "system:mcp_config:v1"
CACHE_TTL_SECONDS = 60


@dataclass
class McpRuntimeConfig:
    enabled: bool
    base_url: str
    api_key: str
    source: str = "env"


async def invalidate_mcp_config_cache() -> None:
    await redis_cli.delete(CACHE_KEY)


async def get_mcp_runtime_config() -> McpRuntimeConfig:
    cached = await redis_cli.get(CACHE_KEY)
    if cached:
        try:
            data = json.loads(cached)
            return McpRuntimeConfig(**data)
        except (json.JSONDecodeError, TypeError):
            await invalidate_mcp_config_cache()

    row = await SystemMcpConfig.first()
    if row:
        cfg = McpRuntimeConfig(
            enabled=bool(row.enabled),
            base_url=(row.base_url or "").strip(),
            api_key=decrypt_value(row.api_key or ""),
            source="platform",
        )
    else:
        cfg = McpRuntimeConfig(
            enabled=bool(ENV_MCP_ENABLED),
            base_url=(ENV_BASE_URL or "").strip(),
            api_key=(ENV_MCP_API_KEY or "").strip(),
            source="env",
        )

    await redis_cli.setex(
        CACHE_KEY,
        CACHE_TTL_SECONDS,
        json.dumps(
            {
                "enabled": cfg.enabled,
                "base_url": cfg.base_url,
                "api_key": cfg.api_key,
                "source": cfg.source,
            },
            ensure_ascii=False,
        ),
    )
    return cfg


def resolve_public_base_url(cfg: McpRuntimeConfig, request_base: str = "") -> str:
    if cfg.base_url:
        return cfg.base_url.rstrip("/")
    if request_base:
        return request_base.rstrip("/")
    if ENV_BASE_URL:
        return ENV_BASE_URL.rstrip("/")
    return ""


async def get_mcp_config_for_admin() -> dict:
    row = await SystemMcpConfig.first()
    if not row:
        return {
            "enabled": bool(ENV_MCP_ENABLED),
            "base_url": ENV_BASE_URL or "",
            "api_key_masked": mask_key(ENV_MCP_API_KEY) if ENV_MCP_API_KEY else "",
            "has_api_key": bool(ENV_MCP_API_KEY),
            "using_env_fallback": True,
            "update_by": "",
            "update_time": "",
        }
    plain_key = decrypt_value(row.api_key or "")
    return {
        "id": row.id,
        "enabled": bool(row.enabled),
        "base_url": row.base_url or "",
        "api_key_masked": mask_key(plain_key) if plain_key else "",
        "has_api_key": bool(plain_key),
        "using_env_fallback": False,
        "update_by": row.update_by or "",
        "update_time": row.update_time.strftime("%Y-%m-%d %H:%M:%S") if row.update_time else "",
    }


async def save_mcp_config(
    *,
    enabled: bool,
    base_url: str,
    api_key: str | None,
    username: str,
) -> dict:
    row = await SystemMcpConfig.first()
    encrypted_key = None
    if api_key is not None:
        encrypted_key = encrypt_value(api_key.strip()) if api_key.strip() else ""

    if row:
        row.enabled = enabled
        row.base_url = (base_url or "").strip()
        if encrypted_key is not None:
            row.api_key = encrypted_key
        row.update_by = username
        await row.save()
    else:
        row = await SystemMcpConfig.create(
            enabled=enabled,
            base_url=(base_url or "").strip(),
            api_key=encrypted_key if encrypted_key is not None else "",
            update_by=username,
        )

    await invalidate_mcp_config_cache()
    plain_key = decrypt_value(row.api_key or "")
    return {
        "id": row.id,
        "enabled": bool(row.enabled),
        "base_url": row.base_url or "",
        "api_key_masked": mask_key(plain_key) if plain_key else "",
        "has_api_key": bool(plain_key),
        "using_env_fallback": False,
        "update_by": row.update_by or "",
        "update_time": row.update_time.strftime("%Y-%m-%d %H:%M:%S") if row.update_time else "",
    }
