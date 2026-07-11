"""UI 用例执行状态：Runner / 库表 / 筛选口径对齐。"""

from __future__ import annotations

# 筛选 key -> 库中可能出现的 status 值
UI_CASE_STATUS_FILTER_VALUES: dict[str, tuple[str, ...]] = {
    "success": ("success",),
    "fail": ("fail", "failed"),
    "error": ("error",),
    "skip": ("skip", "skipped"),
    "no_run": ("no_run", "pending"),
}


def normalize_ui_case_status(status: str | None) -> str | None:
    """落库时统一为模型约定值（skip / fail / no_run …）。"""
    if not status:
        return status
    key = status.strip().lower()
    aliases = {
        "skipped": "skip",
        "failed": "fail",
        "pending": "no_run",
    }
    return aliases.get(key, key)


def apply_ui_case_status_filter(query, status: str | None):
    """Tortoise QuerySet：按筛选 key 过滤用例执行记录。"""
    if not status:
        return query
    key = status.strip().lower()
    values = UI_CASE_STATUS_FILTER_VALUES.get(key)
    if not values:
        return query.filter(status=status)
    if len(values) == 1:
        return query.filter(status=values[0])
    return query.filter(status__in=list(values))
