"""
AI LLM 配置管理路由
"""
import time
from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel, Field
from typing import Optional
from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import AI_CONFIG_VIEW, AI_CONFIG_EDIT, AI_TEST_EXECUTE, UI_CASE_EXECUTE
from app.core.platform.encryption import encrypt_value, decrypt_value, mask_key
from app.core.llm.llm_client import LLMClientFactory
from app.core.llm.ai_usage_log import log_ai_usage
from app.modules.ai.ai_scene_config import list_scene_bindings, save_scene_bindings, apply_scene_recommendations
from app.models.ai import AiConfig
from app.schemas.ai import (
    AiConfigCreate,
    AiConfigUpdate,
    StandardResponse,
)
from app.schemas.project_settings import AiExecutionSettingsBody

router = APIRouter(prefix="/configs", tags=["AI配置"])


def _mask_config(config: AiConfig) -> dict:
    """将配置对象转为脱敏后的字典"""
    return {
        "id": config.id,
        "name": config.name,
        "provider": config.provider,
        "api_key": mask_key(decrypt_value(config.api_key)),
        "api_base": config.api_base,
        "model": config.model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "timeout": config.timeout,
        "thinking_enabled": config.thinking_enabled,
        "reasoning_effort": config.reasoning_effort,
        "is_default": config.is_default,
        "is_enabled": config.is_enabled,
        "create_time": config.create_time.strftime("%Y-%m-%d %H:%M:%S") if config.create_time else "",
        "update_time": config.update_time.strftime("%Y-%m-%d %H:%M:%S") if config.update_time else "",
        "create_by": config.create_by,
    }


async def _get_decrypted_key(config: AiConfig) -> str:
    """获取解密后的 API Key"""
    return decrypt_value(config.api_key)


@router.post("", summary="创建 LLM 配置", dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))])
async def create_config(
    item: AiConfigCreate,
    user_info: dict = Depends(is_authenticated),
):
    """创建新的 LLM 配置，API Key 加密存储"""
    # 加密 API Key
    encrypted_key = encrypt_value(item.api_key)

    # 如果设为默认，先取消其他默认配置
    if item.model_dump().get("is_default"):
        await AiConfig.filter(is_default=True).update(is_default=False)

    config = await AiConfig.create(
        **item.model_dump(exclude={"api_key"}),
        api_key=encrypted_key,
        create_by=user_info.get("username", ""),
    )

    return StandardResponse(data=_mask_config(config))


@router.get("", summary="LLM 配置列表", dependencies=[Depends(require_permissions(AI_CONFIG_VIEW))])
async def list_configs(
    page: int = 1,
    size: int = 100,
    user_info: dict = Depends(is_authenticated),
):
    """获取 LLM 配置列表（脱敏返回）"""
    query = AiConfig.filter(is_del=False).order_by("-id")
    total = await query.count()
    configs = await query.offset((page - 1) * size).limit(size)

    return StandardResponse(
        data={
            "total": total,
            "list": [_mask_config(c) for c in configs],
        }
    )


@router.get(
    "/select-options",
    summary="模型下拉选项（AI 执行权限）",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def list_config_select_options(
    user_info: dict = Depends(is_authenticated),
):
    """供失败分析、生成等场景选择模型，仅需 ai_test:execute"""
    configs = await AiConfig.filter(is_del=False, is_enabled=True).order_by("-is_default", "-id")
    return StandardResponse(
        data=[
            {
                "id": c.id,
                "name": c.name,
                "model": c.model,
                "provider": c.provider,
                "is_default": c.is_default,
                "is_enabled": c.is_enabled,
            }
            for c in configs
        ]
    )


@router.get(
    "/execution-settings",
    summary="[兼容] 获取项目执行设置 → 请改用 GET /sys/project-settings/execution",
    deprecated=True,
    dependencies=[Depends(require_permissions(AI_CONFIG_VIEW))],
)
async def get_execution_settings(
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    """兼容旧客户端；正式入口：GET /sys/project-settings/execution"""
    from app.routers.sys.project_settings import get_project_execution_settings
    return await get_project_execution_settings(project_id=project_id, user_info=user_info)


@router.put(
    "/execution-settings",
    summary="[兼容] 保存项目执行设置 → 请改用 PUT /sys/project-settings/execution",
    deprecated=True,
    dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))],
)
async def update_execution_settings(
    body: AiExecutionSettingsBody,
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    """兼容旧客户端；正式入口：PUT /sys/project-settings/execution"""
    from app.routers.sys.project_settings import update_project_execution_settings
    return await update_project_execution_settings(
        body=body, project_id=project_id, user_info=user_info
    )


class SceneBindingItem(BaseModel):
    scene: str
    config_id: Optional[int] = None
    overrides: Optional[dict] = Field(
        default=None,
        description="场景参数覆盖: max_tokens, temperature, timeout, min_timeout",
    )


class SceneBindingsBody(BaseModel):
    bindings: list[SceneBindingItem]


@router.get(
    "/scene-bindings",
    summary="AI 场景模型绑定列表",
    dependencies=[Depends(require_permissions(AI_CONFIG_VIEW))],
)
async def get_scene_bindings(user_info: dict = Depends(is_authenticated)):
    data = await list_scene_bindings()
    return StandardResponse(data=data)


@router.put(
    "/scene-bindings",
    summary="保存 AI 场景模型绑定",
    dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))],
)
async def update_scene_bindings(
    body: SceneBindingsBody,
    user_info: dict = Depends(is_authenticated),
):
    username = user_info.get("username", "")
    await save_scene_bindings(
        [item.model_dump() for item in body.bindings],
        username,
    )
    data = await list_scene_bindings()
    return StandardResponse(data=data, message="场景绑定已保存")


@router.post(
    "/scene-bindings/apply-recommendations",
    summary="一键套用场景推荐模型绑定",
    dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))],
)
async def post_apply_scene_recommendations(user_info: dict = Depends(is_authenticated)):
    username = user_info.get("username", "")
    data = await apply_scene_recommendations(username)
    applied = data.get("applied_count", 0)
    skipped = data.get("skipped_labels") or []
    msg = f"已为 {applied} 个场景套用推荐绑定"
    if skipped:
        msg += f"；以下场景未找到合适模型请手动配置：{'、'.join(skipped)}"
    return StandardResponse(data=data, message=msg)


@router.get("/{config_id}", summary="LLM 配置详情", dependencies=[Depends(require_permissions(AI_CONFIG_VIEW))])
async def get_config(
    config_id: int,
    user_info: dict = Depends(is_authenticated),
):
    """获取单个 LLM 配置详情（脱敏返回）"""
    config = await AiConfig.get_or_none(id=config_id, is_del=False)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在")

    return StandardResponse(data=_mask_config(config))


@router.put("/{config_id}", summary="更新 LLM 配置", dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))])
async def update_config(
    config_id: int,
    item: AiConfigUpdate,
    user_info: dict = Depends(is_authenticated),
):
    """更新 LLM 配置"""
    config = await AiConfig.get_or_none(id=config_id, is_del=False)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在")

    update_data = item.model_dump(exclude_unset=True)

    # 处理 API Key 更新
    if "api_key" in update_data:
        new_key = update_data.pop("api_key")
        # 如果传入的是脱敏值（含 ****），不更新
        if "****" not in new_key:
            update_data["api_key"] = encrypt_value(new_key)

    # 处理默认配置切换
    if update_data.get("is_default"):
        await AiConfig.filter(is_default=True).update(is_default=False)

    if update_data:
        await config.update_from_dict(update_data)
        await config.save()

    return StandardResponse(data=_mask_config(config))


@router.delete("/{config_id}", summary="删除 LLM 配置", dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))])
async def delete_config(
    config_id: int,
    user_info: dict = Depends(is_authenticated),
):
    """软删除 LLM 配置"""
    config = await AiConfig.get_or_none(id=config_id, is_del=False)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在")

    config.is_del = True
    await config.save()

    return StandardResponse(message="删除成功")


@router.post("/{config_id}/test", summary="测试 LLM 连通性")
async def test_config(
    config_id: int,
    user_info: dict = Depends(is_authenticated),
):
    """
    测试 LLM 配置的连通性
    发送一条简单消息验证 API Key 是否有效
    """
    config = await AiConfig.get_or_none(id=config_id, is_del=False)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在")

    try:
        api_key = await _get_decrypted_key(config)
        client = LLMClientFactory.create(
            provider=config.provider,
            api_key=api_key,
            api_base=config.api_base,
            model=config.model,
            timeout=config.timeout,
        )

        extra_body = {}
        if config.thinking_enabled:
            extra_body["thinking"] = {"type": "enabled"}
        kwargs = {}
        if config.thinking_enabled and config.reasoning_effort:
            kwargs["reasoning_effort"] = config.reasoning_effort
        t0 = time.time()
        resp = await client.chat(
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'Pong' only."},
            ],
            temperature=0.1,
            max_tokens=10,
            extra_body=extra_body or None,
            **kwargs,
        )

        content = resp.get("content", "").strip()
        tokens_used = int(resp.get("tokens", 0) or 0)
        duration_ms = int((time.time() - t0) * 1000)
        project_id = user_info.get("project_id") or user_info.get("current_project_id")
        await log_ai_usage(
            config,
            "config_test",
            user_info=user_info,
            project_id=project_id,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            input_summary=f"连通性测试 · {config.name}"[:500],
            output_summary=content[:500],
            config_id=config.id,
        )
        return StandardResponse(
            data={
                "connected": True,
                "response": content,
                "tokens_used": tokens_used,
            }
        )

    except Exception as e:
        project_id = user_info.get("project_id") or user_info.get("current_project_id")
        await log_ai_usage(
            config,
            "config_test",
            user_info=user_info,
            project_id=project_id,
            tokens_used=0,
            duration_ms=0,
            status="failed",
            input_summary=f"连通性测试 · {config.name}"[:500],
            output_summary=str(e)[:500],
            config_id=config.id,
        )
        return StandardResponse(
            code=500,
            message=f"连通性测试失败: {str(e)}",
            data={"connected": False, "error": str(e)},
        )


@router.post("/{config_id}/set-default", summary="设为默认配置", dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))])
async def set_default_config(
    config_id: int,
    user_info: dict = Depends(is_authenticated),
):
    """将指定配置设为默认"""
    config = await AiConfig.get_or_none(id=config_id, is_del=False)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在")

    # 取消其他默认
    await AiConfig.filter(is_default=True).update(is_default=False)
    config.is_default = True
    await config.save()

    return StandardResponse(data=_mask_config(config))
