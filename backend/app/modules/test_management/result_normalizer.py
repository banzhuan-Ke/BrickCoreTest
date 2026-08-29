"""各模块执行原始状态 → 测试管理统一结果"""
from __future__ import annotations

from typing import Optional

UNIFIED_RESULTS = frozenset({
    "not_run",
    "passed",
    "failed",
    "blocked",
    "skipped",
    "cancelled",
    "error",
    "unknown",
})

# 允许从运行项一键建缺陷的结果（不含 unknown/blocked，避免解析失败误建缺陷）
DEFECT_CREATABLE_RESULTS = frozenset({"failed", "error", "blocked"})

# 同步时不应被 Runner 回写覆盖的终态
TERMINAL_RESULTS = frozenset({
    "passed",
    "failed",
    "blocked",
    "skipped",
    "cancelled",
    "error",
})

# 未关闭缺陷（列表/统计口径，含已修复待验证）
OPEN_DEFECT_STATUSES = frozenset({"open", "in_progress", "resolved"})

# 质量门禁阻塞口径：不含 resolved（已修复待验证不再挡发布）
GATE_OPEN_DEFECT_STATUSES = frozenset({"open", "in_progress"})


def normalize_ui_status(raw: Optional[str]) -> str:
    s = (raw or "").strip().lower()
    mapping = {
        "success": "passed",
        "fail": "failed",
        "failed": "failed",
        "error": "error",
        "skip": "skipped",
        "skipped": "skipped",
        "running": "not_run",
        "no_run": "not_run",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "stopped": "cancelled",
    }
    if not s:
        return "not_run"
    return mapping.get(s, "unknown")


def normalize_app_status(raw: Optional[str]) -> str:
    return normalize_ui_status(raw)


def normalize_api_status(raw: Optional[str]) -> str:
    s = (raw or "").strip().lower()
    mapping = {
        "success": "passed",
        "passed": "passed",
        "fail": "failed",
        "failed": "failed",
        "error": "error",
        "pending": "not_run",
        "running": "not_run",
        "skipped": "skipped",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "stopped": "cancelled",
    }
    if not s:
        return "not_run"
    return mapping.get(s, "unknown")


def normalize_perf_status(raw: Optional[str]) -> str:
    s = (raw or "").strip().lower()
    mapping = {
        "success": "passed",
        "passed": "passed",
        "fail": "failed",
        "failed": "failed",
        "error": "error",
        "running": "not_run",
        "pending": "not_run",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "stopped": "cancelled",
    }
    if not s:
        return "not_run"
    return mapping.get(s, "unknown")


def normalize_by_record_type(record_type: str, raw_status: Optional[str]) -> str:
    rt = (record_type or "").strip().lower()
    if rt in ("ui_case", "ui_case_execution"):
        return normalize_ui_status(raw_status)
    if rt in ("app_case", "app_case_execution"):
        return normalize_app_status(raw_status)
    if rt in ("api_case", "api_run_record"):
        return normalize_api_status(raw_status)
    if rt in ("perf_scene", "perf_record"):
        return normalize_perf_status(raw_status)
    # 未知类型不静默按 API 映射，避免错误归一化
    return "unknown"


def is_terminal_result(status: str) -> bool:
    return (status or "") in TERMINAL_RESULTS


def build_report_paths(
    record_type: str,
    record_id: int,
    *,
    asset_id: Optional[int] = None,
) -> dict[str, str]:
    """受控前端路由路径，供跳转原始报告 / 用例编辑页。"""
    rid = int(record_id)
    rt = (record_type or "").strip().lower()
    if rt in ("api_case", "api_run_record"):
        path = f"/api-module/report/{rid}"
        return {"record_url": path, "report_url": path}
    if rt in ("ui_case", "ui_case_execution"):
        if asset_id:
            path = f"/case/edit/{int(asset_id)}?execution_id={rid}"
        else:
            path = f"/record?execution_id={rid}"
        return {"record_url": path, "report_url": path}
    if rt in ("app_case", "app_case_execution"):
        if asset_id:
            path = f"/app-case/edit/{int(asset_id)}?execution_id={rid}"
        else:
            path = f"/app-record?execution_id={rid}"
        return {"record_url": path, "report_url": path}
    if rt in ("perf_scene", "perf_record"):
        path = f"/perf-report/{rid}"
        return {"record_url": path, "report_url": path}
    return {"record_url": f"/record?id={rid}", "report_url": f"/record?id={rid}"}
