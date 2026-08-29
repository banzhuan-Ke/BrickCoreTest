"""UI Agent 逐步探索：多步目标完成度判定（通用，非 Browser Lab 专用）。"""
from __future__ import annotations

import re

_FILL_METHODS = frozenset({"fill_value", "type_value"})
_STEPWISE_SOURCES = frozenset({
    "ui_case_edit",
    "browser_lab_import",
    "functional_case_batch",
})


def is_stepwise_ui_agent_job(source: str | None) -> bool:
    """逐步 snapshot→规划→执行 的 Agent 任务（排除多轮 explore 批量模式）。"""
    src = (source or "").strip()
    if src == "ui_case_explore":
        return False
    return True


def count_numbered_goals(description: str) -> int:
    if not isinstance(description, str):
        return 0
    return len(re.findall(r"(?m)^\s*\d+[\.、．)]\s*", description))


def should_strict_goal_completion(description: str) -> bool:
    """描述含多项子目标时启用严格完成校验。"""
    if not isinstance(description, str):
        return False
    desc = description.strip()
    if not desc:
        return False
    if count_numbered_goals(desc) >= 2:
        return True
    if len(desc) >= 100 and any(
        k in desc for k in ("然后", "接着", "再", "并且", "完成后", "下一步", "须", "必须")
    ):
        return True
    return False


def _done_message_indicates_completion(done_message: str) -> bool:
    msg = (done_message or "").strip()
    if not msg:
        return False
    return any(
        k in msg
        for k in (
            "任务已全部完成",
            "已全部完成",
            "任务完成",
            "成功完成",
            "共1条记录",
            "确认存在",
        )
    )


def is_premature_agent_done(
    description: str,
    executed_steps: list | None,
    *,
    done_message: str = "",
) -> bool:
    """多步目标下步骤过少或关键动作缺失时，视为 LLM 过早 done。"""
    if not should_strict_goal_completion(description):
        return False
    if "已达最大步数" in (done_message or ""):
        return False
    steps = [s for s in (executed_steps or []) if isinstance(s, dict)]
    methods = {(s.get("method") or "").strip() for s in steps}
    n = len(steps)
    goals = count_numbered_goals(description)
    # 逐步 commit 时 fill 常与 click 合并为一步；按子目标数 + 缓冲判定，勿用 goals*2
    min_ops = max(goals + 1, 4) if goals >= 2 else 4
    if n >= min_ops:
        return False
    if _done_message_indicates_completion(done_message) and n >= max(goals, 3):
        return False
    desc = description or ""
    # 登录 fill 可能未单独 commit；有跳转等待 + 足够步数时不因缺 fill 判失败
    has_login_nav = (
        ("登录" in desc or "密码" in desc)
        and "wait_for_load" in methods
        and n >= max(goals - 1, 3)
    )
    if has_login_nav:
        return False
    if ("登录" in desc or "密码" in desc) and not (methods & _FILL_METHODS):
        if n < max(goals - 1, 3):
            return True
    if goals >= 2 and n < goals:
        return True
    return n < 3


AGENT_REJECT_DONE_HINT = (
    "【目标未完成】禁止 done=true。"
    "用户描述含多项子任务，须逐项在页面上真实完成并在 snapshot 中可确认。"
    "涉及登录须先 fill_value/type_value 输入凭证再 click；"
    "涉及搜索/验证须完成相应输入与确认后再 done。"
)
