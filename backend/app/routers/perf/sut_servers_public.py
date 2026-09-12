"""被测监控采集器公共 API（仅 X-SUT-Token，无浏览器 JWT）。"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q

from app.core.platform.datetime_utils import now_app, now_epoch_ms
from app.models.perf import SutMetricChunk, SutServer
from app.modules.perf.sut_agent_settings import agent_settings_from_row
from app.modules.perf.sut_rate_limit import check_rate_limit
from app.modules.perf.sut_schedule import is_monitoring_allowed
from app.modules.perf.sut_force import (
    get_force_until_ms_from_row,
    get_force_window_from_row,
    is_server_pressure_active,
    load_force_windows_for_server,
)
from app.modules.perf.sut_metrics_store import platform_sut_metrics_retain_days
from app.modules.perf.sut_token import hash_sut_token, verify_sut_token

logger = logging.getLogger(__name__)

public_router = APIRouter(prefix="/sut-agent", tags=["被测监控采集器"])

MAX_POINTS_PER_UPLOAD = 300
MAX_FUTURE_SKEW_MS = 60_000
MAX_HOST_INFO_KEYS = 32
MAX_HOST_INFO_STR = 512


def _max_point_age_ms() -> int:
    """与 chunk 保留天数一致，避免 retain=30 仍拒 >14d 或 retain=7 收已过期点。"""
    days = max(1, min(90, int(platform_sut_metrics_retain_days())))
    return days * 24 * 3600 * 1000


# 限流：每 server 每分钟
HEARTBEAT_RATE = (60, 60.0)
METRICS_RATE = (30, 60.0)
ACTIVATE_RATE = (10, 60.0)

_AGENT_SAVE_FIELDS = (
    "agent_uid",
    "hostname",
    "host_info",
    "last_heartbeat_at",
)


class ActivateBody(BaseModel):
    agent_uid: str = Field(..., min_length=8, max_length=64)
    hostname: Optional[str] = Field(None, max_length=255)
    host_info: Optional[dict[str, Any]] = None


class HeartbeatBody(BaseModel):
    agent_uid: str = Field(..., min_length=8, max_length=64)
    hostname: Optional[str] = Field(None, max_length=255)
    host_info: Optional[dict[str, Any]] = None


class MetricsBody(BaseModel):
    agent_uid: str = Field(..., min_length=8, max_length=64)
    start_ms: int
    end_ms: int
    interval_sec: int = 5
    points: list[dict[str, Any]] = Field(default_factory=list)
    config_rev: Optional[int] = None


def _sanitize_host_info(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for i, (k, v) in enumerate(raw.items()):
        if i >= MAX_HOST_INFO_KEYS:
            break
        key = str(k)[:64]
        if isinstance(v, bool):
            out[key] = v
        elif isinstance(v, int):
            out[key] = v
        elif isinstance(v, float):
            if math.isfinite(v):
                out[key] = v
        elif isinstance(v, str):
            out[key] = v[:MAX_HOST_INFO_STR]
        elif v is None:
            out[key] = None
        else:
            out[key] = str(v)[:MAX_HOST_INFO_STR]
    return out


async def _resolve_server(x_sut_token: Optional[str]) -> SutServer:
    if not x_sut_token or not str(x_sut_token).strip():
        raise HTTPException(status_code=401, detail="缺少 X-SUT-Token")
    plain = str(x_sut_token).strip()
    digest = hash_sut_token(plain)
    row = await SutServer.get_or_none(token_hash=digest, is_del=False)
    if row and verify_sut_token(plain, row.token_hash):
        return row
    raise HTTPException(status_code=401, detail="无效的 X-SUT-Token")


async def _bind_agent_uid_atomic(row: SutServer, agent_uid: str) -> SutServer:
    """条件更新绑定 agent_uid，避免多采集器并发抢绑。"""
    uid = (agent_uid or "").strip()
    if not uid or len(uid) < 8:
        raise HTTPException(status_code=422, detail="agent_uid 无效")
    uid = uid[:64]
    if row.agent_uid and row.agent_uid != uid:
        raise HTTPException(
            status_code=409,
            detail="agent_uid 与已绑定身份不一致：一机一采集器，请勿多机共用同一 Token",
        )
    if not row.agent_uid:
        updated = await SutServer.filter(id=row.id).filter(
            Q(agent_uid__isnull=True) | Q(agent_uid="") | Q(agent_uid=uid)
        ).update(agent_uid=uid)
        row = await SutServer.get(id=row.id)
        if not updated and row.agent_uid != uid:
            raise HTTPException(
                status_code=409,
                detail="agent_uid 与已绑定身份不一致：一机一采集器，请勿多机共用同一 Token",
            )
        row.agent_uid = uid
    return row


def _config_rev(row: SutServer) -> int:
    return int(getattr(row, "config_rev", None) or 1)


def _agent_control_payload(row: SutServer, *, pressure_active: Optional[bool] = None) -> dict[str, Any]:
    force_until_ms = get_force_until_ms_from_row(row)
    force_from_ms, _ = get_force_window_from_row(row)
    now_ms = now_epoch_ms()
    # pressure_active：仅「仍有压测在跑」时延后上报。finalize 后的 grace force 只用于
    # 接受补传 / pause 下继续采样，不得再阻塞 upload（否则与 90s 再切片死锁）。
    if pressure_active is None:
        pressure_active = force_until_ms is not None and int(force_until_ms) > int(now_ms)
    payload: dict[str, Any] = {
        "server_id": row.id,
        "monitoring_enabled": bool(row.monitoring_enabled),
        "schedule": row.schedule_json,
        "force_until_ms": force_until_ms,
        "force_from_ms": force_from_ms,
        "pressure_active": bool(pressure_active),
        "config_rev": _config_rev(row),
        "sample_allowed": is_monitoring_allowed(
            monitoring_enabled=bool(row.monitoring_enabled),
            schedule=row.schedule_json if isinstance(row.schedule_json, dict) else None,
            force_until_ms=force_until_ms,
        ),
        "agent_uid": row.agent_uid,
    }
    settings = agent_settings_from_row(row)
    if settings is not None:
        payload["agent_settings"] = settings
    return payload


async def _pressure_active_for_server(server_id: int) -> bool:
    """压测进行中延后上报：只读 Redis 标记，禁止查 PerfRecord（小机 OOM）。"""
    return await is_server_pressure_active(int(server_id))


async def _agent_control_payload_async(row: SutServer) -> dict[str, Any]:
    return _agent_control_payload(
        row,
        pressure_active=await _pressure_active_for_server(row.id),
    )


async def _save_agent_fields(row: SutServer, *, extra: Optional[list[str]] = None) -> None:
    fields = list(_AGENT_SAVE_FIELDS)
    if extra:
        for f in extra:
            if f not in fields:
                fields.append(f)
    await row.save(update_fields=fields)


def _finite_or_none(v: Any) -> Optional[float]:
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(fv):
        return None
    return fv


def _pct_or_none(v: Any) -> Optional[float]:
    fv = _finite_or_none(v)
    if fv is None:
        return None
    if fv < 0 or fv > 100:
        return None
    return fv


def _sanitize_points(raw: list[dict[str, Any]], *, now_ms: int) -> tuple[list[dict[str, Any]], list[int]]:
    """返回 (有效点, 被拒绝的 ts_ms 列表)。拒绝同批重复 ts。"""
    out: list[dict[str, Any]] = []
    rejected_ts: list[int] = []
    last_ts: Optional[int] = None
    max_age = _max_point_age_ms()
    for p in raw[:MAX_POINTS_PER_UPLOAD]:
        if not isinstance(p, dict):
            continue
        try:
            ts = int(p.get("ts_ms"))
        except (TypeError, ValueError):
            continue
        if ts > now_ms + MAX_FUTURE_SKEW_MS or ts < now_ms - max_age:
            rejected_ts.append(ts)
            continue
        if last_ts is not None and ts <= last_ts:
            rejected_ts.append(ts)
            continue
        item: dict[str, Any] = {"ts_ms": ts}
        cpu = _pct_or_none(p.get("cpu_pct"))
        mem = _pct_or_none(p.get("mem_pct"))
        used = _finite_or_none(p.get("mem_used_mb"))
        total = _finite_or_none(p.get("mem_total_mb"))
        load1 = _finite_or_none(p.get("load1"))
        disk = _pct_or_none(p.get("disk_pct"))
        net_rx = _finite_or_none(p.get("net_rx_kbps"))
        net_tx = _finite_or_none(p.get("net_tx_kbps"))
        disk_r = _finite_or_none(p.get("disk_read_kbps"))
        disk_w = _finite_or_none(p.get("disk_write_kbps"))
        if used is not None and used < 0:
            used = None
        if total is not None and total < 0:
            total = None
        if used is not None and total is not None and used > total:
            used = None
        if load1 is not None and load1 < 0:
            load1 = None
        # 拒收离谱 load1（常见脏值约 2^32），避免 max 被撑成几十亿
        if load1 is not None and load1 > 1_000_000:
            load1 = None
        if net_rx is not None and net_rx < 0:
            net_rx = None
        if net_tx is not None and net_tx < 0:
            net_tx = None
        if disk_r is not None and disk_r < 0:
            disk_r = None
        if disk_w is not None and disk_w < 0:
            disk_w = None
        if cpu is not None:
            item["cpu_pct"] = cpu
        if mem is not None:
            item["mem_pct"] = mem
        if used is not None:
            item["mem_used_mb"] = used
        if total is not None:
            item["mem_total_mb"] = total
        if load1 is not None:
            item["load1"] = load1
        if disk is not None:
            item["disk_pct"] = disk
        if net_rx is not None:
            item["net_rx_kbps"] = net_rx
        if net_tx is not None:
            item["net_tx_kbps"] = net_tx
        if disk_r is not None:
            item["disk_read_kbps"] = disk_r
        if disk_w is not None:
            item["disk_write_kbps"] = disk_w
        if len(item) == 1:
            rejected_ts.append(ts)
            continue
        out.append(item)
        last_ts = ts
    return out, rejected_ts


def _filter_points_by_schedule(
    points: list[dict[str, Any]],
    *,
    monitoring_enabled: bool,
    schedule: Optional[dict[str, Any]],
    force_until_ms: Optional[int] = None,
    force_from_ms: Optional[int] = None,
    force_windows: Optional[list[tuple[int, int]]] = None,
) -> tuple[list[dict[str, Any]], list[int]]:
    """按每个点的 ts_ms 判断是否落在允许窗口（补传时过滤 pause；force 历史窗覆盖）。"""
    if not monitoring_enabled:
        return [], [int(p["ts_ms"]) for p in points]
    windows = list(force_windows or [])
    if force_from_ms is not None and force_until_ms is not None:
        try:
            windows.append((int(force_from_ms), int(force_until_ms)))
        except (TypeError, ValueError):
            pass
    kept: list[dict[str, Any]] = []
    rejected: list[int] = []
    for p in points:
        ts = int(p["ts_ms"])
        now = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
        force_hit = any(frm <= ts <= until for frm, until in windows)
        if force_hit or is_monitoring_allowed(
            monitoring_enabled=True,
            schedule=schedule,
            force_from_ms=force_from_ms,
            force_until_ms=force_until_ms,
            now=now,
        ):
            kept.append(p)
        else:
            rejected.append(ts)
    return kept, rejected


def _apply_hostname_host_info(row: SutServer, body: ActivateBody | HeartbeatBody) -> None:
    if body.hostname:
        row.hostname = body.hostname.strip()[:255]
    if body.host_info is not None:
        row.host_info = _sanitize_host_info(body.host_info)
    row.last_heartbeat_at = now_app()


@public_router.post("/activate", summary="采集器激活/绑定身份")
async def activate_agent(
    body: ActivateBody,
    x_sut_token: Optional[str] = Header(None, alias="X-SUT-Token"),
):
    row = await _resolve_server(x_sut_token)
    check_rate_limit(f"sut:act:{row.id}", max_calls=ACTIVATE_RATE[0], window_sec=ACTIVATE_RATE[1])
    row = await _bind_agent_uid_atomic(row, body.agent_uid)
    _apply_hostname_host_info(row, body)
    await _save_agent_fields(row)
    return await _agent_control_payload_async(row)


@public_router.post("/heartbeat", summary="采集器心跳")
async def agent_heartbeat(
    body: HeartbeatBody,
    x_sut_token: Optional[str] = Header(None, alias="X-SUT-Token"),
):
    row = await _resolve_server(x_sut_token)
    check_rate_limit(f"sut:hb:{row.id}", max_calls=HEARTBEAT_RATE[0], window_sec=HEARTBEAT_RATE[1])
    row = await _bind_agent_uid_atomic(row, body.agent_uid)
    _apply_hostname_host_info(row, body)
    await _save_agent_fields(row)
    return await _agent_control_payload_async(row)


@public_router.post("/metrics", summary="采集器上传指标 chunk")
async def agent_metrics(
    body: MetricsBody,
    x_sut_token: Optional[str] = Header(None, alias="X-SUT-Token"),
):
    row = await _resolve_server(x_sut_token)
    check_rate_limit(f"sut:mx:{row.id}", max_calls=METRICS_RATE[0], window_sec=METRICS_RATE[1])
    row = await _bind_agent_uid_atomic(row, body.agent_uid)
    row.last_heartbeat_at = now_app()

    rev_mismatch = body.config_rev is not None and int(body.config_rev) != _config_rev(row)

    allowed_now = is_monitoring_allowed(
        monitoring_enabled=bool(row.monitoring_enabled),
        schedule=row.schedule_json if isinstance(row.schedule_json, dict) else None,
        force_until_ms=get_force_until_ms_from_row(row),
    )
    if not rev_mismatch and not allowed_now and not bool(row.monitoring_enabled):
        await _save_agent_fields(row)
        return {
            "ok": True,
            "accepted": False,
            "reason": "monitoring_paused",
            "accepted_count": 0,
            "rejected_count": len(body.points or []),
            "rejected_ts_ms": [],
        }

    if body.end_ms < body.start_ms:
        raise HTTPException(status_code=422, detail="end_ms 必须 >= start_ms")
    if len(body.points) > MAX_POINTS_PER_UPLOAD:
        raise HTTPException(status_code=422, detail=f"单次点数不能超过 {MAX_POINTS_PER_UPLOAD}")

    now_ms = now_epoch_ms()
    points, rejected_ts = _sanitize_points(list(body.points or []), now_ms=now_ms)
    schedule = row.schedule_json if isinstance(row.schedule_json, dict) else None
    force_windows = await load_force_windows_for_server(row.id)
    # 当前窗（含已过期但未清空的 grace 窗）优先
    force_from = None
    force_until = None
    if force_windows:
        force_from, force_until = force_windows[0]

    if rev_mismatch:
        # 配置已变：仍接受历史 force 窗内点，避免丢掉压测期合法补传
        kept: list[dict[str, Any]] = []
        for p in points:
            ts = int(p["ts_ms"])
            if any(frm <= ts <= until for frm, until in force_windows):
                kept.append(p)
            else:
                rejected_ts.append(ts)
        points = kept
        if not points:
            await _save_agent_fields(row)
            return {
                "ok": True,
                "accepted": False,
                "reason": "config_mismatch",
                "config_rev": _config_rev(row),
                "accepted_count": 0,
                "rejected_count": len(rejected_ts) or len(body.points or []),
                "rejected_ts_ms": rejected_ts[:50],
            }
    else:
        points, schedule_rej = _filter_points_by_schedule(
            points,
            monitoring_enabled=bool(row.monitoring_enabled),
            schedule=schedule,
            force_from_ms=force_from,
            force_until_ms=force_until,
            force_windows=force_windows,
        )
        rejected_ts.extend(schedule_rej)

    if not points:
        await _save_agent_fields(row)
        return {
            "ok": True,
            "accepted": False,
            "reason": "no_valid_points",
            "accepted_count": 0,
            "rejected_count": len(rejected_ts) or len(body.points or []),
            "rejected_ts_ms": rejected_ts[:50],
        }

    # 契约：清洗后的起止须与声明一致（允许声明略宽，但首尾点必须匹配）
    start_ms = int(points[0]["ts_ms"])
    end_ms = int(points[-1]["ts_ms"])
    if body.start_ms != start_ms or body.end_ms != end_ms:
        # 以清洗后 points 为准，仍接受；响应标明实际起止
        pass

    row.last_metrics_at = now_app()
    await _save_agent_fields(row, extra=["last_metrics_at"])

    existing = await SutMetricChunk.get_or_none(server_id=row.id, start_ms=start_ms)
    resp_base = {
        "ok": True,
        "accepted": True,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "accepted_count": len(points),
        "rejected_count": len(rejected_ts),
        "rejected_ts_ms": rejected_ts[:50],
    }
    if existing:
        existing.end_ms = end_ms
        existing.points_json = points
        await existing.save(update_fields=["end_ms", "points_json"])
        return {**resp_base, "chunk_id": existing.id, "upsert": True}

    try:
        chunk = await SutMetricChunk.create(
            server_id=row.id,
            start_ms=start_ms,
            end_ms=end_ms,
            points_json=points,
        )
    except IntegrityError:
        existing = await SutMetricChunk.get_or_none(server_id=row.id, start_ms=start_ms)
        if not existing:
            raise
        existing.end_ms = end_ms
        existing.points_json = points
        await existing.save(update_fields=["end_ms", "points_json"])
        return {**resp_base, "chunk_id": existing.id, "upsert": True}

    return {**resp_base, "chunk_id": chunk.id, "upsert": False}
