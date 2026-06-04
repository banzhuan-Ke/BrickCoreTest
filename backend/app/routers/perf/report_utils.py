"""性能测试报告数据组装与衍生指标"""
from typing import Any, Dict, List, Optional


def build_rt_histogram(samples: List[float], bucket_ms: int = 100, max_buckets: int = 30) -> List[dict]:
    """根据响应时间样本构建直方图分桶"""
    if not samples:
        return []
    valid = [float(s) for s in samples if s and s > 0]
    if not valid:
        return []

    max_rt = max(valid)
    bucket = max(bucket_ms, 50)
    if max_rt > bucket * max_buckets:
        bucket = int(max_rt / max_buckets) + 1

    counts: Dict[int, int] = {}
    for v in valid:
        idx = int(v // bucket)
        counts[idx] = counts.get(idx, 0) + 1

    result = []
    for idx in sorted(counts.keys()):
        low = idx * bucket
        high = low + bucket
        result.append({
            "label": f"{int(low)}-{int(high)}",
            "min": low,
            "max": high,
            "count": counts[idx],
        })
    return result


def normalize_time_series_for_chart(
    time_series: Optional[List[dict]],
    overall_p95: Optional[float] = None,
) -> List[dict]:
    """规范秒级时序：瞬时 QPS、补齐 P95，避免累计 total_req 导致趋势图与汇总卡片不一致"""
    if not time_series:
        return []
    points = sorted(time_series, key=lambda p: p.get("timestamp", 0))
    totals = [int(p.get("total_req") or 0) for p in points]
    looks_cumulative = (
        len(points) > 1
        and all(totals[i] >= totals[i - 1] for i in range(1, len(points)))
        and totals[-1] > 0
    )
    out: List[dict] = []
    for i, raw in enumerate(points):
        item = dict(raw)
        sec_req = float(item.get("qps") or 0)
        if looks_cumulative:
            prev = totals[i - 1] if i > 0 else 0
            sec_req = max(0.0, float(totals[i] - prev))
            item["qps"] = round(sec_req, 2)
            item["total_req"] = int(sec_req)
        elif sec_req <= 0 and item.get("total_req"):
            sec_req = float(item["total_req"])
            item["qps"] = round(sec_req, 2)
        if item.get("p95_rt") is None:
            item["p95_rt"] = item.get("avg_rt")
        out.append(item)
    if overall_p95 and out and all(p.get("p95_rt") == p.get("avg_rt") for p in out):
        for p in out:
            if p.get("p95_rt") == p.get("avg_rt"):
                p["p95_rt"] = overall_p95
    return out


def compute_concurrent_stats(time_series: Optional[List[dict]]) -> dict:
    """从秒级时序计算并发统计"""
    if not time_series:
        return {"peak_concurrent": 0, "avg_concurrent": 0}
    users = [int(p.get("active_users") or 0) for p in time_series]
    if not users:
        return {"peak_concurrent": 0, "avg_concurrent": 0}
    return {
        "peak_concurrent": max(users),
        "avg_concurrent": round(sum(users) / len(users), 2),
    }


def enrich_case_aggregations(case_aggs: Optional[dict], duration: float) -> dict:
    """为用例聚合补充 QPS"""
    if not case_aggs:
        return {}
    dur = duration or 0
    out = {}
    for cid, agg in case_aggs.items():
        item = dict(agg)
        total = item.get("total") or 0
        item["qps"] = round(total / dur, 2) if dur > 0 and total > 0 else 0
        out[cid] = item
    return out


def _pct_change(current: float, previous: float) -> Optional[float]:
    if previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100, 2)


def _success_qps(record: Any) -> float:
    dur = record.duration or 0
    return round((record.success_count or 0) / dur, 2) if dur > 0 else 0


def build_previous_comparison(current: Any, previous: Any) -> Optional[dict]:
    """与同场景上一次执行记录对比"""
    if not previous:
        return None
    metrics = [
        ("qps", "QPS", False, lambda r: r.qps),
        ("success_qps", "成功 QPS", False, _success_qps),
        ("avg_response_time", "平均响应时间", True, lambda r: r.avg_response_time),
        ("p95_response_time", "P95 响应时间", True, lambda r: r.p95_response_time),
        ("error_rate", "错误率", True, lambda r: r.error_rate),
        ("total_requests", "总请求数", False, lambda r: r.total_requests),
    ]
    changes = {}
    for key, label, lower_is_better, getter in metrics:
        cur = getter(current)
        prev = getter(previous)
        if cur is None or prev is None:
            continue
        pct = _pct_change(float(cur), float(prev))
        if pct is None:
            continue
        changes[key] = {
            "label": label,
            "current": cur,
            "previous": prev,
            "change_pct": pct,
            "lower_is_better": lower_is_better,
        }
    if not changes:
        return None
    return {
        "record_id": previous.id,
        "started_at": previous.started_at.strftime("%Y-%m-%d %H:%M:%S") if previous.started_at else None,
        "changes": changes,
    }


def build_config_summary(config: Optional[dict], distribution_info: Optional[dict]) -> dict:
    """压测配置摘要（供报告展示）"""
    cfg = config or {}
    mode = cfg.get("mode", "fixed")
    mode_labels = {"fixed": "固定模式", "loop": "循环模式", "stepping": "梯度模式"}
    dist = cfg.get("distribution_mode", "random_weight")
    dist_label = "固定比例" if dist == "fixed_ratio" else "随机权重"

    duration_label = "-"
    if mode == "fixed":
        duration_label = f"{cfg.get('duration_seconds', '-')} 秒"
    elif mode == "loop":
        duration_label = f"{cfg.get('loop_count', '-')} 次/用户"
    elif mode == "stepping":
        steps = cfg.get("steps") or []
        duration_label = f"{len(steps)} 个阶段"

    dist_info = distribution_info or {}
    workers = dist_info.get("workers") or []
    is_distributed = bool(workers) or dist_info.get("is_distributed")

    return {
        "mode": mode,
        "mode_label": mode_labels.get(mode, mode),
        "distribution_mode_label": dist_label,
        "concurrent_users": cfg.get("concurrent_users"),
        "ramp_up_seconds": cfg.get("ramp_up_seconds", 0),
        "target_host": cfg.get("target_host") or "使用环境默认 Host",
        "duration_label": duration_label,
        "error_rate_threshold": cfg.get("error_rate_threshold") or 0,
        "execution_type": "分布式 Worker" if is_distributed else "本机执行",
        "worker_count": len(workers),
        "workers": workers,
    }


def normalize_status_code_distribution(dist: dict, total_requests: int) -> dict:
    """将状态码计数对齐到本次总请求数（修复历史数据重复合并导致的翻倍）"""
    if not dist:
        return {}
    total_requests = int(total_requests or 0)
    if total_requests <= 0:
        return {str(k): int(v) for k, v in dist.items()}
    dist_sum = sum(int(v) for v in dist.values())
    if dist_sum <= total_requests:
        return {str(k): int(v) for k, v in dist.items()}
    ratio = total_requests / dist_sum
    out: Dict[str, int] = {}
    allocated = 0
    items = list(dist.items())
    for i, (k, v) in enumerate(items):
        if i == len(items) - 1:
            out[str(k)] = max(0, total_requests - allocated)
        else:
            c = int(round(int(v) * ratio))
            out[str(k)] = c
            allocated += c
    return out


def build_report_payload(record: Any, scene: Any, previous_record: Any = None) -> dict:
    """组装完整报告 API 响应"""
    config = record.config_snapshot or {}
    mode = config.get("mode", "fixed")
    duration = record.duration or 0
    raw_time_series = record.time_series_data or []
    time_series = normalize_time_series_for_chart(
        raw_time_series,
        overall_p95=getattr(record, "p95_response_time", None),
    )
    concurrent = compute_concurrent_stats(time_series)

    total_requests = record.total_requests or 0
    success_count = record.success_count or 0
    fail_count = record.fail_count or 0
    if fail_count == 0 and (record.error_rate or 0) == 0 and success_count < total_requests:
        success_count = total_requests

    if duration > 0 and total_requests > 0:
        qps = round(total_requests / duration, 2)
        success_qps = round(success_count / duration, 2)
    else:
        qps = record.qps or 0
        success_qps = round(success_count / duration, 2) if duration > 0 else 0

    raw_breakdown = record.error_breakdown or {}
    stop_reason = raw_breakdown.get("stop_reason") if isinstance(raw_breakdown, dict) else None
    error_breakdown = {}
    if isinstance(raw_breakdown, dict):
        error_breakdown = {
            k: v for k, v in raw_breakdown.items()
            if not str(k).startswith("_")
        }
        raw_dist = error_breakdown.get("status_code_distribution")
        if isinstance(raw_dist, dict) and raw_dist:
            error_breakdown["status_code_distribution"] = normalize_status_code_distribution(
                raw_dist, total_requests
            )

    case_aggs = enrich_case_aggregations(record.case_aggregations, duration)
    rt_histogram = error_breakdown.get("rt_histogram") or []

    dist_info = record.distribution_info or {}

    payload = {
        "id": record.id,
        "scene_id": record.scene_id,
        "scene_name": scene.name if scene else "未知场景",
        "project_id": record.project_id,
        "status": record.status,
        "trigger_type": record.trigger_type,
        "trigger_type_label": {"manual": "手动", "cron": "定时"}.get(record.trigger_type, record.trigger_type),
        "mode": mode,
        "config_snapshot": config,
        "config_summary": build_config_summary(config, dist_info),
        "distribution_info": dist_info,
        "scene_items_snapshot": record.scene_items_snapshot,
        "total_requests": total_requests,
        "success_count": success_count,
        "fail_count": fail_count,
        "qps": qps,
        "success_qps": success_qps,
        "avg_response_time": record.avg_response_time,
        "min_response_time": record.min_response_time,
        "max_response_time": record.max_response_time,
        "median_response_time": record.median_response_time,
        "p90_response_time": record.p90_response_time,
        "p95_response_time": record.p95_response_time,
        "p99_response_time": record.p99_response_time,
        "std_dev_response_time": record.std_dev_response_time,
        "error_rate": record.error_rate,
        "received_kb_per_sec": record.received_kb_per_sec,
        "sent_kb_per_sec": record.sent_kb_per_sec,
        "peak_concurrent": concurrent["peak_concurrent"],
        "avg_concurrent": concurrent["avg_concurrent"],
        "time_series_data": time_series,
        "case_aggregations": case_aggs,
        "error_breakdown": error_breakdown,
        "rt_histogram": rt_histogram,
        "stop_reason": stop_reason,
        "started_at": record.started_at.strftime("%Y-%m-%d %H:%M:%S") if record.started_at else None,
        "ended_at": record.ended_at.strftime("%Y-%m-%d %H:%M:%S") if record.ended_at else None,
        "duration": record.duration,
        "run_by": record.run_by,
        "previous_comparison": build_previous_comparison(record, previous_record),
    }
    return payload
