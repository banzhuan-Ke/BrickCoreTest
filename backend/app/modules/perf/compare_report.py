"""压测多记录对比 / 异场景合订报告构建（2–20 条）。"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from fastapi import HTTPException

from app.modules.perf.metrics_accuracy import build_comparison_trust
from app.modules.perf.perf_html_theme import metric_lower_is_better

MAX_COMPARE_RECORDS = 20
MIN_COMPARE_RECORDS = 2

REPORT_KIND_COMPARE = "compare"
REPORT_KIND_MERGE = "merge"
REPORT_KIND_HYBRID = "hybrid"

REPORT_KINDS = (REPORT_KIND_COMPARE, REPORT_KIND_MERGE, REPORT_KIND_HYBRID)

_METRIC_KEYS = (
    ("qps", "QPS"),
    ("success_qps", "成功 QPS"),
    ("avg_response_time", "平均响应时间(ms)"),
    ("p95_response_time", "P95(ms)"),
    ("error_rate", "错误率(%)"),
    ("total_requests", "总请求数"),
)


def detect_report_kind(records: Sequence[Any]) -> str:
    """同场景 → 对比；跨场景 → 合订合并。"""
    scene_ids = {getattr(r, "scene_id", None) for r in records}
    if len(scene_ids) <= 1:
        return REPORT_KIND_COMPARE
    return REPORT_KIND_MERGE


def _record_summary(record: Any, scene_name: str = "") -> dict:
    # 延迟导入，避免 routers.perf.__init__ ↔ compare_report 循环依赖
    from app.routers.perf.report_utils import _success_qps

    return {
        "id": record.id,
        "scene_id": getattr(record, "scene_id", None),
        "scene_name": scene_name or "未知场景",
        "status": record.status,
        "started_at": record.started_at.strftime("%Y-%m-%d %H:%M:%S") if record.started_at else None,
        "ended_at": record.ended_at.strftime("%Y-%m-%d %H:%M:%S") if record.ended_at else None,
        "duration": record.duration,
        "total_requests": record.total_requests,
        "success_count": record.success_count,
        "fail_count": record.fail_count,
        "qps": record.qps,
        "success_qps": _success_qps(record),
        "avg_response_time": record.avg_response_time,
        "min_response_time": record.min_response_time,
        "max_response_time": record.max_response_time,
        "median_response_time": record.median_response_time,
        "p90_response_time": record.p90_response_time,
        "p95_response_time": record.p95_response_time,
        "p99_response_time": record.p99_response_time,
        "error_rate": record.error_rate,
        "config_snapshot": record.config_snapshot or {},
        "case_aggregations": record.case_aggregations or {},
        "phase_metrics": getattr(record, "phase_metrics", None) or {},
        "time_series_data": record.time_series_data or [],
        "rt_histogram": ((record.error_breakdown or {}) if isinstance(getattr(record, "error_breakdown", None), dict) else {}).get("rt_histogram") or [],
    }


def _phase_metric_maps_from_records(records: Sequence[Any]) -> list[dict[str, dict]]:
    from app.routers.perf.report_utils import _phase_metrics_by_key

    return [_phase_metrics_by_key(r) for r in records]


def _build_phase_metric_compare(
    records: Sequence[Any],
    summaries: list[dict],
    *,
    ref_id: int,
) -> list[dict]:
    """各轮 phase_metrics 交集：均值 / P95（秒）纳入 metric_compare。"""
    maps = _phase_metric_maps_from_records(records)
    if not maps or any(not m for m in maps):
        # 若有的轮次完全没有阶段指标，仍取交集（可能为空）
        pass
    common_keys: Optional[set[str]] = None
    for m in maps:
        keys = set(m.keys())
        common_keys = keys if common_keys is None else (common_keys & keys)
    if not common_keys:
        return []

    # 稳定顺序：优先 total_time / answer*，其余按 key
    def _sort_key(k: str) -> tuple:
        low = k.lower()
        if low == "total_time":
            return (0, k)
        if "answer" in low:
            return (1, k)
        return (2, k)

    rows: list[dict] = []
    for phase_key in sorted(common_keys, key=_sort_key):
        label = phase_key
        for m in maps:
            lab = (m.get(phase_key) or {}).get("label")
            if lab:
                label = str(lab)
                break
        for stat_key, suffix, unit in (("mean", "均值", "s"), ("p95", "P95", "s")):
            metric_key = f"phase_{stat_key}_{phase_key}"
            row = {
                "key": metric_key,
                "label": f"{label} {suffix}({unit})",
                "values": {},
                "change_pct": {},
                "group": "phase",
                "phase_key": phase_key,
                "unit": unit,
                "lower_is_better": True,
            }
            base_val = None
            for s, m in zip(summaries, maps):
                raw = (m.get(phase_key) or {}).get(stat_key)
                try:
                    v = float(raw) if raw is not None else None
                except (TypeError, ValueError):
                    v = None
                row["values"][str(s["id"])] = v
                if s["id"] == ref_id and v is not None:
                    base_val = v
            if base_val is None:
                continue
            for s in summaries:
                rid = str(s["id"])
                v = row["values"].get(rid)
                if s["id"] == ref_id:
                    row["change_pct"][rid] = 0.0
                elif v is None:
                    row["change_pct"][rid] = None
                else:
                    row["change_pct"][rid] = _pct(float(v), float(base_val))
            rows.append(row)
    return rows


def _pct(cur: float, base: float) -> Optional[float]:
    if base == 0:
        return 0.0 if cur == 0 else 100.0
    return round((cur - base) / base * 100, 2)


def _safe_pct(cur: Any, base: Any) -> Optional[float]:
    try:
        if cur is None or base is None:
            return None
        return _pct(float(cur), float(base))
    except (TypeError, ValueError):
        return None


_STEPPING_STAGE_METRIC_DEFS = (
    ("users", "并发", None),
    ("planned_duration", "计划时长(s)", None),
    ("observed_seconds", "观察秒数", None),
    ("completed_seconds", "有完成秒数", None),
    ("avg_qps", "平均 QPS", False),
    ("avg_rt", "平均 RT(ms)", True),
    ("avg_p95", "平均 P95(ms)", True),
    ("avg_error_rate", "错误率(%)", True),
)


def _metric_map_from_rows(metric_rows: list[dict]) -> dict[str, dict]:
    return {str(m.get("key")): m for m in metric_rows if isinstance(m, dict) and m.get("key")}


def _stage_compare_line(
    stage_num: int,
    metric_rows: list[dict],
    records: Sequence[Any],
    *,
    ref_id: int,
    baseline_enabled: bool,
) -> str:
    """单阶段一句对照摘要，供报告展示与 AI。"""
    by_key = _metric_map_from_rows(metric_rows)
    users = (by_key.get("users") or {}).get("values") or {}
    qps = (by_key.get("avg_qps") or {}).get("values") or {}
    rt = (by_key.get("avg_rt") or {}).get("values") or {}
    done = (by_key.get("completed_seconds") or {}).get("values") or {}
    qps_pct = (by_key.get("avg_qps") or {}).get("change_pct") or {}
    rt_pct = (by_key.get("avg_rt") or {}).get("change_pct") or {}

    bits = [f"第{stage_num}阶段"]
    u_set = {v for v in users.values() if v is not None}
    if len(u_set) == 1:
        bits[0] += f"（{next(iter(u_set))}并发）"
    for r in records:
        rid = str(r.id)
        tag = "参照" if r.id == ref_id else "对比"
        u = users.get(rid)
        d = done.get(rid)
        q = qps.get(rid)
        t = rt.get(rid)
        piece = f"{tag}轮"
        if u is not None:
            piece += f"{u}并发"
        if d is not None:
            piece += f"/有完成{d}s"
        if q is not None:
            piece += f"/QPS {q}"
        if t is not None:
            piece += f"/RT {t}ms（约{round(float(t)/1000, 1)}s）"
        elif d == 0:
            piece += "/无完成样本"
        if baseline_enabled and r.id != ref_id:
            extras = []
            if qps_pct.get(rid) is not None:
                extras.append(f"QPS{qps_pct.get(rid):+g}%")
            if rt_pct.get(rid) is not None:
                extras.append(f"RT{rt_pct.get(rid):+g}%")
            if extras:
                piece += f"（{('，'.join(extras))}）"
        bits.append(piece)
    return "；".join(bits)


def _build_stepping_stage_compare(
    records: Sequence[Any],
    summaries: list[dict],
    *,
    ref_id: int,
    baseline_enabled: bool = True,
) -> Optional[dict]:
    """梯度模式按阶段序号对齐的观察指标对照；不足两轮有阶段数据则返回 None。"""
    from app.routers.perf.report_utils import (
        format_stepping_stages_narrative,
        summarize_stepping_stages,
    )

    stages_by_rid: dict[Any, list] = {}
    for r, s in zip(records, summaries):
        cfg = getattr(r, "config_snapshot", None) or (s.get("config_snapshot") if isinstance(s, dict) else None) or {}
        if str(cfg.get("mode") or "") != "stepping":
            stages_by_rid[r.id] = []
            continue
        ts = getattr(r, "time_series_data", None) or (s.get("time_series_data") if isinstance(s, dict) else None) or []
        stages_by_rid[r.id] = summarize_stepping_stages(cfg, ts)

    with_data = [rid for rid, st in stages_by_rid.items() if st]
    if len(with_data) < 2:
        return None

    max_n = max(len(st) for st in stages_by_rid.values())
    out_stages = []
    narrative_lines = []
    for i in range(max_n):
        stage_num = i + 1
        metric_rows = []
        users_vals: dict[str, Any] = {}
        for key, label, lower_is_better in _STEPPING_STAGE_METRIC_DEFS:
            values: dict[str, Any] = {}
            for r in records:
                st_list = stages_by_rid.get(r.id) or []
                values[str(r.id)] = st_list[i].get(key) if i < len(st_list) else None
            if key == "users":
                users_vals = dict(values)
            change_pct: dict[str, Any] = {}
            if baseline_enabled:
                base = values.get(str(ref_id))
                for r in records:
                    rid = str(r.id)
                    if r.id == ref_id:
                        change_pct[rid] = 0.0
                    else:
                        change_pct[rid] = _safe_pct(values.get(rid), base)
            metric_rows.append({
                "key": key,
                "label": label,
                "values": values,
                "change_pct": change_pct,
                "lower_is_better": lower_is_better,
            })

        user_set = {v for v in users_vals.values() if v is not None}
        if len(user_set) == 1:
            label = f"第 {stage_num} 阶段 · {next(iter(user_set))} 并发"
        else:
            label = f"第 {stage_num} 阶段"

        summary = _stage_compare_line(
            stage_num,
            metric_rows,
            records,
            ref_id=ref_id,
            baseline_enabled=baseline_enabled,
        )
        narrative_lines.append(summary)
        out_stages.append({
            "stage": stage_num,
            "label": label,
            "users": users_vals,
            "metrics": metric_rows,
            "summary": summary,
        })

    per_record_narratives = {}
    for r in records:
        st_list = stages_by_rid.get(r.id) or []
        if st_list:
            per_record_narratives[str(r.id)] = format_stepping_stages_narrative(st_list)

    return {
        "stages": out_stages,
        "summary": "。".join(narrative_lines) + ("。" if narrative_lines else ""),
        "per_record_narratives": per_record_narratives,
        "note": (
            "按阶段序号对齐对照。"
            "QPS 按整段时长平均；RT/P95 只统计有完成请求的秒。"
        ),
    }


def _top_cases(record: Any, limit: int = 8) -> list[dict]:
    ag = record.case_aggregations or {}
    rows = []
    for cid, info in ag.items():
        if not isinstance(info, dict):
            continue
        rows.append({
            "name": info.get("name") or f"接口-{cid}",
            "total": info.get("total", 0),
            "fail": info.get("fail", 0),
            "avg_rt": info.get("avg_rt"),
            "p95_rt": info.get("p95_rt"),
            "error_rate": info.get("error_rate"),
            "min_rt": info.get("min_rt"),
            "max_rt": info.get("max_rt"),
            "median_rt": info.get("median_rt"),
            "p90_rt": info.get("p90_rt"),
        })
    rows.sort(key=lambda x: (-float(x.get("error_rate") or 0), -float(x.get("p95_rt") or 0), -int(x.get("total") or 0)))
    return rows[:limit]


def _case_align_key(cid: Any, info: dict) -> str:
    """优先按接口名对齐（跨场景/重跑）；无名时回退 case_id。"""
    name = str(info.get("name") or "").strip()
    if name:
        return f"name:{name.casefold()}"
    return f"id:{cid}"


def _empty_case_cell() -> dict:
    return {
        "present": False,
        "total": None,
        "error_rate": None,
        "avg_rt": None,
        "p95_rt": None,
        "fail": None,
        "min_rt": None,
        "max_rt": None,
        "median_rt": None,
        "p90_rt": None,
    }


def _present_case_cell(info: dict) -> dict:
    return {
        "present": True,
        "total": info.get("total", 0),
        "error_rate": info.get("error_rate"),
        "avg_rt": info.get("avg_rt"),
        "p95_rt": info.get("p95_rt"),
        "fail": info.get("fail", 0),
        "min_rt": info.get("min_rt"),
        "max_rt": info.get("max_rt"),
        "median_rt": info.get("median_rt"),
        "p90_rt": info.get("p90_rt"),
    }


def _build_case_compare(records: Sequence[Any], *, reference_record_id: int) -> list[dict]:
    """按接口名对齐用例；缺侧标记 present=False，避免把「本轮无」当成 0 算出 -100%。"""
    # key -> {name, by_record: {rid: cell}}
    buckets: dict[str, dict] = {}
    for r in records:
        ag = r.case_aggregations or {}
        if not isinstance(ag, dict):
            continue
        for cid, info in ag.items():
            if not isinstance(info, dict):
                continue
            key = _case_align_key(cid, info)
            bucket = buckets.setdefault(key, {"name": "", "case_ids": set(), "by_record": {}})
            display = str(info.get("name") or "").strip() or f"接口-{cid}"
            if not bucket["name"] or bucket["name"].startswith("接口-"):
                bucket["name"] = display
            bucket["case_ids"].add(str(cid))
            bucket["by_record"][str(r.id)] = _present_case_cell(info)

    rows: list[dict] = []
    for key, bucket in buckets.items():
        values: dict[str, dict] = {}
        present_count = 0
        for r in records:
            rid = str(r.id)
            cell = bucket["by_record"].get(rid)
            if cell and cell.get("present"):
                values[rid] = cell
                present_count += 1
            else:
                values[rid] = _empty_case_cell()
        coverage = "common" if present_count == len(records) else "partial"
        change_pct: dict[str, Optional[float]] = {}
        ref_vals = values.get(str(reference_record_id)) or {}
        for r in records:
            rid = str(r.id)
            if r.id == reference_record_id:
                change_pct[rid] = 0.0 if (ref_vals.get("present")) else None
                continue
            cur = values.get(rid) or {}
            if not ref_vals.get("present") or not cur.get("present"):
                change_pct[rid] = None
                continue
            try:
                base_avg = float(ref_vals.get("avg_rt") or 0)
                cur_avg = float(cur.get("avg_rt") or 0)
                change_pct[rid] = _pct(cur_avg, base_avg)
            except (TypeError, ValueError):
                change_pct[rid] = None
        rows.append({
            "align_key": key,
            "case_id": next(iter(bucket["case_ids"]), ""),
            "name": bucket["name"],
            "coverage": coverage,
            "values": values,
            "change_pct_avg": change_pct,
        })

    # 共有接口优先，再按错误率/P95 排序
    def _sort_key(row: dict):
        common_first = 0 if row.get("coverage") == "common" else 1
        max_err = 0.0
        max_p95 = 0.0
        max_n = 0
        for v in (row.get("values") or {}).values():
            if not v.get("present"):
                continue
            max_err = max(max_err, float(v.get("error_rate") or 0))
            max_p95 = max(max_p95, float(v.get("p95_rt") or 0))
            max_n = max(max_n, int(v.get("total") or 0))
        return (common_first, -max_err, -max_p95, -max_n, row.get("name") or "")

    rows.sort(key=_sort_key)
    return rows[:80]


def _error_summary(record: Any) -> dict:
    err = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
    out = {
        k: v for k, v in err.items()
        if not str(k).startswith("_") and k not in (
            "failed_samples", "request_traces", "rt_histogram",
            "journey_aggregations", "metrics_meta", "success_latency",
        )
    }
    samples = err.get("failed_samples") or []
    if isinstance(samples, list) and samples:
        out["failed_sample_count"] = len(samples)
        out["failed_sample_preview"] = [
            {
                "url": s.get("url") or s.get("name"),
                "status_code": s.get("status_code"),
                "error": (s.get("error") or s.get("error_message") or "")[:160],
            }
            for s in samples[:5]
            if isinstance(s, dict)
        ]
    return out


def _validate_records(records: Sequence[Any]) -> None:
    n = len(records)
    if n < MIN_COMPARE_RECORDS:
        raise HTTPException(status_code=400, detail=f"请至少选择 {MIN_COMPARE_RECORDS} 条记录")
    if n > MAX_COMPARE_RECORDS:
        raise HTTPException(status_code=400, detail=f"最多支持 {MAX_COMPARE_RECORDS} 条记录")
    project_ids = {r.project_id for r in records}
    if len(project_ids) != 1:
        raise HTTPException(status_code=400, detail="只能选择同一项目下的执行记录")


def build_compare_snapshot(
    records: Sequence[Any],
    *,
    reference_record_id: Optional[int] = None,
    scene_names: Optional[dict[int, str]] = None,
) -> dict:
    """同场景对比快照。"""
    _validate_records(records)
    by_id = {r.id: r for r in records}
    ordered_ids = [r.id for r in records]
    ref_id = reference_record_id or ordered_ids[0]
    if ref_id not in by_id:
        raise HTTPException(status_code=400, detail="基准记录不在对比列表中")
    ref = by_id[ref_id]
    names = scene_names or {}

    summaries = [_record_summary(r, names.get(r.id, "")) for r in records]

    metric_compare = []
    for key, label in _METRIC_KEYS:
        row = {
            "key": key,
            "label": label,
            "values": {},
            "change_pct": {},
            "lower_is_better": metric_lower_is_better(key),
        }
        base_val = float(summaries[next(i for i, s in enumerate(summaries) if s["id"] == ref_id)].get(key) or 0)
        for s in summaries:
            v = float(s.get(key) or 0)
            row["values"][str(s["id"])] = v
            if s["id"] == ref_id:
                row["change_pct"][str(s["id"])] = 0.0
            else:
                row["change_pct"][str(s["id"])] = _pct(v, base_val)
        metric_compare.append(row)

    phase_rows = _build_phase_metric_compare(records, summaries, ref_id=ref_id)
    metric_compare.extend(phase_rows)

    trust_by_record: dict[str, Any] = {}
    for r in records:
        if r.id == ref_id:
            continue
        trust_by_record[str(r.id)] = build_comparison_trust(
            getattr(r, "config_snapshot", None),
            getattr(ref, "config_snapshot", None),
            int(getattr(r, "total_requests", 0) or 0),
            int(getattr(ref, "total_requests", 0) or 0),
            current_scene_items=getattr(r, "scene_items_snapshot", None),
            previous_scene_items=getattr(ref, "scene_items_snapshot", None),
        )

    changes = None
    n = len(records)
    if n == 2:
        from app.routers.perf.report_utils import _comparison_changes

        other = next(r for r in records if r.id != ref_id)
        changes = _comparison_changes(other, ref)

    case_compare = _build_case_compare(records, reference_record_id=ref_id)
    common_n = sum(1 for c in case_compare if c.get("coverage") == "common")
    same_scene = len({getattr(r, "scene_id", None) for r in records}) <= 1
    stepping_stage_compare = _build_stepping_stage_compare(
        records, summaries, ref_id=ref_id, baseline_enabled=True,
    )

    return {
        "kind": REPORT_KIND_COMPARE,
        "record_ids": ordered_ids,
        "reference_record_id": ref_id,
        "records": summaries,
        "metric_compare": metric_compare,
        "case_compare": case_compare,
        "stepping_stage_compare": stepping_stage_compare,
        "case_common_count": common_n,
        "same_scene": same_scene,
        # 对比报告：始终做基准变化率对照
        "baseline_enabled": True,
        "trust_by_record": trust_by_record,
        "changes": changes,
        "trust": trust_by_record.get(str(next((r.id for r in records if r.id != ref_id), "")), None) if n == 2 else None,
    }


def build_merge_snapshot(
    records: Sequence[Any],
    *,
    scene_names: Optional[dict[int, str]] = None,
) -> dict:
    """跨场景合订：分章展示 + 简单对照表（无变化率、无用例矩阵对齐）。"""
    _validate_records(records)
    names = scene_names or {}
    ordered_ids = [r.id for r in records]
    summaries = [_record_summary(r, names.get(r.id, "")) for r in records]

    chapters = []
    for r, s in zip(records, summaries):
        cfg = s.get("config_snapshot") or {}
        chapters.append({
            "record_id": r.id,
            "scene_id": s.get("scene_id"),
            "scene_name": s.get("scene_name"),
            "status": s.get("status"),
            "started_at": s.get("started_at"),
            "duration": s.get("duration"),
            "qps": s.get("qps"),
            "success_qps": s.get("success_qps"),
            "avg_response_time": s.get("avg_response_time"),
            "min_response_time": s.get("min_response_time"),
            "max_response_time": s.get("max_response_time"),
            "median_response_time": s.get("median_response_time"),
            "p90_response_time": s.get("p90_response_time"),
            "p95_response_time": s.get("p95_response_time"),
            "p99_response_time": s.get("p99_response_time"),
            "error_rate": s.get("error_rate"),
            "total_requests": s.get("total_requests"),
            "success_count": s.get("success_count"),
            "fail_count": s.get("fail_count"),
            "config": {
                k: cfg.get(k)
                for k in ("mode", "concurrent_users", "ramp_up_seconds", "duration_seconds", "steps")
            },
            "top_cases": _top_cases(r),
            "error_summary": _error_summary(r),
        })

    overview_table = []
    for key, label in _METRIC_KEYS:
        row = {"key": key, "label": label, "values": {}}
        for s in summaries:
            row["values"][str(s["id"])] = float(s.get(key) or 0)
        overview_table.append(row)

    return {
        "kind": REPORT_KIND_MERGE,
        "record_ids": ordered_ids,
        "reference_record_id": ordered_ids[0],
        "records": summaries,
        "chapters": chapters,
        "overview_table": overview_table,
        "metric_compare": [],
        "case_compare": [],
        "case_common_count": 0,
        "same_scene": len({getattr(r, "scene_id", None) for r in records}) <= 1,
        "baseline_enabled": False,
        "trust_by_record": {},
        "changes": None,
        "trust": None,
        "note": "各场景分章展示；顶层指标并排，不计算变化率。",
    }


def build_hybrid_snapshot(
    records: Sequence[Any],
    *,
    reference_record_id: Optional[int] = None,
    scene_names: Optional[dict[int, str]] = None,
) -> dict:
    """合并+对比：分章叙述；同场景时再做相对基准的指标/用例对照。"""
    merge = build_merge_snapshot(records, scene_names=scene_names)
    compare = build_compare_snapshot(
        records,
        reference_record_id=reference_record_id,
        scene_names=scene_names,
    )
    same_scene = bool(compare.get("same_scene"))
    # 仅同场景启用基准对照；跨场景只分章 + 指标并排
    baseline_enabled = same_scene
    all_cases = list(compare.get("case_compare") or [])
    metric_compare = list(compare.get("metric_compare") or [])

    if baseline_enabled:
        case_rows = [c for c in all_cases if c.get("coverage") == "common"]
        common_n = len(case_rows)
        note = "同场景合并+对比：先看相对参照轮对照，再看各轮画像。"
        if not case_rows:
            note += " 无同名接口可对齐，已省略用例对照。"
        elif common_n < len(all_cases):
            note += f" 用例表仅展示共有接口（{common_n} 个）。"
        stepping_stage_compare = compare.get("stepping_stage_compare")
    else:
        for m in metric_compare:
            if isinstance(m, dict):
                m["change_pct"] = {}
        case_rows = []
        common_n = 0
        note = "跨场景合并+对比：分章展示，指标并排，不计算变化率。"
        stepping_stage_compare = _build_stepping_stage_compare(
            records,
            compare.get("records") or [],
            ref_id=compare["reference_record_id"],
            baseline_enabled=False,
        )

    return {
        "kind": REPORT_KIND_HYBRID,
        "record_ids": compare["record_ids"],
        "reference_record_id": compare["reference_record_id"],
        "records": compare["records"],
        "chapters": merge["chapters"],
        "overview_table": merge["overview_table"],
        "metric_compare": metric_compare,
        "case_compare": case_rows,
        "stepping_stage_compare": stepping_stage_compare,
        "case_common_count": common_n,
        "same_scene": same_scene,
        "baseline_enabled": baseline_enabled,
        "trust_by_record": compare["trust_by_record"] if baseline_enabled else {},
        "changes": compare.get("changes") if baseline_enabled else None,
        "trust": compare.get("trust") if baseline_enabled else None,
        "note": note,
    }


def apply_report_labels(
    snapshot: dict,
    *,
    display_names: Optional[dict] = None,
    user_extra_prompt: Optional[str] = None,
) -> dict:
    """为报告内记录/章节写入 display_name；可选附加用户提示词（仅存快照，供 AI 使用）。"""
    names: dict[str, str] = {}
    for k, v in (display_names or {}).items():
        label = str(v or "").strip()
        if label:
            names[str(k)] = label[:80]

    for r in snapshot.get("records") or []:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id"))
        r["display_name"] = names.get(rid) or (r.get("scene_name") or f"执行#{rid}")

    for c in snapshot.get("chapters") or []:
        if not isinstance(c, dict):
            continue
        rid = str(c.get("record_id"))
        c["display_name"] = names.get(rid) or (c.get("scene_name") or f"执行#{rid}")

    extra = (user_extra_prompt or "").strip()
    if extra:
        snapshot["user_extra_prompt"] = extra[:2000]
    elif "user_extra_prompt" in snapshot:
        snapshot.pop("user_extra_prompt", None)
    return snapshot


def build_report_snapshot(
    records: Sequence[Any],
    *,
    reference_record_id: Optional[int] = None,
    scene_names: Optional[dict[int, str]] = None,
    kind: Optional[str] = None,
    display_names: Optional[dict] = None,
    user_extra_prompt: Optional[str] = None,
) -> dict:
    """构建快照。kind 可显式指定 compare / merge / hybrid；空则按场景自动选择。"""
    requested = (kind or "").strip().lower() or None
    if requested and requested not in REPORT_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的报告类型: {kind}（可选 compare / merge / hybrid）",
        )

    if requested == REPORT_KIND_HYBRID:
        snap = build_hybrid_snapshot(
            records,
            reference_record_id=reference_record_id,
            scene_names=scene_names,
        )
    elif requested == REPORT_KIND_MERGE:
        snap = build_merge_snapshot(records, scene_names=scene_names)
    elif requested == REPORT_KIND_COMPARE:
        snap = build_compare_snapshot(
            records,
            reference_record_id=reference_record_id,
            scene_names=scene_names,
        )
    else:
        auto = detect_report_kind(records)
        if auto == REPORT_KIND_MERGE:
            snap = build_merge_snapshot(records, scene_names=scene_names)
        else:
            snap = build_compare_snapshot(
                records,
                reference_record_id=reference_record_id,
                scene_names=scene_names,
            )

    return apply_report_labels(
        snap,
        display_names=display_names,
        user_extra_prompt=user_extra_prompt,
    )


def trim_snapshot_for_ai(snapshot: dict, *, max_ts_points: int = 30) -> dict:
    """缩减 token：去掉冗长时序细节；对外分析上下文不含 case_id。"""
    kind = snapshot.get("kind") or REPORT_KIND_COMPARE

    def _hist_summary(hist: list, top_n: int = 5) -> list:
        if not isinstance(hist, list) or not hist:
            return []
        ranked = sorted(
            [h for h in hist if isinstance(h, dict)],
            key=lambda x: -(int(x.get("count") or 0)),
        )[:top_n]
        return [{"label": h.get("label"), "count": h.get("count")} for h in ranked]

    def _ts_sample(ts: list) -> list:
        if not isinstance(ts, list):
            return []
        pts = ts
        if len(pts) > max_ts_points:
            step = max(1, len(pts) // max_ts_points)
            pts = pts[::step][:max_ts_points]
        return [
            {
                "t": p.get("timestamp"),
                "qps": p.get("qps"),
                "avg_rt": p.get("avg_rt"),
                "p95": p.get("p95_rt"),
                "err": p.get("error_rate"),
                "users": p.get("active_users"),
            }
            for p in pts
            if isinstance(p, dict)
        ]

    def _cases_public(cases: list) -> list:
        out = []
        for c in (cases or [])[:40]:
            if not isinstance(c, dict):
                continue
            item = {
                "name": c.get("name") or "未命名接口",
                "total": c.get("total"),
                "avg_rt": c.get("avg_rt"),
                "p95_rt": c.get("p95_rt"),
                "error_rate": c.get("error_rate"),
                "fail": c.get("fail"),
            }
            if c.get("values"):
                vals = {}
                label_by_id = {
                    str(r.get("id")): (r.get("display_name") or r.get("scene_name") or str(r.get("id")))
                    for r in (snapshot.get("records") or [])
                    if isinstance(r, dict)
                }
                for rid, v in (c.get("values") or {}).items():
                    if not isinstance(v, dict):
                        continue
                    if v.get("present") is False:
                        vals[label_by_id.get(str(rid), str(rid))] = {"present": False}
                    else:
                        vals[label_by_id.get(str(rid), str(rid))] = {
                            "present": True,
                            "total": v.get("total"),
                            "avg_rt": v.get("avg_rt"),
                            "p95_rt": v.get("p95_rt"),
                            "error_rate": v.get("error_rate"),
                        }
                item["values"] = vals
            if c.get("coverage"):
                item["coverage"] = c.get("coverage")
            out.append(item)
        return out

    def _public_config(cfg: dict) -> dict:
        raw = cfg if isinstance(cfg, dict) else {}
        out = {
            k: raw.get(k)
            for k in (
                "mode", "concurrent_users", "ramp_up_seconds", "duration_seconds",
                "warmup_seconds", "steps",
            )
        }
        try:
            from app.routers.perf.report_utils import (
                perf_mode_label,
                peak_users_from_config,
                format_steps_summary,
            )
            out["mode_label"] = perf_mode_label(raw.get("mode"))
            if str(raw.get("mode") or "") == "stepping":
                out["peak_concurrent_users"] = peak_users_from_config(raw)
                out["steps_summary"] = format_steps_summary(raw) or None
        except Exception:
            out["mode_label"] = str(raw.get("mode") or "")
        return out

    def _record_public(r: dict) -> dict:
        phase = r.get("phase_metrics") or {}
        phase_rows = []
        if isinstance(phase, dict):
            for item in (phase.get("metrics") or [])[:20]:
                if not isinstance(item, dict):
                    continue
                phase_rows.append({
                    "key": item.get("key"),
                    "label": item.get("label") or item.get("key"),
                    "mean": item.get("mean"),
                    "p95": item.get("p95"),
                })
        return {
            "label": r.get("display_name") or r.get("scene_name") or f"执行#{r.get('id')}",
            "scene_name": r.get("scene_name"),
            "started_at": r.get("started_at"),
            "duration": r.get("duration"),
            "qps": r.get("qps"),
            "p95_response_time": r.get("p95_response_time"),
            "error_rate": r.get("error_rate"),
            "total_requests": r.get("total_requests"),
            "avg_response_time": r.get("avg_response_time"),
            "phase_metrics": phase_rows,
            "config_snapshot": _public_config(r.get("config_snapshot") or {}),
        }

    base = {
        "kind": kind,
        "note": snapshot.get("note"),
        "user_extra_prompt": snapshot.get("user_extra_prompt") or None,
        "baseline_enabled": bool(snapshot.get("baseline_enabled", kind == REPORT_KIND_COMPARE)),
        "same_scene": snapshot.get("same_scene"),
        "case_common_count": snapshot.get("case_common_count"),
    }
    # 给 AI 的显式分析模式，避免 merge 误用「指标对照」话术
    if kind == REPORT_KIND_MERGE or (
        kind == REPORT_KIND_HYBRID and not base["baseline_enabled"]
    ):
        base["analysis_mode"] = "chapter_portrait"
    else:
        base["analysis_mode"] = "baseline_delta"

    if kind == REPORT_KIND_MERGE:
        records_by_id = {
            r.get("id"): r
            for r in (snapshot.get("records") or [])
            if isinstance(r, dict) and r.get("id") is not None
        }
        scenes = []
        for c in snapshot.get("chapters") or []:
            if not isinstance(c, dict):
                continue
            rec = records_by_id.get(c.get("record_id")) or {}
            scenes.append({
                "label": c.get("display_name") or c.get("scene_name"),
                "scene_name": c.get("scene_name"),
                "qps": c.get("qps"),
                "avg_response_time": c.get("avg_response_time"),
                "p95_response_time": c.get("p95_response_time"),
                "error_rate": c.get("error_rate"),
                "total_requests": c.get("total_requests"),
                "config": c.get("config"),
                "top_cases": _cases_public(c.get("top_cases") or []),
                "error_summary": c.get("error_summary"),
                "time_series_sample": _ts_sample(rec.get("time_series_data") or []),
                "rt_histogram_summary": _hist_summary(rec.get("rt_histogram") or []),
            })
        return {
            **base,
            "scenes": scenes,
            "overview_table": snapshot.get("overview_table"),
        }

    # compare + hybrid
    out = {
        **base,
        "reference_label": next(
            (
                (r.get("display_name") or r.get("scene_name"))
                for r in (snapshot.get("records") or [])
                if r.get("id") == snapshot.get("reference_record_id")
            ),
            "基准",
        ),
        "metric_compare": snapshot.get("metric_compare"),
        "trust_by_record": snapshot.get("trust_by_record"),
        "stepping_stage_compare": snapshot.get("stepping_stage_compare"),
        "records": [],
        "case_compare": _cases_public(snapshot.get("case_compare") or []),
    }
    if kind == REPORT_KIND_HYBRID:
        out["chapters"] = [
            {
                "label": c.get("display_name") or c.get("scene_name"),
                "scene_name": c.get("scene_name"),
                "qps": c.get("qps"),
                "p95_response_time": c.get("p95_response_time"),
                "error_rate": c.get("error_rate"),
                "total_requests": c.get("total_requests"),
                "config": c.get("config"),
                "top_cases": _cases_public(c.get("top_cases") or [])[:6],
            }
            for c in (snapshot.get("chapters") or [])
        ]

    for r in snapshot.get("records") or []:
        if not isinstance(r, dict):
            continue
        item = _record_public(r)
        item["time_series_sample"] = _ts_sample(r.get("time_series_data") or [])
        item["rt_histogram_summary"] = _hist_summary(r.get("rt_histogram") or [])
        out["records"].append(item)
    return out


async def hydrate_snapshot_chart_fields(snapshot: Optional[dict]) -> dict:
    """为旧增强报告补齐 rt_histogram / 缺失时序（不落库，仅内存）。"""
    snap = dict(snapshot or {})
    records = list(snap.get("records") or [])
    if not records:
        return snap
    need_ids = []
    for r in records:
        if not isinstance(r, dict) or r.get("id") is None:
            continue
        if not r.get("rt_histogram") or not r.get("time_series_data"):
            need_ids.append(r["id"])
    if not need_ids:
        return snap
    from app.models.perf import PerfRecord

    rows = await PerfRecord.filter(id__in=list(dict.fromkeys(need_ids))).all()
    by_id = {r.id: r for r in rows}
    hydrated = []
    for r in records:
        if not isinstance(r, dict):
            continue
        item = dict(r)
        src = by_id.get(item.get("id"))
        if src:
            if not item.get("rt_histogram"):
                eb = src.error_breakdown if isinstance(src.error_breakdown, dict) else {}
                item["rt_histogram"] = eb.get("rt_histogram") or []
            if not item.get("time_series_data"):
                item["time_series_data"] = src.time_series_data or []
        hydrated.append(item)
    snap["records"] = hydrated
    return snap
