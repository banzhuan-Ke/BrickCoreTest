"""AI 根据 SSE 样例生成 rule_based 解析规则草稿（不自动落库）。"""
from __future__ import annotations

import logging
import time
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.integration.stream_parser_config_service import test_stream_parser_config
from app.core.llm.ai_usage_log import log_ai_usage
from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import AI_TEST_EXECUTE
from app.modules.ai.ai_prompts import PromptManager
from app.modules.stream_phase.ai_rules_draft import (
    compact_sample_for_prompt,
    normalize_sample_lines,
    parse_llm_rules_json,
    validate_and_normalize_draft,
)
from app.routers.ai.generate import _call_llm, _get_ai_config
from app.schemas.ai import StandardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generate", tags=["AI生成"])

SAMPLE_LINES_CAP = 200
SAMPLE_CHARS_CAP = 50000


class GenerateStreamParserRulesRequest(BaseModel):
    sample_text: Optional[str] = Field(None, description="SSE 样例原文（按行拆分）")
    sample_lines: Optional[List[str]] = Field(None, description="SSE 样例行列表")
    phase_description: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="白话阶段说明：哪些事件对应哪些阶段指标",
    )
    ai_config_id: Optional[int] = None
    name_hint: Optional[str] = Field(None, max_length=100, description="建议配置名称")
    run_test: bool = Field(True, description="是否用样例试跑解析并返回 test_preview")


@router.post(
    "/stream-parser-rules",
    summary="根据 SSE 样例生成解析规则草稿",
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def generate_stream_parser_rules(
    body: GenerateStreamParserRulesRequest,
    user_info: dict = Depends(is_authenticated),
):
    start_time = time.time()
    phase_description = (body.phase_description or "").strip()
    if not phase_description:
        raise HTTPException(status_code=422, detail="请填写阶段说明")

    lines = normalize_sample_lines(body.sample_text, body.sample_lines)
    if not lines:
        raise HTTPException(status_code=422, detail="请粘贴 SSE 样例")
    if len(lines) > SAMPLE_LINES_CAP:
        raise HTTPException(
            status_code=422,
            detail=f"样例行数过多（最多 {SAMPLE_LINES_CAP} 行），请截取代表性片段",
        )
    sample_joined = "\n".join(lines)
    if len(sample_joined) > SAMPLE_CHARS_CAP:
        raise HTTPException(
            status_code=422,
            detail=f"样例过长（最多 {SAMPLE_CHARS_CAP} 字符），请截取代表性片段",
        )

    # Prompt 用压缩样例（去掉 id:/event:，截断超长 eof），试解析仍用完整行
    prompt_sample = compact_sample_for_prompt(lines)
    if len(phase_description) > 1500:
        raise HTTPException(
            status_code=422,
            detail="阶段说明过长：请用白话描述阶段含义，不要把整段 data: JSON 粘进说明里",
        )

    config = await _get_ai_config(body.ai_config_id, scene="stream_parser_rules_generate")

    try:
        system_prompt, user_prompt = await PromptManager.render(
            "stream_parser_rules_generation",
            {
                "sample_text": prompt_sample,
                "phase_description": phase_description,
                "name_hint": (body.name_hint or "").strip(),
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Prompt 渲染失败: {e}") from e

    try:
        resp = await _call_llm(system_prompt, user_prompt, config)
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        await log_ai_usage(
            config,
            "stream_parser_rules_generate",
            user_info=user_info,
            project_id=None,
            tokens_used=0,
            duration_ms=duration_ms,
            status="failed",
            input_summary=phase_description[:500],
            output_summary=str(e)[:500],
        )
        logger.error("[generate_stream_parser_rules] LLM 失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"LLM 调用失败: {e}") from e

    raw_response = resp.get("content", "") or ""
    tokens_used = int(resp.get("tokens") or 0)
    parsed = parse_llm_rules_json(raw_response)
    duration_ms = int((time.time() - start_time) * 1000)

    if not parsed:
        await log_ai_usage(
            config,
            "stream_parser_rules_generate",
            user_info=user_info,
            project_id=None,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            input_summary=phase_description[:500],
            output_summary="无法解析 JSON",
        )
        raise HTTPException(
            status_code=422,
            detail=(
                "模型未返回合法 JSON。建议：①阶段说明只用白话（勿粘贴整段 data:）；"
                "②样例截取代表性几行（含思考首包、正式回答首字、结束包）；"
                "③换用更稳的 JSON 模型（如 DeepSeek）；④缩短样例后重试"
            ),
        )

    draft, errors = validate_and_normalize_draft(parsed, name_hint=body.name_hint)
    if errors or not draft:
        await log_ai_usage(
            config,
            "stream_parser_rules_generate",
            user_info=user_info,
            project_id=None,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            input_summary=phase_description[:500],
            output_summary="; ".join(errors)[:500],
        )
        raise HTTPException(
            status_code=422,
            detail="规则校验失败：" + "；".join(errors[:8]),
        )

    normalize_warnings = list(draft.pop("_ai_normalize_warnings", None) or [])

    test_preview: Optional[dict[str, Any]] = None
    if body.run_test:
        try:
            test_preview = await test_stream_parser_config(
                parser_id=draft["parser_id"],
                lines=lines,
                parser_options=draft.get("parser_options") or {},
                success_rule=draft.get("success_rule"),
            )
        except Exception as e:
            logger.warning("[generate_stream_parser_rules] 试解析失败: %s", e)
            test_preview = {"error": str(e)}

    await log_ai_usage(
        config,
        "stream_parser_rules_generate",
        user_info=user_info,
        project_id=None,
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        input_summary=phase_description[:500],
        output_summary=(draft.get("name") or "")[:500],
    )

    return StandardResponse(
        code=200,
        message="ok",
        data={
            "draft": draft,
            "test_preview": test_preview,
            "tokens_used": tokens_used,
            "duration_ms": duration_ms,
            "sample_line_count": len(lines),
            "normalize_warnings": normalize_warnings,
        },
    )
