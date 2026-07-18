"""UI 执行记录状态：终态保护与迁移规则。"""
from __future__ import annotations

UI_PLAN_TERMINAL_STATUSES = frozenset({"执行完成", "已停止"})
UI_SUITE_TERMINAL_STATUSES = frozenset({"执行完成", "已停止"})
UI_CASE_TERMINAL_STATUSES = frozenset({"success", "fail", "error", "skip", "no_run"})


def is_ui_plan_terminal(status: str | None) -> bool:
    return (status or "") in UI_PLAN_TERMINAL_STATUSES


def is_ui_suite_terminal(status: str | None) -> bool:
    return (status or "") in UI_SUITE_TERMINAL_STATUSES


def is_ui_case_terminal(status: str | None) -> bool:
    return (status or "") in UI_CASE_TERMINAL_STATUSES


def should_apply_suite_status_update(
    current_status: str | None,
    new_status: str,
    *,
    result_cancelled: bool = False,
) -> bool:
    """已停止的套件不被迟到的自然结束结果改回执行中/执行完成。"""
    current = current_status or ""
    if current == "已停止":
        return new_status == "已停止" or result_cancelled
    if current in UI_SUITE_TERMINAL_STATUSES:
        return False
    return True


def should_apply_plan_status_update(
    current_status: str | None,
    new_status: str,
) -> bool:
    current = current_status or ""
    if current == "已停止":
        return new_status == "已停止"
    if current in UI_PLAN_TERMINAL_STATUSES:
        return False
    return True
