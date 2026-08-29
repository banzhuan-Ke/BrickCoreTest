"""稳定度指标、不稳定规则包 A、套件通过率口径。"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from app.modules.stability.buckets import (
    extract_api_failure_code,
    extract_ui_error_msg,
    extract_ui_failure_code,
    map_failure_bucket,
)
from app.modules.stability.tags import has_quarantine

SKIP_REASON_QUARANTINE = "quarantine"
SKIP_REASON_MEMBERSHIP = "membership"

TERMINAL_OK = frozenset({"success"})
TERMINAL_SKIP = frozenset({"skip", "skipped"})
NON_SAMPLE_STATUS = frozenset({
    "running", "pending", "no_run", "skip", "skipped",
})


def compute_suite_pass_rate(
    *,
    success: int,
    skip: int,
    quarantine_skip: int,
    case_count: int,
) -> float:
    """隔离既不进分子也不进分母；套件成员 skip 仍计入分子（与历史口径一致）。"""
    qs = max(0, int(quarantine_skip or 0))
    total = int(case_count or 0)
    denom = max(0, total - qs)
    membership_skip = max(0, int(skip or 0) - qs)
    if denom <= 0:
        return 0.0
    return round((int(success or 0) + membership_skip) / denom * 100, 2)


def count_quarantine_skips(executed_cases: Iterable[Mapping[str, Any]] | None) -> int:
    n = 0
    for item in executed_cases or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("skip_reason") or "").strip().lower() == SKIP_REASON_QUARANTINE:
            n += 1
            continue
        rd = item.get("result_data") if isinstance(item.get("result_data"), dict) else {}
        if str(rd.get("skip_reason") or "").strip().lower() == SKIP_REASON_QUARANTINE:
            n += 1
    return n


def _is_success(status: Any) -> bool:
    return str(status or "").strip().lower() in TERMINAL_OK


def _is_skip(status: Any) -> bool:
    return str(status or "").strip().lower() in TERMINAL_SKIP


def _is_sample_status(status: Any, skip_reason: Any = None) -> bool:
    st = str(status or "").strip().lower()
    if st in {"running", "pending", "no_run"}:
        return False
    if _is_skip(st) and str(skip_reason or "").strip().lower() == SKIP_REASON_QUARANTINE:
        return False
    return True


def parse_retry_first_success(request_detail: Any, final_status: Any) -> tuple[bool | None, bool]:
    """
    返回 (first_pass, salvaged)。
    first_pass 为 None 表示无法区分首跑（无 retry_info）。
    salvaged：首跑失败且终态成功。
    """
    final_ok = _is_success(final_status)
    detail = request_detail if isinstance(request_detail, dict) else {}
    retry_info = detail.get("retry_info") if isinstance(detail.get("retry_info"), dict) else None
    if not retry_info:
        return (final_ok if final_ok or str(final_status or "").strip() else None, False)
    attempts = retry_info.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        total = retry_info.get("total_attempts")
        try:
            n = int(total) if total is not None else 1
        except (TypeError, ValueError):
            n = 1
        if n <= 1:
            return final_ok, False
        return False, final_ok
    first = attempts[0] if isinstance(attempts[0], dict) else {}
    first_st = str(first.get("status") or "").strip().lower()
    first_ok = first_st in TERMINAL_OK or first_st == "passed"
    if first_ok:
        return True, False
    return False, final_ok


DEFAULT_UNSTABLE_RULES = {
    "min_n": 10,
    "pass_below": 0.85,
    "first_pass_below": 0.85,
    "salvage_min": 3,
    "switch_min_n": 5,
    "switch_min": 3,
}


def evaluate_unstable(
    *,
    n: int,
    first_pass_rate: float | None,
    retry_salvage_count: int,
    statuses: Sequence[str],
    pass_rate: float | None = None,
    rules: Mapping[str, Any] | None = None,
) -> bool:
    """规则包 A（阈值可由项目设置覆盖）。"""
    r = {**DEFAULT_UNSTABLE_RULES, **(dict(rules) if isinstance(rules, Mapping) else {})}
    min_n = max(1, int(r.get("min_n") or 10))
    pass_below = float(r.get("pass_below") if r.get("pass_below") is not None else 0.85)
    first_below = float(r.get("first_pass_below") if r.get("first_pass_below") is not None else 0.85)
    salvage_min = max(0, int(r.get("salvage_min") or 0))
    switch_min_n = max(1, int(r.get("switch_min_n") or 5))
    switch_min = max(0, int(r.get("switch_min") or 0))

    if n >= min_n and pass_rate is not None and pass_rate < pass_below:
        return True
    if n >= min_n and first_pass_rate is not None and first_pass_rate < first_below:
        return True
    if n >= min_n and salvage_min > 0 and retry_salvage_count >= salvage_min:
        return True
    if switch_min > 0 and n >= switch_min_n:
        switches = 0
        prev = None
        for st in statuses:
            cur = "ok" if _is_success(st) else ("skip" if _is_skip(st) else "bad")
            if prev is not None and cur != prev and {prev, cur} <= {"ok", "bad"}:
                switches += 1
            prev = cur
        if switches >= switch_min:
            return True
    return False


RECENT_SHORT_K = 5


def _pass_rate(samples: Sequence[Mapping[str, Any]]) -> float | None:
    n = len(samples)
    if n <= 0:
        return None
    return round(sum(1 for s in samples if _is_success(s.get("status"))) / n, 4)


def collect_run_samples(
    runs: Sequence[Mapping[str, Any]],
    *,
    first_pass_fallback: str = "equal",
) -> list[dict[str, Any]]:
    """将执行记录转为最近优先的有效样本（已排除 running/quarantine skip 等）。"""
    samples: list[dict[str, Any]] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        status = str(run.get("status") or "").strip().lower()
        skip_reason = run.get("skip_reason")
        if not skip_reason and isinstance(run.get("request_detail"), dict):
            skip_reason = run["request_detail"].get("skip_reason")
        if not skip_reason and isinstance(run.get("result_data"), dict):
            skip_reason = run["result_data"].get("skip_reason")
        if not _is_sample_status(status, skip_reason):
            continue
        first_pass = run.get("first_pass")
        salvaged = bool(run.get("salvaged"))
        if first_pass is None and "request_detail" in run:
            first_pass, salvaged = parse_retry_first_success(run.get("request_detail"), status)
        elif first_pass is None:
            if first_pass_fallback == "equal":
                first_pass = _is_success(status)
            else:
                first_pass = None
        code = run.get("failure_code")
        if not code:
            code = extract_ui_failure_code(run.get("result_data"))
        if not code:
            code = extract_api_failure_code(
                request_detail=run.get("request_detail"),
                assertions_result=run.get("assertions_result"),
                error_msg=run.get("error_msg"),
            )
        err = run.get("error_msg") or extract_ui_error_msg(run.get("result_data"))
        bucket = run.get("failure_bucket") or map_failure_bucket(
            failure_code=code,
            response_status=run.get("response_status"),
            error_msg=err,
            status=status,
        )
        samples.append({
            "status": status,
            "first_pass": first_pass,
            "salvaged": salvaged,
            "failure_code": code,
            "failure_bucket": bucket if not _is_success(status) else None,
            "ended_at": run.get("ended_at") or run.get("start_time"),
            "record_id": run.get("record_id") or run.get("id"),
            "request_id": run.get("request_id"),
        })
    return samples


def summarize_samples(
    samples: Sequence[Mapping[str, Any]],
    *,
    tags: Any = None,
    first_pass_fallback: str = "equal",
    recent_k: int = RECENT_SHORT_K,
    overall_samples: Sequence[Mapping[str, Any]] | None = None,
    rules: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    对「窗口样本」算主指标；近况=窗口内最近 recent_k 次；历史=overall_samples（默认=窗口）。
    """
    window = list(samples or [])
    n = len(window)
    pass_rate = _pass_rate(window) or 0.0
    known_first = [s for s in window if s.get("first_pass") is not None]
    if not known_first:
        first_pass_rate = None if first_pass_fallback == "null" else pass_rate
    else:
        # SoT §4.1：首跑即成功 / N
        first_pass_rate = round(sum(1 for s in window if s.get("first_pass")) / n, 4) if n else 0.0
    retry_salvage_count = sum(1 for s in window if s.get("salvaged"))
    histogram: dict[str, int] = {}
    last_bucket = None
    for s in window:
        b = s.get("failure_bucket")
        if not b:
            continue
        histogram[str(b)] = histogram.get(str(b), 0) + 1
        if last_bucket is None:
            last_bucket = b
    unstable = evaluate_unstable(
        n=n,
        first_pass_rate=first_pass_rate,
        retry_salvage_count=retry_salvage_count,
        statuses=[str(s.get("status") or "") for s in window],
        pass_rate=pass_rate,
        rules=rules,
    )
    last_request_id = None
    for s in window:
        rid = str(s.get("request_id") or "").strip()
        if rid:
            last_request_id = rid
            break

    k = max(1, int(recent_k or RECENT_SHORT_K))
    short = window[: min(k, n)] if n else []
    overall = list(overall_samples) if overall_samples is not None else window
    return {
        "n": n,
        "pass_rate": pass_rate,
        "first_pass_rate": first_pass_rate,
        "retry_salvage_count": retry_salvage_count,
        "unstable": unstable,
        "quarantine": has_quarantine(tags),
        "last_failure_bucket": last_bucket,
        "bucket_histogram": histogram,
        "last_run_at": window[0].get("ended_at") if window else None,
        "last_request_id": last_request_id,
        "recent_pass_rate": _pass_rate(short),
        "recent_n": len(short),
        "overall_pass_rate": _pass_rate(overall),
        "overall_n": len(overall),
        "recent": window,
    }


def summarize_runs(
    runs: Sequence[Mapping[str, Any]],
    *,
    tags: Any = None,
    first_pass_fallback: str = "equal",
    recent_k: int = RECENT_SHORT_K,
    rules: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    runs: 新→旧；本函数按传入顺序视为「最近优先」的已筛样本。
    first_pass_fallback: equal → 无首跑信息时 first_pass_rate=pass_rate；null → 标 null。
    """
    samples = collect_run_samples(runs, first_pass_fallback=first_pass_fallback)
    return summarize_samples(
        samples,
        tags=tags,
        first_pass_fallback=first_pass_fallback,
        recent_k=recent_k,
        overall_samples=samples,
        rules=rules,
    )
