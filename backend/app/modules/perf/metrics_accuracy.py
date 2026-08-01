"""压测准确性 / 对比可信度辅助。

- 配置指纹：对比前校验负载画像是否一致
- 样本门槛：请求过少时标记变化%不可信
- 蓄水池合并：多 Worker 真分位，避免「P95 的加权平均」
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

# 对比时低于此总请求数则提示样本不足（与报告 UI 共用）
MIN_COMPARE_REQUESTS = 50
# 流式 / 链路 / 问答类场景通常低并发、单轮请求少，门槛单独放宽
MIN_COMPARE_REQUESTS_STREAM_OR_JOURNEY = 5

_LOW_SAMPLE_MODES = frozenset({
    "stream_burst",
    "sse_burst",
    "journey_fixed",
    "journey_loop",
})


def is_low_concurrency_workload(config: Optional[dict]) -> bool:
    """流式突发、业务链路、或配置了 stream_profile 的问答类场景。"""
    cfg = config or {}
    mode = str(cfg.get("mode") or "").strip().lower()
    if mode in _LOW_SAMPLE_MODES:
        return True
    try:
        from app.modules.stream_phase.contract import use_stream_execution

        if use_stream_execution(cfg):
            return True
    except Exception:
        pass
    return bool(cfg.get("stream_profile"))


def resolve_compare_sample_threshold(*configs: Optional[dict]) -> int:
    """按场景类型选择样本门槛；任一侧重为流式/链路则用宽松门槛。"""
    for cfg in configs:
        if is_low_concurrency_workload(cfg):
            return MIN_COMPARE_REQUESTS_STREAM_OR_JOURNEY
    return MIN_COMPARE_REQUESTS


def sample_size_warning(
    *request_counts: int,
    threshold: Optional[int] = None,
    configs: Optional[Sequence[Optional[dict]]] = None,
) -> Optional[str]:
    if threshold is None:
        threshold = resolve_compare_sample_threshold(*(configs or ()))
    lows = [c for c in request_counts if (c or 0) < threshold]
    if not lows:
        return None
    shown = ", ".join(str(c or 0) for c in request_counts)
    if threshold <= MIN_COMPARE_REQUESTS_STREAM_OR_JOURNEY:
        return (
            f"请求数偏少（总请求 {shown}）。流式/链路/问答场景通常并发较低，"
            f"若本轮完成量已接近预期可正常解读；若远少于并发×轮次，建议加长时长或增加轮次后再对比。"
        )
    return (
        f"样本偏少（总请求 {shown}，建议每侧 ≥ {threshold}），"
        "变化百分比仅供参考，不宜作为性能结论。"
    )


# 多 Worker 合并后全局分位样本上限
MAX_MERGED_RT_SAMPLES = 20000

_COMPARE_CONFIG_KEYS = (
    "mode",
    "concurrent_users",
    "duration_seconds",
    "loop_count",
    "ramp_up_seconds",
    "warmup_seconds",
    "target_host",
    "distribution_mode",
    "error_rate_threshold",
)


def resolve_warmup_seconds(config: Optional[dict]) -> int:
    """warmup 未显式配置时，跟随 ramp_up，便于默认剔除加压段噪声。"""
    cfg = config or {}
    if "warmup_seconds" in cfg and cfg["warmup_seconds"] is not None:
        try:
            return max(0, int(cfg["warmup_seconds"]))
        except (TypeError, ValueError):
            return 0
    try:
        return max(0, int(cfg.get("ramp_up_seconds") or 0))
    except (TypeError, ValueError):
        return 0


def _norm_int(val: Any, default: int = 0) -> int:
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _delay_fields(obj: dict) -> dict:
    mode = (obj.get("delay_mode") or "fixed")
    if mode not in ("fixed", "random"):
        mode = "fixed"
    return {
        "delay_mode": mode,
        "delay_ms": _norm_int(obj.get("delay_ms"), 0),
        "delay_ms_min": _norm_int(obj.get("delay_ms_min"), 0),
        "delay_ms_max": _norm_int(obj.get("delay_ms_max"), 0),
    }


def scene_items_delay_fingerprint(scene_items: Optional[list]) -> List[dict]:
    """场景项请求间隔指纹（按 case_id 排序，忽略 weight 等非间隔字段）。"""
    out: List[dict] = []
    for item in scene_items or []:
        if not isinstance(item, dict):
            continue
        try:
            cid = int(item.get("case_id"))
        except (TypeError, ValueError):
            continue
        row = {"case_id": cid}
        row.update(_delay_fields(item))
        out.append(row)
    out.sort(key=lambda x: (x["case_id"], x["delay_mode"], x["delay_ms"], x["delay_ms_min"], x["delay_ms_max"]))
    return out


def journey_delay_fingerprint(config: Optional[dict]) -> dict:
    """journey 步骤间隔 + 链路间间隔。"""
    cfg = config or {}
    journey = cfg.get("journey")
    if not isinstance(journey, dict):
        return {}
    steps_fp: List[dict] = []
    for pi, phase in enumerate(journey.get("phases") or []):
        if not isinstance(phase, dict):
            continue
        for si, step in enumerate(phase.get("steps") or []):
            if not isinstance(step, dict):
                continue
            try:
                cid = int(step.get("case_id"))
            except (TypeError, ValueError):
                continue
            row = {"phase": pi, "step": si, "case_id": cid}
            row.update(_delay_fields(step))
            steps_fp.append(row)
    return {
        "delay_between_journeys_ms": _norm_int(journey.get("delay_between_journeys_ms"), 0),
        "steps": steps_fp,
    }


def config_fingerprint(config: Optional[dict]) -> dict:
    cfg = config or {}
    out = {}
    for key in _COMPARE_CONFIG_KEYS:
        if key == "warmup_seconds":
            out[key] = resolve_warmup_seconds(cfg)
            continue
        val = cfg.get(key)
        if key in ("concurrent_users", "duration_seconds", "loop_count", "ramp_up_seconds"):
            try:
                out[key] = int(val) if val is not None else None
            except (TypeError, ValueError):
                out[key] = val
        else:
            out[key] = val if val not in ("",) else None
    # stepping 阶段也会影响负载
    steps = cfg.get("steps")
    if isinstance(steps, list):
        out["steps"] = [
            {"users": s.get("users"), "duration": s.get("duration")}
            for s in steps
            if isinstance(s, dict)
        ]
    # journey 间隔影响有效 QPS / RT 形态
    jfp = journey_delay_fingerprint(cfg)
    if jfp.get("steps") or jfp.get("delay_between_journeys_ms"):
        out["journey_delays"] = jfp
    return out


def configs_comparable(
    a: Optional[dict],
    b: Optional[dict],
    scene_items_a: Optional[list] = None,
    scene_items_b: Optional[list] = None,
) -> Tuple[bool, List[str]]:
    fa, fb = config_fingerprint(a), config_fingerprint(b)
    diffs: List[str] = []
    keys = set(fa) | set(fb)
    for key in sorted(keys):
        if fa.get(key) != fb.get(key):
            diffs.append(key)
    sa = scene_items_delay_fingerprint(scene_items_a)
    sb = scene_items_delay_fingerprint(scene_items_b)
    if sa != sb:
        diffs.append("scene_item_delays")
    return (len(diffs) == 0), diffs


def merge_rt_samples(sample_lists: Sequence[Sequence[float]], max_samples: int = MAX_MERGED_RT_SAMPLES) -> List[float]:
    """合并多 Worker 蓄水池；超出上限时再蓄水池抽样。"""
    merged: List[float] = []
    seen = 0
    for samples in sample_lists:
        if not samples:
            continue
        for value in samples:
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            if v <= 0:
                continue
            seen += 1
            if len(merged) < max_samples:
                merged.append(v)
            else:
                j = random.randint(0, seen - 1)
                if j < max_samples:
                    merged[j] = v
    return merged


def percentiles_from_samples(samples: Sequence[float]) -> Dict[str, float]:
    if not samples:
        return {
            "median_response_time": 0.0,
            "p90_response_time": 0.0,
            "p95_response_time": 0.0,
            "p99_response_time": 0.0,
        }
    arr = sorted(float(x) for x in samples if x and x > 0)
    if not arr:
        return {
            "median_response_time": 0.0,
            "p90_response_time": 0.0,
            "p95_response_time": 0.0,
            "p99_response_time": 0.0,
        }

    def _pct(p: float) -> float:
        if len(arr) == 1:
            return round(arr[0], 2)
        # 与 numpy.percentile 线性插值接近的简单实现，避免 workers 依赖 numpy
        k = (len(arr) - 1) * (p / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return round(arr[int(k)], 2)
        return round(arr[f] * (c - k) + arr[c] * (k - f), 2)

    return {
        "median_response_time": _pct(50),
        "p90_response_time": _pct(90),
        "p95_response_time": _pct(95),
        "p99_response_time": _pct(99),
    }


def build_comparison_trust(
    current_cfg: Optional[dict],
    previous_cfg: Optional[dict],
    current_requests: int,
    previous_requests: int,
    current_scene_items: Optional[list] = None,
    previous_scene_items: Optional[list] = None,
) -> dict:
    ok, diffs = configs_comparable(
        current_cfg,
        previous_cfg,
        scene_items_a=current_scene_items,
        scene_items_b=previous_scene_items,
    )
    threshold = resolve_compare_sample_threshold(current_cfg, previous_cfg)
    warn = sample_size_warning(
        current_requests,
        previous_requests,
        threshold=threshold,
        configs=(current_cfg, previous_cfg),
    )
    messages: List[str] = []
    if not ok:
        messages.append(
            "压测配置不一致（" + "、".join(diffs) + "），对比仅供参考。"
        )
    if warn:
        messages.append(warn)
    return {
        "config_match": ok,
        "config_diffs": diffs,
        "sample_sufficient": warn is None,
        "min_requests": threshold,
        "workload_hint": (
            "stream_or_journey" if is_low_concurrency_workload(current_cfg) or is_low_concurrency_workload(previous_cfg)
            else "standard"
        ),
        "warnings": messages,
        "trustworthy": ok and warn is None,
    }


# ---------- 基线钉选 / 阈值 ----------

DEFAULT_BASELINE_THRESHOLDS = {
    "p95_degrade_pct": 20.0,       # 当前 P95 高于基线超过该百分比 → 告警
    "qps_degrade_pct": 15.0,       # 当前 QPS 低于基线超过该百分比 → 告警
    "error_rate_increase": 5.0,    # 错误率绝对百分点升高超过该值 → 告警
}


def normalize_baseline_thresholds(raw: Optional[dict]) -> dict:
    out = dict(DEFAULT_BASELINE_THRESHOLDS)
    if not isinstance(raw, dict):
        return out
    for key in DEFAULT_BASELINE_THRESHOLDS:
        if key in raw and raw[key] is not None:
            try:
                out[key] = float(raw[key])
            except (TypeError, ValueError):
                pass
    return out


def evaluate_baseline_alerts(
    *,
    current_qps: float,
    baseline_qps: float,
    current_p95: float,
    baseline_p95: float,
    current_error_rate: float,
    baseline_error_rate: float,
    thresholds: Optional[dict] = None,
) -> List[dict]:
    """相对基线的超阈值告警列表。"""
    th = normalize_baseline_thresholds(thresholds)
    alerts: List[dict] = []

    qps_th = float(th["qps_degrade_pct"])
    if baseline_qps > 0 and qps_th >= 0:
        drop_pct = (baseline_qps - current_qps) / baseline_qps * 100
        if drop_pct >= qps_th:
            alerts.append({
                "metric": "qps",
                "severity": "QPS",
                "severity": "degrade",
                "threshold": qps_th,
                "change_pct": round(drop_pct, 2),
                "message": f"QPS 相对基线下降 {drop_pct:.1f}%（阈值 {qps_th:g}%）",
            })

    p95_th = float(th["p95_degrade_pct"])
    if baseline_p95 > 0 and p95_th >= 0:
        rise_pct = (current_p95 - baseline_p95) / baseline_p95 * 100
        if rise_pct >= p95_th:
            alerts.append({
                "metric": "p95_response_time",
                "severity": "P95 响应时间",
                "severity": "degrade",
                "threshold": p95_th,
                "change_pct": round(rise_pct, 2),
                "message": f"P95 相对基线升高 {rise_pct:.1f}%（阈值 {p95_th:g}%）",
            })

    err_th = float(th["error_rate_increase"])
    if err_th >= 0:
        delta = float(current_error_rate or 0) - float(baseline_error_rate or 0)
        if delta >= err_th:
            alerts.append({
                "metric": "error_rate",
                "severity": "错误率",
                "severity": "degrade",
                "threshold": err_th,
                "change_abs": round(delta, 2),
                "message": f"错误率相对基线升高 {delta:.1f} 个百分点（阈值 {err_th:g}）",
            })

    return alerts
