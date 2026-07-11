"""Embedding config CRUD for CE-safe public release."""
from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.core.llm.ai_usage_log import log_ai_usage
from app.core.platform.auth import get_current_username, is_authenticated, require_permissions
from app.core.platform.encryption import decrypt_value, encrypt_value, mask_key
from app.core.platform.permissions import AI_CONFIG_EDIT, AI_CONFIG_VIEW, AI_TEST_EXECUTE
from app.models.ai import AiEmbedConfig
from app.schemas.ai import StandardResponse

router = APIRouter(prefix="/embed-configs", tags=["Embedding Config"])

_EMBED_PROVIDER_ALIASES = {
    "tongyi": "qwen",
    "dashscope": "qwen",
    "aliyun": "qwen",
}

_EMBED_PROVIDER_DEFAULT_BASES = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}


class AiEmbedConfigBase(BaseModel):
    name: str = Field(default="Embedding Config", max_length=100)
    provider: str = Field(..., description="openai|deepseek|qwen|claude|custom")
    api_key: str = Field(..., max_length=255)
    api_base: Optional[str] = Field(default=None, max_length=500)
    model: str = Field(default="text-embedding-v3", max_length=100)
    dimensions: int = Field(default=1024, ge=64, le=2048, description="Embedding vector size")
    timeout: int = Field(default=120, ge=5, le=600)
    is_enabled: bool = True


class AiEmbedConfigCreate(AiEmbedConfigBase):
    pass


class AiEmbedConfigUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    provider: Optional[str] = None
    api_key: Optional[str] = Field(default=None, max_length=255)
    api_base: Optional[str] = Field(default=None, max_length=500)
    model: Optional[str] = Field(default=None, max_length=100)
    dimensions: Optional[int] = Field(default=None, ge=64, le=2048)
    timeout: Optional[int] = Field(default=None, ge=5, le=600)
    is_enabled: Optional[bool] = None


def normalize_embed_provider(provider: str | None) -> str:
    value = (provider or "").strip().lower()
    if not value:
        return "qwen"
    return _EMBED_PROVIDER_ALIASES.get(value, value)


def resolve_embed_dimensions(row: Any, model_name: str | None) -> int | None:
    dimensions = getattr(row, "dimensions", None)
    if not dimensions:
        return None
    model = (model_name or "").strip().lower()
    if not model or "embedding" in model:
        return dimensions
    return None


def resolve_api_base(row: Any) -> str | None:
    custom_base = (getattr(row, "api_base", None) or "").strip()
    if custom_base:
        return custom_base
    provider = normalize_embed_provider(getattr(row, "provider", None))
    return _EMBED_PROVIDER_DEFAULT_BASES.get(provider)


def _mask_row(row: AiEmbedConfig) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "provider": row.provider,
        "api_key": mask_key(decrypt_value(row.api_key)),
        "api_base": row.api_base,
        "model": row.model,
        "dimensions": row.dimensions,
        "timeout": row.timeout,
        "is_default": row.is_default,
        "is_enabled": row.is_enabled,
        "create_time": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else "",
        "update_time": row.update_time.strftime("%Y-%m-%d %H:%M:%S") if row.update_time else "",
        "create_by": row.create_by or "",
    }


@router.post("", dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))])
async def create_embed_config(item: AiEmbedConfigCreate, username: str = Depends(get_current_username)):
    row = await AiEmbedConfig.create(
        name=item.name,
        provider=normalize_embed_provider(item.provider),
        api_key=encrypt_value(item.api_key),
        api_base=item.api_base,
        model=item.model.strip(),
        dimensions=item.dimensions,
        timeout=item.timeout,
        is_enabled=item.is_enabled,
        create_by=username,
    )
    if not await AiEmbedConfig.filter(is_default=True, is_del=False).exists():
        row.is_default = True
        await row.save()
    return StandardResponse(data=_mask_row(row))


@router.get("", dependencies=[Depends(require_permissions(AI_CONFIG_VIEW))])
async def list_embed_configs(page: int = 1, size: int = 100, user_info: dict = Depends(is_authenticated)):
    qs = AiEmbedConfig.filter(is_del=False).order_by("-is_default", "-id")
    total = await qs.count()
    rows = await qs.offset((page - 1) * size).limit(size)
    return StandardResponse(data={"total": total, "list": [_mask_row(r) for r in rows]})


@router.get("/select-options", dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def list_embed_config_select_options(user_info: dict = Depends(is_authenticated)):
    rows = await AiEmbedConfig.filter(is_del=False, is_enabled=True).order_by("-is_default", "-id")
    return StandardResponse(
        data=[
            {
                "id": r.id,
                "name": r.name,
                "model": r.model,
                "dimensions": r.dimensions,
                "provider": r.provider,
                "is_default": r.is_default,
            }
            for r in rows
        ]
    )


@router.get("/{config_id}", dependencies=[Depends(require_permissions(AI_CONFIG_VIEW))])
async def get_embed_config(config_id: int, user_info: dict = Depends(is_authenticated)):
    row = await AiEmbedConfig.get_or_none(id=config_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="Config not found")
    return StandardResponse(data=_mask_row(row))


@router.put("/{config_id}", dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))])
async def update_embed_config(config_id: int, item: AiEmbedConfigUpdate, user_info: dict = Depends(is_authenticated)):
    row = await AiEmbedConfig.get_or_none(id=config_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="Config not found")
    data = item.model_dump(exclude_unset=True)
    if "api_key" in data:
        key = data.pop("api_key")
        if key and "****" not in key:
            data["api_key"] = encrypt_value(key)
    if "provider" in data and data["provider"] is not None:
        data["provider"] = normalize_embed_provider(data["provider"])
    if data:
        await row.update_from_dict(data)
        await row.save()
    return StandardResponse(data=_mask_row(row))


@router.delete("/{config_id}", dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))])
async def delete_embed_config(config_id: int, user_info: dict = Depends(is_authenticated)):
    row = await AiEmbedConfig.get_or_none(id=config_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="Config not found")
    row.is_del = True
    await row.save()
    return StandardResponse(message="Deleted")


@router.post("/{config_id}/set-default", dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))])
async def set_default_embed_config(config_id: int, user_info: dict = Depends(is_authenticated)):
    row = await AiEmbedConfig.get_or_none(id=config_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="Config not found")
    await AiEmbedConfig.filter(is_default=True).update(is_default=False)
    row.is_default = True
    await row.save()
    return StandardResponse(data=_mask_row(row))


@router.post("/{config_id}/test", dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))])
async def test_embed_config(config_id: int, user_info: dict = Depends(is_authenticated)):
    row = await AiEmbedConfig.get_or_none(id=config_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="Config not found")
    try:
        api_key = decrypt_value(row.api_key)
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=resolve_api_base(row),
            timeout=max(int(row.timeout or 120), 30),
        )
        t0 = time.time()
        create_kwargs: dict[str, Any] = {"model": row.model, "input": ["ping"]}
        dim = resolve_embed_dimensions(row, row.model)
        if dim is not None:
            create_kwargs["dimensions"] = dim
        resp = await client.embeddings.create(**create_kwargs)
        duration_ms = int((time.time() - t0) * 1000)
        dim = len(resp.data[0].embedding) if resp.data else 0
        tokens = int(resp.usage.total_tokens) if resp.usage else 0
        await log_ai_usage(
            row,
            "embed_config_test",
            user_info=user_info,
            tokens_used=tokens,
            duration_ms=duration_ms,
            input_summary=f"Embedding connectivity test - {row.name}"[:500],
            output_summary=f"dim={dim}",
        )
        return StandardResponse(data={"connected": True, "dimension": dim, "tokens_used": tokens})
    except Exception as ex:
        await log_ai_usage(
            row,
            "embed_config_test",
            user_info=user_info,
            status="failed",
            input_summary=f"Embedding connectivity test - {row.name}"[:500],
            output_summary=str(ex)[:500],
        )
        return StandardResponse(
            code=500,
            message=f"Embedding connectivity test failed: {ex}",
            data={"connected": False, "error": str(ex)},
        )
