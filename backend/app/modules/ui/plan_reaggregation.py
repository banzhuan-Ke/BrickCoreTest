"""计划执行汇总纯函数（与 runner tools.plan_reaggregation 保持同步）。"""
from __future__ import annotations

from typing import Any, Iterable, Mapping


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
    run_all = sum(int(s.get("run_all") or 0) for s in suite_list)
    duration = max((int(s.get("duration") or 0) for s in suite_list), default=0)
    pass_rate = round((success + skip) / case_count * 100, 2) if case_count > 0 else 0

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
        "run_all": run_all,
        "no_run": no_run,
        "duration": duration,
        "pass_rate": pass_rate,
    }
