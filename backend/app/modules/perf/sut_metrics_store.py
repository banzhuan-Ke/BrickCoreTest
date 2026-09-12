"""被测服务器指标 chunk 查询与过期清理。"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Optional

from app.core.infra.scheduler_lock import with_scheduler_lock
from app.core.platform.datetime_utils import now_app
from app.models.perf import SutMetricChunk, SutServer

logger = logging.getLogger(__name__)

PURGE_JOB_ID = "sut_metric_chunk_purge"
DEFAULT_RETAIN_DAYS = 14
MAX_SERIES_POINTS = 3600


def platform_sut_metrics_retain_days() -> int:
    try:
        from app.core.platform import config as platform_config

        return max(
            1,
            min(
                90,
                int(getattr(platform_config, "SUT_METRICS_RETAIN_DAYS", DEFAULT_RETAIN_DAYS) or DEFAULT_RETAIN_DAYS),
            ),
        )
    except Exception:
        return DEFAULT_RETAIN_DAYS


def platform_sut_metrics_baseline_sec() -> int:
    try:
        from app.core.platform import config as platform_config

        return max(60, min(1800, int(getattr(platform_config, "SUT_METRICS_BASELINE_SEC", 300) or 300)))
    except Exception:
        return 300


def resolve_sut_metrics_retain_days(settings=None) -> int:
    """项目覆盖优先；未配置则用平台默认。"""
    raw = None
    if isinstance(settings, dict):
        raw = settings.get("sut_metrics_retain_days")
    if raw is None or raw == "" or raw is False:
        return platform_sut_metrics_retain_days()
    try:
        return max(1, min(90, int(raw)))
    except (TypeError, ValueError):
        return platform_sut_metrics_retain_days()


def resolve_sut_metrics_baseline_sec(settings=None) -> int:
    raw = None
    if isinstance(settings, dict):
        raw = settings.get("sut_metrics_baseline_sec")
    if raw is None or raw == "" or raw is False:
        return platform_sut_metrics_baseline_sec()
    try:
        return max(60, min(1800, int(raw)))
    except (TypeError, ValueError):
        return platform_sut_metrics_baseline_sec()


def compact_phase_stats(summary=None):
    """从 summarize_series 结果抽出对照用峰值/均值。"""
    sm = summary if isinstance(summary, dict) else {}

    def _pair(key: str):
        block = sm.get(key) if isinstance(sm.get(key), dict) else {}
        return {"avg": block.get("avg"), "max": block.get("max")}

    return {
        "cpu_pct": _pair("cpu_pct"),
        "mem_pct": _pair("mem_pct"),
        "disk_pct": _pair("disk_pct"),
        "load1": _pair("load1"),
        "net_rx_kbps": _pair("net_rx_kbps"),
        "net_tx_kbps": _pair("net_tx_kbps"),
        "disk_read_kbps": _pair("disk_read_kbps"),
        "disk_write_kbps": _pair("disk_write_kbps"),
        "point_count": sm.get("point_count") or 0,
    }


async def purge_old_chunks(*, retain_days=None) -> int:
    """按项目保留天数删除过期 chunk；孤儿 chunk 按平台默认清理。"""
    fallback = max(1, int(retain_days or platform_sut_metrics_retain_days()))
    servers = await SutServer.filter(is_del=False).all()
    by_project = {}
    for s in servers:
        try:
            pid = int(s.project_id)
            sid = int(s.id)
        except (TypeError, ValueError):
            continue
        by_project.setdefault(pid, []).append(sid)

    deleted = 0
    if by_project:
        from app.modules.ai.ai_project_settings import load_ai_project_settings

        for pid, sids in by_project.items():
            try:
                settings = await load_ai_project_settings(pid)
                days = resolve_sut_metrics_retain_days(settings)
            except Exception:
                days = fallback
            cutoff = now_app() - timedelta(days=days)
            n = await SutMetricChunk.filter(server_id__in=sids, received_at__lt=cutoff).delete()
            deleted += int(n or 0)
    else:
        cutoff = now_app() - timedelta(days=fallback)
        n = await SutMetricChunk.filter(received_at__lt=cutoff).delete()
        deleted += int(n or 0)

    orphan_cutoff = now_app() - timedelta(days=fallback)
    live_ids = [sid for sids in by_project.values() for sid in sids]
    q = SutMetricChunk.filter(received_at__lt=orphan_cutoff)
    if live_ids:
        q = q.exclude(server_id__in=live_ids)
    n2 = await q.delete()
    deleted += int(n2 or 0)
    return deleted


@with_scheduler_lock("scheduler:sut", expire_seconds=600)
async def purge_sut_metric_chunks_job(job_id: str = PURGE_JOB_ID) -> dict:
    deleted = await purge_old_chunks()
    if deleted:
        logger.info("[sut_metric_purge] deleted=%s", deleted)
    return {"deleted": deleted}


def register_sut_metric_purge_job(scheduler) -> None:
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(
        purge_sut_metric_chunks_job,
        trigger=IntervalTrigger(hours=6),
        id=PURGE_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        kwargs={"job_id": PURGE_JOB_ID},
    )


def flatten_chunks_to_points(
    chunks: list[SutMetricChunk],
    *,
    from_ms: Optional[int] = None,
    to_ms: Optional[int] = None,
) -> list[dict[str, Any]]:
    """去重排序后的全量点（不降采样）。"""
    by_ts: dict[int, dict[str, Any]] = {}
    for ch in chunks:
        raw = ch.points_json or []
        if not isinstance(raw, list):
            continue
        for p in raw:
            if not isinstance(p, dict):
                continue
            try:
                ts = int(p.get("ts_ms"))
            except (TypeError, ValueError):
                continue
            if from_ms is not None and ts < from_ms:
                continue
            if to_ms is not None and ts > to_ms:
                continue
            by_ts[ts] = p
    return [by_ts[k] for k in sorted(by_ts.keys())]


def flatten_chunks_to_series(
    chunks: list[SutMetricChunk],
    *,
    from_ms: Optional[int] = None,
    to_ms: Optional[int] = None,
    max_points: int = MAX_SERIES_POINTS,
) -> list[dict[str, Any]]:
    """曲线用：全量去重后再降采样。"""
    points = flatten_chunks_to_points(chunks, from_ms=from_ms, to_ms=to_ms)
    return downsample_series(points, max_points=max_points)


def downsample_series(points: list[dict[str, Any]], *, max_points: int = MAX_SERIES_POINTS) -> list[dict[str, Any]]:
    n = len(points)
    if n <= max_points or max_points < 2:
        return points
    # 均匀抽样，始终保留首尾
    step = (n - 1) / (max_points - 1)
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for i in range(max_points):
        idx = int(round(i * step))
        if idx in seen:
            continue
        seen.add(idx)
        out.append(points[idx])
    return out


def summarize_series(points: list[dict[str, Any]]) -> dict[str, Any]:
    empty_pair = {"avg": None, "max": None}
    if not points:
        return {
            "cpu_pct": dict(empty_pair),
            "mem_pct": dict(empty_pair),
            "disk_pct": dict(empty_pair),
            "load1": dict(empty_pair),
            "net_rx_kbps": dict(empty_pair),
            "net_tx_kbps": dict(empty_pair),
            "disk_read_kbps": dict(empty_pair),
            "disk_write_kbps": dict(empty_pair),
            "point_count": 0,
        }

    def _nums(key: str) -> list[float]:
        out = []
        for p in points:
            v = p.get(key)
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if fv != fv or abs(fv) == float("inf"):
                continue
            # load1 拒收离谱脏点（如约 2^32）
            if key == "load1" and (fv < 0 or fv > 1_000_000):
                continue
            out.append(fv)
        return out

    def _pair(vals: list[float]) -> dict[str, Any]:
        return {
            "avg": round(sum(vals) / len(vals), 2) if vals else None,
            "max": round(max(vals), 2) if vals else None,
        }

    return {
        "cpu_pct": _pair(_nums("cpu_pct")),
        "mem_pct": _pair(_nums("mem_pct")),
        "disk_pct": _pair(_nums("disk_pct")),
        "load1": _pair(_nums("load1")),
        "net_rx_kbps": _pair(_nums("net_rx_kbps")),
        "net_tx_kbps": _pair(_nums("net_tx_kbps")),
        "disk_read_kbps": _pair(_nums("disk_read_kbps")),
        "disk_write_kbps": _pair(_nums("disk_write_kbps")),
        "point_count": len(points),
    }
