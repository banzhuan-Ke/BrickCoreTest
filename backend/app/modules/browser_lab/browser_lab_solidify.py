"""Browser Lab 任务 → Agent 固化描述构建（Phase 3 · W-2.1）。"""
from __future__ import annotations

import re

from app.models.ai import BrowserLabActionCache, BrowserLabTask

_GOAL_PREAMBLE = (
    "请从零开始在浏览器中逐步执行下列目标，产出可回归的 Playwright 步骤。"
    "须在本会话中真实操作并确认 snapshot；"
    "禁止因历史摘要/报告/「已成功」文案直接返回 done。"
)

_SUMMARY_OMIT_MARKERS = (
    "任务成功",
    "成功完成",
    "最终结论",
    "✅",
    "## 任务",
    "### 执行步骤",
)


def _count_numbered_lines(text: str) -> int:
    if not text:
        return 0
    return len(re.findall(r"(?m)^\s*\d+[\.、．)]\s*", text))


def _should_omit_result_summary(summary: str) -> bool:
    """结论型报告会误导 Agent 误判 done，且撑爆 prompt。"""
    s = (summary or "").strip()
    if not s:
        return True
    if any(m in s for m in _SUMMARY_OMIT_MARKERS):
        return True
    if len(s) > 500 and _count_numbered_lines(s) >= 2:
        return True
    return False


def _sanitize_execution_summary(summary: str, *, max_len: int = 320) -> str:
    """仅保留简短路径提示，去掉 markdown 标题与结论段。"""
    if not summary:
        return ""
    lines: list[str] = []
    for line in summary.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if any(m in s for m in _SUMMARY_OMIT_MARKERS):
            continue
        if s.startswith("|") or s.startswith("---"):
            continue
        lines.append(re.sub(r"\*+", "", s)[:100])
    text = "；".join(lines)
    return text[:max_len].strip()


def _format_cache_hints(actions: list) -> str:
    lines: list[str] = []
    for act in actions[:10]:
        if not isinstance(act, dict):
            continue
        strength = (act.get("strength") or act.get("locator_strength") or "").strip().lower()
        selector = (
            act.get("selector")
            or act.get("locator")
            or (act.get("params") or {}).get("locator")
            or ""
        )
        if strength != "strong" and not str(selector).startswith(("#", "[", "get_by_")):
            continue
        goal = (act.get("goal") or act.get("desc") or act.get("next_goal") or "").strip()
        if not goal and not selector:
            continue
        lines.append(f"- {goal[:80] or '操作'}: {str(selector)[:120]}")
    if not lines:
        return ""
    return "已探索过的操作参考（优先使用 selector，勿使用 index）：\n" + "\n".join(lines)


def _format_step_log_hints(step_log: list | None) -> str:
    goals: list[str] = []
    for evt in list(step_log or [])[-12:]:
        if not isinstance(evt, dict) or evt.get("type") != "step":
            continue
        g = (evt.get("next_goal") or evt.get("memory") or "").strip()
        if not g or g in goals:
            continue
        if any(m in g for m in ("启动无头", "Runner 正在", "调度 Agent")):
            continue
        goals.append(g[:90])
    if not goals:
        return ""
    return "Browser Lab 执行过程参考：\n" + "\n".join(f"- {g}" for g in goals[:5])


def _normalize_goal_text(text: str) -> str:
    """去掉导入弹窗自动加的「来源：智能浏览器 #id」前缀。"""
    s = (text or "").strip()
    if not s:
        return ""
    m = re.match(r"^来源：智能浏览器\s*#\d+\s*\n?", s)
    if m:
        s = s[m.end() :].strip()
    return s


async def build_solidify_description(
    task: BrowserLabTask,
    *,
    goal_text_override: str | None = None,
) -> str:
    """拼装 Agent 固化用的自然语言描述（控制长度，避免塞入成功结论报告）。"""
    override = _normalize_goal_text(goal_text_override or "")
    task_text = override or (task.task_text or "").strip()
    parts: list[str] = [_GOAL_PREAMBLE]
    if task_text:
        parts.append(task_text)

    summary_raw = (task.result_summary or "").strip()
    if not override and summary_raw and not _should_omit_result_summary(summary_raw):
        brief = _sanitize_execution_summary(summary_raw)
        if brief:
            parts.append(
                "历史路径参考（须重新操作一遍，不可视为已完成）：\n" + brief
            )

    cfg = task.config_json or {}
    cache_id = cfg.get("cache_entry_id")
    hints = ""
    if cache_id:
        row = await BrowserLabActionCache.get_or_none(
            id=int(cache_id), project_id=task.project_id
        )
        if row and isinstance(row.actions_json, list):
            hints = _format_cache_hints(row.actions_json)
    if not hints:
        hints = _format_step_log_hints(task.step_log)

    if hints:
        parts.append(hints)

    text = "\n\n".join(p for p in parts if p)
    return text[:1200]
