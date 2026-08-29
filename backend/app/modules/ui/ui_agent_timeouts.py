"""UI Agent 单步规划超时（Runner HTTP / 平台 LLM 共用上限）。"""
from __future__ import annotations

from typing import Any

# 单步规划：禁止沿用批量生成场景的 600s+ 配置，否则 Runner 一次规划可挂 10 分钟+
UI_AGENT_PLAN_LLM_TIMEOUT_CAP = 240
UI_AGENT_PLAN_HTTP_TIMEOUT_CAP = 300


def resolve_ui_agent_plan_timeouts(config: Any) -> tuple[int, int]:
    """返回 (llm_timeout, plan_request_timeout)，均已封顶。"""
    raw = max(120, int(getattr(config, "timeout", None) or 180))
    llm_timeout = min(raw, UI_AGENT_PLAN_LLM_TIMEOUT_CAP)
    plan_request_timeout = min(
        max(180, llm_timeout + 60),
        UI_AGENT_PLAN_HTTP_TIMEOUT_CAP,
    )
    return llm_timeout, plan_request_timeout
