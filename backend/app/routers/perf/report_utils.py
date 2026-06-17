"""性能测试报告数据组装与衍生指标"""
import html as html_module
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.routers.perf.progress_utils import normalize_distribution_mode


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
    """趋势图当秒 P95：仅在该秒有完成请求时返回值，否则为 None（不连线）。"""
    if float(point.get("qps") or 0) <= 0:
        return None
    val = point.get("p95_rt")
    if val is None:
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


def build_previous_comparison(current: Any, previous: Any) -> Optional[dict]:
    """与同场景上一次执行记录对比"""
    if not previous:
        return None
    metrics = [
        ("qps", "QPS", False, lambda r: (r.total_requests or 0) / (r.duration or 1) if (r.duration or 0) > 0 else (r.qps or 0)),
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
    from app.routers.perf.case_agg_utils import MAX_CASE_RT_SAMPLES

    cfg = config or {}
    mode = cfg.get("mode", "fixed")
    from app.core.stream_phase import normalize_perf_mode, STREAM_BURST_MODE
    mode_labels = {
        "fixed": "固定模式", "loop": "循环模式", "stepping": "梯度模式",
        STREAM_BURST_MODE: "流式阶段压测", "sse_burst": "流式阶段压测",
        "journey_fixed": "链路固定模式", "journey_loop": "链路循环模式",
    }
    dist = normalize_distribution_mode(cfg.get("distribution_mode"))
    dist_label = "固定比例" if dist == "fixed_ratio" else "随机权重"

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
        steps = cfg.get("steps") or []
        duration_label = f"{len(steps)} 个阶段"

    dist_info = distribution_info or {}
    workers = dist_info.get("workers") or []
    is_distributed = bool(workers) or dist_info.get("is_distributed")

    detail_level = cfg.get("request_detail_level", "brief")
    detail_label = "详细（含成功请求接口信息）" if detail_level == "full" else "简略（失败仍含接口详情）"

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
        "request_detail_level": detail_level,
        "request_detail_level_label": detail_label,
        "case_rt_sample_limit": MAX_CASE_RT_SAMPLES,
        "case_rt_sample_note": (
            f"接口维度 P90/P95/P99 等分位基于最多 {MAX_CASE_RT_SAMPLES} 条响应时间样本（蓄水池采样）；"
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
    journey_aggregations = {}
    if isinstance(raw_breakdown, dict):
        journey_aggregations = raw_breakdown.get("journey_aggregations") or {}
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
        "phase_metrics": getattr(record, "phase_metrics", None) or {},
        "request_details_total": len(getattr(record, "request_details", None) or []),
        "request_details": [],
        "request_traces_total": _count_http_trace_items(record),
        "request_traces": [],
        "stream_profile": (config.get("stream_profile") or {}),
        "journey_aggregations": journey_aggregations,
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
    from app.core.stream_phase import migrate_legacy_detail

    page = max(1, page)
    size = max(1, min(size, 100))
    status = status if status in ("all", "success", "fail") else "all"

    if kind == "stream":
        items = [migrate_legacy_detail(d) for d in (record.request_details or [])]
        if status == "success":
            items = [d for d in items if d.get("success")]
        elif status == "fail":
            items = [d for d in items if not d.get("success")]
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
            items = traces + failures

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


def _render_echarts_script_tag() -> str:
    js = _load_echarts_js_for_html()
    if not js:
        return '  <script src="https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js"></script>'
    return f"  <script>\n{js}\n  </script>"


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
    blocks: list[str] = []
    for label, key in (
        ("请求头", "request_headers_preview"),
        ("Query 参数", "request_params_preview"),
        ("请求 Body", "request_body_preview"),
        ("响应 / 流式内容", "response_body_preview"),
        ("思考过程", "thinking_preview"),
    ):
        val = item.get(key)
        if val:
            pre_cls = "trace-pre trace-pre-full" if key in ("thinking_preview", "response_body_preview") else "trace-pre"
            blocks.append(
                f'<div class="trace-block"><div class="trace-label">{_h(label)}</div>'
                f'<pre class="{pre_cls}">{_h(val)}</pre></div>'
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
    bd = record.error_breakdown or {}
    if not isinstance(bd, dict):
        return [], False
    traces = list(bd.get("request_traces") or [])
    failures = list(bd.get("failed_samples") or [])
    combined = traces + failures
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
    """错误分类与失败采样（无错误时不输出）。"""
    bd = record.error_breakdown or {}
    if not isinstance(bd, dict):
        return ""
    by_type = {k: v for k, v in (bd.get("by_type") or {}).items() if v}
    samples = (bd.get("failed_samples") or [])[:50]
    if not by_type and not samples:
        return ""

    type_map = {
        "timeout": "请求超时", "connection_error": "连接错误", "network_error": "网络错误",
        "server_error": "服务端错误(5xx)", "client_error": "客户端错误(4xx)",
        "assertion_failed": "断言失败", "unknown": "未知错误",
    }
    parts: list[str] = []
    if by_type:
        total_fail = record.fail_count or sum(by_type.values()) or 1
        err_type_rows = ""
        for etype, count in sorted(by_type.items(), key=lambda x: -x[1]):
            pct = round(count / total_fail * 100, 1) if total_fail > 0 else 0
            err_type_rows += f"<tr><td>{_h(type_map.get(etype, etype))}</td><td>{count}</td><td>{pct}%</td></tr>"
        parts.append(f"""
  <div class="section">
    <h2>错误分类统计</h2>
    <table>
      <thead><tr><th>错误类型</th><th>次数</th><th>占比</th></tr></thead>
      <tbody>{err_type_rows}</tbody>
    </table>
  </div>""")

    if samples:
        sample_rows = ""
        for idx, s in enumerate(samples, 1):
            sample_rows += f"""
        <tr>
            <td>{idx}</td>
            <td>{_h(s.get('case_name', '未知'))}</td>
            <td>{_h(s.get('user_id', '') or '-')}</td>
            <td class="col-text">{_h(s.get('question', '') or '-')}</td>
            <td>{_h(s.get('method', '') or '-')}</td>
            <td class="col-text">{_h(s.get('url', '') or '-')}</td>
            <td>{_h(s.get('status_code', 0))}</td>
            <td>{round(float(s.get('response_time', 0) or 0), 2)} ms</td>
            <td class="error-cell">{_h(s.get('error_msg', '') or '-')}</td>
        </tr>"""
            detail = _render_trace_detail_html(s)
            if detail:
                sample_rows += f'<tr class="trace-detail-row"><td colspan="9">{detail}</td></tr>'
        parts.append(f"""
  <div class="section">
    <h2>失败请求采样（前{len(samples)}条，含接口信息）</h2>
    <div class="table-scroll">
    <table>
      <thead><tr><th>#</th><th>用例名称</th><th>用户ID</th><th>问题</th><th>方法</th><th>URL</th><th>状态码</th><th>响应时间</th><th>错误详情</th></tr></thead>
      <tbody>{sample_rows}</tbody>
    </table>
    </div>
  </div>""")
    return "".join(parts)


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
    """流式阶段汇总 + 逐路请求明细（仅 stream 压测有数据时输出）。"""
    from app.core.stream_phase import detail_to_excel_row, migrate_legacy_detail

    details = [migrate_legacy_detail(d) for d in (record.request_details or [])]
    phase_metrics = record.phase_metrics or {}
    metrics = phase_metrics.get("metrics") or []
    if not details and not metrics:
        return ""

    parts: list[str] = []
    if metrics:
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


def render_perf_html_chart_parts(record: Any) -> tuple[str, str]:
    """导出 HTML 报告用：ECharts 趋势图 + RT 分布图。

    返回 (图表区块 HTML, 页脚脚本 HTML)。ECharts 内嵌至页脚脚本，导出文件可离线打开；
    脚本置于文档末尾，不阻塞上方表格渲染。
    """
    time_series = normalize_time_series_for_chart(
        record.time_series_data or [],
        overall_p95=getattr(record, "p95_response_time", None),
    )
    raw_breakdown = record.error_breakdown or {}
    rt_histogram = raw_breakdown.get("rt_histogram") if isinstance(raw_breakdown, dict) else None
    rt_histogram = rt_histogram or []

    if not time_series and not rt_histogram:
        return "", ""

    chart_payload = _json_for_html_script({
        "timeSeries": time_series,
        "summaryQps": record.qps,
        "summaryP95": record.p95_response_time,
        "histogram": rt_histogram,
    })

    sections = f"""
  <details class="section-fold">
    <summary>性能趋势图（点击展开）</summary>
    <div class="section">
    <div id="perfTrendChart" class="chart-box"></div>
    <p class="chart-hint">柱状图为该秒瞬时 QPS；折线为响应时间与错误率。图表库已内嵌，离线打开也可正常显示。</p>
    </div>
  </details>
  <details class="section-fold" id="histogramSectionWrap" style="display:none">
    <summary>响应时间分布（点击展开）</summary>
    <div class="section" id="histogramSection">
    <div id="perfHistogramChart" class="chart-box"></div>
    </div>
  </details>"""

    echarts_tag = _render_echarts_script_tag()
    scripts = f"""
  <script type="application/json" id="perf-chart-data">{chart_payload}</script>
{echarts_tag}
  <script>
  (function() {{
    function readData() {{
      var el = document.getElementById('perf-chart-data');
      if (!el) return null;
      try {{ return JSON.parse(el.textContent || ''); }} catch (e) {{ return null; }}
    }}
    function showChartError(msg) {{
      var el = document.getElementById('perfTrendChart');
      if (!el || el.getAttribute('data-chart-error')) return;
      el.setAttribute('data-chart-error', '1');
      el.innerHTML = '<p style="color:#999;text-align:center;padding:40px 0;">' + msg + '</p>';
    }}
    function initTrend(data) {{
      var el = document.getElementById('perfTrendChart');
      if (!el || !window.echarts || !data.timeSeries || !data.timeSeries.length) return;
      var ts = data.timeSeries;
      var chart = echarts.init(el);
      var xData = ts.map(function(d) {{ return (d.timestamp || 0) + 's'; }});
      var qpsData = ts.map(function(d) {{ return d.qps; }});
      var avgRtData = ts.map(function(d) {{ return d.avg_rt; }});
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
      chart.setOption({{
        tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
        legend: {{ data: ['QPS', '平均RT', 'P95 RT', '错误率', '并发用户数'], bottom: 0 }},
        grid: {{ left: '3%', right: '4%', bottom: '15%', top: '10%', containLabel: true }},
        xAxis: {{ type: 'category', boundaryGap: true, data: xData, name: '时间(秒)' }},
        yAxis: [
          {{ type: 'value', name: '响应时间(ms)', position: 'left' }},
          {{ type: 'value', name: 'QPS', position: 'right' }}
        ],
        series: [
          {{ name: 'QPS', type: 'bar', yAxisIndex: 1, data: qpsData, itemStyle: {{ color: '#91cc75', opacity: 0.7 }}, barMaxWidth: 20 }},
          {{ name: '平均RT', type: 'line', yAxisIndex: 0, data: avgRtData, smooth: true, itemStyle: {{ color: '#5470c6' }} }},
          {{ name: 'P95 RT', type: 'line', yAxisIndex: 0, data: p95RtData, connectNulls: false, smooth: true, itemStyle: {{ color: '#fac858' }}, lineStyle: {{ type: 'dashed' }}, markLine: p95MarkLine }},
          {{ name: '错误率', type: 'line', yAxisIndex: 1, data: errorRateData, smooth: true, itemStyle: {{ color: '#e6a23c' }} }},
          {{ name: '并发用户数', type: 'line', yAxisIndex: 1, data: usersData, smooth: true, itemStyle: {{ color: '#ee6666' }}, lineStyle: {{ type: 'dotted' }} }}
        ]
      }});
      window.addEventListener('resize', function() {{ chart.resize(); }});
    }}
    function initHistogram(data) {{
      var hist = data.histogram || [];
      if (!hist.length || !window.echarts) return;
      var wrap = document.getElementById('histogramSectionWrap');
      var el = document.getElementById('perfHistogramChart');
      if (!wrap || !el) return;
      wrap.style.display = 'block';
      hist.sort(function(a, b) {{ return (a.min || 0) - (b.min || 0); }});
      var chart = echarts.init(el);
      chart.setOption({{
        tooltip: {{ trigger: 'axis' }},
        grid: {{ left: '3%', right: '4%', bottom: '12%', containLabel: true }},
        xAxis: {{ type: 'category', data: hist.map(function(h) {{ return h.label + ' ms'; }}), axisLabel: {{ rotate: 35, fontSize: 11 }} }},
        yAxis: {{ type: 'value', name: '请求数' }},
        series: [{{ name: '请求数', type: 'bar', data: hist.map(function(h) {{ return h.count; }}), itemStyle: {{ color: '#5470c6', opacity: 0.85 }}, barMaxWidth: 40 }}]
      }});
      window.addEventListener('resize', function() {{ chart.resize(); }});
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
        document.querySelectorAll('details.section-fold').forEach(function(d) {{
          d.addEventListener('toggle', function() {{
            if (!d.open || !window.echarts) return;
            ['perfTrendChart', 'perfHistogramChart'].forEach(function(id) {{
              var el = document.getElementById(id);
              if (!el) return;
              var inst = echarts.getInstanceByDom(el);
              if (inst) inst.resize();
            }});
          }});
        }});
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


def render_perf_html_charts(record: Any) -> str:
    """兼容旧调用：图表区块与脚本合并（不推荐，会阻塞页面解析）。"""
    sections, scripts = render_perf_html_chart_parts(record)
    return sections + scripts
