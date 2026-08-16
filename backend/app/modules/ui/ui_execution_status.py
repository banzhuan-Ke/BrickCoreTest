"""UI 执行记录状态：终态保护与迁移规则。"""
from __future__ import annotations

from app.modules.ui.ui_case_status import normalize_ui_case_status

UI_PLAN_TERMINAL_STATUSES = frozenset({"执行完成", "已停止"})
UI_SUITE_TERMINAL_STATUSES = frozenset({"执行完成", "已停止"})
UI_CASE_TERMINAL_STATUSES = frozenset({"success", "fail", "error", "skip", "no_run"})


def is_ui_plan_terminal(status: str | None) -> bool:
    return (status or "") in UI_PLAN_TERMINAL_STATUSES


def is_ui_suite_terminal(status: str | None) -> bool:
    return (status or "") in UI_SUITE_TERMINAL_STATUSES


def is_ui_case_terminal(status: str | None) -> bool:
    return (normalize_ui_case_status(status) or "") in UI_CASE_TERMINAL_STATUSES


def should_apply_case_status_update(
    current_status: str | None,
    new_status: str | None,
) -> bool:
    """
    用例终态保护：
    - 允许 fail/error → success（自动重试恢复）
    - 允许 error → fail
    - 禁止 success → fail/error 等「变差」覆盖，避免进度/乱序回报把已成功打回失败
    """
    cur = normalize_ui_case_status(current_status) or ""
    nxt = normalize_ui_case_status(new_status) or ""
    if not nxt or nxt == cur:
        return True
    if not is_ui_case_terminal(cur):
        return True
    if cur in ("fail", "error") and nxt == "success":
        return True
    if cur == "error" and nxt == "fail":
        return True
    return False


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
