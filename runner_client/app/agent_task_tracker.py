"""从 Runner 日志解析当前 Agent 类任务（智能浏览器 / UI Agent）。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_BL_START = re.compile(r"开始 Browser Lab Runner 任务: task_id=(?:%s\s+)?(\d+)")
_BL_END = re.compile(r"Browser Lab Runner 任务结束: task_id=(?:%s\s+)?(\d+)")
_UI_START = re.compile(r"开始 UI Agent Runner 任务: job_id=(?:%s\s+)?(\d+)")
_UI_END = re.compile(r"UI Agent Runner 任务结束: job_id=(?:%s\s+)?(\d+)")
_EXPLORE_START = re.compile(r"开始 UI Explore Runner 任务: job_id=(?:%s\s+)?(\d+)")
_EXPLORE_END = re.compile(r"UI Explore Runner 任务结束: job_id=(?:%s\s+)?(\d+)")


@dataclass
class ActiveAgentTask:
    kind: str
    task_id: int

    @property
    def label(self) -> str:
        if self.kind == "browser_lab":
            return f"智能浏览器 #{self.task_id}"
        if self.kind == "ui_agent":
            return f"UI Agent #{self.task_id}"
        if self.kind == "ui_explore":
            return f"UI 探索 #{self.task_id}"
        return f"任务 #{self.task_id}"


def apply_log_line(state: Optional[ActiveAgentTask], line: str) -> Optional[ActiveAgentTask]:
    """根据单行日志更新当前 Agent 任务状态。"""
    text = line or ""
    for pat, kind in (
        (_BL_START, "browser_lab"),
        (_UI_START, "ui_agent"),
        (_EXPLORE_START, "ui_explore"),
    ):
        m = pat.search(text)
        if m:
            return ActiveAgentTask(kind=kind, task_id=int(m.group(1)))

    for pat in (_BL_END, _UI_END, _EXPLORE_END):
        m = pat.search(text)
        if m:
            end_id = int(m.group(1))
            if state and state.task_id == end_id:
                return None
    return state
