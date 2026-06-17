"""用例维度 RT 聚合：蓄水池采样、分位计算与分布式合并。"""
from __future__ import annotations

import random
from typing import Dict, Optional

import numpy as np

MAX_CASE_RT_SAMPLES = 5000


def append_rt_reservoir(
    rts: list,
    rt: float,
    rt_count: int,
    *,
    max_samples: int = MAX_CASE_RT_SAMPLES,
) -> None:
    if rt <= 0:
        return
    if len(rts) < max_samples:
        rts.append(rt)
    else:
        j = random.randint(0, rt_count - 1)
        if j < max_samples:
            rts[j] = rt


def metrics_from_rts(rts: list, agg: dict) -> dict:
    """从 RT 样本计算用例维度指标（不含 rts 字段）。"""
    total = int(agg.get("total") or 0)
    success = int(agg.get("success") or 0)
    fail = int(agg.get("fail") or 0)
    out = {
        "name": agg.get("name", ""),
        "total": total,
        "success": success,
        "fail": fail,
        "error_rate": round(fail / total * 100, 2) if total > 0 else 0,
    }
    if not rts:
        out.update({
            "avg_rt": 0, "min_rt": 0, "max_rt": 0,
            "median_rt": 0, "p90_rt": 0, "p95_rt": 0, "p99_rt": 0, "std_dev": 0,
        })
        return out
    out.update({
        "avg_rt": round(sum(rts) / len(rts), 2),
        "min_rt": round(min(rts), 2),
        "max_rt": round(max(rts), 2),
        "median_rt": round(float(np.median(rts)), 2),
        "p90_rt": round(float(np.percentile(rts, 90)), 2),
        "p95_rt": round(float(np.percentile(rts, 95)), 2),
        "p99_rt": round(float(np.percentile(rts, 99)), 2),
        "std_dev": round(float(np.std(rts)), 2),
    })
    return out


def finalize_case_aggregation(agg: dict, *, keep_samples: bool = False) -> dict:
    """计算指标；默认剥离 rts/rt_count 供持久化。"""
    rts = list(agg.get("rts") or [])
    out = metrics_from_rts(rts, agg)
    if keep_samples and rts:
        out["rts"] = rts
        out["rt_count"] = int(agg.get("rt_count") or len(rts))
    return out


def _ingest_rt_list(target: dict, rts: list) -> None:
    if not rts:
        return
    samples = target.setdefault("rts", [])
    rt_count = int(target.get("rt_count") or len(samples))
    for rt in rts:
        if rt <= 0:
            continue
        rt_count += 1
        append_rt_reservoir(samples, float(rt), rt_count)
    target["rt_count"] = rt_count


def merge_case_aggregation(existing: Optional[dict], incoming: dict) -> dict:
    """合并两个 Worker/节点的用例聚合（保留 RT 样本供后续精确分位）。"""
    if not existing:
        base = {
            "name": incoming.get("name", ""),
            "total": 0,
            "success": 0,
            "fail": 0,
            "rts": [],
            "rt_count": 0,
        }
    else:
        base = {
            "name": existing.get("name") or incoming.get("name", ""),
            "total": int(existing.get("total") or 0),
            "success": int(existing.get("success") or 0),
            "fail": int(existing.get("fail") or 0),
            "rts": list(existing.get("rts") or []),
            "rt_count": int(existing.get("rt_count") or len(existing.get("rts") or [])),
        }
    base["total"] += int(incoming.get("total") or 0)
    base["success"] += int(incoming.get("success") or 0)
    base["fail"] += int(incoming.get("fail") or 0)
    _ingest_rt_list(base, incoming.get("rts") or [])
    # 兼容旧 Worker 仅上报汇总值、无 rts 的情况
    if not incoming.get("rts") and incoming.get("avg_rt") and incoming.get("total"):
        avg = float(incoming["avg_rt"])
        repeat = min(int(incoming["total"]), MAX_CASE_RT_SAMPLES)
        _ingest_rt_list(base, [avg] * repeat)
    return base


def strip_rt_samples_from_case_aggregations(case_aggs: dict) -> dict:
    """持久化前移除 RT 样本，仅保留计算后的指标。"""
    out: Dict[str, dict] = {}
    for cid, agg in (case_aggs or {}).items():
        if isinstance(agg, dict) and (agg.get("rts") or agg.get("rt_count")):
            out[str(cid)] = finalize_case_aggregation(agg, keep_samples=False)
        else:
            out[str(cid)] = dict(agg)
    return out
