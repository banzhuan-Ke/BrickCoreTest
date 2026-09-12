"""压测进行中：向被测监控采集器下发 force 窗口（覆盖 pause 日程）。"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Iterable, Optional

from tortoise.expressions import Q

from app.core.platform.datetime_utils import now_app, now_epoch_ms
from app.models.perf import PerfRecord, SutServer
from app.modules.perf.sut_metrics_store import platform_sut_metrics_retain_days

logger = logging.getLogger(__name__)

# 收尾后再留缓冲，便于采集器补传末窗点；clear 时若无其它活跃任务则落到 now+grace
FORCE_TAIL_BUFFER_MS = 120_000
FORCE_CLEAR_GRACE_MS = 90_000
# 与平台 chunk 保留 / 采集点可接受年龄对齐（默认 14 天，下限 2）
FORCE_HISTORY_LOOKBACK_DAYS = 14

# Redis：压测进行中延后上报标记（与 grace force_until 分离，心跳勿查 PerfRecord）
_PRESSURE_REDIS_PREFIX = "sut:pressure_active:"


def _pressure_redis_key(server_id: int) -> str:
    return f"{_PRESSURE_REDIS_PREFIX}{int(server_id)}"


async def set_server_pressure_active(
    server_ids: Iterable[int],
    *,
    active: bool,
    until_ms: Optional[int] = None,
) -> None:
    """标记/清除「压测进行中、采集器应延后上报」。grace 补传窗不要置 active。"""
    ids = [int(x) for x in server_ids if x is not None]
    if not ids:
        return
    try:
        from app.core.infra.redis_client import redis_cli
    except Exception:
        logger.exception("redis 不可用，跳过 pressure_active 标记")
        return
    now_ms = now_epoch_ms()
    for sid in ids:
        key = _pressure_redis_key(sid)
        try:
            if not active:
                await redis_cli.delete(key)
                continue
            ttl = 3600
            if until_ms is not None:
                try:
                    ttl = max(120, min(172800, (int(until_ms) - now_ms) // 1000 + 120))
                except (TypeError, ValueError):
                    ttl = 3600
            await redis_cli.set(key, "1", ex=int(ttl))
        except Exception:
            logger.exception("写入 pressure_active 失败 server_id=%s", sid)


async def is_server_pressure_active(server_id: int) -> bool:
    try:
        from app.core.infra.redis_client import redis_cli

        return bool(await redis_cli.exists(_pressure_redis_key(server_id)))
    except Exception:
        logger.exception("读取 pressure_active 失败 server_id=%s", server_id)
        return False


def estimate_wait_seconds(config: Optional[dict[str, Any]]) -> int:
    """与 exec._estimate_distributed_max_wait 对齐的粗估（秒），避免循环导入。"""
    from app.modules.perf.perf_journey import (
        JOURNEY_FIXED_MODE,
        JOURNEY_LOOP_MODE,
        normalize_journey_config,
    )
    from app.modules.stream_phase import (
        is_stream_burst_mode,
        normalize_perf_mode,
        normalize_stream_profile,
        use_stream_execution,
    )

    cfg = config or {}
    mode = normalize_perf_mode(cfg.get("mode", "fixed"))
    concurrent = int(cfg.get("concurrent_users") or 1)
    ramp_up = int(cfg.get("ramp_up_seconds") or 0)
    buffer = 600
    stream_timeout = 0
    if use_stream_execution(cfg):
        stream_timeout = int(normalize_stream_profile(cfg).get("timeout_seconds") or 600)

    if mode in ("loop", JOURNEY_LOOP_MODE):
        loop_count = int(cfg.get("loop_count") or 100)
        per_iter = 10
        if use_stream_execution(cfg):
            per_iter = max(
                per_iter,
                int(normalize_stream_profile(cfg).get("timeout_seconds") or 600),
            )
        if mode == JOURNEY_LOOP_MODE:
            journey = normalize_journey_config(cfg)
            step_count = sum(len(p.get("steps") or []) for p in journey.get("phases") or [])
            per_iter = max(per_iter, step_count * 30)
        wait_sec = min(86400, max(3600, loop_count * per_iter + ramp_up + buffer))
    elif mode == "stepping":
        steps = cfg.get("steps") or []
        stage_sum = sum(int(s.get("duration") or 30) for s in steps if isinstance(s, dict))
        drain = max(stream_timeout, 120) if stream_timeout else 120
        wait_sec = stage_sum + ramp_up + drain + buffer
    elif is_stream_burst_mode(mode):
        timeout = int(normalize_stream_profile(cfg).get("timeout_seconds") or 600)
        wait_sec = timeout + concurrent * 30 + ramp_up + buffer
    elif mode == JOURNEY_FIXED_MODE:
        wait_sec = int(cfg.get("duration_seconds") or 60) + ramp_up + buffer
    else:
        wait_sec = int(cfg.get("duration_seconds") or 60) + ramp_up + buffer
        if stream_timeout:
            wait_sec = max(wait_sec, stream_timeout + ramp_up + buffer)
    return max(300, min(int(wait_sec), 86400))


def estimate_force_until_ms(*, config: dict, now_ms: Optional[int] = None) -> int:
    now_ms = int(now_ms if now_ms is not None else now_epoch_ms())
    return now_ms + estimate_wait_seconds(config) * 1000 + FORCE_TAIL_BUFFER_MS


async def apply_force_until(
    server_ids: Iterable[int],
    *,
    until_ms: int,
    from_ms: Optional[int] = None,
) -> None:
    """下发 force 窗口：until 取 max；from 取最早（便于补传覆盖整段）。"""
    ids = [int(x) for x in server_ids if x is not None]
    if not ids:
        return
    until_ms = int(until_ms)
    from_ms = int(from_ms if from_ms is not None else now_epoch_ms())
    rows = await SutServer.filter(id__in=ids, is_del=False).all()
    for row in rows:
        cur_until = getattr(row, "force_until_ms", None)
        cur_from = getattr(row, "force_from_ms", None)
        try:
            cur_until_i = int(cur_until) if cur_until is not None else None
        except (TypeError, ValueError):
            cur_until_i = None
        try:
            cur_from_i = int(cur_from) if cur_from is not None else None
        except (TypeError, ValueError):
            cur_from_i = None

        new_until = until_ms if cur_until_i is None else max(cur_until_i, until_ms)
        # 仍在有效 force 内则保留更早的 from，否则开新窗
        if cur_from_i is not None and cur_until_i is not None and cur_until_i > now_epoch_ms():
            new_from = min(cur_from_i, from_ms)
        else:
            new_from = from_ms

        if cur_until_i == new_until and cur_from_i == new_from:
            continue
        row.force_from_ms = new_from
        row.force_until_ms = new_until
        await row.save(update_fields=["force_from_ms", "force_until_ms"])
    # 下发 force 即视为压测进行中（延后上报）；与 DB force 窗一并设置
    await set_server_pressure_active(ids, active=True, until_ms=until_ms)


async def clear_force_for_servers(
    server_ids: Iterable[int],
    *,
    record_id: Optional[int] = None,
    grace_ms: int = FORCE_CLEAR_GRACE_MS,
) -> None:
    """
    清理强制采集。
    - 若同机仍有其它 pending/running 绑定 → 刷新为那些记录的较大 until，并保持 pressure_active
    - 否则：grace_ms>0 时落到 now+grace（保留 force_from，便于补传判定），并关闭 pressure_active
    """
    ids = list({int(x) for x in server_ids if x is not None})
    if not ids:
        return

    keep_until: dict[int, int] = {}
    keep_from: dict[int, int] = {}
    q = PerfRecord.filter(status__in=["pending", "running"])
    if record_id is not None:
        q = q.filter(~Q(id=record_id))
    # 只取 config_snapshot，禁止整行加载 time_series / request_details
    active_rows = await q.limit(100).values("id", "config_snapshot")
    now_ms = now_epoch_ms()
    for rec in active_rows:
        cfg = rec.get("config_snapshot") if isinstance(rec, dict) else None
        if not isinstance(cfg, dict):
            continue
        sids = cfg.get("sut_server_ids") or []
        if not isinstance(sids, list):
            continue
        try:
            sids = [int(x) for x in sids]
        except (TypeError, ValueError):
            continue
        until = cfg.get("sut_force_until_ms")
        frm = cfg.get("sut_force_from_ms")
        try:
            until_i = int(until) if until is not None else None
        except (TypeError, ValueError):
            until_i = None
        try:
            from_i = int(frm) if frm is not None else None
        except (TypeError, ValueError):
            from_i = None
        if until_i is None or until_i < now_ms:
            until_i = now_ms + estimate_wait_seconds(cfg) * 1000
        if from_i is None:
            from_i = now_ms
        for sid in sids:
            if sid in ids:
                keep_until[sid] = max(keep_until.get(sid, 0), until_i)
                if sid in keep_from:
                    keep_from[sid] = min(keep_from[sid], from_i)
                else:
                    keep_from[sid] = from_i

    grace_until = now_ms + max(0, int(grace_ms)) if grace_ms else None
    rows = await SutServer.filter(id__in=ids).all()
    still_pressure: list[int] = []
    clear_pressure: list[int] = []
    for row in rows:
        if row.id in keep_until:
            row.force_until_ms = keep_until[row.id]
            row.force_from_ms = keep_from.get(row.id) or getattr(row, "force_from_ms", None) or now_ms
            await row.save(update_fields=["force_from_ms", "force_until_ms"])
            still_pressure.append(int(row.id))
        elif grace_until is not None:
            # 保留 from，延长 until，使 force 期间采样点在 grace 内仍可补传
            if getattr(row, "force_from_ms", None) is None:
                row.force_from_ms = now_ms
            row.force_until_ms = grace_until
            await row.save(update_fields=["force_from_ms", "force_until_ms"])
            clear_pressure.append(int(row.id))
        else:
            row.force_from_ms = None
            row.force_until_ms = None
            await row.save(update_fields=["force_from_ms", "force_until_ms"])
            clear_pressure.append(int(row.id))

    if still_pressure:
        # 其它压测仍在跑：保持延后上报
        max_until = max(keep_until.get(sid, now_ms) for sid in still_pressure)
        await set_server_pressure_active(still_pressure, active=True, until_ms=max_until)
    if clear_pressure:
        # grace / 清空：允许立刻补传，勿再阻塞 upload
        await set_server_pressure_active(clear_pressure, active=False)

async def activate_sut_force_for_record(record: PerfRecord) -> None:
    """记录创建成功后再下发 force，避免 create 失败留下强制采集。"""
    cfg = dict(record.config_snapshot or {}) if isinstance(record.config_snapshot, dict) else {}
    sids = cfg.get("sut_server_ids") or []
    if not isinstance(sids, list) or not sids:
        return
    try:
        sids = [int(x) for x in sids]
    except (TypeError, ValueError):
        return
    from_ms = now_epoch_ms()
    until_ms = estimate_force_until_ms(config=cfg, now_ms=from_ms)
    cfg["sut_force_from_ms"] = from_ms
    cfg["sut_force_until_ms"] = until_ms
    cfg["sut_metrics_status"] = cfg.get("sut_metrics_status") or "pending"
    record.config_snapshot = cfg
    await record.save(update_fields=["config_snapshot"])
    await apply_force_until(sids, until_ms=until_ms, from_ms=from_ms)


async def release_sut_force_from_record(
    record: PerfRecord,
    *,
    grace_ms: int = 0,
) -> None:
    """失败/收尾路径统一释放本记录绑定的 force。"""
    cfg = dict(record.config_snapshot or {}) if isinstance(record.config_snapshot, dict) else {}
    sids = cfg.get("sut_server_ids") or []
    if not isinstance(sids, list) or not sids:
        return
    try:
        sids = [int(x) for x in sids]
    except (TypeError, ValueError):
        return
    # 收尾后把记录窗口延长到 grace，供 metrics 按历史窗接受补传点
    if grace_ms:
        now_ms = now_epoch_ms()
        cfg["sut_force_until_ms"] = now_ms + int(grace_ms)
        if cfg.get("sut_force_from_ms") is None:
            cfg["sut_force_from_ms"] = now_ms
        record.config_snapshot = cfg
        await record.save(update_fields=["config_snapshot"])
    await clear_force_for_servers(sids, record_id=record.id, grace_ms=grace_ms)


def get_force_until_ms_from_row(row: SutServer) -> Optional[int]:
    """心跳/实时 sample_allowed：仅返回尚未过期的 until。"""
    raw = getattr(row, "force_until_ms", None)
    if raw is None:
        return None
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return None
    if v <= now_epoch_ms():
        return None
    return v


def get_force_window_from_row(row: SutServer) -> tuple[Optional[int], Optional[int]]:
    """metrics 补传过滤：返回原始 from/until（即使 until 已过期，只要窗口仍在）。"""
    raw_until = getattr(row, "force_until_ms", None)
    raw_from = getattr(row, "force_from_ms", None)
    try:
        until = int(raw_until) if raw_until is not None else None
    except (TypeError, ValueError):
        until = None
    try:
        frm = int(raw_from) if raw_from is not None else None
    except (TypeError, ValueError):
        frm = None
    return frm, until


async def load_force_windows_for_server(server_id: int) -> list[tuple[int, int]]:
    """
    合并：服务器当前窗 + 近 retain 天内绑定该机的压测记录窗。
    用于补传时判定历史点是否曾处于 force（与 MAX_POINT_AGE / 平台保留对齐）。
    """
    windows: list[tuple[int, int]] = []
    row = await SutServer.get_or_none(id=server_id)
    if row:
        frm, until = get_force_window_from_row(row)
        if frm is not None and until is not None and until >= frm:
            windows.append((frm, until))

    lookback = max(2, min(FORCE_HISTORY_LOOKBACK_DAYS, int(platform_sut_metrics_retain_days())))
    since = now_app() - timedelta(days=lookback)
    # 只取 config_snapshot，避免把压测时序/明细整行拖进内存
    records = await PerfRecord.filter(
        status__in=["pending", "running", "success", "failed", "stopped"],
        started_at__gte=since,
    ).limit(200).values("id", "config_snapshot")
    sid = int(server_id)
    for rec in records:
        cfg = rec.get("config_snapshot") if isinstance(rec, dict) else None
        if not isinstance(cfg, dict):
            continue
        sids = cfg.get("sut_server_ids") or []
        if not isinstance(sids, list):
            continue
        try:
            if sid not in {int(x) for x in sids}:
                continue
        except (TypeError, ValueError):
            continue
        frm = cfg.get("sut_force_from_ms")
        until = cfg.get("sut_force_until_ms")
        try:
            frm_i = int(frm) if frm is not None else None
            until_i = int(until) if until is not None else None
        except (TypeError, ValueError):
            continue
        if frm_i is None or until_i is None or until_i < frm_i:
            continue
        windows.append((frm_i, until_i))
    return windows
