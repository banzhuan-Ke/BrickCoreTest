"""压测结束：按施压窗切 chunk → 写入 perf_record_sut_metric。"""
from __future__ import annotations

import logging
from datetime import timedelta
from statistics import median
from typing import Any, Optional
from urllib.parse import quote, urlsplit

from app.core.infra.scheduler_lock import with_scheduler_lock
from app.core.platform.datetime_utils import now_app, now_epoch_ms
from app.models.perf import PerfRecord, PerfRecordSutMetric, SutMetricChunk, SutServer
from app.modules.perf.sut_metrics_store import (
    compact_phase_stats,
    downsample_series,
    flatten_chunks_to_points,
    resolve_sut_metrics_baseline_sec,
    summarize_series,
)
from app.modules.perf.sut_pressure_window import infer_pressure_window

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 5
REPORT_MAX_POINTS = 1200
# finalize 后延迟再切；与 grace force 并行，给结束后立即补传留时间
RESLICE_GRACE_MS = 120_000
RESLICE_RETRY_MS = 45_000
RESLICE_MAX_ATTEMPTS = 4
RESLICE_JOB_ID = "sut_metrics_reslice"


def _report_max_points(window_ms: int) -> int:
    """按 SoT 建议控制报告点数。"""
    if window_ms <= 0:
        return 300
    minutes = window_ms / 60_000
    if minutes <= 15:
        return min(REPORT_MAX_POINTS, max(60, int(window_ms / 1000) + 1))
    if minutes <= 60:
        return min(REPORT_MAX_POINTS, max(180, int(window_ms / 10_000) + 1))
    return min(REPORT_MAX_POINTS, max(240, int(window_ms / 30_000) + 1))


def infer_interval_sec(points: list[dict[str, Any]], *, default: int = DEFAULT_INTERVAL_SEC) -> int:
    """按相邻点中位间隔推断采样间隔（钳制到 2～60s，与采集器一致）。"""
    if len(points) < 2:
        return max(2, min(60, int(default)))
    deltas: list[float] = []
    prev = None
    for p in points:
        try:
            ts = int(p["ts_ms"])
        except (TypeError, ValueError, KeyError):
            continue
        if prev is not None and ts > prev:
            deltas.append((ts - prev) / 1000.0)
        prev = ts
    if not deltas:
        return max(2, min(60, int(default)))
    med = float(median(deltas))
    return max(2, min(60, int(round(med))))


def compute_coverage(
    points: list[dict[str, Any]],
    *,
    start_ms: int,
    end_ms: int,
    interval_sec: int = DEFAULT_INTERVAL_SEC,
) -> float:
    """点数覆盖率（兼容旧调用）；更完整的质量见 compute_coverage_quality。"""
    return float(
        compute_coverage_quality(
            points, start_ms=start_ms, end_ms=end_ms, interval_sec=interval_sec
        ).get("coverage")
        or 0.0
    )


def compute_coverage_quality(
    points: list[dict[str, Any]],
    *,
    start_ms: int,
    end_ms: int,
    interval_sec: int = DEFAULT_INTERVAL_SEC,
) -> dict[str, Any]:
    """
    覆盖与时间质量：
    - coverage: 点数 / 期望点数
    - bucket_coverage: 时间桶有点比例（可发现尾部空洞）
    - max_gap_sec / first_point_delay_sec / last_point_delay_sec
    - resolution_level: high|medium|low
    """
    empty = {
        "coverage": 0.0,
        "bucket_coverage": 0.0,
        "max_gap_sec": None,
        "first_point_delay_sec": None,
        "last_point_delay_sec": None,
        "resolution_level": "low",
        "expected_points": 0,
        "actual_points": 0,
    }
    if end_ms <= start_ms:
        return empty
    interval_ms = max(1000, int(interval_sec) * 1000)
    expected = max(1, int((end_ms - start_ms) / interval_ms) + 1)
    ts_list: list[int] = []
    for p in points:
        try:
            ts_list.append(int(p["ts_ms"]))
        except (TypeError, ValueError, KeyError):
            continue
    ts_list = sorted(set(ts_list))
    actual = len(ts_list)
    coverage = round(min(1.0, actual / expected), 4) if expected else 0.0

    bucket_count = max(1, int((end_ms - start_ms + interval_ms - 1) / interval_ms))
    hit = [False] * bucket_count
    for ts in ts_list:
        if ts < start_ms or ts > end_ms:
            continue
        idx = min(bucket_count - 1, max(0, int((ts - start_ms) / interval_ms)))
        hit[idx] = True
    bucket_coverage = round(sum(1 for x in hit if x) / bucket_count, 4)

    max_gap_sec: Optional[float] = None
    if len(ts_list) >= 2:
        gaps = [(ts_list[i] - ts_list[i - 1]) / 1000.0 for i in range(1, len(ts_list))]
        max_gap_sec = round(max(gaps), 3) if gaps else None
    elif actual == 0:
        max_gap_sec = round((end_ms - start_ms) / 1000.0, 3)

    first_delay = None
    last_delay = None
    if ts_list:
        first_delay = round(max(0.0, (ts_list[0] - start_ms) / 1000.0), 3)
        last_delay = round(max(0.0, (end_ms - ts_list[-1]) / 1000.0), 3)

    # 分辨率：间隔粗或桶覆盖差 → low
    if interval_sec > 30 or (actual > 0 and actual < max(3, expected * 0.15)):
        resolution = "low"
    elif interval_sec > 10 or bucket_coverage < 0.7:
        resolution = "medium"
    else:
        resolution = "high"

    return {
        "coverage": coverage,
        "bucket_coverage": bucket_coverage,
        "max_gap_sec": max_gap_sec,
        "first_point_delay_sec": first_delay,
        "last_point_delay_sec": last_delay,
        "resolution_level": resolution,
        "expected_points": expected,
        "actual_points": actual,
    }


def status_from_coverage(coverage: float, *, point_count: int) -> str:
    if point_count <= 0 or coverage <= 0:
        return "no_data"
    if coverage >= 0.9:
        return "complete"
    return "partial"


def status_from_quality(quality: dict[str, Any], *, point_count: int) -> str:
    coverage = float(quality.get("coverage") or 0)
    if point_count <= 0 or coverage <= 0:
        return "no_data"
    bucket = float(quality.get("bucket_coverage") or 0)
    resolution = str(quality.get("resolution_level") or "")
    if resolution == "low":
        return "low_resolution"
    # 点数够但时间空洞明显 → partial
    if coverage >= 0.9 and bucket >= 0.85:
        return "complete"
    if coverage >= 0.9 and bucket < 0.85:
        return "partial"
    return "partial"


def is_safe_http_url(url: Optional[str]) -> bool:
    s = (url or "").strip()
    if not s:
        return False
    try:
        parts = urlsplit(s)
    except Exception:
        return False
    return parts.scheme.lower() in ("http", "https") and bool(parts.netloc)


def validate_grafana_url_template(template: Optional[str]) -> Optional[str]:
    """
    校验 Grafana 深链模板。空串表示清除；非空必须为 http(s) 绝对 URL。
    抛 ValueError 供路由转 422。
    """
    if template is None:
        return None
    s = str(template).strip()
    if not s:
        return ""
    if len(s) > 1024:
        raise ValueError("Grafana 模板过长（上限 1024）")
    # 模板里可能含 {from_ms} 等，先替换成数字再验 scheme
    probe = s
    for k in ("from_ms", "to_ms", "from", "to", "server_id", "hostname", "name", "role"):
        probe = probe.replace("{" + k + "}", "1")
    if not is_safe_http_url(probe):
        raise ValueError("Grafana 模板仅允许 http/https 绝对 URL")
    return s


def build_grafana_url(
    template: Optional[str],
    *,
    from_ms: int,
    to_ms: int,
    server: Optional[SutServer] = None,
    role: str = "",
) -> Optional[str]:
    try:
        tpl = validate_grafana_url_template(template)
    except ValueError:
        return None
    if not tpl:
        return None
    hostname = (server.hostname if server else "") or ""
    name = (server.name if server else "") or ""
    sid = str(server.id) if server else ""
    mapping = {
        "from_ms": str(from_ms),
        "to_ms": str(to_ms),
        "from": str(from_ms),
        "to": str(to_ms),
        "server_id": sid,
        "hostname": quote(hostname, safe=""),
        "name": quote(name, safe=""),
        "role": quote(role or "", safe=""),
    }
    try:
        out = tpl
        for k, v in mapping.items():
            out = out.replace("{" + k + "}", v)
    except Exception:
        return None
    if not is_safe_http_url(out):
        return None
    return out


def aggregate_record_sut_status(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "none"
    statuses = [str(r.get("status") or "") for r in rows]
    if all(s == "complete" for s in statuses):
        return "complete"
    if any(s in ("complete", "partial", "low_resolution") for s in statuses):
        return "partial"
    return "failed"


async def slice_and_persist_sut_metrics(record: PerfRecord) -> dict[str, Any]:
    """
    压测收尾：切窗写快照。无绑定则 status=none。
    幂等：同一 record+server 覆盖更新。
    """
    cfg = record.config_snapshot if isinstance(record.config_snapshot, dict) else {}
    server_ids = cfg.get("sut_server_ids") or []
    if not isinstance(server_ids, list):
        server_ids = []
    try:
        server_ids = [int(x) for x in server_ids]
    except (TypeError, ValueError):
        server_ids = []

    if not server_ids:
        cfg["sut_metrics_status"] = "none"
        record.config_snapshot = cfg
        await record.save(update_fields=["config_snapshot"])
        return {"status": "none", "series": [], "pressure_window": None}

    window = infer_pressure_window(
        record.time_series_data,
        started_at=record.started_at,
        ended_at=record.ended_at,
        duration_sec=record.duration,
        load_started_ms=cfg.get("load_started_ms") or cfg.get("sut_load_started_ms"),
        load_stopped_ms=cfg.get("load_stopped_ms") or cfg.get("sut_load_stopped_ms"),
        drain_until_ms=cfg.get("drain_until_ms") or cfg.get("sut_drain_until_ms"),
    )
    start_ms = window.get("start_ms")
    end_ms = window.get("end_ms")
    if start_ms is None or end_ms is None:
        cfg["sut_metrics_status"] = "failed"
        cfg["sut_pressure_window"] = window
        cfg["sut_metrics_error"] = "pressure_window_unknown"
        record.config_snapshot = cfg
        await record.save(update_fields=["config_snapshot"])
        return {"status": "failed", "series": [], "pressure_window": window}

    # 角色映射：来自绑定快照
    snap = cfg.get("sut_binding_snapshot") if isinstance(cfg.get("sut_binding_snapshot"), dict) else {}
    role_by_server: dict[int, str] = {}
    for s in snap.get("servers") or []:
        if isinstance(s, dict) and s.get("id") is not None:
            try:
                role_by_server[int(s["id"])] = str(s.get("role") or s.get("bound_role") or "")
            except (TypeError, ValueError):
                pass
    for role, ids in (snap.get("by_role") or {}).items():
        for sid in ids or []:
            try:
                role_by_server.setdefault(int(sid), str(role))
            except (TypeError, ValueError):
                pass

    grafana_tpl = (
        (cfg.get("sut_grafana_url_template") or "").strip()
        or (snap.get("grafana_url_template") or "").strip()
        or None
    )

    servers = await SutServer.filter(id__in=server_ids)
    by_id = {s.id: s for s in servers}
    # 施压前基线回看（项目/平台可配，默认 5 分钟）
    baseline_sec = 300
    try:
        from app.modules.ai.ai_project_settings import load_ai_project_settings

        _settings = await load_ai_project_settings(int(record.project_id))
        baseline_sec = resolve_sut_metrics_baseline_sec(_settings)
    except Exception:
        baseline_sec = resolve_sut_metrics_baseline_sec(None)
    baseline_lookback_ms = int(baseline_sec) * 1000
    cfg["sut_baseline_sec"] = baseline_sec

    max_pts = _report_max_points(int(end_ms) - int(start_ms))
    series_out: list[dict[str, Any]] = []

    for sid in server_ids:
        server = by_id.get(sid)
        role = role_by_server.get(sid) or (server.role if server else "") or ""
        server_snapshot = {
            "id": sid,
            "name": server.name if server else f"server-{sid}",
            "hostname": (server.hostname if server else "") or "",
            "role": role,
            "host_info": (server.host_info if server and isinstance(server.host_info, dict) else {}) or {},
        }

        if not server or server.is_del:
            status = "offline"
            coverage = 0.0
            interval_sec = DEFAULT_INTERVAL_SEC
            points: list[dict[str, Any]] = []
            series: list[dict[str, Any]] = []
            summary = summarize_series([])
            summary["phases"] = {
                "baseline": {"from_ms": None, "to_ms": None, "lookback_sec": baseline_sec, **compact_phase_stats(None)},
                "during": {"from_ms": int(start_ms), "to_ms": int(end_ms), **compact_phase_stats(None)},
            }
            source = "agent"
        else:
            query_from = int(start_ms) - int(baseline_lookback_ms)
            chunks = await SutMetricChunk.filter(
                server_id=sid,
                start_ms__lte=int(end_ms),
                end_ms__gte=query_from,
            ).all()
            points = flatten_chunks_to_points(chunks, from_ms=int(start_ms), to_ms=int(end_ms))
            baseline_to = max(int(start_ms) - 1, query_from)
            baseline_points = flatten_chunks_to_points(
                chunks, from_ms=query_from, to_ms=baseline_to
            )
            # 「施压中」统计/覆盖率不含 drain 观察段，避免冷却期稀释 avg/max
            during_end_ms = int(end_ms)
            load_stop = window.get("load_stopped_ms")
            try:
                if load_stop is not None:
                    ls = int(load_stop)
                    if ls >= int(start_ms):
                        during_end_ms = min(ls, int(end_ms))
            except (TypeError, ValueError):
                during_end_ms = int(end_ms)
            during_points = (
                points
                if during_end_ms >= int(end_ms)
                else flatten_chunks_to_points(chunks, from_ms=int(start_ms), to_ms=during_end_ms)
            )
            interval_sec = infer_interval_sec(during_points or points, default=DEFAULT_INTERVAL_SEC)
            quality = compute_coverage_quality(
                during_points,
                start_ms=int(start_ms),
                end_ms=during_end_ms,
                interval_sec=interval_sec,
            )
            coverage = float(quality.get("coverage") or 0.0)
            status = status_from_quality(quality, point_count=len(during_points))
            # force 心跳延迟提示：首点晚于施压起点超过 25s（约一轮旧心跳）
            first_delay = quality.get("first_point_delay_sec")
            if (
                isinstance(first_delay, (int, float))
                and first_delay >= 25
                and window.get("note")
                and "force 生效延迟" not in str(window.get("note"))
            ):
                window = dict(window)
                window["note"] = (
                    f"{window.get('note')}；首个资源点晚于施压起点约 {first_delay:.0f}s"
                    "（可能为 force/心跳延迟，前段资源不可用）"
                )
            series = downsample_series(points, max_points=max_pts)
            for p in series:
                try:
                    p["rel_sec"] = round((int(p["ts_ms"]) - int(start_ms)) / 1000.0, 3)
                except (TypeError, ValueError, KeyError):
                    pass
            during_summary = summarize_series(during_points)
            summary = dict(during_summary)
            summary["coverage"] = coverage
            summary["interval_sec"] = interval_sec
            summary["raw_point_count"] = len(points)
            summary["during_point_count"] = len(during_points)
            summary["quality"] = quality
            baseline_summary = summarize_series(baseline_points)
            summary["phases"] = {
                "baseline": {
                    "from_ms": query_from,
                    "to_ms": baseline_to,
                    "lookback_sec": baseline_sec,
                    **compact_phase_stats(baseline_summary),
                },
                "during": {
                    "from_ms": int(start_ms),
                    "to_ms": during_end_ms,
                    **compact_phase_stats(during_summary),
                },
            }
            if during_end_ms < int(end_ms):
                drain_points = flatten_chunks_to_points(
                    chunks, from_ms=during_end_ms + 1, to_ms=int(end_ms)
                )
                summary["phases"]["drain"] = {
                    "from_ms": during_end_ms + 1,
                    "to_ms": int(end_ms),
                    **compact_phase_stats(summarize_series(drain_points)),
                }
            source = "agent"

        gurl = build_grafana_url(
            grafana_tpl,
            from_ms=int(start_ms),
            to_ms=int(end_ms),
            server=server,
            role=role,
        )
        if gurl and status == "no_data" and not points:
            source = "grafana_link"

        existing = await PerfRecordSutMetric.get_or_none(record_id=record.id, server_id=sid)
        payload = {
            "server_snapshot_json": server_snapshot,
            "series_json": series,
            "summary_json": summary,
            "source": source,
            "status": status,
            "coverage": coverage,
            "grafana_url": gurl,
        }
        if existing:
            for k, v in payload.items():
                setattr(existing, k, v)
            await existing.save()
            row_id = existing.id
        else:
            row = await PerfRecordSutMetric.create(
                record_id=record.id,
                server_id=sid,
                **payload,
            )
            row_id = row.id

        series_out.append(
            {
                "id": row_id,
                "server_id": sid,
                "role": role,
                "source": source,
                "display_name": server_snapshot["name"],
                "host_info": server_snapshot.get("host_info") or {},
                "series": series,
                "summary": summary,
                "coverage": coverage,
                "status": status,
                "grafana_url": gurl,
                "hostname": server_snapshot.get("hostname") or "",
                "interval_sec": interval_sec if server and not server.is_del else None,
            }
        )

    record_status = aggregate_record_sut_status(series_out)

    cfg["sut_metrics_status"] = record_status
    cfg["sut_pressure_window"] = window
    cfg.pop("sut_metrics_error", None)
    record.config_snapshot = cfg
    await record.save(update_fields=["config_snapshot"])

    return {
        "status": record_status,
        "series": series_out,
        "pressure_window": window,
    }


async def mark_sut_reslice_deadline(
    record: PerfRecord,
    *,
    grace_ms: int = RESLICE_GRACE_MS,
) -> None:
    """finalize 后登记延迟再切片时间（持久化，重启可恢复）。"""
    cfg = dict(record.config_snapshot or {}) if isinstance(record.config_snapshot, dict) else {}
    sids = cfg.get("sut_server_ids") or []
    if not isinstance(sids, list) or not sids:
        return
    cfg["sut_metrics_reslice_after_ms"] = now_epoch_ms() + max(0, int(grace_ms))
    cfg["sut_metrics_reslice_attempt"] = 0
    record.config_snapshot = cfg
    await record.save(update_fields=["config_snapshot"])


async def maybe_reslice_sut_metrics(
    record: PerfRecord,
    *,
    force: bool = False,
) -> bool:
    """
    若已到 reslice 截止（或 force），重新切片。
    若仍无数据/覆盖不足则再延期重试，避免「延后上报」与「一次性再切」竞态丢切片。
    """
    cfg = dict(record.config_snapshot or {}) if isinstance(record.config_snapshot, dict) else {}
    sids = cfg.get("sut_server_ids") or []
    if not isinstance(sids, list) or not sids:
        return False
    after = cfg.get("sut_metrics_reslice_after_ms")
    if after is None and not force:
        return False
    try:
        after_i = int(after) if after is not None else 0
    except (TypeError, ValueError):
        after_i = 0
    now = now_epoch_ms()
    if not force:
        if after_i and now < after_i:
            return False
    await slice_and_persist_sut_metrics(record)
    fresh = await PerfRecord.get_or_none(id=record.id)
    if fresh:
        cfg2 = dict(fresh.config_snapshot or {}) if isinstance(fresh.config_snapshot, dict) else {}
        try:
            attempt = int(cfg2.get("sut_metrics_reslice_attempt") or 0)
        except (TypeError, ValueError):
            attempt = 0
        status = str(cfg2.get("sut_metrics_status") or "")
        need_retry = status in ("no_data", "partial", "pending", "low_resolution", "failed")
        if force and after_i and now < after_i:
            # 提前刷新：保留截止，等定时再做最终切
            pass
        elif need_retry and attempt < RESLICE_MAX_ATTEMPTS:
            cfg2["sut_metrics_reslice_after_ms"] = now + RESLICE_RETRY_MS
            cfg2["sut_metrics_reslice_attempt"] = attempt + 1
            fresh.config_snapshot = cfg2
            await fresh.save(update_fields=["config_snapshot"])
            record.config_snapshot = cfg2
        else:
            cfg2.pop("sut_metrics_reslice_after_ms", None)
            cfg2.pop("sut_metrics_reslice_attempt", None)
            fresh.config_snapshot = cfg2
            await fresh.save(update_fields=["config_snapshot"])
            record.config_snapshot = cfg2
    return True


async def mark_sut_slice_failed(record: PerfRecord, *, error: str) -> None:
    cfg = dict(record.config_snapshot or {}) if isinstance(record.config_snapshot, dict) else {}
    if not (cfg.get("sut_server_ids") or []):
        return
    cfg["sut_metrics_status"] = "failed"
    cfg["sut_metrics_error"] = (error or "slice_failed")[:500]
    record.config_snapshot = cfg
    await record.save(update_fields=["config_snapshot"])


@with_scheduler_lock("scheduler:sut_reslice", expire_seconds=120)
async def reslice_due_sut_metrics_job(job_id: str = RESLICE_JOB_ID) -> dict[str, int]:
    """扫描近 2 小时内需延迟再切片的压测记录。

    只取 id + config_snapshot，避免把 PerfRecord 大字段（结果 JSON 等）整行拖进内存；
    低配机 MySQL mem_limit 较紧时，全量 SELECT 易触发 mysqld OOM → 2013 Lost connection。
    """
    since = now_app() - timedelta(hours=2)
    rows = await PerfRecord.filter(
        status__in=["success", "failed", "stopped"],
        ended_at__gte=since,
    ).limit(200).values("id", "config_snapshot")
    now = now_epoch_ms()
    done = 0
    for row in rows:
        cfg = row.get("config_snapshot") if isinstance(row.get("config_snapshot"), dict) else {}
        after = cfg.get("sut_metrics_reslice_after_ms")
        if after is None:
            continue
        try:
            if now < int(after):
                continue
        except (TypeError, ValueError):
            continue
        rec = await PerfRecord.get_or_none(id=row["id"])
        if rec is None:
            continue
        try:
            if await maybe_reslice_sut_metrics(rec, force=False):
                done += 1
        except Exception:
            logger.exception("延迟切片失败 record_id=%s", rec.id)
            try:
                await mark_sut_slice_failed(rec, error="reslice_failed")
            except Exception:
                pass
    if done:
        logger.info("[sut_metrics_reslice] done=%s", done)
    return {"resliced": done}


def register_sut_metrics_reslice_job(scheduler) -> None:
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(
        reslice_due_sut_metrics_job,
        trigger=IntervalTrigger(seconds=30),
        id=RESLICE_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        kwargs={"job_id": RESLICE_JOB_ID},
    )


async def load_sut_resource_series(record_id: int) -> list[dict[str, Any]]:
    rows = await PerfRecordSutMetric.filter(record_id=record_id).prefetch_related("server").all()
    out: list[dict[str, Any]] = []
    for r in rows:
        snap = r.server_snapshot_json if isinstance(r.server_snapshot_json, dict) else {}
        summary = r.summary_json if isinstance(r.summary_json, dict) else {}
        out.append(
            {
                "id": r.id,
                "server_id": r.server_id,
                "role": snap.get("role") or "",
                "source": r.source or "agent",
                "display_name": snap.get("name") or (r.server.name if r.server else f"server-{r.server_id}"),
                "host_info": snap.get("host_info") or {},
                "hostname": snap.get("hostname") or "",
                "series": r.series_json if isinstance(r.series_json, list) else [],
                "summary": summary,
                "coverage": r.coverage,
                "status": r.status,
                "grafana_url": r.grafana_url if is_safe_http_url(r.grafana_url) else None,
                "interval_sec": summary.get("interval_sec"),
                "raw_point_count": summary.get("raw_point_count"),
            }
        )
    return out
