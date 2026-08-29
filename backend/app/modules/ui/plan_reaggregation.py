"""计划执行汇总纯函数（与 runner tools.plan_reaggregation 保持同步）。"""
from __future__ import annotations

from typing import Any, Iterable, Mapping


def _compute_pass_rate(*, success: int, skip: int, quarantine_skip: int, case_count: int) -> float:
    qs = max(0, int(quarantine_skip or 0))
    total = int(case_count or 0)
    denom = max(0, total - qs)
    membership_skip = max(0, int(skip or 0) - qs)
    if denom <= 0:
        return 0.0
    return round((int(success or 0) + membership_skip) / denom * 100, 2)


def aggregate_plan_from_suites(
    suites: Iterable[Mapping[str, Any]],
    *,
    case_count: int,
) -> dict[str, Any]:
    """根据各套件执行记录汇总计划统计与终态。"""
    suite_list = list(suites)
    success = sum(int(s.get("success") or 0) for s in suite_list)
    fail = sum(int(s.get("fail") or 0) for s in suite_list)
    error = sum(int(s.get("error") or 0) for s in suite_list)
    skip = sum(int(s.get("skip") or 0) for s in suite_list)
    quarantine_skip = sum(int(s.get("quarantine_skip") or 0) for s in suite_list)
    run_all = sum(int(s.get("run_all") or 0) for s in suite_list)
    duration = max((int(s.get("duration") or 0) for s in suite_list), default=0)
    pass_rate = _compute_pass_rate(
        success=success,
        skip=skip,
        quarantine_skip=quarantine_skip,
        case_count=case_count,
    )

    statuses = [s.get("status") for s in suite_list]
    terminal = {"执行完成", "已停止"}
    if any(s not in terminal for s in statuses):
        status = "已停止" if any(s == "已停止" for s in statuses) else "执行中"
    elif all(s == "执行完成" for s in statuses):
        status = "执行完成"
    else:
        status = "已停止"

    accounted = success + fail + error + skip
    if status == "执行中":
        no_run = max(0, int(case_count) - accounted)
    else:
        no_run = sum(int(s.get("no_run") or 0) for s in suite_list)

    return {
        "status": status,
        "success": success,
        "fail": fail,
        "error": error,
        "skip": skip,
        "quarantine_skip": quarantine_skip,
        "run_all": run_all,
        "no_run": no_run,
        "duration": duration,
        "pass_rate": pass_rate,
    }
