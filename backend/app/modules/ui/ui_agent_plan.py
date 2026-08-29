"""UI Agent 单步规划（local / Runner proxy 共用）。"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.models.ai import AiConfig
from app.modules.ai.ai_prompts import PromptManager
from app.modules.ui.ui_agent_completion_guard import (
    AGENT_REJECT_DONE_HINT,
    is_premature_agent_done,
    should_strict_goal_completion,
)
from app.routers.ai.generate import _extract_json_object, _normalize_ui_steps


def _compact_agent_executed_steps(steps: list | None, *, tail: int = 10) -> str:
    if not steps:
        return ""
    if len(steps) <= tail:
        return json.dumps(steps, ensure_ascii=False, indent=2)
    payload = {
        "total_executed": len(steps),
        "note": "仅展示最近步骤，禁止重复相同 method+locator",
        "recent_steps": steps[-tail:],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)

logger = logging.getLogger(__name__)


async def plan_ui_agent_step(
    *,
    config: AiConfig,
    description: str,
    accessibility_snapshot: str,
    snapshot_type: str,
    executed_steps: list,
    current_url: str,
    step_index: int,
    stuck_hint: str = "",
    strict_goal_mode: bool | None = None,
    call_llm,
) -> dict[str, Any]:
    """返回 {done, message?, step?, tokens}。"""
    strict = (
        should_strict_goal_completion(description)
        if strict_goal_mode is None
        else bool(strict_goal_mode)
    )
    executed_steps_text = _compact_agent_executed_steps(executed_steps)
    hint = (stuck_hint or "").strip()
    try:
        system_prompt, user_prompt = await PromptManager.render("ui_agent_plan", {
            "description": description,
            "accessibility_snapshot": accessibility_snapshot,
            "snapshot_type": snapshot_type,
            "executed_steps": executed_steps_text,
            "current_url": current_url,
            "step_index": step_index,
            "stuck_hint": hint,
            "has_stuck_hint": bool(hint),
            "strict_goal_mode": strict,
        })
    except ValueError as exc:
        return {"done": True, "message": f"Prompt 渲染失败: {exc}", "tokens": 0}

    try:
        resp = await call_llm(system_prompt, user_prompt)
    except Exception as exc:
        logger.error("[ui_agent] LLM 调用失败: %s", exc)
        return {"done": True, "message": f"LLM 调用失败: {exc}", "tokens": 0}

    tokens = int(resp.get("tokens") or 0)
    raw = resp.get("content") or ""
    parsed = _extract_json_object(raw)
    if not parsed:
        return {"done": True, "message": "无法解析 LLM 响应", "tokens": tokens, "raw_response": raw[:500]}

    if parsed.get("done"):
        done_msg = (parsed.get("message") or "完成").strip()
        if (
            strict
            and is_premature_agent_done(
                description, executed_steps, done_message=done_msg
            )
        ):
            logger.info(
                "[ui_agent] 过早 done 拒绝 step=%s executed=%s（交 Runner 重规划）",
                step_index,
                len(executed_steps or []),
            )
            return {
                "done": False,
                "replan_required": True,
                "stuck_hint": AGENT_REJECT_DONE_HINT,
                "message": done_msg,
                "tokens": tokens,
            }
        return {"done": True, "message": done_msg, "tokens": tokens}

    step = parsed.get("step")
    if not step:
        return {"done": True, "message": "LLM 未返回 step", "tokens": tokens}

    valid_steps, errs = _normalize_ui_steps([step])
    if errs:
        logger.warning("[ui_agent] 第 %s 步校验警告: %s", step_index, errs)
    if not valid_steps:
        return {"done": True, "message": "步骤校验失败", "tokens": tokens}

    return {"done": False, "step": valid_steps[0], "tokens": tokens, "raw_response": raw[:500]}
