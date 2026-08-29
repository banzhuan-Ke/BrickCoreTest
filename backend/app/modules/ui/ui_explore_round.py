"""多轮探索（SmartPageExplorer）单轮 LLM 生成步骤。"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Awaitable, Optional

from app.models.ai import AiConfig
from app.modules.ai.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

CallLlmFunc = Callable[[str, str], Awaitable[dict[str, Any]]]


async def generate_explore_round_steps(
    *,
    config: AiConfig,
    description: str,
    page_elements: list | None,
    executed_steps: list | None,
    current_url: str,
    round_index: int,
    call_llm: CallLlmFunc,
    normalize_steps,
    extract_json_array,
    dom_text_override: Optional[str] = None,
) -> tuple[list[dict], int, str]:
    """
    单轮探索：根据 DOM + 已执行步骤生成一批 UI 步骤。
    返回 (valid_steps, tokens_used, raw_response)。
    """
    from app.modules.ui.page_fetcher import format_elements_for_prompt

    executed_steps_text = ""
    if executed_steps:
        executed_steps_text = json.dumps(executed_steps, ensure_ascii=False, indent=2)
    dom_text = dom_text_override if dom_text_override is not None else format_elements_for_prompt(page_elements or [])

    try:
        system_prompt, user_prompt = await PromptManager.render("ui_case_generation", {
            "description": description,
            "page_url": current_url,
            "page_elements": dom_text,
            "executed_steps": executed_steps_text,
            "executed_steps_count": len(executed_steps or []),
            "current_url": current_url,
            "round_index": round_index,
        })
    except ValueError as exc:
        logger.error("[explore] Prompt 渲染失败: %s", exc)
        return [], 0, ""

    try:
        resp = await call_llm(system_prompt, user_prompt)
    except Exception as exc:
        logger.error("[explore] LLM 调用失败: %s", exc)
        return [], 0, ""

    raw = resp.get("content", "") if isinstance(resp, dict) else ""
    tokens = int(resp.get("tokens") or 0) if isinstance(resp, dict) else 0
    steps = extract_json_array(raw)
    if not steps:
        logger.warning("[explore] 第 %s 轮无法解析 JSON: %s", round_index, raw[:300])
        return [], tokens, raw

    valid_steps, errs = normalize_steps(steps)
    if errs:
        logger.warning("[explore] 第 %s 轮步骤校验警告: %s", round_index, errs)
    return valid_steps, tokens, raw
