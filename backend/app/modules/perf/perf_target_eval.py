"""性能验收目标 perf_targets：确定性判定（不经 AI）。

与 baseline_policy（相对基线退化）、error_rate_threshold（运行中熔断）分离。
报告判定只读 PerfRecord.config_snapshot.perf_targets。
"""
from __future__ import annotations

from typing import Any, Optional

GLOBAL_METRIC_META = {
    "qps": {"label": "QPS", "op": ">=", "unit": "/s"},
    "success_qps": {"label": "成功 QPS", "op": ">=", "unit": "/s"},
    "total_requests": {"label": "总请求数", "op": ">=", "unit": "次"},
    "avg_response_time": {"label": "平均响应时间", "op": "<=", "unit": "ms"},
    "success_avg_response_time": {"label": "成功平均响应时间", "op": "<=", "unit": "ms"},
    "p90_response_time": {"label": "P90 响应时间", "op": "<=", "unit": "ms"},
    "p95_response_time": {"label": "P95 响应时间", "op": "<=", "unit": "ms"},
    "success_p95_response_time": {"label": "成功 P95 响应时间", "op": "<=", "unit": "ms"},
    "p99_response_time": {"label": "P99 响应时间", "op": "<=", "unit": "ms"},
    "error_rate": {"label": "错误率", "op": "<=", "unit": "%"},
}

# 默认勾选启用（目标值仍可空，空值不参与判定）
_DEFAULT_ENABLED_GLOBAL_KEYS = frozenset({"qps", "p95_response_time", "error_rate"})


def _global_item_skeleton(key: str, *, enabled: Optional[bool] = None) -> dict:
    meta = GLOBAL_METRIC_META[key]
    return {
        "scope": "global",
        "key": key,
        "label": meta["label"],
        "op": meta["op"],
        "value": None,
        "unit": meta["unit"],
        "severity": "fail",
        "enabled": bool(enabled) if enabled is not None else (key in _DEFAULT_ENABLED_GLOBAL_KEYS),
    }


def _default_global_items() -> list[dict]:
    return [_global_item_skeleton(k) for k in GLOBAL_METRIC_META]


def _merge_global_items(items: list[dict]) -> list[dict]:
    """按 GLOBAL_METRIC_META 顺序补齐缺失全局指标，保留用户已有配置与非 global 项。"""
    by_key: dict[str, dict] = {}
    others: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("scope") == "global" and it.get("key") in GLOBAL_METRIC_META:
            by_key[str(it["key"])] = it
        else:
            others.append(it)
    merged = [by_key[k] if k in by_key else _global_item_skeleton(k, enabled=False) for k in GLOBAL_METRIC_META]
    return merged + others

CASE_METRIC_META = {
    "total": {"label": "请求数", "op": ">=", "unit": "次"},
    "error_rate": {"label": "错误率", "op": "<=", "unit": "%"},
    "avg_rt": {"label": "平均响应时间", "op": "<=", "unit": "ms"},
    "p95_rt": {"label": "P95 响应时间", "op": "<=", "unit": "ms"},
}

PHASE_METRIC_META = {
    "mean": {"label": "均值", "op": "<=", "unit": "s"},
    "median": {"label": "中位数", "op": "<=", "unit": "s"},
    "p95": {"label": "P95", "op": "<=", "unit": "s"},
    "max": {"label": "最大", "op": "<=", "unit": "s"},
}

VALID_OPS = {">=", "<=", ">", "<", "=="}
VALID_SEVERITIES = {"fail", "warn"}
VALID_SCOPES = {"global", "case", "phase"}


def default_perf_targets() -> dict:
    """场景编辑默认骨架：全量全局指标；常用三项默认勾选，value 为空（不参与判定）。"""
    return {
        "enabled": False,
        "profile": "custom",
        "mode": "all",
        "min_total_requests": 100,
        "min_duration_seconds": 60,
        "items": _default_global_items(),
    }


def _to_float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _to_nonneg_float(val: Any) -> Optional[float]:
    """目标值：可空；负数视为非法配置，丢弃为 None。"""
    n = _to_float(val)
    if n is None:
        return None
    if n < 0:
        return None
    return n


def _to_int(val: Any, default: int) -> int:
    try:
        n = int(val)
        return n if n >= 0 else default
    except (TypeError, ValueError):
        return default


def _compare(actual: float, op: str, expected: float) -> bool:
    if op == ">=":
        return actual >= expected
    if op == "<=":
        return actual <= expected
    if op == ">":
        return actual > expected
    if op == "<":
        return actual < expected
    if op == "==":
        return abs(actual - expected) < 1e-9
    return False


def _op_phrase(op: str) -> str:
    return {
        ">=": "≥",
        "<=": "≤",
        ">": ">",
        "<": "<",
        "==": "=",
    }.get(op, op)


def _normalize_item(raw: Any) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    scope = str(raw.get("scope") or "global").strip().lower()
    if scope not in VALID_SCOPES:
        return None
    key = str(raw.get("key") or "").strip()
    if scope == "global":
        meta = GLOBAL_METRIC_META.get(key)
    elif scope == "case":
        meta = CASE_METRIC_META.get(key)
    else:
        meta = PHASE_METRIC_META.get(key)
    if not meta:
        return None

    op = str(raw.get("op") or meta["op"]).strip()
    if op not in VALID_OPS:
        op = meta["op"]

    severity = str(raw.get("severity") or "fail").strip().lower()
    if severity not in VALID_SEVERITIES:
        severity = "fail"

    enabled = bool(raw.get("enabled", True))
    value = _to_nonneg_float(raw.get("value"))
    label = str(raw.get("label") or meta["label"]).strip() or meta["label"]
    unit = str(raw.get("unit") or meta["unit"]).strip() or meta["unit"]

    item: dict[str, Any] = {
        "scope": scope,
        "key": key,
        "label": label,
        "op": op,
        "value": value,
        "unit": unit,
        "severity": severity,
        "enabled": enabled,
    }
    if scope == "case":
        cid = raw.get("case_id")
        try:
            item["case_id"] = int(cid) if cid is not None and cid != "" else None
        except (TypeError, ValueError):
            item["case_id"] = None
        name = str(raw.get("case_name") or "").strip()
        if name:
            item["case_name"] = name
    if scope == "phase":
        pk = str(raw.get("phase_key") or "").strip()
        item["phase_key"] = pk or None
        pl = str(raw.get("phase_label") or "").strip()
        if pl:
            item["phase_label"] = pl
    return item


def normalize_perf_targets(raw: Any) -> dict:
    """清洗场景/启动覆盖的 perf_targets；非法项丢弃，不抛异常。"""
    base = default_perf_targets()
    if not isinstance(raw, dict):
        return base

    enabled = bool(raw.get("enabled", False))
    items_in = raw.get("items")
    items: list[dict] = []
    if isinstance(items_in, list):
        for it in items_in:
            norm = _normalize_item(it)
            if norm:
                items.append(norm)
    if not items:
        items = list(base["items"])
    else:
        items = _merge_global_items(items)

    return {
        "enabled": enabled,
        "profile": "custom",
        "mode": "all",
        "min_total_requests": _to_int(raw.get("min_total_requests"), 100),
        "min_duration_seconds": _to_int(raw.get("min_duration_seconds"), 60),
        "items": items,
    }


def _empty_evaluation(*, enabled: bool = False) -> dict:
    return {
        "enabled": enabled,
        "overall_status": "unknown",
        "trust_level": "normal",
        "trust_warnings": [],
        "summary": {
            "total": 0,
            "passed": 0,
            "warned": 0,
            "failed": 0,
            "unknown": 0,
            "skipped": 0,
        },
        "items": [],
    }


def _record_attr(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def resolve_core_metrics(record: Any) -> dict[str, Any]:
    """与报告卡片一致的核心指标（含 success_count / QPS 兼容修正）。

    供 ``evaluate_perf_targets`` 与 ``build_report_payload`` 共用，避免卡片达标、目标判定不达标。
    """
    total_requests = int(_record_attr(record, "total_requests", 0) or 0)
    success_count = int(_record_attr(record, "success_count", 0) or 0)
    fail_count = int(_record_attr(record, "fail_count", 0) or 0)
    error_rate = _to_float(_record_attr(record, "error_rate", 0))
    if error_rate is None:
        error_rate = 0.0
    duration = float(_record_attr(record, "duration", 0) or 0)

    # 历史数据偶发：错误率为 0 且无失败计数，但 success_count 未写全
    if fail_count == 0 and error_rate == 0 and success_count < total_requests:
        success_count = total_requests

    if duration > 0 and total_requests > 0:
        qps = round(total_requests / duration, 2)
        success_qps = round(success_count / duration, 2)
    else:
        qps = _to_float(_record_attr(record, "qps", None))
        if qps is None:
            qps = 0.0
        if duration > 0:
            success_qps = round(success_count / duration, 2)
        else:
            success_qps = _to_float(_record_attr(record, "success_qps", None))
            if success_qps is None:
                success_qps = 0.0

    success_avg = None
    success_p95 = None
    bd = _record_attr(record, "error_breakdown", None) or {}
    if isinstance(bd, dict):
        sl = bd.get("success_latency") or {}
        if isinstance(sl, dict):
            success_avg = _to_float(sl.get("avg_response_time", sl.get("avg")))
            success_p95 = _to_float(sl.get("p95_response_time", sl.get("p95")))

    return {
        "total_requests": total_requests,
        "success_count": success_count,
        "fail_count": fail_count,
        "duration": duration,
        "qps": qps,
        "success_qps": success_qps,
        "avg_response_time": _to_float(_record_attr(record, "avg_response_time", None)),
        "success_avg_response_time": success_avg,
        "p90_response_time": _to_float(_record_attr(record, "p90_response_time", None)),
        "p95_response_time": _to_float(_record_attr(record, "p95_response_time", None)),
        "success_p95_response_time": success_p95,
        "p99_response_time": _to_float(_record_attr(record, "p99_response_time", None)),
        "error_rate": error_rate,
    }


def _global_actual(metrics: dict[str, Any], key: str) -> Optional[float]:
    if key not in GLOBAL_METRIC_META:
        return None
    return _to_float(metrics.get(key))


def _case_actual(record: Any, item: dict) -> Optional[float]:
    aggs = _record_attr(record, "case_aggregations", None) or {}
    if not isinstance(aggs, dict):
        return None
    cid = item.get("case_id")
    if cid is None:
        return None
    row = aggs.get(str(cid))
    if row is None:
        row = aggs.get(cid)
    if not isinstance(row, dict):
        return None
    return _to_float(row.get(item["key"]))


def _phase_actual(record: Any, item: dict) -> Optional[float]:
    pm = _record_attr(record, "phase_metrics", None) or {}
    if not isinstance(pm, dict):
        return None
    phase_key = item.get("phase_key")
    if not phase_key:
        return None
    rows = pm.get("metrics") or []
    if not isinstance(rows, list):
        return None
    for r in rows:
        if isinstance(r, dict) and str(r.get("key") or "") == phase_key:
            return _to_float(r.get(item["key"]))
    return None


def _item_display_label(item: dict) -> str:
    label = item.get("label") or item.get("key") or "指标"
    if item.get("scope") == "case":
        name = item.get("case_name") or (
            f"用例#{item.get('case_id')}" if item.get("case_id") is not None else "用例"
        )
        return f"{name} · {label}"
    if item.get("scope") == "phase":
        pl = item.get("phase_label") or item.get("phase_key") or "阶段"
        return f"{pl} · {label}"
    return str(label)


def _format_num(v: Optional[float]) -> str:
    if v is None:
        return "-"
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _build_message(item: dict, actual: Optional[float], status: str) -> str:
    label = _item_display_label(item)
    unit = item.get("unit") or ""
    unit_s = f" {unit}" if unit else ""
    op = item.get("op") or ""
    expected = item.get("value")
    if status == "skipped":
        return f"{label} 已禁用，不参与判定"
    if status == "unknown":
        if expected is None:
            return f"{label} 未填写目标值，无法判定"
        return f"{label} 缺少实际值，无法判定"
    act_s = _format_num(actual)
    exp_s = _format_num(expected)
    phrase = _op_phrase(op)
    if status == "pass":
        return f"{label} {act_s}{unit_s}，满足目标 {phrase} {exp_s}{unit_s}"
    if op in ("<=", "<"):
        relation = "高于"
    elif op in (">=", ">"):
        relation = "低于"
    else:
        relation = "不符合"
    return f"{label} {act_s}{unit_s}，{relation}目标 {phrase} {exp_s}{unit_s}"


def _evaluate_one(record: Any, item: dict, *, metrics: dict[str, Any]) -> dict:
    out: dict[str, Any] = {
        "scope": item["scope"],
        "key": item["key"],
        "label": _item_display_label(item),
        "op": item["op"],
        "unit": item.get("unit") or "",
        "severity": item.get("severity") or "fail",
        "expected": item.get("value"),
        "actual": None,
        "status": "unknown",
        "message": "",
    }
    if item.get("scope") == "case" and item.get("case_id") is not None:
        out["case_id"] = item["case_id"]
    if item.get("scope") == "phase" and item.get("phase_key"):
        out["phase_key"] = item["phase_key"]

    if not item.get("enabled", True):
        out["status"] = "skipped"
        out["message"] = _build_message(item, None, "skipped")
        return out

    expected = item.get("value")
    if expected is None:
        # 启用但未填目标值：调用方应已过滤；此处兜底为跳过
        out["status"] = "skipped"
        out["message"] = f"{_item_display_label(item)} 未填写目标值，跳过"
        return out

    scope = item["scope"]
    if scope == "global":
        actual = _global_actual(metrics, item["key"])
    elif scope == "case":
        actual = _case_actual(record, item)
    else:
        actual = _phase_actual(record, item)

    out["actual"] = actual
    if actual is None:
        out["status"] = "unknown"
        out["message"] = _build_message(item, None, "unknown")
        return out

    ok = _compare(actual, item["op"], float(expected))
    if ok:
        out["status"] = "pass"
    else:
        sev = item.get("severity") or "fail"
        out["status"] = "warn" if sev == "warn" else "fail"
    out["message"] = _build_message(item, actual, out["status"])
    return out


def evaluate_perf_targets(record: Any) -> dict:
    """基于 config_snapshot.perf_targets 对记录做确定性验收判定。"""
    cfg = _record_attr(record, "config_snapshot", None) or {}
    if not isinstance(cfg, dict):
        cfg = {}
    raw_targets = cfg.get("perf_targets")
    targets = normalize_perf_targets(raw_targets if isinstance(raw_targets, dict) else None)

    if not targets.get("enabled"):
        return _empty_evaluation(enabled=False)

    metrics = resolve_core_metrics(record)
    items_cfg = targets.get("items") or []
    results: list[dict] = []
    for it in items_cfg:
        # 无目标值：不展示、不计入（无论是否勾选）；勾选但留空 = 未配置该项
        if it.get("value") is None:
            continue
        results.append(_evaluate_one(record, it, metrics=metrics))

    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r["status"] == "pass"),
        "warned": sum(1 for r in results if r["status"] == "warn"),
        "failed": sum(1 for r in results if r["status"] == "fail"),
        "unknown": sum(1 for r in results if r["status"] == "unknown"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
    }

    # 仅「启用且有目标值」的项参与 overall；缺实际值记 unknown
    valued = [r for r in results if r["status"] != "skipped" and r.get("expected") is not None]
    if not valued:
        overall = "unknown"
    elif any(r["status"] == "fail" for r in valued):
        overall = "fail"
    elif any(r["status"] == "warn" for r in valued):
        overall = "warn"
    elif all(r["status"] == "pass" for r in valued):
        overall = "pass"
    else:
        overall = "unknown"

    trust_level = "normal"
    trust_warnings: list[str] = []
    total_req = int(metrics.get("total_requests") or 0)
    duration = float(metrics.get("duration") or 0)
    min_req = int(targets.get("min_total_requests") or 0)
    min_dur = float(targets.get("min_duration_seconds") or 0)
    if min_req > 0 and total_req < min_req:
        trust_level = "low"
        trust_warnings.append(
            f"总请求数 {total_req} 低于最小样本数 {min_req}，结论仅供参考"
        )
    if min_dur > 0 and duration < min_dur:
        trust_level = "low"
        trust_warnings.append(
            f"执行时长 {duration:g}s 低于最小时长 {min_dur:g}s，结论仅供参考"
        )

    return {
        "enabled": True,
        "overall_status": overall,
        "trust_level": trust_level,
        "trust_warnings": trust_warnings,
        "summary": summary,
        "items": results,
    }
