"""Embedding 模型配置 CRUD"""
from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.core.llm.ai_usage_log import log_ai_usage
from app.core.llm.embed_providers import (
    normalize_embed_provider,
    resolve_embed_api_base,
    resolve_embed_dimensions,
)
from app.core.platform.auth import get_current_username, is_authenticated, require_permissions
from app.core.platform.encryption import decrypt_value, encrypt_value, mask_key
from app.core.platform.permissions import AI_CONFIG_EDIT, AI_CONFIG_VIEW, AI_TEST_EXECUTE
from app.models.ai import AiEmbedConfig
from app.schemas.ai import StandardResponse

router = APIRouter(prefix="/embed-configs", tags=["Embedding配置"])


class AiEmbedConfigBase(BaseModel):
    name: str = Field(default="Embedding 配置", max_length=100)
    provider: str = Field(..., description="openai|deepseek|qwen|claude|custom")
    api_key: str = Field(..., max_length=255)
    api_base: Optional[str] = Field(default=None, max_length=500)
    model: str = Field(default="text-embedding-v3", max_length=100)
    dimensions: int = Field(default=1024, ge=64, le=2048, description="向量维度（v3/v4 可调）")
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


@router.post("", summary="创建 Embedding 配置", dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))])
async def create_embed_config(
    item: AiEmbedConfigCreate,
    username: str = Depends(get_current_username),
):
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


@router.get("", summary="Embedding 配置列表", dependencies=[Depends(require_permissions(AI_CONFIG_VIEW))])
async def list_embed_configs(
    page: int = 1,
    size: int = 100,
    user_info: dict = Depends(is_authenticated),
):
    qs = AiEmbedConfig.filter(is_del=False).order_by("-is_default", "-id")
    total = await qs.count()
    rows = await qs.offset((page - 1) * size).limit(size)
    return StandardResponse(data={"total": total, "list": [_mask_row(r) for r in rows]})


@router.get(
    "/select-options",
    summary="Embedding 配置下拉（资料库等）",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
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


@router.get("/{config_id}", summary="Embedding 配置详情", dependencies=[Depends(require_permissions(AI_CONFIG_VIEW))])
async def get_embed_config(config_id: int, user_info: dict = Depends(is_authenticated)):
    row = await AiEmbedConfig.get_or_none(id=config_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="配置不存在")
    return StandardResponse(data=_mask_row(row))


@router.put("/{config_id}", summary="更新 Embedding 配置", dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))])
async def update_embed_config(
    config_id: int,
    item: AiEmbedConfigUpdate,
    user_info: dict = Depends(is_authenticated),
):
    row = await AiEmbedConfig.get_or_none(id=config_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="配置不存在")
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


@router.delete("/{config_id}", summary="删除 Embedding 配置", dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))])
async def delete_embed_config(config_id: int, user_info: dict = Depends(is_authenticated)):
    row = await AiEmbedConfig.get_or_none(id=config_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="配置不存在")
    row.is_del = True
    await row.save()
    return StandardResponse(message="删除成功")


@router.post("/{config_id}/set-default", summary="设为默认 Embedding", dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))])
async def set_default_embed_config(config_id: int, user_info: dict = Depends(is_authenticated)):
    row = await AiEmbedConfig.get_or_none(id=config_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="配置不存在")
    await AiEmbedConfig.filter(is_default=True).update(is_default=False)
    row.is_default = True
    await row.save()
    return StandardResponse(data=_mask_row(row))


@router.post("/{config_id}/test", summary="测试 Embedding 连通性", dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))])
async def test_embed_config(config_id: int, user_info: dict = Depends(is_authenticated)):
    row = await AiEmbedConfig.get_or_none(id=config_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="配置不存在")
    try:
        api_key = decrypt_value(row.api_key)
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=resolve_embed_api_base(row),
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
            "knowledge_embed",
            user_info=user_info,
            tokens_used=tokens,
            duration_ms=duration_ms,
            input_summary=f"Embedding 连通性测试 · {row.name}"[:500],
            output_summary=f"dim={dim}",
        )
        return StandardResponse(data={"connected": True, "dimension": dim, "tokens_used": tokens})
    except Exception as ex:
        await log_ai_usage(
            row,
            "knowledge_embed",
            user_info=user_info,
            status="failed",
            input_summary=f"Embedding 连通性测试 · {row.name}"[:500],
            output_summary=str(ex)[:500],
        )
        return StandardResponse(code=500, message=f"连通性测试失败: {ex}", data={"connected": False, "error": str(ex)})
