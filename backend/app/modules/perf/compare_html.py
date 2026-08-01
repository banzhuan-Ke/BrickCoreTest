"""对比 / 合订 / 合并+对比报告汇报型 HTML 导出。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.modules.perf.compare_report import REPORT_KIND_COMPARE, REPORT_KIND_HYBRID, REPORT_KIND_MERGE
from app.modules.perf.perf_html_theme import (
    case_note_map,
    chart_notes_by_label,
    colorize_pct_in_text,
    err_tag,
    h,
    metric_lower_is_better,
    metric_note,
    pct_span,
    pct_tone,
    render_conclusion_box,
    render_metric_glossary,
    render_overview_para,
    render_percentile_table,
    render_rt_bars,
    report_css,
    report_edit_chrome,
)
from app.routers.perf.report_utils import render_perf_html_chart_parts, render_compare_overlay_charts


def _ai_conclusion(ai: dict, *, fallback_html: str = "") -> str:
    return render_conclusion_box(ai, fallback_html=fallback_html)


def _rec_label(r: dict) -> str:
    return str(r.get("display_name") or r.get("scene_name") or f"#{r.get('id')}")


def _ch_label(c: dict) -> str:
    return str(c.get("display_name") or c.get("scene_name") or f"#{c.get('record_id')}")


def _short_time(ts: Any) -> str:
    s = str(ts or "").strip()
    if not s:
        return ""
    # "2026-07-17 17:08:41" → "17:08"
    if " " in s and ":" in s:
        return s.split(" ", 1)[1][:5]
    return s[:16]


_MODE_LABELS = {
    "fixed": "固定模式",
    "loop": "循环模式",
    "stepping": "梯度模式",
    "stream_burst": "流式阶段压测",
    "sse_burst": "流式阶段压测",
    "journey_fixed": "链路固定模式",
    "journey_loop": "链路循环模式",
}


def _mode_label(mode: Any) -> str:
    try:
        from app.routers.perf.report_utils import perf_mode_label
        return perf_mode_label(mode)
    except Exception:
        m = str(mode or "").strip()
        return _MODE_LABELS.get(m, m or "-")


def _concurrent_config_cell(cfg: dict) -> str:
    mode = str((cfg or {}).get("mode") or "")
    if mode == "stepping":
        try:
            from app.routers.perf.report_utils import peak_users_from_config, format_steps_summary
            peak = peak_users_from_config(cfg)
            summary = format_steps_summary(cfg)
            if peak is not None and summary:
                return f"峰值 {peak}（{summary}）"
            if peak is not None:
                return f"峰值 {peak}"
        except Exception:
            pass
    v = (cfg or {}).get("concurrent_users")
    return "-" if v is None or v == "" else str(v)


def _duration_config_cell(cfg: dict) -> str | None:
    """无固定时长的模式返回 None（不展示该行）。纯文本，供非 HTML 场景。"""
    mode = str((cfg or {}).get("mode") or "")
    if mode in ("stream_burst", "sse_burst"):
        return None
    if mode in ("fixed", "journey_fixed"):
        v = cfg.get("duration_seconds")
        return f"{v}s" if v is not None and v != "" else "-"
    if mode in ("loop", "journey_loop"):
        v = cfg.get("loop_count")
        return f"{v} 次/用户" if v is not None and v != "" else "-"
    if mode == "stepping":
        steps = [s for s in (cfg.get("steps") or []) if isinstance(s, dict) and s.get("users") is not None]
        summary = " → ".join(
            f"{s.get('users')}用户×{s.get('duration')}s" if s.get("duration") is not None else f"{s.get('users')}用户"
            for s in steps
        )
        n = len(steps)
        if summary:
            return f"{n} 个阶段（{summary}）"
        return f"{n} 个阶段"
    v = cfg.get("duration_seconds")
    if v is None or v == "":
        return "-"
    return f"{v}s"


def _duration_config_cell_html(cfg: dict) -> str | None:
    """时长配置 HTML；梯度模式按阶段分行展示。"""
    mode = str((cfg or {}).get("mode") or "")
    if mode in ("stream_burst", "sse_burst"):
        return None
    if mode != "stepping":
        plain = _duration_config_cell(cfg)
        return h(plain) if plain is not None else None
    steps = [s for s in (cfg.get("steps") or []) if isinstance(s, dict) and s.get("users") is not None]
    if not steps:
        return h("0 个阶段")
    lines = []
    for i, s in enumerate(steps, 1):
        bit = f"{s.get('users')}用户 × {s.get('duration')}s" if s.get("duration") is not None else f"{s.get('users')}用户"
        lines.append(f"<div class='step-line'>第 {i} 阶段 · {h(bit)}</div>")
    return (
        f"<div class='steps-stack'>"
        f"<div class='steps-head'>{len(steps)} 个阶段</div>"
        f"{''.join(lines)}</div>"
    )


def _concurrent_config_cell_html(cfg: dict) -> str:
    mode = str((cfg or {}).get("mode") or "")
    if mode != "stepping":
        return h(_concurrent_config_cell(cfg))
    try:
        from app.routers.perf.report_utils import peak_users_from_config
        peak = peak_users_from_config(cfg)
    except Exception:
        peak = None
    steps = [s for s in (cfg.get("steps") or []) if isinstance(s, dict) and s.get("users") is not None]
    if not steps:
        return h(_concurrent_config_cell(cfg))
    lines = []
    for i, s in enumerate(steps, 1):
        bit = f"{s.get('users')}用户 × {s.get('duration')}s" if s.get("duration") is not None else f"{s.get('users')}用户"
        lines.append(f"<div class='step-line'>第 {i} 阶段 · {h(bit)}</div>")
    head = f"峰值 {peak}" if peak is not None else "梯度并发"
    return (
        f"<div class='steps-stack'>"
        f"<div class='steps-head'>{h(head)}</div>"
        f"{''.join(lines)}</div>"
    )


def _metric_tone_cls(cur: Any, base: Any, *, lower_is_better: bool = True) -> str:
    try:
        c = float(cur)
        b = float(base)
    except (TypeError, ValueError):
        return ""
    if b == 0:
        return ""
    pct = (c - b) / abs(b) * 100.0
    if abs(pct) < 3:
        return "pct-flat"
    better = pct < 0 if lower_is_better else pct > 0
    return "pct-better" if better else "pct-worse"


def _round_role(r: dict, *, ref_id: Any, baseline: bool) -> str:
    if not baseline:
        return "本轮"
    return "参照轮" if r.get("id") == ref_id else "对比轮"


def _round_heading(r: dict, *, ref_id: Any, baseline: bool) -> str:
    """同名场景时用角色 + 时间 + 记录号区分，避免两列都叫同一场景名。"""
    role = _round_role(r, ref_id=ref_id, baseline=baseline)
    t = _short_time(r.get("started_at"))
    bits = [role, f"#{r.get('id')}"]
    if t:
        bits.append(t)
    name = _rec_label(r)
    # 名字与角色信息拼接：参照轮 · #35 · 17:08 · 获取快速入口信息
    return " · ".join(bits) + f" · {name}"


def _kind_title(kind: str) -> str:
    return {
        REPORT_KIND_MERGE: "汇总报告",
        REPORT_KIND_HYBRID: "合并+对比报告",
    }.get(kind, "对比报告")


def _records_by_id(snap: dict) -> dict:
    out = {}
    for r in snap.get("records") or []:
        if isinstance(r, dict) and r.get("id") is not None:
            out[r["id"]] = r
            out[str(r["id"])] = r
    return out


def _chart_note_for(ai: dict, label: str) -> dict:
    notes = chart_notes_by_label(ai)
    return notes.get(label) or notes.get("_default") or {}


def _top_cases_from_aggs(case_aggregations: Any, limit: int = 8) -> list[dict]:
    ag = case_aggregations if isinstance(case_aggregations, dict) else {}
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


def _chapters_from_snap_records(records: list) -> list[dict]:
    """纯对比快照无 chapters 时，从 records 合成分章画像，便于导出/平台展示。"""
    chapters = []
    for r in records or []:
        if not isinstance(r, dict) or r.get("id") is None:
            continue
        cfg = r.get("config_snapshot") or {}
        chapters.append({
            "record_id": r.get("id"),
            "display_name": r.get("display_name"),
            "scene_id": r.get("scene_id"),
            "scene_name": r.get("scene_name"),
            "status": r.get("status"),
            "started_at": r.get("started_at"),
            "duration": r.get("duration"),
            "qps": r.get("qps"),
            "success_qps": r.get("success_qps"),
            "avg_response_time": r.get("avg_response_time"),
            "min_response_time": r.get("min_response_time"),
            "max_response_time": r.get("max_response_time"),
            "median_response_time": r.get("median_response_time"),
            "p90_response_time": r.get("p90_response_time"),
            "p95_response_time": r.get("p95_response_time"),
            "p99_response_time": r.get("p99_response_time"),
            "error_rate": r.get("error_rate"),
            "total_requests": r.get("total_requests"),
            "success_count": r.get("success_count"),
            "fail_count": r.get("fail_count"),
            "config": {
                k: cfg.get(k)
                for k in (
                    "mode", "concurrent_users", "ramp_up_seconds", "duration_seconds",
                    "warmup_seconds", "steps",
                )
            },
            "top_cases": _top_cases_from_aggs(r.get("case_aggregations")),
            "error_summary": {},
        })
    return chapters


def _render_record_charts(
    rec: dict,
    *,
    prefix: str,
    trend_heading: str,
    hist_heading: str,
    ai: dict,
    label: str,
    include_echarts: bool,
) -> tuple[str, str]:
    note = _chart_note_for(ai, label)
    return render_perf_html_chart_parts(
        rec,
        prefix=prefix,
        trend_heading=trend_heading,
        hist_heading=hist_heading,
        include_echarts=include_echarts,
        ai_trend_note=note.get("trend") or "",
        ai_dist_note=note.get("distribution") or "",
    )


def _fmt_ms(v: Any) -> str:
    if v is None or v == "":
        return "-"
    try:
        return f"{h(round(float(v), 2))} <span class='unit'>ms</span>"
    except (TypeError, ValueError):
        return f"{h(v)} <span class='unit'>ms</span>"


def _fmt_qps(v: Any) -> str:
    if v is None or v == "":
        return "-"
    try:
        return f"{h(round(float(v), 2))} <span class='unit'>/s</span>"
    except (TypeError, ValueError):
        return f"{h(v)} <span class='unit'>/s</span>"


def _render_chapters_html(
    chapters: list,
    ai: dict,
    records_by_id: dict,
    *,
    start_idx: int = 1,
    include_echarts: bool = True,
) -> tuple[str, str]:
    notes_by_case = case_note_map(ai)
    parts: list[str] = []
    scripts: list[str] = []
    echarts_once = include_echarts
    for i, c in enumerate(chapters):
        idx = start_idx + i
        cases = c.get("top_cases") or []
        case_rows = []
        for x in cases:
            name = x.get("name") or "未命名"
            cnote = notes_by_case.get(name, "")
            note_html = f'<div class="case-note">{h(cnote)}</div>' if cnote else ""
            case_rows.append(
                f"<tr><td>{h(name)}{note_html}</td>"
                f"<td class='num'>{h(x.get('total'))}</td><td class='num'>{h(x.get('fail'))}</td>"
                f"<td>{err_tag(x.get('error_rate'))}</td>"
                f"<td class='num'>{_fmt_ms(x.get('avg_rt'))}</td>"
                f"<td class='num'>{_fmt_ms(x.get('p95_rt'))}</td>"
                f"<td class='num'>{_fmt_ms(x.get('max_rt') if x.get('max_rt') is not None else None)}</td></tr>"
            )
        case_body = "".join(case_rows) or '<tr><td colspan="7" style="color:#999">无用例数据</td></tr>'
        err = c.get("error_summary") or {}
        err_note = ""
        if err.get("failed_sample_count"):
            err_note = (
                f"<p style='font-size:13px;color:#666;margin-top:8px'>"
                f"失败采样 {h(err.get('failed_sample_count'))} 条</p>"
            )
        bars = render_rt_bars(
            min_rt=c.get("min_response_time"),
            median_rt=c.get("median_response_time"),
            avg_rt=c.get("avg_response_time"),
            p90_rt=c.get("p90_response_time"),
            p95_rt=c.get("p95_response_time"),
            max_rt=c.get("max_response_time"),
        )
        pct_table = render_percentile_table(
            min_rt=c.get("min_response_time"),
            median_rt=c.get("median_response_time"),
            avg_rt=c.get("avg_response_time"),
            p90_rt=c.get("p90_response_time"),
            p95_rt=c.get("p95_response_time"),
            p99_rt=c.get("p99_response_time"),
            max_rt=c.get("max_response_time"),
        )
        label = _ch_label(c)
        rid = c.get("record_id")
        rec = records_by_id.get(rid) or records_by_id.get(str(rid)) or {}
        load_line = _chapter_load_line(c.get("config") or (rec.get("config_snapshot") if isinstance(rec, dict) else {}) or {})
        load_html = f" · {h(load_line)}" if load_line else ""
        chart_sec, chart_scr = "", ""
        if rec:
            chart_sec, chart_scr = _render_record_charts(
                rec,
                prefix=f"ch{rid}",
                trend_heading=f"{idx}.5 性能趋势",
                hist_heading=f"{idx}.6 响应时间分布",
                ai=ai,
                label=label,
                include_echarts=echarts_once,
            )
            if chart_sec:
                echarts_once = False
                scripts.append(chart_scr)

        parts.append(f"""
  <div class="section">
    <h2>{idx}. {h(label)}</h2>
    <p style="font-size:13px;color:#666;margin-bottom:12px">
      场景 {h(c.get('scene_name'))} · 执行 #{h(c.get('record_id'))}
      {load_html} ·
      开始 {h(c.get('started_at'))} · 时长 {h(c.get('duration'))}s
    </p>
    <h3>{idx}.1 核心指标</h3>
    <div class="summary-grid">
      <div class="summary-card"><div class="label">QPS</div><div class="value">{_fmt_qps(c.get('qps'))}</div></div>
      <div class="summary-card"><div class="label">平均 RT</div><div class="value">{_fmt_ms(c.get('avg_response_time'))}</div></div>
      <div class="summary-card"><div class="label">P95</div><div class="value">{_fmt_ms(c.get('p95_response_time'))}</div></div>
      <div class="summary-card"><div class="label">错误率</div><div class="value">{h(c.get('error_rate'))}<span class="unit">%</span></div></div>
      <div class="summary-card"><div class="label">总请求</div><div class="value">{h(c.get('total_requests'))}<span class="unit">次</span></div></div>
    </div>
    <h3>{idx}.2 响应时间分位</h3>
    {pct_table}
    <h3>{idx}.3 响应时间可视化</h3>
    {bars or '<p style="color:#999;font-size:13px">暂无分位数据</p>'}
    {err_note}
    <h3>{idx}.4 接口明细</h3>
    <table>
      <thead><tr>
        <th>接口</th><th>请求数</th><th>失败</th><th>失败率</th>
        <th>Avg RT <span class="unit">(ms)</span></th>
        <th>P95 <span class="unit">(ms)</span></th>
        <th>Max <span class="unit">(ms)</span></th>
      </tr></thead>
      <tbody>{case_body}</tbody>
    </table>
  </div>
  {chart_sec}""")
    return "".join(parts), "".join(scripts)


def _render_records_charts_section(
    records: list,
    ai: dict,
    *,
    heading: str,
    include_echarts: bool = True,
) -> tuple[str, str]:
    """纯对比模式：各轮趋势与分布。"""
    parts: list[str] = []
    scripts: list[str] = []
    echarts_once = include_echarts
    for r in records:
        if not isinstance(r, dict):
            continue
        label = _rec_label(r)
        rid = r.get("id")
        sec, scr = _render_record_charts(
            r,
            prefix=f"rec{rid}",
            trend_heading=f"{label} · 性能趋势",
            hist_heading=f"{label} · 响应时间分布",
            ai=ai,
            label=label,
            include_echarts=echarts_once,
        )
        if not sec:
            continue
        echarts_once = False
        scripts.append(scr)
        parts.append(sec)
    if not parts:
        return "", ""
    return f'<div class="section"><h2>{h(heading)}</h2></div>' + "".join(parts), "".join(scripts)


def _fmt_stage_metric_val(key: str, val: Any) -> str:
    if val is None or val == "-":
        return "-"
    try:
        if key in ("avg_qps",):
            return f"{h(round(float(val), 2))}"
        if key in ("avg_rt", "avg_p95"):
            sec = round(float(val) / 1000, 1)
            return f"{h(round(float(val), 1))}<span class='unit'>ms</span>（约 {h(sec)}s）"
        if key == "avg_error_rate":
            return f"{h(round(float(val), 2))}<span class='unit'>%</span>"
        if key in ("planned_duration", "observed_seconds", "completed_seconds"):
            return f"{h(int(float(val)))}<span class='unit'>s</span>"
        if key == "users":
            return h(int(float(val)))
    except (TypeError, ValueError):
        pass
    return h(val)


def _stage_metrics_by_key(stage: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for m in stage.get("metrics") or []:
        if isinstance(m, dict) and m.get("key"):
            out[str(m["key"])] = m
    return out


def _stage_card_tone(stage: dict, *, ref_id: Any, records: list, baseline: bool) -> str:
    """用对比轮相对参照的 QPS/RT 变化粗判卡片色调。"""
    if not baseline:
        return "flat"
    by = _stage_metrics_by_key(stage)
    tones = []
    for key, lower in (("avg_qps", False), ("avg_rt", True)):
        row = by.get(key) or {}
        for r in records:
            if r.get("id") == ref_id:
                continue
            pct = (row.get("change_pct") or {}).get(str(r.get("id")))
            if pct is None:
                continue
            tones.append(pct_tone(pct, lower_is_better=lower))
    if any(t == "worse" for t in tones):
        return "worse"
    if tones and all(t == "better" for t in tones):
        return "better"
    return "flat"


def _render_stage_summary_cards(
    stages: list,
    records: list,
    *,
    ref_id: Any,
    baseline: bool,
) -> str:
    cards = []
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        by = _stage_metrics_by_key(stage)
        users = (by.get("users") or {}).get("values") or {}
        qps = (by.get("avg_qps") or {}).get("values") or {}
        rt = (by.get("avg_rt") or {}).get("values") or {}
        done = (by.get("completed_seconds") or {}).get("values") or {}
        qps_pct = (by.get("avg_qps") or {}).get("change_pct") or {}
        rt_pct = (by.get("avg_rt") or {}).get("change_pct") or {}
        tone = _stage_card_tone(stage, ref_id=ref_id, records=records, baseline=baseline)
        stage_num = stage.get("stage") or ""
        label = stage.get("label") or f"第 {stage_num} 阶段"
        lines = []
        for r in records:
            rid = str(r.get("id"))
            is_ref = baseline and r.get("id") == ref_id
            role = _round_role(r, ref_id=ref_id, baseline=baseline)
            tag_cls = "round-ref" if is_ref else ("round-cmp" if baseline else "tag-blue")
            bits = []
            if users.get(rid) is not None:
                bits.append(f"{h(users.get(rid))}并发")
            if done.get(rid) is not None:
                bits.append(f"有完成 {h(done.get(rid))}s")
            if qps.get(rid) is not None:
                bits.append(f"QPS {h(qps.get(rid))}")
            if rt.get(rid) is not None:
                try:
                    sec = round(float(rt.get(rid)) / 1000, 1)
                    bits.append(f"RT {h(rt.get(rid))}ms（约 {h(sec)}s）")
                except (TypeError, ValueError):
                    bits.append(f"RT {h(rt.get(rid))}ms")
            elif done.get(rid) == 0:
                bits.append("无完成样本")
            lines.append(
                f"<div class='stage-sum-line'>"
                f"<span class='tag {tag_cls}'>{h(role)}</span>"
                f"<span class='stage-sum-meta'>{' · '.join(bits) if bits else '—'}</span>"
                f"</div>"
            )
        chips = []
        if baseline:
            for r in records:
                if r.get("id") == ref_id:
                    continue
                rid = str(r.get("id"))
                if qps_pct.get(rid) is not None:
                    try:
                        p = float(qps_pct.get(rid))
                        cls = pct_tone(p, lower_is_better=False)
                        chips.append(
                            f"<span class='delta-chip pct-{cls}'>QPS {h(f'{p:+g}%')}</span>"
                        )
                    except (TypeError, ValueError):
                        pass
                if rt_pct.get(rid) is not None:
                    try:
                        p = float(rt_pct.get(rid))
                        cls = pct_tone(p, lower_is_better=True)
                        chips.append(
                            f"<span class='delta-chip pct-{cls}'>RT {h(f'{p:+g}%')}</span>"
                        )
                    except (TypeError, ValueError):
                        pass
        deltas = (
            f"<div class='stage-sum-deltas'>{''.join(chips)}</div>" if chips else ""
        )
        cards.append(
            f"<div class='stage-summary-card {tone}'>"
            f"<div class='stage-sum-title'>"
            f"<span class='stage-idx'>{h(stage_num)}</span>"
            f"<span>{h(label)}</span>"
            f"</div>"
            f"{''.join(lines)}"
            f"{deltas}"
            f"</div>"
        )
    if not cards:
        return ""
    return (
        "<div class='stage-summary-block'>"
        "<div class='stage-summary-label'>分阶段对照摘要</div>"
        f"<div class='stage-summary-list'>{''.join(cards)}</div>"
        "</div>"
    )


def _render_stepping_stage_compare_section(snap: dict, *, heading: str) -> str:
    """梯度模式按阶段序号对齐的对照表。"""
    block = snap.get("stepping_stage_compare")
    if not isinstance(block, dict):
        return ""
    stages = block.get("stages") or []
    if not stages:
        return ""
    records = snap.get("records") or []
    ref_id = snap.get("reference_record_id")
    baseline = bool(snap.get("baseline_enabled", True))
    note = block.get("note") or ""

    header_cols = "".join(
        f"<th class='{'round-col-ref' if (baseline and r.get('id') == ref_id) else ('round-col-cmp' if baseline else '')}'>"
        f"{h(_round_heading(r, ref_id=ref_id, baseline=baseline))}</th>"
        for r in records
    )
    parts = [
        f'<div class="section"><h2>{h(heading)}</h2>',
    ]
    if note:
        parts.append(f'<p class="compare-intro">{h(note)}</p>')
    parts.append(
        _render_stage_summary_cards(stages, records, ref_id=ref_id, baseline=baseline)
    )
    if baseline:
        ref = next((r for r in records if r.get("id") == ref_id), None)
        ref_h = _round_heading(ref, ref_id=ref_id, baseline=True) if ref else f"#{ref_id}"
        parts.append(
            f'<p class="compare-intro">变化率相对<strong>{h(ref_h)}</strong>；'
            f'<span class="pct-better">绿色偏好转</span>，'
            f'<span class="pct-worse">红色偏变差</span>。</p>'
        )

    for stage in stages:
        if not isinstance(stage, dict):
            continue
        label = stage.get("label") or f"第 {stage.get('stage')} 阶段"
        stage_num = stage.get("stage") or ""
        tone = _stage_card_tone(stage, ref_id=ref_id, records=records, baseline=baseline)
        parts.append(
            f"<div class='stage-detail-head {tone}'>"
            f"<span class='stage-idx' style='display:inline-flex;align-items:center;justify-content:center;"
            f"min-width:22px;height:22px;padding:0 6px;border-radius:999px;background:#1a73e8;color:#fff;"
            f"font-size:11px;font-weight:700'>{h(stage_num)}</span>"
            f"<h3 class='stage-detail-title'>{h(label)}</h3>"
            f"</div>"
        )
        rows_html = []
        for m in stage.get("metrics") or []:
            if not isinstance(m, dict):
                continue
            mkey = str(m.get("key") or "")
            cells = []
            for r in records:
                rid = str(r.get("id"))
                val = (m.get("values") or {}).get(rid)
                pct = (m.get("change_pct") or {}).get(rid) if baseline else None
                lib = m.get("lower_is_better")
                if lib is None:
                    pct_html = ""
                    if baseline and r.get("id") != ref_id and pct is not None:
                        try:
                            pct_html = (
                                f' <span class="pct-flat" style="font-size:12px">'
                                f"({float(pct):+g}%)</span>"
                            )
                        except (TypeError, ValueError):
                            pct_html = ""
                else:
                    pct_html = pct_span(
                        pct,
                        ref=(baseline and r.get("id") == ref_id),
                        metric_key=mkey,
                        lower_is_better=lib,
                    )
                cells.append(
                    f"<td class='num'>{_fmt_stage_metric_val(mkey, val)}{pct_html}</td>"
                )
            rows_html.append(
                f"<tr><td>{h(m.get('label') or mkey)}</td>{''.join(cells)}</tr>"
            )
        if rows_html:
            parts.append(
                f"<table class='stage-table'><thead><tr><th>指标</th>{header_cols}</tr></thead>"
                f"<tbody>{''.join(rows_html)}</tbody></table>"
            )
    parts.append("</div>")
    return "".join(parts)


def _fallback_metric_note(
    *,
    label: str,
    pct: float,
    lower_is_better: Optional[bool],
) -> str:
    """无 AI 短评时的可读兜底，避免「较参照轮 x% · 更差」填空感。"""
    name = (label or "该指标").strip()
    mag = abs(float(pct))
    if mag < 0.5:
        return f"{name}与参照轮基本持平"
    # 中性指标不做好坏判断，只陈述变化幅度
    if lower_is_better is None:
        return f"{name}较参照轮变化 {float(pct):+g}%"
    tone = pct_tone(pct, lower_is_better=lower_is_better)
    if tone == "flat":
        return f"{name}与参照轮基本持平"
    if tone == "better":
        return f"{name}较参照轮改善约 {mag:g}%"
    if tone == "worse":
        return f"{name}较参照轮恶化约 {mag:g}%"
    return f"{name}较参照轮变化 {float(pct):+g}%"


def _render_metric_compare_section(snap: dict, ai: dict, *, heading: str) -> str:
    records = snap.get("records") or []
    metrics = snap.get("metric_compare") or []
    ref_id = snap.get("reference_record_id")
    baseline = bool(snap.get("baseline_enabled", True))
    if not metrics:
        return ""

    header_cols = "".join(
        f"<th>{h(_round_heading(r, ref_id=ref_id, baseline=baseline))}</th>"
        for r in records
    )
    metric_key_to_note = {
        "qps": "qps",
        "avg_response_time": "avg_rt",
        "p95_response_time": "p95",
        "error_rate": "error_rate",
        "total_requests": "total_requests",
        "success_qps": "success_qps",
    }
    metric_rows = []
    for m in metrics:
        mkey = m.get("key") or ""
        lib = m.get("lower_is_better")
        if lib is None:
            lib = metric_lower_is_better(mkey)
        cells = []
        for r in records:
            rid = str(r.get("id"))
            val = (m.get("values") or {}).get(rid, "-")
            pct = (m.get("change_pct") or {}).get(rid) if baseline else None
            if mkey in ("avg_response_time", "p95_response_time"):
                val_html = _fmt_ms(val) if val not in ("-", None) else "-"
            elif str(mkey).startswith("phase_"):
                try:
                    val_html = f"{h(round(float(val), 3))}<span class='unit'>s</span>" if val not in ("-", None) else "-"
                except (TypeError, ValueError):
                    val_html = h(val)
            elif mkey in ("qps", "success_qps"):
                val_html = _fmt_qps(val) if val not in ("-", None) else "-"
            elif mkey == "error_rate":
                val_html = f"{h(val)}<span class='unit'>%</span>" if val not in ("-", None) else "-"
            elif mkey == "total_requests":
                val_html = f"{h(val)}<span class='unit'>次</span>" if val not in ("-", None) else "-"
            else:
                val_html = h(val)
            cells.append(
                f"<td class='num'>{val_html}{pct_span(pct, ref=(baseline and r.get('id') == ref_id), metric_key=mkey, lower_is_better=lib)}</td>"
            )
        note_key = metric_key_to_note.get(mkey, mkey if str(mkey).startswith("phase_") else "")
        mnote = metric_note(ai, note_key) if note_key else ""
        if not mnote and str(mkey).startswith("phase_"):
            mnote = metric_note(ai, mkey)
        if not mnote:
            if baseline:
                diffs = []
                for r in records:
                    if r.get("id") == ref_id:
                        continue
                    pct = (m.get("change_pct") or {}).get(str(r.get("id")))
                    if pct is not None:
                        try:
                            diffs.append(
                                _fallback_metric_note(
                                    label=str(m.get("label") or mkey),
                                    pct=float(pct),
                                    lower_is_better=lib if isinstance(lib, bool) else None,
                                )
                            )
                        except (TypeError, ValueError):
                            pass
                mnote = "；".join(diffs) if diffs else "—"
            else:
                mnote = "并排观察（未计算变化率）"
        note_html = (
            "—"
            if mnote in ("—", "")
            else colorize_pct_in_text(
                mnote,
                metric_key=str(mkey),
                lower_is_better=lib if isinstance(lib, bool) else metric_lower_is_better(mkey),
            )
        )
        metric_rows.append(
            f"<tr><td>{h(m.get('label'))}</td>{''.join(cells)}"
            f"<td class='metric-note-cell'>{note_html}</td></tr>"
        )
    analysis_h = "解读" if baseline else "说明"
    intro = ""
    if baseline:
        ref = next((r for r in records if r.get("id") == ref_id), None)
        ref_h = _round_heading(ref, ref_id=ref_id, baseline=True) if ref else f"#{ref_id}"
        intro = (
            f'<p class="compare-intro">百分比相对<strong>{h(ref_h)}</strong>；'
            f'<span class="pct-better">绿色偏好转</span>，'
            f'<span class="pct-worse">红色偏变差</span>。</p>'
        )
    return f"""
  <div class="section">
    <h2>{h(heading)}</h2>
    {intro}
    <table>
      <thead><tr><th>指标</th>{header_cols}<th>{analysis_h}</th></tr></thead>
      <tbody>{''.join(metric_rows)}</tbody>
    </table>
  </div>"""


def _render_delta_highlight(snap: dict, *, heading: str = "二、差异速览") -> str:
    """把相对参照轮的关键变化提到前面，用大数字展示。"""
    records = snap.get("records") or []
    metrics = snap.get("metric_compare") or []
    ref_id = snap.get("reference_record_id")
    baseline = bool(snap.get("baseline_enabled", True))
    if not baseline or len(records) < 2 or not metrics:
        return ""

    ref = next((r for r in records if r.get("id") == ref_id), None)
    others = [r for r in records if r.get("id") != ref_id]
    if not ref or not others:
        return ""

    by_key = {m.get("key"): m for m in metrics if isinstance(m, dict)}
    focus = [
        ("qps", "QPS"),
        ("avg_response_time", "平均 RT"),
        ("p95_response_time", "P95"),
        ("error_rate", "错误率"),
        ("total_requests", "总请求"),
    ]
    # 追加阶段/派生耗时（优先整体耗时、问答耗时）
    phase_metrics = [m for m in metrics if isinstance(m, dict) and str(m.get("key") or "").startswith("phase_mean_")]
    phase_metrics.sort(
        key=lambda m: (
            0 if "total_time" in str(m.get("key") or "") else
            (1 if "answer" in str(m.get("key") or "").lower() else 2),
            str(m.get("label") or ""),
        )
    )
    for m in phase_metrics[:6]:
        focus.append((m.get("key"), m.get("label") or m.get("key")))

    blocks = []
    for other in others:
        rid = str(other.get("id"))
        cards = []
        for key, label in focus:
            m = by_key.get(key) or {}
            vals = m.get("values") or {}
            pcts = m.get("change_pct") or {}
            cur = vals.get(rid)
            base = vals.get(str(ref_id))
            pct = pcts.get(rid)
            if pct is None and cur is None:
                continue
            lib = m.get("lower_is_better")
            if lib is None:
                lib = metric_lower_is_better(key)
            tone = pct_tone(pct, lower_is_better=lib)
            pct_txt = f"{float(pct):+g}%" if pct is not None else "—"
            if key == "error_rate":
                unit = "%"
            elif key in ("avg_response_time", "p95_response_time"):
                unit = "ms"
            elif str(key).startswith("phase_"):
                unit = "s"
            elif key == "qps":
                unit = "/s"
            elif key == "total_requests":
                unit = "次"
            else:
                unit = ""
            if unit == "s" and base is not None:
                try:
                    base_s = f"{round(float(base), 3)} s"
                    cur_s = f"{round(float(cur), 3)} s" if cur is not None else "—"
                except (TypeError, ValueError):
                    base_s = f"{base}"
                    cur_s = f"{cur}"
            else:
                base_s = f"{base}{(' ' + unit) if unit and base is not None else ''}"
                cur_s = f"{cur}{(' ' + unit) if unit and cur is not None else ''}"
            label_u = f"{label}" + (f" ({unit})" if unit and key != "error_rate" and not str(key).startswith("phase_") else "")
            cards.append(
                f"""<div class="delta-card {tone}">
                  <div class="delta-label">{h(label_u if key != 'error_rate' else label)}</div>
                  <div class="delta-pct {tone}">{h(pct_txt)}</div>
                  <div class="delta-vals">参照 {h(base_s)} → 本轮 {h(cur_s)}</div>
                </div>"""
            )
        if not cards:
            continue
        blocks.append(
            f"""<div style="margin-bottom:14px">
              <p style="font-size:13px;color:#334155;margin-bottom:8px">
                <span class="tag round-cmp">对比轮</span>
                <strong style="margin-left:8px">{h(_round_heading(other, ref_id=ref_id, baseline=True))}</strong>
                <span style="color:#94a3b8;margin:0 6px">相对</span>
                <span class="tag round-ref">参照轮</span>
                <strong style="margin-left:8px">{h(_round_heading(ref, ref_id=ref_id, baseline=True))}</strong>
              </p>
              <div class="delta-grid">{''.join(cards)}</div>
            </div>"""
        )

    if not blocks:
        return ""

    intro = (
        '<p class="compare-intro">相对参照轮的关键变化一览。</p>'
    )
    return f"""
  <div class="section">
    <h2>{h(heading)}</h2>
    {intro}
    {''.join(blocks)}
  </div>"""


def _pct_line(
    pct,
    *,
    ref: bool = False,
    metric_key: str = "",
) -> str:
    span = pct_span(pct, ref=ref, metric_key=metric_key).strip()
    if not span:
        return ""
    return f"<div class='pct-line'>{span}</div>"


def _render_case_compare_section(snap: dict, ai: dict, *, heading: str) -> str:
    records = snap.get("records") or []
    ref_id = snap.get("reference_record_id")
    baseline = bool(snap.get("baseline_enabled", True))
    notes_by_case = case_note_map(ai)
    case_rows = (snap.get("case_compare") or [])[:40]
    if not case_rows:
        return ""
    if not baseline:
        # 未启用基准时不做用例对照表（由分章展示）
        return ""

    common_n = snap.get("case_common_count")
    if common_n is None:
        common_n = sum(1 for c in case_rows if c.get("coverage") == "common")
    hint = ""
    if common_n and common_n < len(case_rows):
        hint = (
            f'<p class="compare-intro">'
            f"按接口名对齐：共有 {common_n} 个；其余为某轮独有。</p>"
        )
    elif all((c.get("coverage") == "common") for c in case_rows):
        hint = (
            '<p class="compare-intro">'
            "各轮共有接口；Avg / P95 单位 ms，变化率在数值下方。</p>"
        )

    case_rows_html = []
    for c in case_rows:
        name = c.get("name") or "未命名接口"
        cnote = notes_by_case.get(name, "")
        cov = c.get("coverage") or ""
        badge = (
            ' <span class="tag tag-blue" style="font-weight:500">共有</span>'
            if cov == "common"
            else ' <span class="tag tag-orange" style="font-weight:500">独有</span>'
        )
        name_cell = h(name) + badge + (f'<div class="case-note">{h(cnote)}</div>' if cnote else "")
        cells = [f'<td class="case-name-col">{name_cell}</td>']
        ref_vals = (c.get("values") or {}).get(str(ref_id)) or {}
        for gi, r in enumerate(records):
            if gi > 0:
                cells.append('<td class="case-g-gap"></td>')
            rid = str(r.get("id"))
            is_ref = r.get("id") == ref_id
            g_cls = "case-g-ref" if is_ref else "case-g-cmp"
            v = (c.get("values") or {}).get(rid) or {}
            present = v.get("present")
            if present is None:
                present = not (
                    (v.get("total") in (0, None))
                    and (v.get("avg_rt") in (0, None))
                    and (v.get("p95_rt") in (0, None))
                )
            if not present:
                cells.append(
                    f"<td colspan='4' class='{g_cls}' "
                    f"style='text-align:center;color:#94a3b8;font-size:12px'>本轮无此接口</td>"
                )
                continue
            avg, p95, err, n = v.get("avg_rt"), v.get("p95_rt"), v.get("error_rate"), v.get("total")
            avg_pct = p95_pct = None
            if r.get("id") != ref_id and ref_vals:
                ref_present = ref_vals.get("present")
                if ref_present is None:
                    ref_present = not (
                        (ref_vals.get("total") in (0, None))
                        and (ref_vals.get("avg_rt") in (0, None))
                    )
                if ref_present:
                    try:
                        base_avg = float(ref_vals.get("avg_rt") or 0)
                        cur_avg = float(avg or 0)
                        avg_pct = None if base_avg == 0 and cur_avg == 0 else (
                            0.0 if base_avg == 0 else round((cur_avg - base_avg) / base_avg * 100, 2)
                        )
                        base_p95 = float(ref_vals.get("p95_rt") or 0)
                        cur_p95 = float(p95 or 0)
                        p95_pct = None if base_p95 == 0 and cur_p95 == 0 else (
                            0.0 if base_p95 == 0 else round((cur_p95 - base_p95) / base_p95 * 100, 2)
                        )
                    except (TypeError, ValueError):
                        pass
            cells.append(
                f"<td class='{g_cls} case-m-avg num'>{_fmt_ms(avg)}"
                f"{_pct_line(avg_pct, ref=is_ref, metric_key='avg_rt')}</td>"
                f"<td class='{g_cls} case-m-p95 num'>{_fmt_ms(p95)}"
                f"{_pct_line(p95_pct, ref=is_ref, metric_key='p95_rt')}</td>"
                f"<td class='{g_cls} case-m-err'>{err_tag(err)}</td>"
                f"<td class='{g_cls} case-m-n num'>{h(n)}</td>"
            )
        case_rows_html.append(f"<tr>{''.join(cells)}</tr>")

    sub_headers = []
    sub_cols = []
    for gi, r in enumerate(records):
        if gi > 0:
            sub_headers.append('<th class="case-g-gap" rowspan="2"></th>')
        is_ref = r.get("id") == ref_id
        g_cls = "case-g-ref" if is_ref else "case-g-cmp"
        sub_cls = "case-g-sub-ref" if is_ref else "case-g-sub-cmp"
        role = "参照轮" if is_ref else "对比轮"
        name = _rec_label(r)
        t = _short_time(r.get("started_at"))
        sub_line = f"#{r.get('id')}" + (f" · {t}" if t else "") + f" · {name}"
        sub_headers.append(
            f"<th colspan='4' class='{g_cls}'>"
            f"<span class='tag {'round-ref' if is_ref else 'round-cmp'}'>{h(role)}</span>"
            f"<div style='margin-top:6px;font-size:12px;font-weight:600;line-height:1.35'>"
            f"{h(sub_line)}</div></th>"
        )
        sub_cols.append(
            f"<th class='{sub_cls} case-m-avg'>Avg <span class='unit'>(ms)</span></th>"
            f"<th class='{sub_cls} case-m-p95'>P95 <span class='unit'>(ms)</span></th>"
            f"<th class='{sub_cls} case-m-err'>错误率</th>"
            f"<th class='{sub_cls} case-m-n'>次数</th>"
        )
    return f"""
  <div class="section">
    <h2>{h(heading)}</h2>
    {hint}
    <div style="overflow-x:auto">
    <table class="case-cmp-table">
      <thead>
        <tr><th rowspan="2" class="case-name-col">接口</th>{''.join(sub_headers)}</tr>
        <tr>{''.join(sub_cols)}</tr>
      </thead>
      <tbody>{''.join(case_rows_html)}</tbody>
    </table>
    </div>
  </div>"""


def _chapter_load_line(cfg: dict | None) -> str:
    """分章页眉：并发/梯度摘要。"""
    cfg = cfg or {}
    mode = str(cfg.get("mode") or "")
    if mode == "stepping":
        try:
            from app.routers.perf.report_utils import peak_users_from_config, format_steps_summary
            peak = peak_users_from_config(cfg)
            summary = format_steps_summary(cfg)
            if peak is not None and summary:
                return f"峰值并发 {peak}（{summary}）"
            if peak is not None:
                return f"峰值并发 {peak}"
        except Exception:
            pass
    cu = cfg.get("concurrent_users")
    if cu is not None and cu != "":
        return f"并发 {cu}"
    return ""


def _scrub_ai_for_snap(ai: Any, snap: dict) -> dict:
    raw = ai if isinstance(ai, dict) else {}
    try:
        from app.modules.perf.perf_ai_analyze import metric_label_map_from_snapshot, scrub_ai_payload
        return scrub_ai_payload(dict(raw), metric_label_map_from_snapshot(snap))
    except Exception:
        return raw


def _render_merge_html(report: Any) -> str:
    snap = report.snapshot or {}
    records = snap.get("records") or []
    chapters = snap.get("chapters") or []
    overview = snap.get("overview_table") or []
    ai = _scrub_ai_for_snap(report.ai_analysis or {}, snap)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    note = snap.get("note") or "各场景分章展示；顶层指标并排，不计算变化率。"

    overview_header = "".join(
        f"<th>{h(_rec_label(r))}<br/><span style='font-weight:400;font-size:12px'>#{h(r.get('id'))}</span></th>"
        for r in records
    )
    overview_rows = []
    for m in overview:
        key = m.get("key") or ""
        note_key = {
            "qps": "qps", "avg_response_time": "avg_rt", "p95_response_time": "p95",
            "error_rate": "error_rate", "total_requests": "total_requests", "success_qps": "success_qps",
        }.get(key, "")
        mnote = metric_note(ai, note_key) if note_key else ""
        if not mnote and str(key).startswith("phase_"):
            mnote = metric_note(ai, key)
        cells = "".join(f"<td class='num'>{h((m.get('values') or {}).get(str(r.get('id')), '-'))}</td>" for r in records)
        overview_rows.append(
            f"<tr><td>{h(m.get('label'))}</td>{cells}"
            f"<td class='metric-note-cell'>{h(mnote) if mnote else '—'}</td></tr>"
        )

    conclusion = _ai_conclusion(
        ai,
        fallback_html=(
            f"<p>共汇总 {len(chapters)} 个章节，请按章节查看各轮表现。</p>"
        ) if records else "",
    )
    by_id = _records_by_id(snap)
    chapters_html, chart_scripts = _render_chapters_html(chapters, ai, by_id, start_idx=2)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{h(report.title)}</title>
{report_css()}
</head>
<body>
{report_edit_chrome()}
<div class="container" id="reportRoot" contenteditable="true">
  <div class="header">
    <h1>{h(report.title)}</h1>
    <div class="meta">
      <span>汇总报告</span>
      <span>导出时间：{h(generated)}</span>
    </div>
  </div>
  <div class="section">
    <h2>一、测试概览</h2>
    {render_overview_para(ai)}
    <p class="compare-intro">{h(note)}</p>
    <table>
      <thead><tr><th>指标</th>{overview_header}<th>解读</th></tr></thead>
      <tbody>{''.join(overview_rows) or '<tr><td colspan="99">无数据</td></tr>'}</tbody>
    </table>
  </div>
  {chapters_html}
  <div class="section">
    <h2>总结论与建议</h2>
    {conclusion}
  </div>
  {render_metric_glossary()}
  <div class="footer">BrickCore 性能测试汇总报告 — {h(generated)}</div>
</div>
{chart_scripts}
</body>
</html>"""


def _render_compare_html(report: Any, *, hybrid: bool = False) -> str:
    snap = report.snapshot or {}
    records = snap.get("records") or []
    ref_id = snap.get("reference_record_id")
    baseline = bool(snap.get("baseline_enabled", True))
    ai = _scrub_ai_for_snap(report.ai_analysis or {}, snap)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    kind_label = _kind_title(REPORT_KIND_HYBRID if hybrid else REPORT_KIND_COMPARE)
    note = snap.get("note") or ""

    overview_bits = []
    ref_rec = next((x for x in records if baseline and x.get("id") == ref_id), None)
    for r in records:
        role = _round_role(r, ref_id=ref_id, baseline=baseline)
        tag_cls = "round-ref" if (baseline and r.get("id") == ref_id) else ("round-cmp" if baseline else "tag-blue")
        cfg = r.get("config_snapshot") or {}
        dur_cfg_html = _duration_config_cell_html(cfg)
        dur_row = (
            f"<tr><td>时长配置</td><td>{dur_cfg_html}</td></tr>"
            if dur_cfg_html is not None
            else ""
        )
        is_ref = baseline and ref_rec is not None and r.get("id") == ref_id
        if baseline and ref_rec is not None and not is_ref:
            dur_cls = _metric_tone_cls(r.get("duration"), ref_rec.get("duration"), lower_is_better=True)
            avg_cls = _metric_tone_cls(r.get("avg_response_time"), ref_rec.get("avg_response_time"), lower_is_better=True)
            p95_cls = _metric_tone_cls(r.get("p95_response_time"), ref_rec.get("p95_response_time"), lower_is_better=True)
        else:
            dur_cls = avg_cls = p95_cls = ""
        panel_cls = "is-ref" if (baseline and r.get("id") == ref_id) else ("is-cmp" if baseline else "")
        overview_bits.append(f"""
        <div class="overview-panel {panel_cls}">
          <p style="margin-bottom:8px"><span class="tag {tag_cls}">{h(role)}</span>
            <strong style="margin-left:8px">{h(_rec_label(r))}</strong>
            <span style="color:#666;font-size:12px;margin-left:6px">#{h(r.get('id'))}
            · {_short_time(r.get('started_at')) or '-'}</span>
          </p>
          <table class="config-table">
            <tr><td>并发用户</td><td>{_concurrent_config_cell_html(cfg)}</td></tr>
            <tr><td>模式</td><td>{h(_mode_label(cfg.get('mode')))}</td></tr>
            <tr><td>Ramp-up <span title="从 0 到目标并发的爬升时间；0 表示立即达到目标并发" style="cursor:help;color:#94a3b8">(?)</span></td><td>{h(cfg.get('ramp_up_seconds') or 0)}s</td></tr>
            {dur_row}
            <tr><td>预热 <span title="统计 Avg/P95 时剔除开始一段时间的样本，降低冷启动噪声" style="cursor:help;color:#94a3b8">(?)</span></td><td>{h(cfg.get('warmup_seconds') or 0)}s</td></tr>
            <tr><td>实际时长</td><td><span class="{dur_cls}">{h(r.get('duration'))}s</span></td></tr>
            <tr><td>开始 / 结束</td><td>{h(r.get('started_at'))} ~ {h(r.get('ended_at') or '-')}</td></tr>
            <tr><td>请求 / 成功 / 失败</td><td>{h(r.get('total_requests'))} / {h(r.get('success_count'))} / {h(r.get('fail_count'))}</td></tr>
            <tr><td>Avg / P95</td><td><span class="{avg_cls}">{h(r.get('avg_response_time'))} ms</span> / <span class="{p95_cls}">{h(r.get('p95_response_time'))} ms</span></td></tr>
          </table>
        </div>""")

    by_id = _records_by_id(snap)
    chapters = list(snap.get("chapters") or [])
    if not chapters:
        chapters = _chapters_from_snap_records(records)

    # 对比主体前置：差异 → 指标表 → 用例表；各轮详细画像后置；叠图对比 → 结论
    has_delta = baseline and len(records) >= 2 and bool(snap.get("metric_compare"))
    sec_n = 2
    delta_html = ""
    if has_delta:
        delta_html = _render_delta_highlight(snap, heading=f"{_cn_num(sec_n)}、差异速览")
        sec_n += 1

    sec_metric = (
        f"{_cn_num(sec_n)}、{'指标对照' if baseline else '指标并排'}"
        if hybrid
        else f"{_cn_num(sec_n)}、{'核心指标对比' if baseline else '核心指标并排'}"
    )
    sec_n += 1

    stage_html = ""
    stage_block = snap.get("stepping_stage_compare")
    if isinstance(stage_block, dict) and (stage_block.get("stages") or []):
        sec_stage = f"{_cn_num(sec_n)}、梯度阶段对照"
        stage_html = _render_stepping_stage_compare_section(snap, heading=sec_stage)
        if stage_html:
            sec_n += 1

    sec_case = f"{_cn_num(sec_n)}、{'用例维度对照' if hybrid else '用例维度对比'}"
    case_html = _render_case_compare_section(snap, ai, heading=sec_case)
    if case_html:
        sec_n += 1

    chapters_html = ""
    chart_scripts = ""
    records_charts_html = ""
    n_ch = len(chapters)
    chapter_start = sec_n
    if hybrid and (snap.get("chapters") or []):
        chapters_html, chart_scripts = _render_chapters_html(
            snap.get("chapters") or [], ai, by_id, start_idx=chapter_start
        )
        sec_n += n_ch
    elif not hybrid and chapters:
        chapters_html, chart_scripts = _render_chapters_html(
            chapters, ai, by_id, start_idx=chapter_start
        )
        sec_n += n_ch
    else:
        records_charts_html, chart_scripts = _render_records_charts_section(
            records, ai, heading=f"{_cn_num(sec_n)}、各轮趋势与分布"
        )
        if records_charts_html:
            sec_n += 1

    # 多轮叠图对比（同图直观对照）
    overlay_labels = [
        _round_heading(r, ref_id=ref_id, baseline=baseline) for r in records
    ]
    overlay_html, overlay_scripts = render_compare_overlay_charts(
        records,
        labels=overlay_labels,
        heading=f"{_cn_num(sec_n)}、统计图对比",
        include_echarts=not bool(chart_scripts),
    )
    if overlay_html:
        chart_scripts = (chart_scripts or "") + (overlay_scripts or "")
        sec_n += 1

    sec_conclusion = f"{_cn_num(sec_n)}、结论与建议"

    metric_html = _render_metric_compare_section(snap, ai, heading=sec_metric)

    conclusion = _ai_conclusion(ai)
    if not conclusion and len(records) >= 2:
        best_qps = max(records, key=lambda x: float(x.get("qps") or 0))
        ref_label = next((_round_heading(r, ref_id=ref_id, baseline=baseline) for r in records if r.get("id") == ref_id), f"#{ref_id}")
        if baseline:
            extra = f"参照轮为 {h(ref_label)}。"
        else:
            extra = "本报告未计算相对变化率，请结合各轮画像阅读。"
        conclusion = f"""<div class="conclusion-box">
          <p><strong>规则摘要（未跑 AI）</strong></p>
          <p>QPS 最高：{h(_rec_label(best_qps))}（{h(best_qps.get('qps'))}）。{extra}</p>
        </div>"""

    ref_rec = next((r for r in records if r.get("id") == ref_id), None)
    if baseline and ref_rec:
        meta_ref = f"<span>参照轮：#{h(ref_rec.get('id'))} · {_short_time(ref_rec.get('started_at')) or h(_rec_label(ref_rec))}</span>"
    else:
        meta_ref = "<span>模式：并排（无相对变化率）</span>"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{h(report.title)}</title>
{report_css()}
</head>
<body>
{report_edit_chrome()}
<div class="container" id="reportRoot" contenteditable="true">
  <div class="header">
    <h1>{h(report.title)}</h1>
    <div class="meta">
      <span>{h(kind_label)}</span>
      {meta_ref}
      <span>导出时间：{h(generated)}</span>
    </div>
  </div>
  <div class="section">
    <h2>一、测试概览</h2>
    {render_overview_para(ai)}
    {f'<p class="compare-intro">{h(note)}</p>' if note else ''}
    <p style="color:#64748b;font-size:13px;margin-bottom:12px">
      <span class="pct-better">绿色偏好转</span>，<span class="pct-worse">红色偏变差</span>。
    </p>
    <div class="overview-panels">{''.join(overview_bits)}</div>
  </div>
  {delta_html}
  {metric_html}
  {stage_html}
  {case_html}
  {chapters_html}
  {records_charts_html}
  {overlay_html}
  <div class="section">
    <h2>{h(sec_conclusion)}</h2>
    {conclusion}
  </div>
  {render_metric_glossary()}
  <div class="footer">BrickCore 性能测试{h(kind_label)} — {h(generated)}</div>
</div>
{chart_scripts}
</body>
</html>"""


def _cn_num(n: int) -> str:
    mapping = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}
    return mapping.get(n, str(n))


def render_comparison_html(report: Any) -> str:
    snap = report.snapshot or {}
    kind = snap.get("kind") or getattr(report, "kind", None) or REPORT_KIND_COMPARE
    if kind == REPORT_KIND_MERGE:
        return _render_merge_html(report)
    if kind == REPORT_KIND_HYBRID:
        return _render_compare_html(report, hybrid=True)
    return _render_compare_html(report, hybrid=False)
