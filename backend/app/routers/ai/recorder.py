"""
AI 录制器路由
支持：启动录制、查询状态、停止录制、接收 Runner 回调、转换操作

作者：AI 协作助手
日期：2026-04-22
"""

import json
import logging
import re
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request, Body
from pydantic import BaseModel, Field

from app.core.auth import is_authenticated, verify_runner_or_internal
from app.core.mq_producer import MQProducer
from app.core.recorder_converter import convert_actions_to_steps
from app.models.ai import AiRecordSession
from app.models.sys import Device
from app.schemas.ai import StandardResponse

logger = logging.getLogger(__name__)


def _patch_meta_from_original_steps(optimized_steps: list, original_steps: list):
    """从原始步骤中补回 meta 到优化后的步骤
    
    LLM 优化时不会返回 meta 字段，但前端 LocatorSelector 需要 meta 来生成候选定位器。
    根据 method + params.locator（或 open_url 的 params.url）匹配原始步骤，复制 meta。
    """
    # 建立原始步骤的查找索引：method + 关键参数 -> meta
    original_meta_map = {}
    for orig in original_steps:
        if not isinstance(orig, dict):
            continue
        method = orig.get("method", "")
        params = orig.get("params", {})
        meta = orig.get("meta", {})
        if not meta:
            continue
        # 匹配键：method + 关键定位参数
        if method == "open_url":
            key = (method, params.get("url", ""))
        else:
            key = (method, params.get("locator", ""))
        original_meta_map[key] = meta
    
    # 为优化后的步骤补回 meta
    for opt in optimized_steps:
        if not isinstance(opt, dict):
            continue
        # 如果 LLM 已经返回了 meta，保留（通常不会）
        if opt.get("meta"):
            continue
        method = opt.get("method", "")
        params = opt.get("params", {})
        if method == "open_url":
            key = (method, params.get("url", ""))
        else:
            key = (method, params.get("locator", ""))
        
        meta = original_meta_map.get(key)
        if meta:
            opt["meta"] = meta


def _extract_json_from_text(content: str) -> Optional[str]:
    """从文本中提取最外层的 JSON 对象（支持嵌套大括号）
    
    1. 先尝试匹配 markdown 代码块 ```json ... ```
    2. 再使用括号计数法找到完整 JSON 对象（解决正则无法处理嵌套的问题）
    """
    # 1. 尝试 markdown 代码块
    md_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
    if md_match:
        return md_match.group(1).strip()
    
    # 2. 括号计数法：找到第一个 { 后，配对找到对应的 }
    start = content.find('{')
    if start == -1:
        return None
    
    count = 0
    in_string = False
    escape = False
    for i, c in enumerate(content[start:], start):
        if escape:
            escape = False
            continue
        if c == '\\':
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '{':
            count += 1
        elif c == '}':
            count -= 1
            if count == 0:
                return content[start:i+1]
    
    return None

router = APIRouter(prefix="/record", tags=["AI录制"])


# ========== 请求模型 ==========

class StartRecordRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=500, description="录制起始页面 URL")
    description: Optional[str] = Field(None, max_length=2000, description="测试描述（可选，用于AI优化）")
    device_id: Optional[str] = Field(None, description="指定 Runner 设备ID（不填则自动分配）")
    max_record_time: int = Field(600, ge=60, le=3600, description="最大录制时间（秒），默认 10 分钟")
    use_ai_optimize: bool = Field(False, description="是否使用 LLM 优化步骤描述")
    hover_delay_ms: int = Field(1000, ge=500, le=5000, description="悬浮停留时间（毫秒），默认 1 秒。悬浮操作需在元素上方停留该时间才会被录制")


class RecordCallbackRequest(BaseModel):
    record_session_id: int = Field(..., description="录制会话ID")
    device_id: str = Field(..., description="Runner 设备ID")
    success: bool = Field(..., description="是否成功")
    actions: list = Field(default_factory=list, description="原始操作列表")
    duration_ms: int = Field(0, description="录制耗时(ms)")
    error: Optional[str] = Field(None, description="错误信息")


class HeartbeatRequest(BaseModel):
    actions_count: int = Field(0, description="当前已记录的操作数量")
    raw_actions: list = Field(default_factory=list, description="当前已记录的原始操作列表")


class OptimizeRequest(BaseModel):
    description: Optional[str] = Field(None, max_length=2000, description="测试描述，用于 AI 优化步骤的上下文")
    ai_config_id: Optional[int] = Field(default=None, description="指定 LLM 配置ID")
    append_assertions: bool = Field(
        default=True,
        description="基于描述中的预期结果补充断言步骤（生成后可人工微调）",
    )
    use_page_context: bool = Field(
        default=True,
        description="使用录制原始操作中的可见文本辅助断言定位",
    )


# ========== 全局 MQ 生产者（懒加载） ==========

_mq_producer: Optional[MQProducer] = None


def _get_mq() -> MQProducer:
    global _mq_producer
    if _mq_producer is None:
        _mq_producer = MQProducer()
    return _mq_producer


# ========== 路由 ==========

@router.post("/start", summary="启动录制")
async def start_record(
    body: StartRecordRequest,
    request: Request,
    user_info: dict = Depends(is_authenticated),
):
    """
    启动 UI 操作录制
    
    1. 查找可用的 Runner 设备（在线状态）
    2. 创建录制会话记录
    3. 发送 MQ 任务到 Runner
    4. 返回 record_id，前端轮询状态
    """
    # 查找可用 Runner
    if body.device_id:
        device = await Device.get_or_none(id=body.device_id, status="在线", is_del=False)
        if not device:
            raise HTTPException(status_code=503, detail=f"指定的 Runner 设备 {body.device_id} 不在线或不存在")
    else:
        device = await Device.filter(status="在线", is_del=False).first()
        if not device:
            raise HTTPException(status_code=503, detail="当前没有可用的 Runner 设备，请检查 Runner 是否在线")
    
    # 创建录制会话
    record = await AiRecordSession.create(
        project_id=user_info.get("project_id"),
        device_id=device.id,
        url=body.url,
        description=body.description,
        use_ai_optimize=body.use_ai_optimize,
        status="recording",
        create_by=user_info.get("username", ""),
    )
    
    # 构建回调 URL（Runner 录制完成后上报结果）
    # 优先从当前请求 base_url 推导，确保 Runner 能正确回调
    base_url = str(request.base_url).rstrip("/")
    callback_url = f"{base_url}/ai/record/{record.id}/callback"
    
    # 发送录制任务到 Runner
    try:
        mq = _get_mq()
        mq.send_test_task(
            env_config={},
            run_case={
                "task_type": "ui_record",
                "record_session_id": record.id,
                "url": body.url,
                "description": body.description,
                "max_record_time": body.max_record_time,
                "callback_url": callback_url,
                "hover_delay_ms": body.hover_delay_ms,
            },
            device_id=device.id,
        )
    except Exception as e:
        logger.error(f"发送录制任务到 Runner 失败: {e}")
        record.status = "failed"
        record.error = f"下发任务失败: {str(e)}"
        await record.save()
        raise HTTPException(status_code=500, detail=f"下发录制任务失败: {str(e)}")
    
    logger.info(f"录制任务已下发: record_id={record.id}, device_id={device.id}, url={body.url}")
    
    return StandardResponse(
        data={
            "record_id": record.id,
            "device_id": device.id,
            "status": "recording",
            "url": body.url,
        }
    )


@router.get("/{record_id}", summary="查询录制状态")
async def get_record_status(
    record_id: int,
    user_info: dict = Depends(is_authenticated),
):
    """查询录制会话状态和已记录的操作"""
    record = await AiRecordSession.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="录制会话不存在")
    
    return StandardResponse(
        data={
            "id": record.id,
            "status": record.status,
            "url": record.url,
            "description": record.description,
            "actions_count": getattr(record, 'actions_count', 0) or len(record.raw_actions),
            "steps": record.steps,
            "optimized_steps": record.optimized_steps,
            "raw_actions": record.raw_actions,
            "error": record.error,
            "duration_ms": record.duration_ms,
            "create_time": record.create_time.isoformat() if record.create_time else None,
        }
    )


@router.get("/{record_id}/runner-status", summary="Runner 查询录制状态（内部）")
async def get_record_status_runner(
    record_id: int,
    _ctx: dict = Depends(verify_runner_or_internal),
):
    """Runner 消费 MQ 前校验任务是否仍有效"""
    record = await AiRecordSession.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="录制会话不存在")

    return StandardResponse(
        data={
            "id": record.id,
            "status": record.status,
        }
    )


@router.post("/{record_id}/stop", summary="停止录制")
async def stop_record(
    record_id: int,
    user_info: dict = Depends(is_authenticated),
):
    """发送停止录制指令到 Runner"""
    record = await AiRecordSession.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="录制会话不存在")
    
    if record.status != "recording":
        raise HTTPException(status_code=400, detail=f"当前状态为 {record.status}，无法停止")
    
    if not record.device_id:
        raise HTTPException(status_code=500, detail="录制会话缺少 device_id")
    
    try:
        mq = _get_mq()
        mq.send_stop_task(
            device_id=record.device_id,
            record_session_id=record.id,
        )
    except Exception as e:
        logger.error(f"发送停止录制消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"发送停止指令失败: {str(e)}")
    
    logger.info(f"停止录制指令已发送: record_id={record.id}, device_id={record.device_id}")
    
    return StandardResponse(
        data={"message": "停止指令已发送", "record_id": record.id}
    )


@router.post("/{record_id}/heartbeat", summary="Runner 录制期间心跳上报")
async def record_heartbeat(
    record_id: int,
    body: HeartbeatRequest,
    _ctx: dict = Depends(verify_runner_or_internal),
):
    """
    Runner 录制期间实时上报当前操作数量，供前端轮询显示
    """
    record = await AiRecordSession.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="录制会话不存在")
    
    # 只更新操作计数和原始操作（不转换步骤）
    if record.status == "recording":
        record.actions_count = body.actions_count
        record.raw_actions = body.raw_actions
        await record.save()
    
    return StandardResponse(data={"message": "heartbeat received", "actions_count": body.actions_count})


@router.post("/{record_id}/callback", summary="Runner 录制结果回调")
async def record_callback(
    record_id: int,
    body: RecordCallbackRequest,
    _ctx: dict = Depends(verify_runner_or_internal),
):
    """
    Runner 录制完成后通过此接口上报结果
    """
    record = await AiRecordSession.get_or_none(id=record_id)
    if not record:
        logger.error(f"Runner 回调时录制会话不存在: record_id={record_id}")
        raise HTTPException(status_code=404, detail="录制会话不存在")
    
    if not body.success:
        record.status = "failed"
        record.error = body.error or "录制失败"
        await record.save()
        logger.warning(f"录制失败: record_id={record_id}, error={body.error}")
        return StandardResponse(data={"message": "录制失败已记录"})
    
    # 保存原始操作
    record.raw_actions = body.actions
    record.duration_ms = body.duration_ms
    record.status = "converting"
    await record.save()
    
    # 调试：检查 action 是否包含 meta
    if body.actions:
        sample = body.actions[0]
        logger.info(f"[recorder.callback] sample action keys={list(sample.keys())}, has_meta={'meta' in sample}")
    
    logger.info(f"录制完成，开始转换: record_id={record_id}, actions={len(body.actions)}")
    
    # 自动转换原始操作为步骤
    try:
        steps = convert_actions_to_steps(body.actions)
        # 调试：检查 step 是否包含 meta
        if steps:
            logger.info(f"[recorder.callback] sample step keys={list(steps[0].keys())}, has_meta={'meta' in steps[0]}")
        record.steps = steps
        record.status = "completed"
        await record.save()
        logger.info(f"转换完成: record_id={record_id}, steps={len(steps)}")
    except Exception as e:
        logger.error(f"转换操作失败: record_id={record_id}, error={e}")
        record.status = "failed"
        record.error = f"转换失败: {str(e)}"
        await record.save()
    
    return StandardResponse(data={"message": "录制结果已接收", "record_id": record_id})


@router.post("/{record_id}/convert", summary="手动转换原始操作为步骤")
async def convert_record(
    record_id: int,
    user_info: dict = Depends(is_authenticated),
):
    """手动触发原始操作 → 步骤转换"""
    record = await AiRecordSession.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="录制会话不存在")
    
    if not record.raw_actions:
        raise HTTPException(status_code=400, detail="没有原始操作数据可供转换")
    
    try:
        steps = convert_actions_to_steps(record.raw_actions)
        record.steps = steps
        record.status = "completed"
        await record.save()
    except Exception as e:
        logger.error(f"手动转换失败: record_id={record_id}, error={e}")
        raise HTTPException(status_code=500, detail=f"转换失败: {str(e)}")
    
    return StandardResponse(data={"steps": steps, "count": len(steps)})


@router.post("/{record_id}/apply", summary="将录制结果应用到用例")
async def apply_record(
    record_id: int,
    user_info: dict = Depends(is_authenticated),
):
    """将录制完成的步骤保存为 AI 生成记录，便于后续导入用例"""
    from app.models.ai import AiGenerateRecord
    
    record = await AiRecordSession.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="录制会话不存在")
    
    if record.status != "completed":
        raise HTTPException(status_code=400, detail=f"当前状态为 {record.status}，无法应用")
    
    if not record.steps:
        raise HTTPException(status_code=400, detail="没有可用的步骤数据")
    
    # 创建 AI 生成记录
    gen_record = await AiGenerateRecord.create(
        project_id=record.project_id,
        generate_type="ui_case",
        input_summary={
            "source": "record",
            "record_id": record.id,
            "url": record.url,
            "description": record.description,
        },
        output_content={"steps": record.steps},
        status="pending",
        duration_ms=record.duration_ms,
        create_by=user_info.get("username", ""),
    )
    
    return StandardResponse(
        data={
            "generate_record_id": gen_record.id,
            "steps": record.steps,
            "steps_count": len(record.steps),
        }
    )


# ========== AI 优化描述 ==========

@router.post("/{record_id}/optimize", summary="AI 优化录制步骤")
async def optimize_record(
    record_id: int,
    body: OptimizeRequest = Body(...),
    user_info: dict = Depends(is_authenticated),
):
    """
    手动触发 AI 优化录制步骤
    
    优化内容包括：
    1. 删除多余步骤（重复导航、不必要等待）
    2. 合并可合并的连续操作
    3. 优化描述为自然语言
    
    优化结果保存在 optimized_steps 中，不覆盖原始 steps。
    支持在结果态传入新的 description 覆盖录制时填写的描述。
    """
    record = await AiRecordSession.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="录制会话不存在")
    
    if not record.steps:
        raise HTTPException(status_code=400, detail="没有可优化的步骤")
    
    # 优先使用前端传入的 description，未传入则使用录制时保存的
    description = body.description if body.description is not None else record.description
    raw_actions = record.raw_actions or []
    start_time = time.time()
    total_tokens = 0
    project_id = record.project_id if record.project_id else None

    try:
        from app.models.ai import AiConfig
        from app.core.ai_usage_log import log_ai_usage

        config = None
        if body.ai_config_id:
            config = await AiConfig.get_or_none(id=body.ai_config_id, is_enabled=True, is_del=False)
        if not config:
            config = await AiConfig.filter(is_enabled=True, is_del=False).order_by("-is_default", "-id").first()

        trimmed, opt_tokens = await _optimize_steps(record.steps, description, config)
        total_tokens += opt_tokens
        assertion_steps: list = []
        page_context = ""

        if body.append_assertions:
            from app.core.recorder_optimize import (
                extract_page_context,
                generate_assertion_steps,
                insert_assertions_into_steps,
            )

            if body.use_page_context:
                page_context = extract_page_context(raw_actions)
            if config:
                assertion_steps, assert_tokens = await generate_assertion_steps(
                    trimmed_steps=trimmed,
                    description=description or "",
                    page_context=page_context,
                    raw_actions=raw_actions,
                    config=config,
                )
                total_tokens += assert_tokens
            else:
                logger.warning("[recorder.optimize] 无 AI 配置，跳过断言生成")

        optimized = insert_assertions_into_steps(trimmed, assertion_steps)
        record.optimized_steps = optimized
        await record.save()
        duration_ms = int((time.time() - start_time) * 1000)
        if config:
            await log_ai_usage(
                config,
                "recorder_optimize",
                user_info=user_info,
                project_id=project_id,
                tokens_used=total_tokens,
                duration_ms=duration_ms,
                input_summary=(description or record.url or "")[:500],
                output_summary=f"{len(record.steps)}→{len(optimized)} 步, 断言 {len(assertion_steps)}",
                record_id=record_id,
                append_assertions=body.append_assertions,
            )
        logger.info(
            "AI 优化完成: record_id=%s, original=%s, trimmed=%s, assertions=%s",
            record_id,
            len(record.steps),
            len(trimmed),
            len(assertion_steps),
        )
    except Exception as e:
        logger.error(f"AI 优化失败: record_id={record_id}, error={e}")
        raise HTTPException(status_code=500, detail=f"AI 优化失败: {str(e)}")

    return StandardResponse(
        data={
            "original_steps": record.steps,
            "optimized_steps": optimized,
            "original_count": len(record.steps),
            "optimized_count": len(optimized),
            "trimmed_count": len(trimmed),
            "assertions_count": len(assertion_steps),
            "append_assertions": body.append_assertions,
            "use_page_context": body.use_page_context,
            "page_context_used": bool(page_context),
        }
    )


async def _optimize_steps(steps: list, description: str, config=None) -> tuple[list, int]:
    """
    使用 LLM 优化录制步骤（删除多余步骤 + 优化描述）
    
    返回 (优化后的步骤列表, tokens_used)，不修改原始列表。
    """
    from app.core.ai_prompts import PromptManager
    from app.core.llm_client import LLMClientFactory
    from app.core.encryption import decrypt_value
    from app.models.ai import AiConfig
    
    if config is None:
        config = await AiConfig.filter(is_enabled=True, is_del=False).order_by("-is_default", "-id").first()
    if not config:
        logger.warning("[recorder.optimize] 未找到可用的 AI 配置，跳过优化")
        return steps, 0
    
    # 构建步骤文本
    steps_text = "\n".join([
        f"{i+1}. [{s['method']}] {s.get('desc', '')} - 参数: {json.dumps(s.get('params', {}), ensure_ascii=False)}"
        for i, s in enumerate(steps)
    ])
    
    # 使用 PromptManager 渲染模板
    try:
        system_prompt, user_prompt = await PromptManager.render(
            code="ui_record_optimize",
            context={
                "description": description or "录制页面操作",
                "steps_text": steps_text,
                "steps_count": len(steps),
            },
        )
    except Exception as e:
        logger.warning(f"[recorder] 渲染 prompt 模板失败: {e}，跳过优化")
        return steps, 0
    
    # 调用 LLM
    api_key = decrypt_value(config.api_key)
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
    result = await client.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=4096,
        extra_body=extra_body or None,
        **kwargs,
    )
    
    content = result.get("content", "")
    tokens_used = int(result.get("tokens") or 0)
    logger.info(f"[recorder.optimize] LLM 原始返回（前1500字）: {content[:1500]}")
    
    # 提取 JSON：先尝试找 markdown 代码块中的 JSON，再用括号计数法找完整 JSON 对象
    json_str = _extract_json_from_text(content)
    
    if not json_str:
        logger.warning("[recorder.optimize] 未从 LLM 返回中提取到 JSON，回退到原始步骤")
        return steps, tokens_used
    
    try:
        data = json.loads(json_str)
        # 新格式：返回完整 steps 数组
        optimized_steps = data.get("steps", [])
        if optimized_steps and isinstance(optimized_steps, list):
            # 校验每个步骤的必填字段
            valid_steps = []
            for s in optimized_steps:
                if isinstance(s, dict) and s.get("method") and s.get("desc"):
                    # 确保 keyword 存在
                    if not s.get("keyword"):
                        s["keyword"] = s.get("desc", "")[:20]
                    valid_steps.append(s)
            
            # 从原始步骤中补回 meta（LLM 不会返回 meta）
            # 匹配策略：method + params.locator / params.url 一致则认为同一元素
            _patch_meta_from_original_steps(valid_steps, steps)
            
            logger.info(f"[recorder.optimize] 解析成功: 原始{len(steps)}步 → 优化后{len(valid_steps)}步")
            return valid_steps if valid_steps else steps, tokens_used
        else:
            logger.warning(f"[recorder.optimize] LLM 返回的 steps 为空或不合法: {type(optimized_steps)}")
        
        # 兼容旧格式：只返回 descriptions 数组
        descriptions = data.get("descriptions", [])
        if len(descriptions) == len(steps):
            for i, desc in enumerate(descriptions):
                if desc and isinstance(desc, str):
                    steps[i]["desc"] = desc
            logger.info(f"[recorder.optimize] 使用旧格式 descriptions 更新描述")
            return steps, tokens_used
    except Exception as e:
        logger.warning(f"[recorder.optimize] 解析 LLM 返回的 JSON 失败: {e}, json_str={json_str[:500]}")
    
    logger.warning("[recorder.optimize] 所有解析路径失败，回退到原始步骤")
    return steps, tokens_used
