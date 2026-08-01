"""用例维度 RT 聚合：全量均值/极值 + 蓄水池分位 + 分布式合并。"""
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


def _ensure_online_fields(agg: dict) -> None:
    if "rt_sum" not in agg:
        # 兼容旧数据：从 rts 回填近似全量统计
        rts = list(agg.get("rts") or [])
        if rts:
            agg["rt_sum"] = float(sum(rts))
            agg["rt_n"] = int(agg.get("rt_n") or agg.get("rt_count") or len(rts))
            agg["min_rt"] = float(min(rts))
            agg["max_rt"] = float(max(rts))
        else:
            agg.setdefault("rt_sum", 0.0)
            agg.setdefault("rt_n", 0)
            agg.setdefault("min_rt", 0.0)
            agg.setdefault("max_rt", 0.0)


def accumulate_case_rt(agg: dict, rt: float, *, max_samples: int = MAX_CASE_RT_SAMPLES) -> None:
    """累计单次 RT：全量 sum/min/max + 蓄水池（仅供分位）。"""
    if rt <= 0:
        return
    _ensure_online_fields(agg)
    n = int(agg.get("rt_n") or 0) + 1
    agg["rt_n"] = n
    agg["rt_sum"] = float(agg.get("rt_sum") or 0) + float(rt)
    if n == 1:
        agg["min_rt"] = float(rt)
        agg["max_rt"] = float(rt)
    else:
        agg["min_rt"] = min(float(agg.get("min_rt") or rt), float(rt))
        agg["max_rt"] = max(float(agg.get("max_rt") or rt), float(rt))
    samples = agg.setdefault("rts", [])
    # rt_count 与蓄水池替换逻辑对齐（历史字段）
    agg["rt_count"] = n
    append_rt_reservoir(samples, float(rt), n, max_samples=max_samples)


def metrics_from_rts(rts: list, agg: dict) -> dict:
    """从全量在线统计 + 蓄水池样本计算用例维度指标。"""
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
    _ensure_online_fields(agg)
    rt_n = int(agg.get("rt_n") or 0)
    rt_sum = float(agg.get("rt_sum") or 0)
    if rt_n <= 0 and not rts:
        out.update({
            "avg_rt": 0, "min_rt": 0, "max_rt": 0,
            "median_rt": 0, "p90_rt": 0, "p95_rt": 0, "p99_rt": 0, "std_dev": 0,
        })
        return out

    avg = round(rt_sum / rt_n, 2) if rt_n > 0 else (round(sum(rts) / len(rts), 2) if rts else 0)
    min_rt = round(float(agg.get("min_rt") or 0), 2) if rt_n > 0 else (round(min(rts), 2) if rts else 0)
    max_rt = round(float(agg.get("max_rt") or 0), 2) if rt_n > 0 else (round(max(rts), 2) if rts else 0)

    sample = list(rts) if rts else []
    if sample:
        median = round(float(np.median(sample)), 2)
        p90 = round(float(np.percentile(sample, 90)), 2)
        p95 = round(float(np.percentile(sample, 95)), 2)
        p99 = round(float(np.percentile(sample, 99)), 2)
        std_dev = round(float(np.std(sample)), 2)
    else:
        median = p90 = p95 = p99 = avg
        std_dev = 0

    out.update({
        "avg_rt": avg,
        "min_rt": min_rt,
        "max_rt": max_rt,
        "median_rt": median,
        "p90_rt": p90,
        "p95_rt": p95,
        "p99_rt": p99,
        "std_dev": std_dev,
        "rt_n": rt_n or len(sample),
    })
    return out


def finalize_case_aggregation(agg: dict, *, keep_samples: bool = False) -> dict:
    """计算指标；默认剥离 rts 供持久化，保留全量 avg/min/max。"""
    rts = list(agg.get("rts") or [])
    out = metrics_from_rts(rts, agg)
    if keep_samples and rts:
        out["rts"] = rts
        out["rt_count"] = int(agg.get("rt_count") or agg.get("rt_n") or len(rts))
        out["rt_sum"] = float(agg.get("rt_sum") or 0)
        out["rt_n"] = int(agg.get("rt_n") or 0)
    return out


def _ingest_rt_list(target: dict, rts: list) -> None:
    if not rts:
        return
    for rt in rts:
        if rt and float(rt) > 0:
            accumulate_case_rt(target, float(rt))


def merge_case_aggregation(existing: Optional[dict], incoming: dict) -> dict:
    """合并两个 Worker/节点的用例聚合（全量 sum/min/max + 蓄水池分位）。"""
    if not existing:
        base = {
            "name": incoming.get("name", ""),
            "total": 0,
            "success": 0,
            "fail": 0,
            "rts": [],
            "rt_count": 0,
            "rt_sum": 0.0,
            "rt_n": 0,
            "min_rt": 0.0,
            "max_rt": 0.0,
        }
    else:
        base = {
            "name": existing.get("name") or incoming.get("name", ""),
            "total": int(existing.get("total") or 0),
            "success": int(existing.get("success") or 0),
            "fail": int(existing.get("fail") or 0),
            "rts": list(existing.get("rts") or []),
            "rt_count": int(existing.get("rt_count") or existing.get("rt_n") or len(existing.get("rts") or [])),
            "rt_sum": float(existing.get("rt_sum") or 0),
            "rt_n": int(existing.get("rt_n") or 0),
            "min_rt": float(existing.get("min_rt") or 0),
            "max_rt": float(existing.get("max_rt") or 0),
        }
        _ensure_online_fields(base)

    base["total"] += int(incoming.get("total") or 0)
    base["success"] += int(incoming.get("success") or 0)
    base["fail"] += int(incoming.get("fail") or 0)

    # 优先合并对方全量在线统计
    in_n = int(incoming.get("rt_n") or 0)
    in_sum = float(incoming.get("rt_sum") or 0)
    if in_n > 0:
        if base["rt_n"] <= 0:
            base["min_rt"] = float(incoming.get("min_rt") or 0)
            base["max_rt"] = float(incoming.get("max_rt") or 0)
        else:
            base["min_rt"] = min(base["min_rt"], float(incoming.get("min_rt") or base["min_rt"]))
            base["max_rt"] = max(base["max_rt"], float(incoming.get("max_rt") or base["max_rt"]))
        base["rt_n"] += in_n
        base["rt_sum"] += in_sum
        base["rt_count"] = base["rt_n"]
        # 蓄水池单独合并，勿再 accumulate（会重复累加 rt_n/rt_sum）
        from app.modules.perf.metrics_accuracy import merge_rt_samples
        base["rts"] = merge_rt_samples(
            [base.get("rts") or [], incoming.get("rts") or []],
            max_samples=MAX_CASE_RT_SAMPLES,
        )
    elif incoming.get("rts"):
        _ingest_rt_list(base, incoming.get("rts") or [])
    elif incoming.get("avg_rt") and incoming.get("total"):
        # 旧 Worker：无 rts / 无 rt_sum，用 avg 近似回填
        avg = float(incoming["avg_rt"])
        repeat = min(int(incoming["total"]), MAX_CASE_RT_SAMPLES)
        _ingest_rt_list(base, [avg] * repeat)
        if incoming.get("min_rt"):
            base["min_rt"] = min(base["min_rt"] or float(incoming["min_rt"]), float(incoming["min_rt"])) if base["rt_n"] else float(incoming["min_rt"])
        if incoming.get("max_rt"):
            base["max_rt"] = max(base["max_rt"] or float(incoming["max_rt"]), float(incoming["max_rt"])) if base["rt_n"] else float(incoming["max_rt"])
    return base


def strip_rt_samples_from_case_aggregations(case_aggs: dict) -> dict:
    """持久化前移除 RT 样本，仅保留计算后的指标（含全量 avg/min/max）。"""
    out: Dict[str, dict] = {}
    for cid, agg in (case_aggs or {}).items():
        if isinstance(agg, dict) and (agg.get("rts") or agg.get("rt_count") or agg.get("rt_n")):
            out[str(cid)] = finalize_case_aggregation(agg, keep_samples=False)
        else:
            out[str(cid)] = dict(agg)
    return out
