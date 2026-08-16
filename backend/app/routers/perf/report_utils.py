"""性能测试报告数据组装与衍生指标"""
import html as html_module
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.routers.perf.progress_utils import normalize_distribution_mode
from app.modules.perf.perf_target_eval import evaluate_perf_targets, resolve_core_metrics


def _format_case_update_time(dt) -> Optional[str]:
    if not dt:
        return None
    if hasattr(dt, "strftime"):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)


async def build_case_drift(scene_items_snapshot: Optional[list]) -> dict:
    """对比执行快照中的 case_update_time 与当前用例，返回漂移列表。"""
    from app.models.http import ApiTestCase

    items = scene_items_snapshot or []
    if not isinstance(items, list) or not items:
        return {"items": [], "has_drift": False}

    # 仅当至少一条带有 case_update_time 时才做提示（兼容旧记录）
    has_meta = any(
        isinstance(it, dict) and it.get("case_update_time")
        for it in items
    )
    if not has_meta:
        return {"items": [], "has_drift": False}

    case_ids = []
    for it in items:
        if not isinstance(it, dict):
            continue
        cid = it.get("case_id")
        if cid is not None:
            try:
                case_ids.append(int(cid))
            except (TypeError, ValueError):
                pass
    case_ids = list(dict.fromkeys(case_ids))
    cases = await ApiTestCase.filter(id__in=case_ids, is_del=False).all() if case_ids else []
    case_map = {c.id: c for c in cases}

    drift_items = []
    for it in items:
        if not isinstance(it, dict):
            continue
        cid = it.get("case_id")
        if cid is None:
            continue
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            continue
        snap_ts = it.get("case_update_time")
        if not snap_ts:
            continue
        case = case_map.get(cid)
        name = it.get("case_name") or (case.name if case else f"#{cid}")
        if not case:
            drift_items.append({
                "case_id": cid,
                "name": name,
                "status": "missing",
                "snapshotted_at": snap_ts,
                "current_update_time": None,
            })
            continue
        current_ts = _format_case_update_time(case.update_time)
        # 字符串比较：快照与当前均为 %Y-%m-%d %H:%M:%S
        if current_ts and current_ts > str(snap_ts):
            drift_items.append({
                "case_id": cid,
                "name": case.name or name,
                "status": "updated",
                "snapshotted_at": snap_ts,
                "current_update_time": current_ts,
            })

    return {"items": drift_items, "has_drift": bool(drift_items)}


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


def merge_rt_histograms(
    *hist_lists: List[dict],
    bucket_ms: int = 100,
    max_buckets: int = 30,
) -> List[dict]:
    """合并多 Worker 直方图：按统一桶宽重采样，避免 label 粒度不一致导致失真。"""
    parts: List[tuple] = []
    global_max = 0.0
    for hist in hist_lists:
        if not hist:
            continue
        for h in hist:
            if not isinstance(h, dict):
                continue
            try:
                mn = float(h.get("min") if h.get("min") is not None else 0)
                mx = float(h.get("max") if h.get("max") is not None else mn)
                c = int(h.get("count") or 0)
            except (TypeError, ValueError):
                continue
            if c <= 0:
                continue
            parts.append((mn, mx, c))
            global_max = max(global_max, mx, mn)
    if not parts:
        return []

    bucket = max(bucket_ms, 50)
    if global_max > bucket * max_buckets:
        bucket = int(global_max / max_buckets) + 1

    counts: Dict[int, int] = {}
    for mn, mx, c in parts:
        mid = (mn + mx) / 2.0 if mx > mn else mn
        idx = int(mid // bucket)
        counts[idx] = counts.get(idx, 0) + c

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
    """规范秒级时序：瞬时 QPS、补齐当秒 P95，避免累计 total_req 导致趋势图与汇总卡片不一致。

    overall_p95 仅用于报告汇总，不再回填到每秒点位（避免 P95 趋势线与汇总值混淆）。
    """
    _ = overall_p95  # 保留参数以兼容既有调用方，汇总 P95 由图表参考线展示
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
    return out


def chart_p95_rt_value(point: dict) -> Optional[float]:
    """趋势图当秒 P95：仅在该秒有完成请求时返回值，否则为 None（折线用 connectNulls 跨空闲秒）。"""
    if float(point.get("qps") or 0) <= 0:
        return None
    val = point.get("p95_rt")
    if val is None:
        val = point.get("avg_rt")
    if val is None:
        return None
    return float(val)


def chart_avg_rt_value(point: dict) -> Optional[float]:
    """趋势图当秒平均 RT：仅在该秒有完成请求时返回值。"""
    if float(point.get("qps") or 0) <= 0:
        return None
    val = point.get("avg_rt")
    if val is None:
        return None
    return float(val)


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
        item = {k: v for k, v in agg.items() if k not in ("rts", "rt_count")}
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


def _record_qps(record: Any) -> float:
    dur = record.duration or 0
    if dur > 0:
        return round((record.total_requests or 0) / dur, 2)
    return float(record.qps or 0)


def _comparison_changes(current: Any, reference: Any) -> dict:
    metrics = [
        ("qps", "QPS", False, _record_qps),
        ("success_qps", "成功 QPS", False, _success_qps),
        ("avg_response_time", "平均响应时间", True, lambda r: r.avg_response_time),
        ("p95_response_time", "P95 响应时间", True, lambda r: r.p95_response_time),
        ("error_rate", "错误率", True, lambda r: r.error_rate),
        ("total_requests", "总请求数", False, lambda r: r.total_requests),
    ]
    changes = {}
    for key, label, lower_is_better, getter in metrics:
        cur = getter(current)
        prev = getter(reference)
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
            "unit": "ms" if "响应时间" in label else ("%" if "错误率" in label else ""),
            "group": "http",
        }
    changes.update(_phase_metric_changes(current, reference))
    return changes


def _phase_metrics_by_key(record: Any) -> dict[str, dict]:
    """仅当次压测配置走流式时，才参与阶段对比（避免普通 HTTP 脏 phase_metrics 污染对照）。"""
    cfg = getattr(record, "config_snapshot", None) or {}
    if not isinstance(cfg, dict):
        cfg = {}
    from app.modules.stream_phase.contract import use_stream_execution

    if not use_stream_execution(cfg):
        return {}
    raw = getattr(record, "phase_metrics", None) or {}
    if not isinstance(raw, dict):
        return {}
    rows = raw.get("metrics") or []
    out: dict[str, dict] = {}
    if not isinstance(rows, list):
        return out
    for item in rows:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        out[key] = item
    return out


def _phase_metric_changes(current: Any, reference: Any) -> dict:
    """按 phase_metrics.metrics[].key 通用对比均值/P95（秒），不绑死业务字段名。"""
    cur_map = _phase_metrics_by_key(current)
    ref_map = _phase_metrics_by_key(reference)
    if not cur_map or not ref_map:
        return {}

    changes: dict[str, dict] = {}
    # 交集：两边都有的阶段/派生指标
    for key in cur_map.keys() & ref_map.keys():
        cur = cur_map[key]
        ref = ref_map[key]
        label = (cur.get("label") or ref.get("label") or key)
        for stat_key, suffix in (("mean", "均值"), ("p95", "P95")):
            cur_v = cur.get(stat_key)
            ref_v = ref.get(stat_key)
            if cur_v is None or ref_v is None:
                continue
            try:
                cur_f = float(cur_v)
                ref_f = float(ref_v)
            except (TypeError, ValueError):
                continue
            pct = _pct_change(cur_f, ref_f)
            if pct is None:
                continue
            change_key = f"phase_{stat_key}_{key}"
            changes[change_key] = {
                "label": f"{label} {suffix}(s)",
                "current": round(cur_f, 3),
                "previous": round(ref_f, 3),
                "change_pct": pct,
                "lower_is_better": True,
                "unit": "s",
                "group": "phase",
                "phase_key": key,
            }
    return changes


def build_previous_comparison(current: Any, previous: Any) -> Optional[dict]:
    """与同场景上一次执行记录对比"""
    if not previous:
        return None
    from app.modules.perf.metrics_accuracy import build_comparison_trust

    changes = _comparison_changes(current, previous)
    if not changes:
        return None
    trust = build_comparison_trust(
        getattr(current, "config_snapshot", None),
        getattr(previous, "config_snapshot", None),
        int(getattr(current, "total_requests", 0) or 0),
        int(getattr(previous, "total_requests", 0) or 0),
        current_scene_items=getattr(current, "scene_items_snapshot", None),
        previous_scene_items=getattr(previous, "scene_items_snapshot", None),
    )
    return {
        "record_id": previous.id,
        "started_at": previous.started_at.strftime("%Y-%m-%d %H:%M:%S") if previous.started_at else None,
        "changes": changes,
        "has_phase_changes": any(
            isinstance(v, dict) and v.get("group") == "phase" for v in changes.values()
        ),
        "trust": trust,
    }


def build_baseline_comparison(
    current: Any,
    baseline: Any,
    thresholds: Optional[dict] = None,
) -> Optional[dict]:
    """与场景钉选基线对比，并附带阈值告警。"""
    if not baseline:
        return None
    from app.modules.perf.metrics_accuracy import (
        build_comparison_trust,
        evaluate_baseline_alerts,
        normalize_baseline_thresholds,
    )

    th = normalize_baseline_thresholds(thresholds)
    trust = build_comparison_trust(
        getattr(current, "config_snapshot", None),
        getattr(baseline, "config_snapshot", None),
        int(getattr(current, "total_requests", 0) or 0),
        int(getattr(baseline, "total_requests", 0) or 0),
        current_scene_items=getattr(current, "scene_items_snapshot", None),
        previous_scene_items=getattr(baseline, "scene_items_snapshot", None),
    )
    alerts = evaluate_baseline_alerts(
        current_qps=_record_qps(current),
        baseline_qps=_record_qps(baseline),
        current_p95=float(current.p95_response_time or 0),
        baseline_p95=float(baseline.p95_response_time or 0),
        current_error_rate=float(current.error_rate or 0),
        baseline_error_rate=float(baseline.error_rate or 0),
        thresholds=th,
    )
    changes = _comparison_changes(current, baseline)
    return {
        "record_id": baseline.id,
        "started_at": baseline.started_at.strftime("%Y-%m-%d %H:%M:%S") if baseline.started_at else None,
        "changes": changes,
        "has_phase_changes": any(
            isinstance(v, dict) and v.get("group") == "phase" for v in changes.values()
        ),
        "trust": trust,
        "thresholds": th,
        "alerts": alerts,
        "has_alerts": bool(alerts),
    }


PERF_MODE_LABELS = {
    "fixed": "固定模式",
    "loop": "循环模式",
    "stepping": "梯度模式",
    "stream_burst": "流式阶段压测",
    "sse_burst": "流式阶段压测",
    "journey_fixed": "链路固定模式",
    "journey_loop": "链路循环模式",
}


def perf_mode_label(mode: Any) -> str:
    """压测模式中文名（报告 / AI 对外文案统一用此，勿直接输出英文枚举）。"""
    from app.modules.stream_phase import normalize_perf_mode

    raw = str(mode or "").strip()
    try:
        m = normalize_perf_mode(raw) if raw else "fixed"
    except Exception:
        m = raw or "fixed"
    return PERF_MODE_LABELS.get(m, PERF_MODE_LABELS.get(raw, raw or "-"))


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _mean(vals: List[float]) -> Optional[float]:
    return round(sum(vals) / len(vals), 2) if vals else None


def parse_stepping_plan(config: Optional[dict]) -> List[dict]:
    """从配置解析梯度阶段计划（不含观察指标）。"""
    steps = (config or {}).get("steps") or []
    plan: List[dict] = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        users = _safe_int(step.get("users"))
        if not users or users <= 0:
            continue
        plan.append({
            "stage": len(plan) + 1,
            "users": users,
            "planned_duration": _safe_int(step.get("duration")),
        })
    return plan


def peak_users_from_config(config: Optional[dict]) -> Optional[int]:
    """峰值并发：梯度取 stages 最大 users，其余取 concurrent_users。"""
    cfg = config or {}
    mode = str(cfg.get("mode") or "")
    if mode == "stepping":
        users = [s["users"] for s in parse_stepping_plan(cfg)]
        return max(users) if users else _safe_int(cfg.get("concurrent_users"))
    return _safe_int(cfg.get("concurrent_users"))


def format_steps_summary(config: Optional[dict]) -> str:
    """如：10用户×5s → 20用户×5s → 50用户×10s"""
    parts = []
    for s in parse_stepping_plan(config):
        dur = s.get("planned_duration")
        if dur:
            parts.append(f"{s['users']}用户×{dur}s")
        else:
            parts.append(f"{s['users']}用户")
    return " → ".join(parts)


def summarize_stepping_stages(
    config: Optional[dict],
    time_series: Optional[list] = None,
) -> List[dict]:
    """梯度阶段计划 + 按 active_users 平台期聚合的观察指标（供报告/AI）。"""
    plan = parse_stepping_plan(config)
    groups: List[dict] = []
    for point in time_series or []:
        if not isinstance(point, dict):
            continue
        users = _safe_int(point.get("active_users"))
        if not users or users <= 0:
            continue
        if groups and groups[-1]["users"] == users:
            groups[-1]["points"].append(point)
        else:
            groups.append({"users": users, "points": [point]})

    by_users: Dict[int, list] = {}
    for g in groups:
        by_users.setdefault(g["users"], []).extend(g["points"])

    observed: Dict[int, dict] = {}
    for users, pts in by_users.items():
        # 吞吐：整段墙钟平均（含无完成秒的 0），反映阶段有效产出
        qps_vals = [v for v in (_safe_float(p.get("qps")) for p in pts) if v is not None]
        # RT/P95/错误率：仅统计有完成请求的秒，避免大量 0 把耗时稀释成「1 秒多」
        complete_pts = [
            p for p in pts
            if (_safe_float(p.get("qps")) or 0) > 0 or (_safe_float(p.get("success")) or 0) > 0
        ]
        sample_pts = complete_pts or []
        rt_vals = [
            v for v in (_safe_float(p.get("avg_rt")) for p in sample_pts)
            if v is not None and v > 0
        ]
        p95_vals = [
            v for v in (
                _safe_float(p.get("p95_rt") if p.get("p95_rt") is not None else p.get("p95"))
                for p in sample_pts
            )
            if v is not None and v > 0
        ]
        err_vals = [
            v for v in (
                _safe_float(p.get("error_rate") if p.get("error_rate") is not None else p.get("err"))
                for p in sample_pts
            )
            if v is not None
        ]
        observed[users] = {
            "observed_seconds": len(pts),
            "completed_seconds": len(complete_pts),
            "avg_qps": _mean(qps_vals),
            "peak_qps": round(max(qps_vals), 2) if qps_vals else None,
            "avg_rt": _mean(rt_vals) if rt_vals else None,
            "avg_p95": _mean(p95_vals) if p95_vals else None,
            "avg_error_rate": _mean(err_vals) if err_vals else (0.0 if pts else None),
        }

    if plan:
        out = []
        for stage in plan:
            row = dict(stage)
            row.update(observed.get(stage["users"]) or {})
            out.append(row)
        return out

    # 无计划 steps 时，仅按时间序列平台期回填
    out = []
    for i, g in enumerate(groups):
        row = {"stage": i + 1, "users": g["users"], "planned_duration": None}
        row.update(observed.get(g["users"]) or {})
        out.append(row)
    return out


def format_stepping_stages_narrative(stages: Optional[list] = None) -> str:
    """把梯度各阶段写成可读中文摘要（单报告概览 / AI / 导出共用）。"""
    if not stages:
        return ""
    parts: list[str] = []
    prev_rt: Optional[float] = None
    inflection = None
    for st in stages:
        if not isinstance(st, dict):
            continue
        stage = st.get("stage")
        users = st.get("users")
        planned = st.get("planned_duration")
        obs = st.get("observed_seconds")
        done = st.get("completed_seconds")
        qps = st.get("avg_qps")
        rt = st.get("avg_rt")
        p95 = st.get("avg_p95")
        err = st.get("avg_error_rate")
        bit = f"第{stage}阶段（{users}并发"
        if planned is not None:
            bit += f"×{planned}s"
        bit += "）"
        detail = []
        if obs is not None:
            detail.append(f"观察{obs}s")
        if done is not None:
            detail.append(f"有完成{done}s")
        if qps is not None:
            detail.append(f"平均QPS {qps}")
        if rt is not None:
            detail.append(f"平均RT {rt}ms（约{round(float(rt)/1000, 1)}s）")
        elif done == 0 or (done is not None and int(done) == 0):
            detail.append("无完成请求，RT无有效样本")
        if p95 is not None:
            detail.append(f"P95 {p95}ms")
        if err is not None:
            detail.append(f"错误率{err}%")
        if detail:
            bit += "：" + "，".join(detail)
        parts.append(bit)
        try:
            rt_f = float(rt) if rt is not None else None
        except (TypeError, ValueError):
            rt_f = None
        if prev_rt is not None and rt_f is not None and prev_rt > 0 and rt_f / prev_rt >= 1.5:
            inflection = f"第{stage}阶段相对上一阶段平均RT升幅约{round((rt_f/prev_rt-1)*100)}%，需关注容量拐点"
        if rt_f is not None:
            prev_rt = rt_f
    text = "；".join(parts)
    if inflection:
        text += f"。{inflection}"
    elif text:
        text += "。"
    return text


def build_config_summary(config: Optional[dict], distribution_info: Optional[dict]) -> dict:
    """压测配置摘要（供报告展示）"""
    from app.routers.perf.case_agg_utils import MAX_CASE_RT_SAMPLES
    from app.modules.perf.metrics_accuracy import resolve_warmup_seconds
    from app.modules.stream_phase import normalize_perf_mode

    cfg = config or {}
    raw_mode = cfg.get("mode", "fixed")
    try:
        mode = normalize_perf_mode(raw_mode) if raw_mode else "fixed"
    except Exception:
        mode = str(raw_mode or "fixed")
    dist = normalize_distribution_mode(cfg.get("distribution_mode"))
    dist_label = "固定比例" if dist == "fixed_ratio" else "随机权重"

    steps_plan = parse_stepping_plan(cfg) if mode == "stepping" else []
    steps_summary = format_steps_summary(cfg) if mode == "stepping" else ""
    peak_users = peak_users_from_config(cfg)

    duration_label = "-"
    if mode == "fixed":
        duration_label = f"{cfg.get('duration_seconds', '-')} 秒"
    elif mode == "loop":
        duration_label = f"{cfg.get('loop_count', '-')} 次/用户"
    elif mode in ("stream_burst", "sse_burst"):
        duration_label = f"{cfg.get('concurrent_users', '-')} 并发（每用户1次）"
    elif mode == "journey_fixed":
        duration_label = f"{cfg.get('duration_seconds', '-')} 秒（链路循环）"
    elif mode == "journey_loop":
        duration_label = f"{cfg.get('loop_count', '-')} 次链路/用户"
    elif mode == "stepping":
        n = len(steps_plan)
        duration_label = f"{n} 个阶段" + (f"（{steps_summary}）" if steps_summary else "")

    if mode == "stepping":
        concurrent_users_label = "峰值并发"
        concurrent_users_display = str(peak_users) if peak_users is not None else "-"
    else:
        concurrent_users_label = "并发用户"
        concurrent_users_display = str(cfg.get("concurrent_users") if cfg.get("concurrent_users") is not None else "-")

    dist_info = distribution_info or {}
    workers = dist_info.get("workers") or []
    is_distributed = bool(workers) or dist_info.get("is_distributed")
    if workers:
        execution_type = "分布式 Worker"
    elif is_distributed:
        execution_type = "分布式 Worker"
    else:
        execution_type = "无 Worker 明细"

    detail_level = cfg.get("request_detail_level", "brief")
    detail_label = "详细（含成功请求接口信息）" if detail_level == "full" else "简略（失败仍含接口详情）"

    return {
        "mode": mode,
        "mode_label": perf_mode_label(mode),
        "distribution_mode_label": dist_label,
        "concurrent_users": cfg.get("concurrent_users"),
        "concurrent_users_label": concurrent_users_label,
        "concurrent_users_display": concurrent_users_display,
        "peak_concurrent_users": peak_users,
        "steps": steps_plan,
        "steps_summary": steps_summary or None,
        "ramp_up_seconds": cfg.get("ramp_up_seconds", 0),
        "warmup_seconds": resolve_warmup_seconds(cfg),
        "target_host": cfg.get("target_host") or "使用环境默认 Host",
        "duration_label": duration_label,
        "error_rate_threshold": cfg.get("error_rate_threshold") or 0,
        "execution_type": execution_type,
        "worker_count": len(workers),
        "workers": workers,
        "request_detail_level": detail_level,
        "request_detail_level_label": detail_label,
        "case_rt_sample_limit": MAX_CASE_RT_SAMPLES,
        "case_rt_sample_note": (
            f"接口维度 Avg/Min/Max 基于全量请求；P90/P95/P99 等分位基于最多 "
            f"{MAX_CASE_RT_SAMPLES} 条响应时间样本（蓄水池采样）；"
            "总请求数、QPS、错误率不受此限制。"
        ),
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


async def build_report_payload(
    record: Any,
    scene: Any,
    previous_record: Any = None,
    baseline_record: Any = None,
) -> dict:
    """组装完整报告 API 响应"""
    config = record.config_snapshot or {}
    mode = config.get("mode", "fixed")
    raw_time_series = record.time_series_data or []
    time_series = normalize_time_series_for_chart(
        raw_time_series,
        overall_p95=getattr(record, "p95_response_time", None),
    )
    concurrent = compute_concurrent_stats(time_series)

    core = resolve_core_metrics(record)
    total_requests = int(core["total_requests"] or 0)
    success_count = int(core["success_count"] or 0)
    fail_count = int(core["fail_count"] or 0)
    qps = core["qps"]
    success_qps = core["success_qps"]
    duration = float(core["duration"] or 0)

    raw_breakdown = record.error_breakdown or {}
    stop_reason = raw_breakdown.get("stop_reason") if isinstance(raw_breakdown, dict) else None
    journey_aggregations = {}
    metrics_meta = {}
    success_latency = {}
    if isinstance(raw_breakdown, dict):
        journey_aggregations = raw_breakdown.get("journey_aggregations") or {}
        metrics_meta = raw_breakdown.get("metrics_meta") or {}
        success_latency = raw_breakdown.get("success_latency") or {}
    error_breakdown = {}
    if isinstance(raw_breakdown, dict):
        # 大体积诊断明细走懒加载接口，主报告不回传
        _HEAVY_BREAKDOWN_KEYS = (
            "request_traces",
            "failed_samples",
            "journey_aggregations",
            "metrics_meta",
            "success_latency",
        )
        error_breakdown = {
            k: v for k, v in raw_breakdown.items()
            if not str(k).startswith("_") and k not in _HEAVY_BREAKDOWN_KEYS
        }
        raw_dist = error_breakdown.get("status_code_distribution")
        if isinstance(raw_dist, dict) and raw_dist:
            error_breakdown["status_code_distribution"] = normalize_status_code_distribution(
                raw_dist, total_requests
            )
        # 仅返回计数，便于前端展示区块，不夹带样本正文
        failed_list = raw_breakdown.get("failed_samples") or []
        error_breakdown["failed_samples_total"] = (
            len(failed_list) if isinstance(failed_list, list) else 0
        )

    case_aggs = enrich_case_aggregations(record.case_aggregations, duration)
    rt_histogram = error_breakdown.get("rt_histogram") or []

    dist_info = record.distribution_info or {}
    baseline_policy = getattr(scene, "baseline_policy", None) if scene else None
    pinned_id = getattr(scene, "baseline_record_id", None) if scene else None
    case_drift = await build_case_drift(record.scene_items_snapshot)
    cfg_summary = build_config_summary(config, dist_info)
    stepping_stages = (
        summarize_stepping_stages(config, raw_time_series)
        if str(cfg_summary.get("mode") or mode) == "stepping"
        else []
    )

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
        "config_summary": cfg_summary,
        "stepping_stages": stepping_stages,
        "stepping_stages_summary": format_stepping_stages_narrative(stepping_stages),
        "distribution_info": dist_info,
        "scene_items_snapshot": record.scene_items_snapshot,
        "case_drift": case_drift,
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
        "success_latency": success_latency,
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
        "baseline_comparison": build_baseline_comparison(
            record, baseline_record, thresholds=baseline_policy
        ),
        "scene_baseline": {
            "baseline_record_id": pinned_id,
            "is_current_baseline": bool(pinned_id and pinned_id == record.id),
            "policy": baseline_policy or {},
        },
        "phase_metrics": getattr(record, "phase_metrics", None) or {},
        "metrics_meta": metrics_meta,
        "request_details_total": len(getattr(record, "request_details", None) or []),
        "request_details": [],
        "request_traces_total": _count_http_trace_items(record),
        "request_traces": [],
        "stream_profile": (config.get("stream_profile") or {}),
        "journey_aggregations": journey_aggregations,
        "ai_analysis": getattr(record, "ai_analysis", None),
        "target_evaluation": evaluate_perf_targets(record),
    }
    return payload


def _count_http_trace_items(record: Any) -> int:
    bd = record.error_breakdown or {}
    if not isinstance(bd, dict):
        return 0
    traces = bd.get("request_traces") or []
    failures = bd.get("failed_samples") or []
    return len(traces) + len(failures)


def paginate_perf_request_items(
    record: Any,
    *,
    kind: str = "stream",
    status: str = "all",
    page: int = 1,
    size: int = 50,
) -> dict[str, Any]:
    """分页返回流式阶段明细或 HTTP 请求 trace（报告页懒加载）。"""
    from app.modules.stream_phase import migrate_legacy_detail
    from app.modules.perf.perf_trace import sanitize_trace_item

    page = max(1, page)
    size = max(1, min(size, 100))
    status = status if status in ("all", "success", "fail") else "all"

    if kind == "stream":
        items = [migrate_legacy_detail(d) for d in (record.request_details or [])]
        if status == "success":
            items = [d for d in items if d.get("success")]
        elif status == "fail":
            items = [d for d in items if not d.get("success")]
        items = [sanitize_trace_item(d) if isinstance(d, dict) else d for d in items]
    else:
        bd = record.error_breakdown or {}
        if not isinstance(bd, dict):
            bd = {}
        traces = list(bd.get("request_traces") or [])
        failures = list(bd.get("failed_samples") or [])
        if status == "success":
            items = [t for t in traces if t.get("success", True)]
        elif status == "fail":
            items = failures
        else:
            # 失败已在 failed_samples；success traces 可能含失败时勿重复
            # 约定：request_traces 仅成功；failed_samples 仅失败 → 合并不重复
            items = traces + failures
        items = [sanitize_trace_item(t) if isinstance(t, dict) else t for t in items]

    total = len(items)
    start = (page - 1) * size
    end = start + size
    return {
        "kind": kind,
        "status": status,
        "items": items[start:end],
        "total": total,
        "page": page,
        "size": size,
        "has_more": end < total,
    }


def _json_for_html_script(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


@lru_cache(maxsize=1)
def _load_echarts_js_for_html() -> str:
    """读取本地 ECharts 构建产物，供导出 HTML 内嵌（离线可打开）。"""
    backend_root = Path(__file__).resolve().parents[3]
    candidates = [
        backend_root / "static" / "vendor" / "echarts.min.js",
        backend_root.parent / "frontend" / "node_modules" / "echarts" / "dist" / "echarts.min.js",
    ]
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8").replace("</", "<\\/")
    return ""


def _render_echarts_script_tag(*, embed: bool = True) -> str:
    """生成 ECharts 脚本标签。

    embed=True：内嵌本地 JS（离线打开可用，体积约 1MB，适合本地下载导出）。
    embed=False：走 CDN（邮件附件更小，降低企业邮拦截概率）。
    """
    if embed:
        js = _load_echarts_js_for_html()
        if js:
            return f"  <script>\n{js}\n  </script>"
    return '  <script src="https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js"></script>'


def _h(val: Any) -> str:
    if val is None:
        return ""
    return html_module.escape(str(val))


def _fmt_cell(val: Any) -> str:
    if val is None or val == "":
        return "-"
    if isinstance(val, float):
        return _h(round(val, 3))
    return _h(val)


def _fmt_stream_detail_cell(header: str, val: Any) -> str:
    if val is None or val == "":
        return "-"
    if header in _STREAM_DETAIL_TEXT_COLS:
        text = str(val)
        return f'<pre class="stream-cell-pre">{_h(text)}</pre>'
    if isinstance(val, float):
        return _h(round(val, 3))
    return _h(val)


_STREAM_DETAIL_TEXT_COLS = frozenset({
    "问题", "答案预览", "思考过程", "参考文件", "错误信息",
    "参考资料(全部)", "参考资料(高分)",
})


def _stream_detail_col_class(header: str) -> str:
    if header in _STREAM_DETAIL_TEXT_COLS:
        return "col-text"
    if header.endswith("(s)") or header in {"序号", "用户ID", "是否成功", "响应状态码", "答案长度", "会话ID"}:
        return "col-narrow"
    if "时间" in header:
        return "col-time"
    return "col-narrow"


def _render_trace_detail_html(item: dict) -> str:
    """HTTP/流式 trace 的请求响应详情块（HTML 导出用）。"""
    from app.modules.perf.perf_trace import sanitize_trace_item

    item = sanitize_trace_item(item) if isinstance(item, dict) else item
    blocks: list[str] = []

    def _val(full_key: str, preview_key: str) -> str:
        v = item.get(full_key)
        if v not in (None, ""):
            return str(v)
        return str(item.get(preview_key) or "")

    for label, full_key, preview_key in (
        ("请求头", "request_headers", "request_headers_preview"),
        ("Query 参数", "request_params", "request_params_preview"),
        ("请求 Body", "request_body", "request_body_preview"),
        ("响应头", "response_headers", "response_headers"),
        ("响应 / 流式内容（解析后的正式回答）", "response_body_preview", "response_body_preview"),
        ("思考过程", "thinking_preview", "thinking_preview"),
        ("原始 SSE", "raw_sse_preview", "raw_sse_preview"),
    ):
        val = _val(full_key, preview_key)
        if val:
            blocks.append(
                f'<div class="trace-block"><div class="trace-label">{_h(label)}</div>'
                f'<pre class="trace-pre trace-pre-full">{_h(val)}</pre></div>'
            )
    err = item.get("error_msg")
    if err:
        blocks.append(
            f'<div class="trace-block"><div class="trace-label">错误信息</div>'
            f'<pre class="trace-pre error-cell">{_h(err)}</pre></div>'
        )
    if not blocks:
        return ""
    return f'<details class="trace-details"><summary>请求/响应详情</summary>{"".join(blocks)}</details>'


def _http_trace_items_for_export(record: Any, *, max_rows: int = 500) -> tuple[list[dict], bool]:
    """合并成功 trace 与失败采样，供 HTML 导出（与 Web 报告 HTTP 明细一致）。"""
    from app.modules.perf.perf_trace import sanitize_trace_item

    bd = record.error_breakdown or {}
    if not isinstance(bd, dict):
        return [], False
    traces = list(bd.get("request_traces") or [])
    failures = list(bd.get("failed_samples") or [])
    combined = [sanitize_trace_item(x) if isinstance(x, dict) else x for x in (traces + failures)]
    truncated = len(combined) > max_rows
    return combined[:max_rows], truncated


def render_perf_html_status_codes(record: Any) -> str:
    """HTTP 状态码分布（有数据时才输出）。"""
    raw_breakdown = record.error_breakdown or {}
    if not isinstance(raw_breakdown, dict):
        return ""
    dist = raw_breakdown.get("status_code_distribution") or {}
    if not dist:
        return ""
    total = int(record.total_requests or 0) or sum(int(v) for v in dist.values())
    normalized = normalize_status_code_distribution(dist, total)
    if not normalized:
        return ""
    rows = ""
    for code, count in sorted(normalized.items(), key=lambda x: (-x[1], x[0])):
        pct = round(int(count) / total * 100, 2) if total > 0 else 0
        rows += f"<tr><td>{_h(code)}</td><td>{count}</td><td>{pct}%</td></tr>"
    return f"""
  <div class="section">
    <h2>HTTP 状态码分布</h2>
    <table>
      <thead><tr><th>状态码</th><th>次数</th><th>占比</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>"""


def render_perf_html_errors(record: Any) -> str:
    """错误分类统计（失败样本详情改由 HTTP 请求明细区块展示，避免重复）。"""
    bd = record.error_breakdown or {}
    if not isinstance(bd, dict):
        return ""
    by_type = {k: v for k, v in (bd.get("by_type") or {}).items() if v}
    if not by_type:
        return ""

    type_map = {
        "timeout": "请求超时", "connection_error": "连接错误", "network_error": "网络错误",
        "server_error": "服务端错误(5xx)", "client_error": "客户端错误(4xx)",
        "assertion_failed": "断言失败", "unknown": "未知错误",
    }
    total_fail = record.fail_count or sum(by_type.values()) or 1
    err_type_rows = ""
    for etype, count in sorted(by_type.items(), key=lambda x: -x[1]):
        pct = round(count / total_fail * 100, 1) if total_fail > 0 else 0
        err_type_rows += f"<tr><td>{_h(type_map.get(etype, etype))}</td><td>{count}</td><td>{pct}%</td></tr>"
    return f"""
  <div class="section">
    <h2>错误分类统计</h2>
    <table>
      <thead><tr><th>错误类型</th><th>次数</th><th>占比</th></tr></thead>
      <tbody>{err_type_rows}</tbody>
    </table>
  </div>"""


def render_perf_html_request_traces(record: Any, *, max_rows: int = 500) -> str:
    """HTTP 请求明细（含成功 trace 与失败采样，通用请求/响应字段）。"""
    items, truncated = _http_trace_items_for_export(record, max_rows=max_rows)
    if not items:
        return ""
    rows = ""
    for idx, t in enumerate(items, 1):
        ok = "否" if t.get("success") is False else "是"
        rows += f"""
        <tr>
            <td>{idx}</td>
            <td>{_h(t.get('case_name', '未知'))}</td>
            <td>{ok}</td>
            <td>{_h(t.get('user_id', '') or '-')}</td>
            <td>{_h(t.get('method', '') or '-')}</td>
            <td class="col-text">{_h(t.get('url', '') or '-')}</td>
            <td>{_h(t.get('status_code', 0))}</td>
            <td>{round(float(t.get('response_time', 0) or 0), 2)} ms</td>
        </tr>"""
        detail = _render_trace_detail_html(t)
        if detail:
            rows += f'<tr class="trace-detail-row"><td colspan="8">{detail}</td></tr>'
    note = f"<p class=\"chart-hint\">仅展示前 {max_rows} 条</p>" if truncated else ""
    return f"""
  <div class="section">
    <h2>HTTP 请求明细（前{len(items)}条）</h2>
    <p class="chart-hint">含详细模式成功请求与失败采样；点击「请求/响应详情」展开请求头、Body、响应等信息。</p>
    <div class="table-scroll">
      <table>
        <thead><tr><th>#</th><th>用例名称</th><th>成功</th><th>用户ID</th><th>方法</th><th>URL</th><th>状态码</th><th>响应时间</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    {note}
  </div>"""


def render_perf_html_stream_sections(record: Any, *, max_detail_rows: int = 500) -> str:
    """流式阶段汇总 + 逐路请求明细（仅当次配置走流式执行时输出）。"""
    from app.modules.stream_phase import detail_to_excel_row, migrate_legacy_detail
    from app.modules.stream_phase.contract import use_stream_execution

    cfg = getattr(record, "config_snapshot", None) or {}
    if not isinstance(cfg, dict):
        cfg = {}
    # 与 Web 报告一致：未开流式（无 stream_profile / 非 stream_burst）不展示 SSE 区
    if not use_stream_execution(cfg):
        return ""

    details = [migrate_legacy_detail(d) for d in (record.request_details or [])]
    phase_metrics = record.phase_metrics or {}
    metrics = phase_metrics.get("metrics") or []
    if not details and not metrics:
        return ""

    profile = cfg.get("stream_profile") or {}
    if not isinstance(profile, dict):
        profile = {}
    raw_hl = profile.get("report_highlight_phases") or []
    highlight_keys = {
        str(k).strip()
        for k in (raw_hl if isinstance(raw_hl, list) else [])
        if k is not None and str(k).strip()
    }

    parts: list[str] = []
    if metrics:
        # 摘要卡片：着重项置顶
        ordered = list(metrics)
        if highlight_keys:
            top = [m for m in ordered if (m.get("key") or "") in highlight_keys]
            rest = [m for m in ordered if (m.get("key") or "") not in highlight_keys]
            ordered = top + rest

        cards_html = ""
        for m in ordered:
            key = m.get("key") or ""
            hl = key in highlight_keys
            hl_cls = " highlight" if hl else ""
            hl_tag = '<span class="tag tag-orange">着重</span>' if hl else ""
            cards_html += f"""
      <div class="summary-card phase-metric-card{hl_cls}">
        <div class="label">{_h(m.get('label') or key)} {hl_tag}</div>
        <div class="value">{_fmt_cell(m.get('mean'))}<span class="unit">s 均值</span></div>
        <div class="note">P95 {_fmt_cell(m.get('p95'))}s · n={_h(m.get('normal_count', ''))}</div>
      </div>"""

        # CSS 横向条：均值 / P95，相对本批最大值归一化
        def _num(v: Any) -> Optional[float]:
            if isinstance(v, (int, float)):
                return float(v)
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        max_v = 0.0
        for m in metrics:
            for k in ("mean", "p95"):
                n = _num(m.get(k))
                if n is not None and n > max_v:
                    max_v = n
        max_v = max_v or 1.0

        bars_html = ""
        for m in metrics:
            label = _h(m.get("label") or m.get("key") or "")
            mean_n = _num(m.get("mean"))
            p95_n = _num(m.get("p95"))
            mean_pct = max(4, int(round((mean_n or 0) / max_v * 100))) if mean_n is not None else 0
            p95_pct = max(4, int(round((p95_n or 0) / max_v * 100))) if p95_n is not None else 0
            mean_fill = (
                f'<div class="bar-fill blue" style="width:{mean_pct}%">{_fmt_cell(mean_n)}s</div>'
                if mean_n is not None else ""
            )
            p95_fill = (
                f'<div class="bar-fill orange" style="width:{p95_pct}%">{_fmt_cell(p95_n)}s</div>'
                if p95_n is not None else ""
            )
            bars_html += f"""
      <div class="chart-bar">
        <div class="bar-label">{label}<br><span style="color:#94a3b8;font-size:11px">均值</span></div>
        <div class="bar-track">{mean_fill}</div>
      </div>
      <div class="chart-bar">
        <div class="bar-label"><span style="color:#94a3b8;font-size:11px">P95</span></div>
        <div class="bar-track">{p95_fill}</div>
      </div>"""

        metric_rows = ""
        for m in metrics:
            metric_rows += f"""
        <tr>
            <td>{_h(m.get('label', ''))}</td>
            <td>{_h(m.get('normal_count', ''))}</td>
            <td>{_fmt_cell(m.get('mean'))}</td>
            <td>{_fmt_cell(m.get('median'))}</td>
            <td>{_fmt_cell(m.get('p90'))}</td>
            <td>{_fmt_cell(m.get('p95'))}</td>
            <td>{_fmt_cell(m.get('p99'))}</td>
            <td>{_fmt_cell(m.get('min'))}</td>
            <td>{_fmt_cell(m.get('max'))}</td>
        </tr>"""
        fail_count = phase_metrics.get("fail_count", 0)
        total_requests = phase_metrics.get("total_requests", len(details))
        error_rate = phase_metrics.get("error_rate", 0)
        parts.append(f"""
  <div class="section">
    <h2>SSE 阶段指标摘要</h2>
    <p class="chart-hint" style="text-align:left;margin-bottom:12px;">按解析配置中的阶段规则与派生指标生成；蓝色=均值，橙色=P95。</p>
    <div class="summary-grid">{cards_html}
    </div>
    <h3>阶段对比（均值 / P95）</h3>
    {bars_html}
  </div>
  <div class="section">
    <h2>SSE 阶段计时汇总（正常请求）</h2>
    <table>
      <thead><tr><th>指标</th><th>正常请求数</th><th>平均(s)</th><th>中位数(s)</th><th>P90(s)</th><th>P95(s)</th><th>P99(s)</th><th>最小(s)</th><th>最大(s)</th></tr></thead>
      <tbody>{metric_rows}</tbody>
    </table>
    <p class="chart-hint">异常率 {error_rate}%（{fail_count}/{total_requests} 未满足成功判定）</p>
  </div>""")

    if details:
        detail_rows_data = [detail_to_excel_row(i, d) for i, d in enumerate(details, 1)]
        truncated = len(detail_rows_data) > max_detail_rows
        if truncated:
            detail_rows_data = detail_rows_data[:max_detail_rows]
        headers = list(detail_rows_data[0].keys()) if detail_rows_data else []
        header_html = "".join(
            f'<th class="{_stream_detail_col_class(h)}">{_h(h)}</th>' for h in headers
        )
        body_html = ""
        for row in detail_rows_data:
            cells = "".join(
                f'<td class="{_stream_detail_col_class(h)}">{_fmt_stream_detail_cell(h, row.get(h))}</td>'
                for h in headers
            )
            body_html += f"<tr>{cells}</tr>"
        note = f"<p class=\"chart-hint\">仅展示前 {max_detail_rows} 条明细</p>" if truncated else ""
        parts.append(f"""
  <div class="section">
    <h2>流式请求阶段明细</h2>
    <p class="chart-hint" style="margin-bottom:12px;">列较多时可左右滑动查看；长文本列完整展示，可上下滚动阅读。</p>
    <div class="table-scroll stream-detail-scroll">
      <table class="stream-detail-table">
        <thead><tr>{header_html}</tr></thead>
        <tbody>{body_html}</tbody>
      </table>
    </div>
    {note}
  </div>""")
    return "".join(parts)


def render_perf_html_chart_parts(
    record: Any,
    *,
    prefix: str = "",
    trend_heading: str = "性能趋势",
    hist_heading: str = "响应时间分布",
    include_echarts: bool = True,
    embed_echarts: bool = True,
    ai_trend_note: str = "",
    ai_dist_note: str = "",
) -> tuple[str, str]:
    """导出 HTML 报告用：ECharts 趋势图 + RT 分布图。

    返回 (图表区块 HTML, 页脚脚本 HTML)。默认内嵌 ECharts，导出文件可离线打开；
    脚本置于文档末尾，不阻塞上方表格渲染。

    prefix: 多记录同页时用于区分 DOM id（如 ``rec37``）。
    include_echarts: 同页多个图表时仅第一次为 True，避免重复内嵌库。
    embed_echarts: False 时用 CDN，显著减小邮件附件体积。
    """
    from types import SimpleNamespace

    if isinstance(record, dict):
        hist = record.get("rt_histogram") or []
        if not hist:
            eb = record.get("error_breakdown") or {}
            if isinstance(eb, dict):
                hist = eb.get("rt_histogram") or []
        record = SimpleNamespace(
            time_series_data=record.get("time_series_data") or [],
            qps=record.get("qps"),
            p95_response_time=record.get("p95_response_time"),
            error_breakdown={"rt_histogram": hist},
        )

    time_series = normalize_time_series_for_chart(
        getattr(record, "time_series_data", None) or [],
        overall_p95=getattr(record, "p95_response_time", None),
    )
    raw_breakdown = getattr(record, "error_breakdown", None) or {}
    rt_histogram = raw_breakdown.get("rt_histogram") if isinstance(raw_breakdown, dict) else None
    rt_histogram = rt_histogram or []

    if not time_series and not rt_histogram:
        return "", ""

    pid = (prefix or "").strip()
    sid = f"-{pid}" if pid else ""
    data_id = f"perf-chart-data{sid}"
    trend_id = f"perfTrendChart{sid}"
    hist_wrap_id = f"histogramSectionWrap{sid}"
    hist_id = f"perfHistogramChart{sid}"

    chart_payload = _json_for_html_script({
        "timeSeries": time_series,
        "summaryQps": getattr(record, "qps", None),
        "summaryP95": getattr(record, "p95_response_time", None),
        "histogram": rt_histogram,
    })

    trend_note_html = (
        f'<p class="chart-ai-note">{_escape_html(ai_trend_note)}</p>' if (ai_trend_note or "").strip() else ""
    )
    dist_note_html = (
        f'<p class="chart-ai-note">{_escape_html(ai_dist_note)}</p>' if (ai_dist_note or "").strip() else ""
    )

    zoom_modal_id = f"perfChartZoomModal{sid}"
    zoom_title_id = f"perfChartZoomTitle{sid}"
    zoom_box_id = f"perfChartZoomBox{sid}"
    zoom_close_id = f"perfChartZoomClose{sid}"

    trend_section = ""
    if time_series:
        trend_section = f"""
  <div class="section" id="perfTrendSection{sid}" contenteditable="false">
    <h2>{_escape_html(trend_heading)}</h2>
    {trend_note_html}
    <div class="chart-toolbar">
      <button type="button" id="perfTrendEnlarge{sid}" class="chart-enlarge-btn">放大</button>
    </div>
    <div id="{trend_id}" class="chart-box" contenteditable="false"></div>
    <p class="chart-hint">柱状图为该秒瞬时 QPS；折线为响应时间与错误率。空闲秒不标 RT，折线连续跨过。可拖拽/滚轮缩放，点「放大」全屏查看。</p>
  </div>"""

    hist_section = ""
    if rt_histogram:
        hist_section = f"""
  <div class="section" id="{hist_wrap_id}" contenteditable="false">
    <h2>{_escape_html(hist_heading)}</h2>
    {dist_note_html}
    <div id="histogramSection{sid}">
    <div class="chart-toolbar">
      <button type="button" id="perfHistEnlarge{sid}" class="chart-enlarge-btn">放大</button>
    </div>
    <div id="{hist_id}" class="chart-box" contenteditable="false"></div>
    </div>
  </div>"""

    zoom_modal = f"""
  <div id="{zoom_modal_id}" class="chart-zoom-modal" contenteditable="false">
    <div class="chart-zoom-panel">
      <div class="chart-zoom-head">
        <div id="{zoom_title_id}" class="chart-zoom-title">图表放大</div>
        <button type="button" id="{zoom_close_id}" class="chart-zoom-close" aria-label="关闭">×</button>
      </div>
      <div id="{zoom_box_id}" class="chart-zoom-box"></div>
    </div>
  </div>"""

    sections = trend_section + hist_section + zoom_modal

    echarts_tag = _render_echarts_script_tag(embed=embed_echarts) if include_echarts else ""
    scripts = f"""
  <script type="application/json" id="{data_id}">{chart_payload}</script>
{echarts_tag}
  <script>
  (function () {{
    var DATA_ID = {json.dumps(data_id)};
    var TREND_ID = {json.dumps(trend_id)};
    var HIST_WRAP_ID = {json.dumps(hist_wrap_id)};
    var HIST_ID = {json.dumps(hist_id)};
    var ZOOM_MODAL_ID = {json.dumps(zoom_modal_id)};
    var ZOOM_TITLE_ID = {json.dumps(zoom_title_id)};
    var ZOOM_BOX_ID = {json.dumps(zoom_box_id)};
    var ZOOM_CLOSE_ID = {json.dumps(zoom_close_id)};
    var TREND_HEADING = {json.dumps(trend_heading)};
    var HIST_HEADING = {json.dumps(hist_heading)};
    var HAS_TREND = {json.dumps(bool(time_series))};
    var HAS_HIST = {json.dumps(bool(rt_histogram))};
    var optionBuilders = {{}};
    var zoomChart = null;
    function readData() {{
      var el = document.getElementById(DATA_ID);
      if (!el) return null;
      try {{ return JSON.parse(el.textContent || ''); }} catch (e) {{ return null; }}
    }}
    function dataZoomOpts(bottom) {{
      return [
        {{ type: 'inside', xAxisIndex: 0, filterMode: 'none' }},
        {{
          type: 'slider', xAxisIndex: 0, height: 18, bottom: bottom || 8,
          borderColor: '#e2e8f0', fillerColor: 'rgba(84,112,198,.15)', handleSize: '80%'
        }}
      ];
    }}
    function showChartError(msg) {{
      var el = document.getElementById(TREND_ID) || document.getElementById(HIST_ID);
      if (!el || el.getAttribute('data-chart-error')) return;
      el.setAttribute('data-chart-error', '1');
      el.innerHTML = '<p style="color:#999;text-align:center;padding:40px 0;">' + msg + '</p>';
    }}
    function buildTrendOption(data, enlarged) {{
      var ts = data.timeSeries || [];
      var xData = ts.map(function(d) {{ return (d.timestamp || 0) + 's'; }});
      var qpsData = ts.map(function(d) {{ return d.qps; }});
      var avgRtData = ts.map(function(d) {{
        if (!d.qps || d.qps <= 0) return null;
        return d.avg_rt != null ? d.avg_rt : null;
      }});
      var p95RtData = ts.map(function(d) {{
        if (!d.qps || d.qps <= 0) return null;
        if (d.p95_rt != null) return d.p95_rt;
        return d.avg_rt != null ? d.avg_rt : null;
      }});
      var usersData = ts.map(function(d) {{ return d.active_users; }});
      var errorRateData = ts.map(function(d) {{ return d.error_rate || 0; }});
      var p95MarkLine = data.summaryP95 != null ? {{
        silent: true,
        symbol: 'none',
        lineStyle: {{ type: 'dotted', color: '#c9a227', opacity: 0.75 }},
        label: {{ formatter: '全程 P95: ' + data.summaryP95 + ' ms', position: 'insideEndTop', color: '#c9a227' }},
        data: [{{ yAxis: data.summaryP95 }}]
      }} : undefined;
      return {{
        tooltip: {{
          trigger: 'axis',
          axisPointer: {{ type: 'cross' }},
          formatter: function(params) {{
            if (!params || !params.length) return '';
            var idx = params[0].dataIndex;
            var point = ts[idx] || {{}};
            var lines = [params[0].axisValue];
            if (!point.qps || point.qps <= 0) {{
              lines.push('<span style="color:#909399">该秒无完成请求</span>');
            }}
            params.forEach(function(p) {{
              var val = p.value;
              if (val == null || val === '-') {{
                lines.push(p.marker + p.seriesName + ': —');
                return;
              }}
              if (p.seriesName === 'QPS') val = val + '（该秒瞬时）';
              else if (String(p.seriesName).indexOf('P95') >= 0 || String(p.seriesName).indexOf('RT') >= 0) val = val + ' ms';
              else if (p.seriesName === '错误率') val = val + '%';
              lines.push(p.marker + p.seriesName + ': ' + val);
            }});
            if (data.summaryQps != null) lines.push('<span style="color:#909399">全程平均 QPS: ' + data.summaryQps + '</span>');
            if (data.summaryP95 != null) lines.push('<span style="color:#909399">全程 P95 RT: ' + data.summaryP95 + ' ms</span>');
            return lines.join('<br/>');
          }}
        }},
        legend: {{ data: ['QPS', '平均RT', 'P95 RT', '错误率', '并发用户数'], bottom: enlarged ? 42 : 28 }},
        grid: {{ left: '3%', right: '4%', bottom: enlarged ? '18%' : '20%', top: '10%', containLabel: true }},
        dataZoom: dataZoomOpts(enlarged ? 28 : 8),
        xAxis: {{ type: 'category', boundaryGap: true, data: xData, name: '时间(秒)' }},
        yAxis: [
          {{ type: 'value', name: '响应时间(ms)', position: 'left' }},
          {{ type: 'value', name: 'QPS', position: 'right' }}
        ],
        series: [
          {{ name: 'QPS', type: 'bar', yAxisIndex: 1, data: qpsData, itemStyle: {{ color: '#91cc75', opacity: 0.7 }}, barMaxWidth: 20 }},
          {{ name: '平均RT', type: 'line', yAxisIndex: 0, data: avgRtData, connectNulls: true, showSymbol: false, smooth: true, itemStyle: {{ color: '#5470c6' }} }},
          {{ name: 'P95 RT', type: 'line', yAxisIndex: 0, data: p95RtData, connectNulls: true, showSymbol: false, smooth: true, itemStyle: {{ color: '#fac858' }}, lineStyle: {{ type: 'dashed' }}, markLine: p95MarkLine }},
          {{ name: '错误率', type: 'line', yAxisIndex: 1, data: errorRateData, connectNulls: true, showSymbol: false, smooth: true, itemStyle: {{ color: '#e6a23c' }} }},
          {{ name: '并发用户数', type: 'line', yAxisIndex: 1, data: usersData, connectNulls: true, showSymbol: false, smooth: true, itemStyle: {{ color: '#ee6666' }}, lineStyle: {{ type: 'dotted' }} }}
        ]
      }};
    }}
    function buildHistOption(data, enlarged) {{
      var hist = (data.histogram || []).slice().sort(function(a, b) {{ return (a.min || 0) - (b.min || 0); }});
      return {{
        tooltip: {{ trigger: 'axis' }},
        grid: {{ left: '3%', right: '4%', bottom: enlarged ? '16%' : '18%', containLabel: true }},
        dataZoom: dataZoomOpts(enlarged ? 28 : 8),
        xAxis: {{ type: 'category', data: hist.map(function(h) {{ return h.label + ' ms'; }}), axisLabel: {{ rotate: 35, fontSize: 11 }} }},
        yAxis: {{ type: 'value', name: '请求数' }},
        series: [{{ name: '请求数', type: 'bar', data: hist.map(function(h) {{ return h.count; }}), itemStyle: {{ color: '#5470c6', opacity: 0.85 }}, barMaxWidth: 40 }}]
      }};
    }}
    function initTrend(data) {{
      if (!HAS_TREND) return;
      var el = document.getElementById(TREND_ID);
      if (!el || !window.echarts || !data.timeSeries || !data.timeSeries.length) return;
      var chart = echarts.init(el);
      optionBuilders.trend = function(enlarged) {{ return buildTrendOption(data, !!enlarged); }};
      chart.setOption(optionBuilders.trend(false));
      window.addEventListener('resize', function() {{ chart.resize(); }});
    }}
    function initHistogram(data) {{
      if (!HAS_HIST) return;
      var hist = data.histogram || [];
      if (!hist.length || !window.echarts) return;
      var el = document.getElementById(HIST_ID);
      if (!el) return;
      var chart = echarts.init(el);
      optionBuilders.hist = function(enlarged) {{ return buildHistOption(data, !!enlarged); }};
      chart.setOption(optionBuilders.hist(false));
      window.addEventListener('resize', function() {{ chart.resize(); }});
    }}
    function closeZoom() {{
      var modal = document.getElementById(ZOOM_MODAL_ID);
      if (modal) modal.classList.remove('is-open');
      if (zoomChart) {{
        zoomChart.dispose();
        zoomChart = null;
      }}
    }}
    function openZoom(kind) {{
      var builder = optionBuilders[kind];
      if (!builder || !window.echarts) return;
      var modal = document.getElementById(ZOOM_MODAL_ID);
      var title = document.getElementById(ZOOM_TITLE_ID);
      var box = document.getElementById(ZOOM_BOX_ID);
      if (!modal || !box) return;
      if (title) title.textContent = kind === 'hist' ? HIST_HEADING : TREND_HEADING;
      if (zoomChart) {{
        zoomChart.dispose();
        zoomChart = null;
      }}
      modal.classList.add('is-open');
      zoomChart = echarts.init(box);
      zoomChart.setOption(builder(true));
      setTimeout(function() {{ if (zoomChart) zoomChart.resize(); }}, 0);
    }}
    function bindZoomUi() {{
      var trendBtn = document.getElementById('perfTrendEnlarge' + {json.dumps(sid)});
      var histBtn = document.getElementById('perfHistEnlarge' + {json.dumps(sid)});
      if (trendBtn) trendBtn.addEventListener('click', function() {{ openZoom('trend'); }});
      if (histBtn) histBtn.addEventListener('click', function() {{ openZoom('hist'); }});
      var closeBtn = document.getElementById(ZOOM_CLOSE_ID);
      var modal = document.getElementById(ZOOM_MODAL_ID);
      if (closeBtn) closeBtn.addEventListener('click', closeZoom);
      if (modal) {{
        modal.addEventListener('click', function(e) {{
          if (e.target === modal) closeZoom();
        }});
      }}
      window.addEventListener('keydown', function(e) {{
        if (e.key === 'Escape') closeZoom();
      }});
    }}
    function boot() {{
      try {{
        if (!window.echarts) {{
          showChartError('图表库加载失败，请重新导出报告或联系管理员检查服务端静态资源。');
          return;
        }}
        var data = readData();
        if (!data) return;
        initTrend(data);
        initHistogram(data);
        bindZoomUi();
      }} catch (e) {{
        showChartError('图表渲染失败：' + (e && e.message ? e.message : '未知错误'));
      }}
    }}
    if (document.readyState === 'loading') {{
      document.addEventListener('DOMContentLoaded', boot);
    }} else {{
      boot();
    }}
  }})();
  </script>"""

    return sections, scripts


_OVERLAY_COLORS = (
    "#1a73e8",
    "#dd6b20",
    "#38a169",
    "#805ad5",
    "#e53e3e",
    "#319795",
    "#d69e2e",
    "#3182ce",
    "#c53030",
    "#2b6cb0",
)


def render_compare_overlay_charts(
    records: list,
    *,
    labels: Optional[list] = None,
    heading: str = "统计图对比",
    include_echarts: bool = True,
) -> tuple[str, str]:
    """多轮压测叠加对比图：QPS / 平均 RT / P95 / 响应时间分布。

    时序按相对秒对齐；分布按桶标签并排柱状。返回 (HTML, scripts)。
    """
    if not records or len(records) < 2:
        return "", ""

    series_meta: list[dict] = []
    all_ts: set[int] = set()
    bucket_order: list[str] = []
    bucket_seen: set[str] = set()

    for i, rec in enumerate(records):
        if isinstance(rec, dict):
            ts_raw = rec.get("time_series_data") or []
            hist = rec.get("rt_histogram") or []
            if not hist:
                eb = rec.get("error_breakdown") or {}
                if isinstance(eb, dict):
                    hist = eb.get("rt_histogram") or []
            p95 = rec.get("p95_response_time")
            label = (labels[i] if labels and i < len(labels) else None) or (
                rec.get("display_name") or rec.get("scene_name") or f"#{rec.get('id', i + 1)}"
            )
        else:
            ts_raw = getattr(rec, "time_series_data", None) or []
            eb = getattr(rec, "error_breakdown", None) or {}
            hist = eb.get("rt_histogram") if isinstance(eb, dict) else []
            hist = hist or []
            p95 = getattr(rec, "p95_response_time", None)
            label = (labels[i] if labels and i < len(labels) else None) or f"执行{i + 1}"

        ts = normalize_time_series_for_chart(ts_raw, overall_p95=p95)
        by_t: dict[int, dict] = {}
        for p in ts:
            try:
                t = int(p.get("timestamp") or 0)
            except (TypeError, ValueError):
                continue
            by_t[t] = p
            all_ts.add(t)

        hist_map: dict[str, int] = {}
        for b in hist or []:
            if not isinstance(b, dict):
                continue
            lab = str(b.get("label") or "").strip() or "?"
            try:
                cnt = int(b.get("count") or 0)
            except (TypeError, ValueError):
                cnt = 0
            hist_map[lab] = cnt
            if lab not in bucket_seen:
                bucket_seen.add(lab)
                bucket_order.append(lab)

        series_meta.append({
            "label": str(label),
            "color": _OVERLAY_COLORS[i % len(_OVERLAY_COLORS)],
            "by_t": by_t,
            "hist": hist_map,
        })

    if not all_ts and not bucket_order:
        return "", ""

    x_ts = sorted(all_ts)
    x_labels = [f"{t}s" for t in x_ts]

    rounds_payload = []
    for m in series_meta:
        qps, avg_rt, p95_rt = [], [], []
        for t in x_ts:
            p = m["by_t"].get(t) or {}
            qps.append(p.get("qps") if p else None)
            if p and float(p.get("qps") or 0) > 0:
                avg_rt.append(p.get("avg_rt"))
                p95_rt.append(p.get("p95_rt") if p.get("p95_rt") is not None else p.get("avg_rt"))
            else:
                avg_rt.append(None)
                p95_rt.append(None)
        hist_counts = [m["hist"].get(lab, 0) for lab in bucket_order]
        rounds_payload.append({
            "label": m["label"],
            "color": m["color"],
            "qps": qps,
            "avg_rt": avg_rt,
            "p95_rt": p95_rt,
            "hist": hist_counts,
        })

    payload = {
        "x": x_labels,
        "buckets": [f"{b} ms" for b in bucket_order],
        "rounds": rounds_payload,
    }
    data_id = "perf-overlay-chart-data"
    chart_payload = _json_for_html_script(payload)
    has_trend = bool(x_ts)
    has_hist = bool(bucket_order)

    parts = [
        f'<div class="section" id="overlayCompareSection" contenteditable="false">',
        f"<h2>{_escape_html(heading)}</h2>",
        '<p class="compare-intro">将各轮时序对齐到相对时间轴（秒），QPS / 平均 RT / P95 与响应时间分布叠在同图对比；'
        "图例可点击隐藏某轮。可拖拽/滚轮缩放，点「放大」全屏查看。各轮独立画像仍见上文分章。</p>",
    ]
    if has_trend:
        parts.append("<h3>QPS 趋势对比</h3>")
        parts.append(
            '<div class="chart-toolbar">'
            '<button type="button" class="chart-enlarge-btn" data-overlay-kind="qps">放大</button>'
            "</div>"
        )
        parts.append('<div id="overlayQpsChart" class="chart-box" contenteditable="false"></div>')
        parts.append("<h3>平均响应时间对比</h3>")
        parts.append(
            '<div class="chart-toolbar">'
            '<button type="button" class="chart-enlarge-btn" data-overlay-kind="avg_rt">放大</button>'
            "</div>"
        )
        parts.append('<div id="overlayAvgRtChart" class="chart-box" contenteditable="false"></div>')
        parts.append("<h3>P95 响应时间对比</h3>")
        parts.append(
            '<div class="chart-toolbar">'
            '<button type="button" class="chart-enlarge-btn" data-overlay-kind="p95_rt">放大</button>'
            "</div>"
        )
        parts.append('<div id="overlayP95Chart" class="chart-box" contenteditable="false"></div>')
    if has_hist:
        parts.append("<h3>响应时间分布对比</h3>")
        parts.append(
            '<div class="chart-toolbar">'
            '<button type="button" class="chart-enlarge-btn" data-overlay-kind="hist">放大</button>'
            "</div>"
        )
        parts.append('<div id="overlayHistChart" class="chart-box" contenteditable="false"></div>')
        parts.append(
            '<p class="chart-hint">分布图按耗时区间统计请求个数；柱越高表示该区间请求越多。可缩放与放大查看。</p>'
        )
    parts.append(
        '<div id="overlayChartZoomModal" class="chart-zoom-modal" contenteditable="false">'
        '<div class="chart-zoom-panel">'
        '<div class="chart-zoom-head">'
        '<div id="overlayChartZoomTitle" class="chart-zoom-title">图表放大</div>'
        '<button type="button" id="overlayChartZoomClose" class="chart-zoom-close" aria-label="关闭">×</button>'
        "</div>"
        '<div id="overlayChartZoomBox" class="chart-zoom-box"></div>'
        "</div></div>"
    )
    parts.append("</div>")
    sections = "\n".join(parts)

    echarts_tag = _render_echarts_script_tag(embed=embed_echarts) if include_echarts else ""
    scripts = f"""
  <script type="application/json" id="{data_id}">{chart_payload}</script>
{echarts_tag}
  <script>
  (function () {{
    var DATA_ID = {json.dumps(data_id)};
    var HAS_TREND = {json.dumps(has_trend)};
    var HAS_HIST = {json.dumps(has_hist)};
    var optionBuilders = {{}};
    var zoomChart = null;
    var TITLES = {{
      qps: 'QPS 趋势对比',
      avg_rt: '平均响应时间对比',
      p95_rt: 'P95 响应时间对比',
      hist: '响应时间分布对比'
    }};
    function readData() {{
      var el = document.getElementById(DATA_ID);
      if (!el) return null;
      try {{ return JSON.parse(el.textContent || ''); }} catch (e) {{ return null; }}
    }}
    function dataZoomOpts(bottom) {{
      return [
        {{ type: 'inside', xAxisIndex: 0, filterMode: 'none' }},
        {{
          type: 'slider', xAxisIndex: 0, height: 18, bottom: bottom || 28,
          borderColor: '#e2e8f0', fillerColor: 'rgba(49,130,206,.15)', handleSize: '80%'
        }}
      ];
    }}
    function lineSeries(rounds, field) {{
      return (rounds || []).map(function(r) {{
        return {{
          name: r.label,
          type: 'line',
          showSymbol: false,
          smooth: true,
          connectNulls: true,
          data: r[field] || [],
          itemStyle: {{ color: r.color }},
          lineStyle: {{ width: 2, color: r.color }}
        }};
      }});
    }}
    function buildLineOption(rounds, field, yName, xData, enlarged) {{
      return {{
        tooltip: {{ trigger: 'axis' }},
        legend: {{ type: 'scroll', bottom: enlarged ? 42 : 28 }},
        grid: {{ left: '3%', right: '4%', bottom: enlarged ? '18%' : '20%', containLabel: true }},
        dataZoom: dataZoomOpts(enlarged ? 28 : 8),
        xAxis: {{ type: 'category', data: xData, boundaryGap: false }},
        yAxis: {{ type: 'value', name: yName, scale: true }},
        series: lineSeries(rounds, field)
      }};
    }}
    function buildHistOption(data, enlarged) {{
      var series = (data.rounds || []).map(function(r) {{
        return {{
          name: r.label,
          type: 'bar',
          data: r.hist || [],
          itemStyle: {{ color: r.color, opacity: 0.85 }},
          barMaxWidth: 28
        }};
      }});
      return {{
        tooltip: {{ trigger: 'axis' }},
        legend: {{ type: 'scroll', bottom: enlarged ? 42 : 28 }},
        grid: {{ left: '3%', right: '4%', bottom: enlarged ? '18%' : '22%', containLabel: true }},
        dataZoom: dataZoomOpts(enlarged ? 28 : 8),
        xAxis: {{ type: 'category', data: data.buckets, axisLabel: {{ rotate: 35, fontSize: 11 }} }},
        yAxis: {{ type: 'value', name: '请求数' }},
        series: series
      }};
    }}
    function initLine(elId, rounds, field, yName, xData, kind) {{
      var el = document.getElementById(elId);
      if (!el || !window.echarts || !xData || !xData.length) return;
      var chart = echarts.init(el);
      optionBuilders[kind] = function(enlarged) {{
        return buildLineOption(rounds, field, yName, xData, !!enlarged);
      }};
      chart.setOption(optionBuilders[kind](false));
      window.addEventListener('resize', function() {{ chart.resize(); }});
    }}
    function initHist(data) {{
      if (!HAS_HIST) return;
      var el = document.getElementById('overlayHistChart');
      if (!el || !window.echarts || !data.buckets || !data.buckets.length) return;
      var chart = echarts.init(el);
      optionBuilders.hist = function(enlarged) {{ return buildHistOption(data, !!enlarged); }};
      chart.setOption(optionBuilders.hist(false));
      window.addEventListener('resize', function() {{ chart.resize(); }});
    }}
    function closeZoom() {{
      var modal = document.getElementById('overlayChartZoomModal');
      if (modal) modal.classList.remove('is-open');
      if (zoomChart) {{
        zoomChart.dispose();
        zoomChart = null;
      }}
    }}
    function openZoom(kind) {{
      var builder = optionBuilders[kind];
      if (!builder || !window.echarts) return;
      var modal = document.getElementById('overlayChartZoomModal');
      var title = document.getElementById('overlayChartZoomTitle');
      var box = document.getElementById('overlayChartZoomBox');
      if (!modal || !box) return;
      if (title) title.textContent = TITLES[kind] || '图表放大';
      if (zoomChart) {{
        zoomChart.dispose();
        zoomChart = null;
      }}
      modal.classList.add('is-open');
      zoomChart = echarts.init(box);
      zoomChart.setOption(builder(true));
      setTimeout(function() {{ if (zoomChart) zoomChart.resize(); }}, 0);
    }}
    function bindZoomUi() {{
      var section = document.getElementById('overlayCompareSection');
      if (!section) return;
      var buttons = section.querySelectorAll('.chart-enlarge-btn[data-overlay-kind]');
      Array.prototype.forEach.call(buttons, function(btn) {{
        btn.addEventListener('click', function() {{
          openZoom(btn.getAttribute('data-overlay-kind') || 'qps');
        }});
      }});
      var closeBtn = document.getElementById('overlayChartZoomClose');
      var modal = document.getElementById('overlayChartZoomModal');
      if (closeBtn) closeBtn.addEventListener('click', closeZoom);
      if (modal) {{
        modal.addEventListener('click', function(e) {{
          if (e.target === modal) closeZoom();
        }});
      }}
      window.addEventListener('keydown', function(e) {{
        if (e.key === 'Escape') closeZoom();
      }});
    }}
    function boot() {{
      try {{
        if (!window.echarts) return;
        var data = readData();
        if (!data) return;
        if (HAS_TREND) {{
          initLine('overlayQpsChart', data.rounds, 'qps', 'QPS', data.x, 'qps');
          initLine('overlayAvgRtChart', data.rounds, 'avg_rt', 'Avg RT (ms)', data.x, 'avg_rt');
          initLine('overlayP95Chart', data.rounds, 'p95_rt', 'P95 (ms)', data.x, 'p95_rt');
        }}
        initHist(data);
        bindZoomUi();
      }} catch (e) {{}}
    }}
    if (document.readyState === 'loading') {{
      document.addEventListener('DOMContentLoaded', boot);
    }} else {{
      boot();
    }}
  }})();
  </script>"""
    return sections, scripts


def _escape_html(v: Any) -> str:
    return html_module.escape("" if v is None else str(v))


def render_perf_html_charts(record: Any) -> str:
    """兼容旧调用：图表区块与脚本合并（不推荐，会阻塞页面解析）。"""
    sections, scripts = render_perf_html_chart_parts(record)
    return sections + scripts
