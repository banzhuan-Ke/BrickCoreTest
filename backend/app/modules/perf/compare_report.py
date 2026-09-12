"""压测多记录对比 / 异场景合订报告构建（2–20 条）。"""
from __future__ import annotations

import json
from typing import Any, Optional, Sequence

from fastapi import HTTPException

from app.modules.perf.metrics_accuracy import build_comparison_trust
from app.modules.perf.perf_html_theme import (
    REPORT_STYLES,
    REPORT_STYLE_STANDARD,
    metric_lower_is_better,
)

MAX_COMPARE_RECORDS = 20
MIN_COMPARE_RECORDS = 2

REPORT_KIND_COMPARE = "compare"
REPORT_KIND_MERGE = "merge"
REPORT_KIND_HYBRID = "hybrid"

REPORT_KINDS = (REPORT_KIND_COMPARE, REPORT_KIND_MERGE, REPORT_KIND_HYBRID)

RECORD_SORT_SELECTION = "selection"
RECORD_SORT_CONCURRENCY_DESC = "concurrency_desc"
RECORD_SORT_CONCURRENCY_ASC = "concurrency_asc"
RECORD_SORT_CHAPTER_SMART = "chapter_smart"
RECORD_SORT_STARTED_DESC = "started_at_desc"
RECORD_SORT_MODES = (
    RECORD_SORT_SELECTION,
    RECORD_SORT_CONCURRENCY_DESC,
    RECORD_SORT_CONCURRENCY_ASC,
    RECORD_SORT_CHAPTER_SMART,
    RECORD_SORT_STARTED_DESC,
)

_LOOP_MODES = frozenset({"loop", "journey_loop"})
_LADDER_PHASE_FIRST_KEYS = ("first_char", "first_token", "ttft", "time_to_first_token")
_LADDER_PHASE_TOTAL_KEYS = ("total_time", "full_stream", "overall", "e2e")

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


def _record_config(record: Any) -> dict:
    if isinstance(record, dict):
        return record.get("config_snapshot") or record.get("config") or {}
    return getattr(record, "config_snapshot", None) or {}


def _record_started_ts(record: Any) -> float:
    if isinstance(record, dict):
        raw = record.get("started_at")
    else:
        dt = getattr(record, "started_at", None)
        raw = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None
    if not raw:
        return 0.0
    try:
        from datetime import datetime

        return datetime.strptime(str(raw)[:19], "%Y-%m-%d %H:%M:%S").timestamp()
    except (TypeError, ValueError):
        return 0.0


def think_time_phrase(delay_label: Optional[str]) -> str:
    """将 request_delay_label 转为汇报用语，如「1～3 秒随机间隔」。"""
    lab = str(delay_label or "").strip()
    if not lab or lab == "无":
        return ""
    import re

    if "随机" in lab:
        m = re.search(r"(\d+(?:\.\d+)?)\s*s?\s*[～~\-—]\s*(\d+(?:\.\d+)?)\s*s?", lab, re.I)
        if m:
            a, b = m.group(1), m.group(2)
            if "." in a or "." in b:
                return f"{a}～{b} 秒随机间隔"
            return f"{int(float(a))}～{int(float(b))} 秒随机间隔"
    m = re.search(r"(\d+(?:\.\d+)?)\s*s", lab, re.I)
    if m:
        return f"{m.group(1)} 秒固定间隔"
    return lab


def sort_report_records(records: Sequence[Any], sort_mode: Optional[str]) -> list[Any]:
    """多记录报告排序：勾选顺序 / 并发 / 智能分章（持续优先，瞬时并发递减）。"""
    rows = list(records)
    mode = (sort_mode or RECORD_SORT_SELECTION).strip().lower()
    if mode == RECORD_SORT_SELECTION or len(rows) < 2:
        return rows
    if mode not in RECORD_SORT_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的 record_sort: {sort_mode}（可选 {', '.join(RECORD_SORT_MODES)}）",
        )

    def _cu(rec: Any) -> int:
        try:
            return int(_record_config(rec).get("concurrent_users") or 0)
        except (TypeError, ValueError):
            return 0

    if mode == RECORD_SORT_CONCURRENCY_DESC:
        return sorted(rows, key=lambda r: (-_cu(r), -_record_started_ts(r), getattr(r, "id", 0)))
    if mode == RECORD_SORT_CONCURRENCY_ASC:
        return sorted(rows, key=lambda r: (_cu(r), -_record_started_ts(r), getattr(r, "id", 0)))
    if mode == RECORD_SORT_STARTED_DESC:
        return sorted(rows, key=lambda r: (-_record_started_ts(r), getattr(r, "id", 0)))

    # chapter_smart：固定时长模式（持续压测）在前，循环/瞬时在后；同组内并发从高到低
    def _smart_key(rec: Any) -> tuple:
        cfg = _record_config(rec)
        mode_name = str(cfg.get("mode") or "fixed")
        tier = 1 if mode_name in _LOOP_MODES else 0
        return (tier, -_cu(rec), -_record_started_ts(rec), getattr(rec, "id", 0) if not isinstance(rec, dict) else rec.get("id", 0))

    return sorted(rows, key=_smart_key)


def default_record_sort_for_kind(kind: Optional[str]) -> str:
    k = (kind or "").strip().lower()
    if k == REPORT_KIND_MERGE:
        return RECORD_SORT_CHAPTER_SMART
    return RECORD_SORT_SELECTION


def normalize_report_style_or_raise(style: Optional[str]) -> str:
    s = (style or "").strip().lower() or REPORT_STYLE_STANDARD
    if s not in REPORT_STYLES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的 report_style: {style}（可选 {', '.join(REPORT_STYLES)}）",
        )
    return s


def _record_summary(record: Any, scene_name: str = "") -> dict:
    # 延迟导入，避免 routers.perf.__init__ ↔ compare_report 循环依赖
    from app.routers.perf.report_utils import _success_qps, summarize_request_delays

    cfg = record.config_snapshot or {}
    items = getattr(record, "scene_items_snapshot", None) or []
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
        "config_snapshot": cfg,
        "request_delay_label": summarize_request_delays(items, cfg),
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


def _phase_rows_for_chapter(phase_metrics: Any, *, limit: int = 12) -> list[dict]:
    """分章用精简阶段指标（均值 / P95）。"""
    rows: list[dict] = []
    if not isinstance(phase_metrics, dict):
        return rows
    for item in (phase_metrics.get("metrics") or [])[:limit]:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if not key:
            continue
        rows.append({
            "key": key,
            "label": item.get("label") or key,
            "mean": item.get("mean"),
            "p95": item.get("p95"),
        })
    return rows


def overview_phase_highlights(phase_metrics: Any, *, limit: int = 3) -> list[dict]:
    """概览分卡用：优先首字/整体流式，最多 limit 条。"""
    rows = _phase_rows_for_chapter(phase_metrics, limit=12)
    if not rows:
        return []
    picked: list[dict] = []
    used: set[str] = set()
    for keys in (_LADDER_PHASE_FIRST_KEYS, _LADDER_PHASE_TOTAL_KEYS):
        hit = _ladder_pick_phase(rows, keys)
        if hit and str(hit.get("key")) not in used:
            picked.append(hit)
            used.add(str(hit.get("key")))
    for r in rows:
        if len(picked) >= limit:
            break
        k = str(r.get("key") or "")
        if k and k not in used and (r.get("mean") is not None or r.get("p95") is not None):
            picked.append(r)
            used.add(k)
    return picked[:limit]


def _ladder_pick_phase(phase_rows: list[dict], preferred_keys: tuple[str, ...]) -> Optional[dict]:
    by_key = {str(p.get("key") or ""): p for p in phase_rows if isinstance(p, dict)}
    for k in preferred_keys:
        if k in by_key:
            return by_key[k]
    return None


def _ladder_case_fingerprint(record: Any, summary: Optional[dict] = None) -> str:
    """阶梯可比性：优先用例名集合；无聚合时回退同场景。"""
    ag = None
    if isinstance(summary, dict):
        ag = summary.get("case_aggregations")
    if not isinstance(ag, dict) or not ag:
        ag = getattr(record, "case_aggregations", None) or {}
    keys: list[str] = []
    if isinstance(ag, dict):
        for cid, info in ag.items():
            if isinstance(info, dict):
                keys.append(_case_align_key(cid, info))
    if keys:
        return "cases:" + "|".join(sorted(set(keys)))
    sid = None
    if isinstance(summary, dict):
        sid = summary.get("scene_id")
    if sid is None:
        sid = getattr(record, "scene_id", None)
    if sid is not None:
        return f"scene:{sid}"
    return "unknown"


def _ladder_infer_zones(levels: list[dict]) -> list[dict]:
    """按失败率断崖划分区间（仅陈述实测，不做 SLA 判定）。"""
    if len(levels) < 2:
        return []
    zones: list[dict] = []
    cliff_idx: Optional[int] = None
    for i in range(1, len(levels)):
        prev_er = float(levels[i - 1].get("error_rate") or 0)
        cur_er = float(levels[i].get("error_rate") or 0)
        # 从接近零失败跳到明显失败，或绝对跳变 ≥15pp
        if (prev_er < 5 and cur_er >= 20) or (cur_er - prev_er >= 15):
            cliff_idx = i
            break

    if cliff_idx is None:
        max_er = max(float(lv.get("error_rate") or 0) for lv in levels)
        kind = "stable" if max_er < 5 else "mixed"
        first_u = levels[0].get("concurrent_users")
        last_u = levels[-1].get("concurrent_users")
        zones.append({
            "kind": kind,
            "from_users": first_u,
            "to_users": last_u,
            "title": f"并发 {first_u}～{last_u}",
            "summary": (
                f"各档失败率最高约 {max_er:g}%。"
                if max_er >= 0.01
                else "各档失败率接近 0%，未观察到明显失败率断崖。"
            ),
        })
        return zones

    stable = levels[:cliff_idx]
    after = levels[cliff_idx:]
    if stable:
        last_ok = stable[-1]
        zones.append({
            "kind": "stable",
            "from_users": stable[0].get("concurrent_users"),
            "to_users": last_ok.get("concurrent_users"),
            "title": f"相对平稳区间（{stable[0].get('concurrent_users')}～{last_ok.get('concurrent_users')} 并发）",
            "summary": (
                f"失败率约 {float(last_ok.get('error_rate') or 0):g}%，"
                f"成功 {last_ok.get('success_count')} / {last_ok.get('total_requests')}。"
            ),
        })
    cliff = levels[cliff_idx]
    prev = levels[cliff_idx - 1]
    zones.append({
        "kind": "inflection",
        "from_users": cliff.get("concurrent_users"),
        "to_users": cliff.get("concurrent_users"),
        "title": f"失败率拐点（{cliff.get('concurrent_users')} 并发）",
        "summary": (
            f"失败率由 {float(prev.get('error_rate') or 0):g}% 升至 "
            f"{float(cliff.get('error_rate') or 0):g}% "
            f"（失败 {cliff.get('fail_count')} / {cliff.get('total_requests')}）。"
        ),
    })
    if len(after) > 1:
        last = after[-1]
        zones.append({
            "kind": "saturated",
            "from_users": after[0].get("concurrent_users"),
            "to_users": last.get("concurrent_users"),
            "title": f"高失败区间（{after[0].get('concurrent_users')}～{last.get('concurrent_users')} 并发）",
            "summary": (
                f"末档失败率约 {float(last.get('error_rate') or 0):g}%，"
                f"成功 {last.get('success_count')} / {last.get('total_requests')}。"
            ),
        })
    return zones


def build_ladder_summary(
    records: Sequence[Any],
    summaries: Sequence[dict],
) -> Optional[dict]:
    """多档不同并发的阶梯汇总。

    仅当「压测模式相同 + 用例集合相同（或同场景）+ 至少 2 档不同并发」时生成，
    避免跨接口/跨场景硬比。梯度单跑不进阶梯。
    """
    candidates: list[dict] = []
    for r, s in zip(records, summaries):
        if not isinstance(s, dict):
            continue
        cfg = s.get("config_snapshot") or {}
        mode = str(cfg.get("mode") or "").strip()
        if not mode or mode == "stepping":
            continue
        try:
            cu = int(cfg.get("concurrent_users") or 0)
        except (TypeError, ValueError):
            cu = 0
        if cu <= 0:
            continue
        phase_rows = _phase_rows_for_chapter(s.get("phase_metrics"))
        first_ph = _ladder_pick_phase(phase_rows, _LADDER_PHASE_FIRST_KEYS)
        total_ph = _ladder_pick_phase(phase_rows, _LADDER_PHASE_TOTAL_KEYS)
        candidates.append({
            "mode": mode,
            "case_fp": _ladder_case_fingerprint(r, s),
            "scene_id": s.get("scene_id") if s.get("scene_id") is not None else getattr(r, "scene_id", None),
            "concurrent_users": cu,
            "record_id": s.get("id") if s.get("id") is not None else getattr(r, "id", None),
            "label": s.get("display_name") or s.get("scene_name") or f"执行#{s.get('id')}",
            "started_at": s.get("started_at"),
            "success_count": int(s.get("success_count") or 0),
            "fail_count": int(s.get("fail_count") or 0),
            "error_rate": float(s.get("error_rate") or 0),
            "total_requests": int(s.get("total_requests") or 0),
            "avg_response_time": s.get("avg_response_time"),
            "p95_response_time": s.get("p95_response_time"),
            "qps": s.get("qps"),
            "success_qps": s.get("success_qps"),
            "duration": s.get("duration"),
            "phase_first_mean": first_ph.get("mean") if first_ph else None,
            "phase_first_label": (first_ph.get("label") if first_ph else None) or "首字/首 token",
            "phase_total_mean": total_ph.get("mean") if total_ph else None,
            "phase_total_label": (total_ph.get("label") if total_ph else None) or "整体流式耗时",
            "phase_metrics": phase_rows,
        })

    # 按（模式, 用例指纹）分组；只取可比组里并发档位最多的一组
    groups: dict[tuple[str, str], list[dict]] = {}
    for c in candidates:
        if c.get("case_fp") in (None, "", "unknown"):
            continue
        key = (str(c.get("mode") or ""), str(c.get("case_fp")))
        groups.setdefault(key, []).append(c)

    best: list[dict] = []
    best_cu_n = 0
    for (_mode, _fp), members in groups.items():
        by_cu: dict[int, dict] = {}
        for c in members:
            cu = c["concurrent_users"]
            prev = by_cu.get(cu)
            if prev is None or str(c.get("started_at") or "") >= str(prev.get("started_at") or ""):
                by_cu[cu] = c
        if len(by_cu) > best_cu_n:
            best_cu_n = len(by_cu)
            best = [by_cu[k] for k in sorted(by_cu.keys())]

    levels = best
    if len(levels) < 2:
        return None

    has_first = any(lv.get("phase_first_mean") is not None for lv in levels)
    has_total_phase = any(lv.get("phase_total_mean") is not None for lv in levels)
    modes = sorted({lv.get("mode") or "" for lv in levels if lv.get("mode")})
    chart_series = {
        "x": [lv["concurrent_users"] for lv in levels],
        "error_rate": [float(lv.get("error_rate") or 0) for lv in levels],
        "success_rate": [
            round(max(0.0, min(100.0, 100.0 - float(lv.get("error_rate") or 0))), 2)
            for lv in levels
        ],
        "avg_rt_ms": [lv.get("avg_response_time") for lv in levels],
        "p95_rt_ms": [lv.get("p95_response_time") for lv in levels],
        "qps": [lv.get("qps") for lv in levels],
        "phase_first_mean": [lv.get("phase_first_mean") for lv in levels] if has_first else [],
        "phase_total_mean": [lv.get("phase_total_mean") for lv in levels] if has_total_phase else [],
    }
    # 展示用别删内部指纹字段
    public_levels = []
    for lv in levels:
        row = dict(lv)
        row.pop("case_fp", None)
        row.pop("phase_metrics", None)
        public_levels.append(row)
    return {
        "eligible": True,
        "mode_hint": modes[0] if len(modes) == 1 else "mixed",
        "modes": modes,
        "same_cases": True,
        "has_phase_first": has_first,
        "has_phase_total": has_total_phase,
        "phase_first_label": next(
            (lv.get("phase_first_label") for lv in levels if lv.get("phase_first_mean") is not None),
            "首字/首 token",
        ),
        "phase_total_label": next(
            (lv.get("phase_total_label") for lv in levels if lv.get("phase_total_mean") is not None),
            "整体流式耗时",
        ),
        "levels": public_levels,
        "chart_series": chart_series,
        "zones": _ladder_infer_zones(public_levels),
        "note": (
            "仅汇总「压测模式相同、用例集合相同」且并发档位 ≥2 的轮次；横轴为并发用户数。"
            "区间观察依据失败率变化；趋势图用成功率。均为实测观察，非验收达标结论。"
        ),
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
        phase_rows = _phase_rows_for_chapter(s.get("phase_metrics"))
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
            "request_delay_label": s.get("request_delay_label") or "无",
            "think_time_phrase": think_time_phrase(s.get("request_delay_label")),
            "phase_metrics": phase_rows,
            "top_cases": _top_cases(r),
            "error_summary": _error_summary(r),
        })

    overview_table = []
    for key, label in _METRIC_KEYS:
        row = {"key": key, "label": label, "values": {}}
        for s in summaries:
            row["values"][str(s["id"])] = float(s.get(key) or 0)
        overview_table.append(row)

    # 共有流式阶段指标并排（无变化率）
    phase_compare = _build_phase_metric_compare(
        records, summaries, ref_id=ordered_ids[0]
    )
    for p in phase_compare:
        if isinstance(p, dict):
            p["change_pct"] = {}
            overview_table.append({
                "key": p.get("key"),
                "label": p.get("label"),
                "values": dict(p.get("values") or {}),
                "group": "phase",
            })

    ladder_summary = build_ladder_summary(records, summaries)

    return {
        "kind": REPORT_KIND_MERGE,
        "record_ids": ordered_ids,
        "reference_record_id": ordered_ids[0],
        "records": summaries,
        "chapters": chapters,
        "overview_table": overview_table,
        "metric_compare": phase_compare,
        "case_compare": [],
        "case_common_count": 0,
        "same_scene": len({getattr(r, "scene_id", None) for r in records}) <= 1,
        "baseline_enabled": False,
        "trust_by_record": {},
        "changes": None,
        "trust": None,
        "ladder_summary": ladder_summary,
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
        "ladder_summary": merge.get("ladder_summary"),
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
    description: Optional[str] = None,
) -> dict:
    """为报告内记录/章节写入 display_name；可选附加用户提示词与报告描述。"""
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

    ladder = snapshot.get("ladder_summary")
    if isinstance(ladder, dict):
        for lv in ladder.get("levels") or []:
            if not isinstance(lv, dict):
                continue
            rid = str(lv.get("record_id"))
            if rid in names:
                lv["label"] = names[rid]

    extra = (user_extra_prompt or "").strip()
    if extra:
        snapshot["user_extra_prompt"] = extra[:2000]
    elif "user_extra_prompt" in snapshot:
        snapshot.pop("user_extra_prompt", None)

    desc = (description or "").strip()
    if desc:
        snapshot["description"] = desc[:2000]
    elif description is not None:
        snapshot.pop("description", None)
    return snapshot


def build_report_snapshot(
    records: Sequence[Any],
    *,
    reference_record_id: Optional[int] = None,
    scene_names: Optional[dict[int, str]] = None,
    kind: Optional[str] = None,
    display_names: Optional[dict] = None,
    user_extra_prompt: Optional[str] = None,
    description: Optional[str] = None,
    record_sort: Optional[str] = None,
    report_style: Optional[str] = None,
) -> dict:
    """构建快照。kind 可显式指定 compare / merge / hybrid；空则按场景自动选择。"""
    requested = (kind or "").strip().lower() or None
    if requested and requested not in REPORT_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的报告类型: {kind}（可选 compare / merge / hybrid）",
        )

    sort_mode = (record_sort or "").strip().lower() or default_record_sort_for_kind(requested)
    style_mode = normalize_report_style_or_raise(report_style)
    ordered_records = sort_report_records(records, sort_mode)

    if requested == REPORT_KIND_HYBRID:
        snap = build_hybrid_snapshot(
            ordered_records,
            reference_record_id=reference_record_id,
            scene_names=scene_names,
        )
    elif requested == REPORT_KIND_MERGE:
        snap = build_merge_snapshot(ordered_records, scene_names=scene_names)
    elif requested == REPORT_KIND_COMPARE:
        snap = build_compare_snapshot(
            ordered_records,
            reference_record_id=reference_record_id,
            scene_names=scene_names,
        )
    else:
        auto = detect_report_kind(ordered_records)
        if auto == REPORT_KIND_MERGE:
            snap = build_merge_snapshot(ordered_records, scene_names=scene_names)
        else:
            snap = build_compare_snapshot(
                ordered_records,
                reference_record_id=reference_record_id,
                scene_names=scene_names,
            )

    snap = apply_report_labels(
        snap,
        display_names=display_names,
        user_extra_prompt=user_extra_prompt,
        description=description,
    )
    snap["record_sort"] = sort_mode
    snap["report_style"] = style_mode
    return snap


def trim_snapshot_for_ai(snapshot: dict, *, max_ts_points: int = 30) -> dict:
    """缩减 token：去掉冗长时序细节；对外分析上下文不含 case_id。

    多章节时优先保留 ladder_summary / chapter_roster（全档并发），再放精简 scenes，
    避免 JSON 尾部截断导致低并发档（如 10～30）进不了 AI 结论。
    """
    kind = snapshot.get("kind") or REPORT_KIND_COMPARE

    def _perf_targets_enabled(cfg: Any) -> bool:
        if not isinstance(cfg, dict):
            return False
        pt = cfg.get("perf_targets")
        return isinstance(pt, dict) and bool(pt.get("enabled"))

    def _acceptance_targets_meta() -> dict:
        flags: list[bool] = []
        for r in snapshot.get("records") or []:
            if isinstance(r, dict):
                flags.append(_perf_targets_enabled(r.get("config_snapshot")))
        for c in snapshot.get("chapters") or []:
            if isinstance(c, dict):
                flags.append(_perf_targets_enabled(c.get("config") or c.get("config_snapshot")))
        any_on = any(flags) if flags else False
        if any_on:
            return {
                "any_enabled": True,
                "overall_status": "configured",
                "guidance": (
                    "部分或全部轮次启用了性能验收目标；达标表述须依据已配置目标，不得改写 pass/fail。"
                    "未启用目标的轮次仍禁止写「未达预期」。"
                ),
            }
        return {
            "any_enabled": False,
            "overall_status": "unknown",
            "guidance": (
                "本报告未启用性能验收目标。结论只笼统陈述实测数字（并发、请求数、QPS、平均RT、P95、错误率）"
                "与稳定性/长尾/阶段耗时观察；禁止「未达预期/不达标/未达SLA/理论最大请求量」等无配置依据的判定。"
            ),
        }

    def _hist_summary(hist: list, top_n: int = 5) -> list:
        if not isinstance(hist, list) or not hist:
            return []
        ranked = sorted(
            [h for h in hist if isinstance(h, dict)],
            key=lambda x: -(int(x.get("count") or 0)),
        )[:top_n]
        return [{"label": h.get("label"), "count": h.get("count")} for h in ranked]

    n_chapters = max(
        len([c for c in (snapshot.get("chapters") or []) if isinstance(c, dict)]),
        len([r for r in (snapshot.get("records") or []) if isinstance(r, dict)]),
    )
    # 章节多时压缩时序，把额度留给「全档 roster / ladder」
    if n_chapters >= 8:
        ts_cap = 0
        hist_top = 0
        cases_cap = 2
    elif n_chapters >= 6:
        ts_cap = min(6, max_ts_points)
        hist_top = 3
        cases_cap = 3
    elif n_chapters >= 4:
        ts_cap = min(12, max_ts_points)
        hist_top = 4
        cases_cap = 4
    else:
        ts_cap = max_ts_points
        hist_top = 5
        cases_cap = 40

    def _ts_sample(ts: list) -> list:
        if ts_cap <= 0 or not isinstance(ts, list):
            return []
        pts = ts
        if len(pts) > ts_cap:
            step = max(1, len(pts) // ts_cap)
            pts = pts[::step][:ts_cap]
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
        for c in (cases or [])[:cases_cap]:
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
                "warmup_seconds", "steps", "loop_count",
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

    def _compact_ladder(raw: Any) -> Any:
        if not isinstance(raw, dict):
            return raw
        levels = []
        for lv in raw.get("levels") or []:
            if not isinstance(lv, dict):
                continue
            levels.append({
                "concurrent_users": lv.get("concurrent_users"),
                "label": lv.get("label"),
                "success_count": lv.get("success_count"),
                "fail_count": lv.get("fail_count"),
                "error_rate": lv.get("error_rate"),
                "total_requests": lv.get("total_requests"),
                "avg_response_time": lv.get("avg_response_time"),
                "p95_response_time": lv.get("p95_response_time"),
                "qps": lv.get("qps"),
                "phase_first_mean": lv.get("phase_first_mean"),
                "phase_first_label": lv.get("phase_first_label"),
                "phase_total_mean": lv.get("phase_total_mean"),
                "phase_total_label": lv.get("phase_total_label"),
            })
        chart = raw.get("chart_series") if isinstance(raw.get("chart_series"), dict) else {}
        return {
            "eligible": raw.get("eligible"),
            "levels": levels,
            "chart_series": {
                "x": chart.get("x") or [lv.get("concurrent_users") for lv in levels],
                "avg_rt_ms": chart.get("avg_rt_ms"),
                "p95_rt_ms": chart.get("p95_rt_ms"),
                "qps": chart.get("qps"),
                "error_rate": chart.get("error_rate"),
                "success_rate": chart.get("success_rate"),
            },
            "guidance": (
                "阶梯并发全档必须写入核心结论与分章要点；禁止只写高并发档而漏掉低并发档。"
            ),
        }

    def _chapter_roster_from_scenes(scenes: list) -> list:
        roster = []
        for s in scenes:
            if not isinstance(s, dict):
                continue
            cfg = s.get("config") if isinstance(s.get("config"), dict) else {}
            roster.append({
                "label": s.get("label") or s.get("scene_name"),
                "concurrent_users": cfg.get("concurrent_users"),
                "mode_label": cfg.get("mode_label") or cfg.get("mode"),
                "qps": s.get("qps"),
                "avg_response_time": s.get("avg_response_time"),
                "p95_response_time": s.get("p95_response_time"),
                "error_rate": s.get("error_rate"),
                "total_requests": s.get("total_requests"),
            })
        return roster

    base = {
        "kind": kind,
        "note": snapshot.get("note"),
        "user_extra_prompt": snapshot.get("user_extra_prompt") or None,
        "baseline_enabled": bool(snapshot.get("baseline_enabled", kind == REPORT_KIND_COMPARE)),
        "same_scene": snapshot.get("same_scene"),
        "case_common_count": snapshot.get("case_common_count"),
        "acceptance_targets": _acceptance_targets_meta(),
        "chapter_count": n_chapters,
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
            cfg = c.get("config") if isinstance(c.get("config"), dict) else {}
            scenes.append({
                "label": c.get("display_name") or c.get("scene_name"),
                "scene_name": c.get("scene_name"),
                "qps": c.get("qps"),
                "avg_response_time": c.get("avg_response_time"),
                "p95_response_time": c.get("p95_response_time"),
                "error_rate": c.get("error_rate"),
                "total_requests": c.get("total_requests"),
                "config": _public_config(cfg),
                "request_delay_label": c.get("request_delay_label"),
                "think_time_phrase": think_time_phrase(c.get("request_delay_label")),
                "phase_metrics": (c.get("phase_metrics") or [])[:8],
                "top_cases": _cases_public(c.get("top_cases") or []),
                "error_summary": c.get("error_summary"),
                "time_series_sample": _ts_sample(rec.get("time_series_data") or []),
                "rt_histogram_summary": _hist_summary(rec.get("rt_histogram") or [], top_n=hist_top),
            })
        # 关键字段顺序：ladder / roster 在前，避免截断时丢掉低并发档
        return {
            **base,
            "ladder_summary": _compact_ladder(snapshot.get("ladder_summary")),
            "chapter_roster": _chapter_roster_from_scenes(scenes),
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
        "ladder_summary": _compact_ladder(snapshot.get("ladder_summary")),
        "metric_compare": snapshot.get("metric_compare"),
        "trust_by_record": snapshot.get("trust_by_record"),
        "stepping_stage_compare": snapshot.get("stepping_stage_compare"),
        "records": [],
        "case_compare": _cases_public(snapshot.get("case_compare") or []),
    }
    if kind == REPORT_KIND_HYBRID:
        chapters_compact = []
        for c in snapshot.get("chapters") or []:
            if not isinstance(c, dict):
                continue
            cfg = c.get("config") if isinstance(c.get("config"), dict) else {}
            chapters_compact.append({
                "label": c.get("display_name") or c.get("scene_name"),
                "scene_name": c.get("scene_name"),
                "qps": c.get("qps"),
                "avg_response_time": c.get("avg_response_time"),
                "p95_response_time": c.get("p95_response_time"),
                "error_rate": c.get("error_rate"),
                "total_requests": c.get("total_requests"),
                "config": _public_config(cfg),
                "top_cases": _cases_public(c.get("top_cases") or [])[:cases_cap],
            })
        out["chapter_roster"] = _chapter_roster_from_scenes(chapters_compact)
        out["chapters"] = chapters_compact

    for r in snapshot.get("records") or []:
        if not isinstance(r, dict):
            continue
        item = _record_public(r)
        item["time_series_sample"] = _ts_sample(r.get("time_series_data") or [])
        item["rt_histogram_summary"] = _hist_summary(r.get("rt_histogram") or [], top_n=hist_top)
        out["records"].append(item)
    return out


def pack_snapshot_json_for_ai(ctx: dict, *, max_chars: int = 48000) -> str:
    """序列化 AI 快照：优先完整保留 ladder / roster，再追加 scenes 等大字段。"""
    must_keys = (
        "kind",
        "analysis_mode",
        "chapter_count",
        "ladder_summary",
        "chapter_roster",
        "acceptance_targets",
        "baseline_enabled",
        "user_extra_prompt",
    )
    soft_keys = (
        "same_scene",
        "note",
        "case_common_count",
        "reference_label",
        # L0：每章资源一行，优先于 scenes 时序；预算紧时可丢但优先于 L1
        "sut_metrics_l0",
    )

    def _dumps(obj: dict) -> str:
        return json.dumps(obj, ensure_ascii=False, indent=2)

    def _slim_ladder(raw: Any) -> Any:
        if not isinstance(raw, dict):
            return raw
        levels = []
        for lv in raw.get("levels") or []:
            if not isinstance(lv, dict):
                continue
            levels.append({
                "concurrent_users": lv.get("concurrent_users"),
                "label": lv.get("label"),
                "avg_response_time": lv.get("avg_response_time"),
                "p95_response_time": lv.get("p95_response_time"),
                "qps": lv.get("qps"),
                "error_rate": lv.get("error_rate"),
                "total_requests": lv.get("total_requests"),
            })
        return {
            "eligible": raw.get("eligible"),
            "levels": levels,
            "guidance": raw.get("guidance") or "阶梯并发全档必须写入核心结论。",
        }

    def _slim_roster(raw: Any) -> list:
        out = []
        for r in raw or []:
            if not isinstance(r, dict):
                continue
            out.append({
                "label": r.get("label"),
                "concurrent_users": r.get("concurrent_users"),
                "avg_response_time": r.get("avg_response_time"),
                "p95_response_time": r.get("p95_response_time"),
                "qps": r.get("qps"),
                "error_rate": r.get("error_rate"),
            })
        return out

    must = {k: ctx[k] for k in must_keys if k in ctx and ctx[k] is not None}
    soft = {k: ctx[k] for k in soft_keys if k in ctx and ctx[k] is not None}
    rest = {k: v for k, v in ctx.items() if k not in must and k not in soft}

    packed = dict(must)
    blob = _dumps(packed)
    if len(blob) > max_chars:
        # 预算极紧：再压 ladder/roster 字段
        if "ladder_summary" in packed:
            packed["ladder_summary"] = _slim_ladder(packed["ladder_summary"])
        if "chapter_roster" in packed:
            packed["chapter_roster"] = _slim_roster(packed["chapter_roster"])
        blob = _dumps(packed)
        if len(blob) > max_chars:
            # 仍超限则至少保住 ladder levels 的并发数字
            emergency = {
                "kind": packed.get("kind"),
                "analysis_mode": packed.get("analysis_mode"),
                "chapter_count": packed.get("chapter_count"),
                "ladder_summary": _slim_ladder(packed.get("ladder_summary")),
                "chapter_roster": _slim_roster(packed.get("chapter_roster")),
            }
            return _dumps(emergency)[:max_chars]

    for k, v in soft.items():
        trial = dict(packed)
        trial[k] = v
        if len(_dumps(trial)) <= max_chars:
            packed = trial

    # rest：小字段优先 → scenes/chapters/records → sut_metrics_l1 最后（最可裁）
    rest_items = list(rest.items())

    def _rest_rank(key: str) -> int:
        if key == "sut_metrics_l1":
            return 90
        if key in ("scenes", "chapters", "records"):
            return 50
        if key in ("case_compare", "metric_compare", "overview_table"):
            return 30
        return 10

    rest_items.sort(key=lambda kv: (_rest_rank(kv[0]), kv[0]))

    for k, v in rest_items:
        trial = dict(packed)
        trial[k] = v
        blob = _dumps(trial)
        if len(blob) > max_chars:
            if k in ("scenes", "chapters", "records", "sut_metrics_l1") and isinstance(v, (list, dict)):
                if isinstance(v, list):
                    partial = []
                    for item in v:
                        trial2 = dict(packed)
                        trial2[k] = partial + [item]
                        if len(_dumps(trial2)) > max_chars:
                            break
                        partial.append(item)
                    if partial:
                        packed[k] = partial
                elif isinstance(v, dict) and isinstance(v.get("chapters"), list):
                    # L1 结构：按 chapters 逐条塞
                    partial_ch = []
                    base_obj = {kk: vv for kk, vv in v.items() if kk != "chapters"}
                    for item in v.get("chapters") or []:
                        trial2 = dict(packed)
                        trial2[k] = {**base_obj, "chapters": partial_ch + [item], "truncated": True}
                        if len(_dumps(trial2)) > max_chars:
                            break
                        partial_ch.append(item)
                    if partial_ch:
                        packed[k] = {
                            **base_obj,
                            "chapters": partial_ch,
                            "truncated": True,
                        }
            continue
        packed = trial
    return _dumps(packed)


async def hydrate_snapshot_chart_fields(snapshot: Optional[dict]) -> dict:
    """为旧增强报告补齐 rt_histogram / 缺失时序 / 受测环境字段（不落库，仅内存）。"""
    from app.modules.perf.perf_html_theme import env_label_from_config

    snap = dict(snapshot or {})
    records = list(snap.get("records") or [])
    if not records:
        return snap

    need_chart_ids = []
    need_env_ids: list[int] = []
    for r in records:
        if not isinstance(r, dict) or r.get("id") is None:
            continue
        if not r.get("rt_histogram") or not r.get("time_series_data"):
            need_chart_ids.append(r["id"])
        cfg = r.get("config_snapshot") if isinstance(r.get("config_snapshot"), dict) else {}
        has_env = bool(str(cfg.get("env_name") or "").strip() or str(cfg.get("env_host") or "").strip())
        if not has_env and not str(r.get("env_label") or "").strip():
            try:
                eid = int(cfg.get("env_id")) if cfg.get("env_id") is not None else None
            except (TypeError, ValueError):
                eid = None
            if eid is not None:
                need_env_ids.append(eid)

    by_id = {}
    if need_chart_ids:
        from app.models.perf import PerfRecord

        rows = await PerfRecord.filter(id__in=list(dict.fromkeys(need_chart_ids))).all()
        by_id = {r.id: r for r in rows}

    env_by_id = {}
    if need_env_ids:
        from app.models.sys import Environment

        envs = await Environment.filter(id__in=list(dict.fromkeys(need_env_ids)), is_del=False).all()
        env_by_id = {e.id: e for e in envs}

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

        cfg = dict(item.get("config_snapshot") or {}) if isinstance(item.get("config_snapshot"), dict) else {}
        if not (str(cfg.get("env_name") or "").strip() or str(cfg.get("env_host") or "").strip()):
            try:
                eid = int(cfg.get("env_id")) if cfg.get("env_id") is not None else None
            except (TypeError, ValueError):
                eid = None
            env = env_by_id.get(eid) if eid is not None else None
            if env:
                cfg["env_name"] = getattr(env, "name", None) or ""
                cfg["env_host"] = getattr(env, "host", None) or ""
                item["config_snapshot"] = cfg
        lab = env_label_from_config(item.get("config_snapshot") or {})
        if lab and lab != "—":
            item["env_label"] = lab
        hydrated.append(item)
    snap["records"] = hydrated
    return snap
