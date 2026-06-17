"""流式阶段指标通用聚合"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np


def jmeter_percentile(data: list[float], percentile: float) -> Optional[float]:
    if not data:
        return None
    numeric = [float(d) for d in data if isinstance(d, (int, float)) and not np.isnan(d)]
    if not numeric:
        return None
    sorted_data = sorted(numeric)
    n = len(sorted_data)
    position = (percentile / 100) * (n + 1)
    if position <= 1:
        return sorted_data[0]
    if position >= n:
        return sorted_data[-1]
    k = int(position)
    d = position - k
    return sorted_data[k - 1] + d * (sorted_data[k] - sorted_data[k - 1])


def _metric_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "p90": None, "p95": None, "p99": None, "min": None, "max": None}
    return {
        "count": len(values),
        "mean": round(float(np.mean(values)), 3),
        "median": round(float(np.median(values)), 3),
        "p90": round(jmeter_percentile(values, 90), 3) if jmeter_percentile(values, 90) is not None else None,
        "p95": round(jmeter_percentile(values, 95), 3) if jmeter_percentile(values, 95) is not None else None,
        "p99": round(jmeter_percentile(values, 99), 3) if jmeter_percentile(values, 99) is not None else None,
        "min": round(float(np.min(values)), 3),
        "max": round(float(np.max(values)), 3),
    }


def aggregate_phase_metrics(
    details: list[dict],
    *,
    parser_id: str = "",
    phase_schema: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """从 StreamRequestResult 列表聚合阶段指标。"""
    total = len(details)
    if total == 0:
        return {
            "parser_id": parser_id,
            "phase_schema": phase_schema or [],
            "total_requests": 0,
            "success_count": 0,
            "fail_count": 0,
            "error_rate": 0,
            "metrics": [],
        }

    success_details = [d for d in details if d.get("success")]
    fail_count = total - len(success_details)
    error_rate = round(fail_count / total * 100, 2) if total > 0 else 0

    schema = phase_schema or []
    if not schema and success_details:
        schema = success_details[0].get("phase_schema") or []
    if not schema and details:
        schema = details[0].get("phase_schema") or []

    aggregate_keys = [s for s in schema if s.get("aggregate", True)]
    if not aggregate_keys:
        aggregate_keys = [{"key": k, "label": k} for k in (success_details[0].get("phases") or {}).keys()] if success_details else []

    metrics = []
    for item in aggregate_keys:
        key = item.get("key") or item.get("field")
        label = item.get("label") or key
        values = []
        for d in success_details:
            phases = d.get("phases") or {}
            v = phases.get(key)
            if v is None and key == "total_time_s":
                v = d.get("total_time_s")
            if isinstance(v, (int, float)):
                values.append(float(v))
        stats = _metric_stats(values)
        metrics.append({
            "key": key,
            "label": label,
            "total_requests": total,
            "normal_count": len(values),
            "abnormal_count": fail_count,
            "error_rate": error_rate,
            **stats,
        })

    return {
        "parser_id": parser_id or (details[0].get("parser_id") if details else ""),
        "phase_schema": schema,
        "total_requests": total,
        "success_count": len(success_details),
        "fail_count": fail_count,
        "error_rate": error_rate,
        "metrics": metrics,
    }


_STREAM_DETAIL_FULL_TEXT_KEYS = frozenset({
    "thinking", "answer_preview", "references_all", "references_high", "reference_files",
})


def _format_stream_extra_value(key: str, val: Any) -> Any:
    if not isinstance(val, str):
        return val
    if key in _STREAM_DETAIL_FULL_TEXT_KEYS:
        return val
    normalized = val.replace("\n", " ")
    return normalized if len(normalized) <= 500 else normalized[:497] + "..."


def detail_to_excel_row(index: int, d: dict) -> dict[str, Any]:
    """动态生成 Excel 明细行。"""
    row: dict[str, Any] = {
        "序号": index,
        "用户ID": d.get("user_id", ""),
        "问题": d.get("question", ""),
        "是否成功": "是" if d.get("success") else "否",
        "整体耗时(s)": d.get("total_time_s"),
        "响应状态码": d.get("status_code", ""),
        "错误信息": (d.get("error") or ""),
    }
    phases = d.get("phases") or {}
    schema = d.get("phase_schema") or []
    schema_keys = [s.get("key") for s in schema if s.get("key")]
    for key in schema_keys:
        label = next((s.get("label") for s in schema if s.get("key") == key), key)
        if label not in row:
            row[label] = phases.get(key)
    for key, val in phases.items():
        label = next((s.get("label") for s in schema if s.get("key") == key), key)
        if label not in row:
            row[label] = val
    extras = d.get("extras") or {}
    extra_schema = d.get("extra_schema") or []
    label_map = {s.get("key"): s.get("label") for s in extra_schema if s.get("key")}
    used_labels: set[str] = set(row.keys())
    for ek, ev in extras.items():
        label = label_map.get(ek) or ek
        col = label
        if col in used_labels:
            col = f"{label}({ek})"
        used_labels.add(col)
        row[col] = _format_stream_extra_value(ek, ev)
    return row
