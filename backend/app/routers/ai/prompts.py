"""
AI Prompt 模板管理路由
"""
import json
import logging
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import StreamingResponse
from app.core.auth import is_authenticated, require_permissions
from app.core.permissions import AI_CONFIG_VIEW, AI_CONFIG_EDIT
from app.core.ai_prompts import PromptManager
from app.core.llm_client import LLMClientFactory
from app.core.encryption import decrypt_value
from app.models.ai import AiPromptTemplate, AiConfig
from app.schemas.ai import (
    PromptTemplateUpdate,
    PromptTestRequest,
    StandardResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["AI提示词模板"])


@router.get("", summary="获取所有 Prompt 模板", dependencies=[Depends(require_permissions(AI_CONFIG_VIEW))])
async def list_prompts(
    user_info: dict = Depends(is_authenticated),
):
    """获取所有 Prompt 模板列表（合并数据库和预置模板）"""
    # 惰性初始化预置模板
    await PromptManager.ensure_initialized()
    # 从数据库读取
    db_templates = await AiPromptTemplate.filter(is_enabled=True).order_by("id")

    result = []
    db_codes = {t.code for t in db_templates}

    # 数据库模板
    for t in db_templates:
        result.append({
            "id": t.id,
            "code": t.code,
            "name": t.name,
            "scene_type": t.scene_type,
            "description": t.description,
            "version": t.version,
            "is_default": t.is_default,
            "is_custom": not t.is_default,  # 用户修改过的是非默认
        })

    # 补充预置模板中尚未写入数据库的
    for code in PromptManager.DEFAULT_TEMPLATES:
        if code not in db_codes:
            data = PromptManager._resolve_default_template(code)
            if not data:
                continue
            result.append({
                "id": None,
                "code": code,
                "name": data["name"],
                "scene_type": data["scene_type"],
                "description": data["description"],
                "version": 1,
                "is_default": True,
                "is_custom": False,
            })

    return StandardResponse(data={"list": result})


@router.get("/{code}", summary="获取指定 Prompt 模板", dependencies=[Depends(require_permissions(AI_CONFIG_VIEW))])
async def get_prompt(
    code: str,
    user_info: dict = Depends(is_authenticated),
):
    """获取指定编码的 Prompt 模板完整内容"""
    try:
        template = await PromptManager.get_template(code)
        # 提取变量
        variables = PromptManager.extract_variables(template["user_prompt_template"])
        return StandardResponse(data={**template, "variables": variables})
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/{code}", summary="更新 Prompt 模板", dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))])
async def update_prompt(
    code: str,
    item: PromptTemplateUpdate,
    user_info: dict = Depends(is_authenticated),
):
    """更新指定 Prompt 模板（用户自定义版本）"""
    # 检查是否为有效的预置模板编码
    if code not in PromptManager.DEFAULT_TEMPLATES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板编码不存在")

    default_data = PromptManager.DEFAULT_TEMPLATES[code]

    # 查找或创建数据库记录
    template = await AiPromptTemplate.filter(code=code).first()

    update_data = item.model_dump(exclude_unset=True)

    if template:
        await template.update_from_dict(update_data)
        template.version += 1
        await template.save()
    else:
        # 首次保存：检查内容是否与默认模板完全一致
        system_prompt = update_data.get("system_prompt", default_data["system_prompt"])
        user_prompt = update_data.get("user_prompt_template", default_data["user_prompt_template"])
        if system_prompt == default_data["system_prompt"] and user_prompt == default_data["user_prompt_template"]:
            # 内容与默认一致，无需创建自定义记录
            return StandardResponse(data={
                "id": None,
                "code": code,
                "name": default_data["name"],
                "version": 1,
                "is_default": True,
            })

        # 内容与默认不同，创建自定义记录
        template = await AiPromptTemplate.create(
            code=code,
            name=update_data.get("name", default_data["name"]),
            description=update_data.get("description", default_data["description"]),
            scene_type=default_data["scene_type"],
            system_prompt=system_prompt,
            user_prompt_template=user_prompt,
            examples=update_data.get("examples", default_data.get("examples", [])),
            is_default=False,
            is_enabled=True,
        )

    return StandardResponse(data={
        "id": template.id,
        "code": template.code,
        "name": template.name,
        "version": template.version,
        "is_default": template.is_default,
    })


@router.post("/{code}/reset", summary="重置 Prompt 模板为默认", dependencies=[Depends(require_permissions(AI_CONFIG_EDIT))])
async def reset_prompt(
    code: str,
    user_info: dict = Depends(is_authenticated),
):
    """将指定 Prompt 模板重置为系统默认"""
    if code not in PromptManager.DEFAULT_TEMPLATES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板编码不存在")

    template = await AiPromptTemplate.filter(code=code).first()
    if template:
        await template.delete()

    return StandardResponse(message="已重置为系统默认模板")


@router.post("/{code}/test", summary="测试 Prompt 模板")
async def test_prompt(
    code: str,
    req: PromptTestRequest,
    user_info: dict = Depends(is_authenticated),
):
    """
    测试 Prompt 模板：使用默认 LLM 配置渲染 Prompt 并发送给 LLM
    用于用户调试自定义 Prompt 效果
    """
    logger.warning(f"[test_prompt] code={code}, variables={req.variables}")
    # 查找可用配置（优先级：默认且启用 > 任意启用 > 任意未删除）
    config = await AiConfig.filter(is_default=True, is_enabled=True, is_del=False).first()
    logger.warning(f"[test_prompt] 查找默认配置: {config}")
    if not config:
        config = await AiConfig.filter(is_enabled=True, is_del=False).first()
        logger.warning(f"[test_prompt] 查找启用配置: {config}")
    if not config:
        # 最后尝试找任意未删除的配置（即使被禁用，测试时临时用）
        config = await AiConfig.filter(is_del=False).first()
        logger.warning(f"[test_prompt] 查找任意配置: {config}")
    if not config:
        logger.error("[test_prompt] 没有找到任何可用配置")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有可用的 LLM 配置，请先创建至少一个配置并确保未删除"
        )
    logger.warning(f"[test_prompt] 使用配置: id={config.id}, provider={config.provider}, model={config.model}")

    try:
        system_prompt, user_prompt = await PromptManager.render(code, req.variables)
    except ValueError as e:
        logger.warning(f"[test_prompt] 渲染失败: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception(f"[test_prompt] 渲染异常: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"模板渲染异常: {str(e)}")

    try:
        api_key = decrypt_value(config.api_key)
        logger.warning(f"[test_prompt] API Key 解密成功, length={len(api_key)}")
        client = LLMClientFactory.create(
            provider=config.provider,
            api_key=api_key,
            api_base=config.api_base,
            model=config.model,
            timeout=config.timeout,
        )
        logger.warning(f"[test_prompt] LLMClient 创建成功, provider={config.provider}, model={config.model}")

        extra_body = {}
        if config.thinking_enabled:
            extra_body["thinking"] = {"type": "enabled"}
        kwargs = {}
        if config.thinking_enabled and config.reasoning_effort:
            kwargs["reasoning_effort"] = config.reasoning_effort
        resp = await client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=config.temperature,
            max_tokens=min(config.max_tokens, 2048),  # 测试时限制输出长度
            extra_body=extra_body or None,
            **kwargs,
        )
        logger.warning(f"[test_prompt] LLM 调用成功, tokens={resp.get('tokens', 0)}")

        return StandardResponse(data={
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "llm_response": resp.get("content", ""),
            "tokens_used": resp.get("tokens", 0),
        })

    except Exception as e:
        logger.error(f"[test_prompt] LLM 调用失败: {e}", exc_info=True)
        return StandardResponse(
            code=500,
            message=f"LLM 调用失败: {str(e)}",
            data={
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "llm_response": None,
                "error": str(e),
            },
        )


@router.post("/{code}/test-stream", summary="测试 Prompt 模板（SSE 流式输出）")
async def test_prompt_stream(
    code: str,
    req: PromptTestRequest,
    user_info: dict = Depends(is_authenticated),
):
    """
    测试 Prompt 模板：使用默认 LLM 配置渲染 Prompt 并流式发送给 LLM
    返回 SSE 流，前端可实时看到生成内容
    """
    print(f"[TEST_STREAM] === 路由被调用, code={code}, variables={req.variables} ===", flush=True)

    # 查找可用配置
    config = await AiConfig.filter(is_default=True, is_enabled=True, is_del=False).first()
    if not config:
        config = await AiConfig.filter(is_enabled=True, is_del=False).first()
    if not config:
        config = await AiConfig.filter(is_del=False).first()
    if not config:
        print("[TEST_STREAM] 没有找到可用配置", flush=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有可用的 LLM 配置，请先创建至少一个配置并确保未删除"
        )
    print(f"[TEST_STREAM] 使用配置: id={config.id}, provider={config.provider}, model={config.model}", flush=True)

    try:
        system_prompt, user_prompt = await PromptManager.render(code, req.variables)
    except ValueError as e:
        print(f"[TEST_STREAM] 渲染失败: {e}", flush=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(f"[TEST_STREAM] 渲染异常: {e}", flush=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"模板渲染异常: {str(e)}")
    print(f"[TEST_STREAM] 渲染成功, system_len={len(system_prompt)}, user_len={len(user_prompt)}", flush=True)

    async def event_generator():
        import asyncio
        print("[TEST_STREAM] event_generator 启动", flush=True)

        # 发送开始事件，包含渲染后的 prompt
        yield f"data: {json.dumps({'type': 'start', 'system_prompt': system_prompt, 'user_prompt': user_prompt}, ensure_ascii=False)}\n\n"
        print("[TEST_STREAM] 已发送 start 事件", flush=True)

        try:
            api_key = decrypt_value(config.api_key)
            client = LLMClientFactory.create(
                provider=config.provider,
                api_key=api_key,
                api_base=config.api_base,
                model=config.model,
                timeout=60,  # 单次 LLM 调用最多 60s，避免无限挂起
            )
            print(f"[TEST_STREAM] LLMClient 创建成功, base_url={client.api_base}", flush=True)

            full_content = ""
            buffer = ""
            last_flush = asyncio.get_event_loop().time()
            start_time = last_flush
            chunk_count = 0

            extra_body = {}
            if config.thinking_enabled:
                extra_body["thinking"] = {"type": "enabled"}
            kwargs = {}
            if config.thinking_enabled and config.reasoning_effort:
                kwargs["reasoning_effort"] = config.reasoning_effort
            async for chunk in client.chat_stream(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=config.temperature,
                max_tokens=min(config.max_tokens, 2048),
                extra_body=extra_body or None,
                **kwargs,
            ):
                chunk_count += 1
                full_content += chunk
                buffer += chunk
                now = asyncio.get_event_loop().time()

                # 总时间超过 120s 强制结束，避免无限空转
                if now - start_time > 120:
                    print("[TEST_STREAM] 总时间超过 120s，强制结束", flush=True)
                    yield f"data: {json.dumps({'type': 'error', 'message': 'LLM 响应超时（超过120秒）'}, ensure_ascii=False)}\n\n"
                    return

                # 每 100ms 或积累 50 个字符以上再 yield，减少频繁序列化开销
                if now - last_flush > 0.1 or len(buffer) >= 50:
                    yield f"data: {json.dumps({'type': 'chunk', 'content': buffer}, ensure_ascii=False)}\n\n"
                    buffer = ""
                    last_flush = now

            # 刷剩余 buffer
            if buffer:
                yield f"data: {json.dumps({'type': 'chunk', 'content': buffer}, ensure_ascii=False)}\n\n"

            print(f"[TEST_STREAM] LLM 流式调用完成，总长度={len(full_content)}, chunks={chunk_count}", flush=True)
            # 发送完成事件
            yield f"data: {json.dumps({'type': 'done', 'content': full_content}, ensure_ascii=False)}\n\n"

        except Exception as e:
            print(f"[TEST_STREAM] LLM 流式调用失败: {e}", flush=True)
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

        print("[TEST_STREAM] event_generator 结束", flush=True)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )
