#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BrickCore 被测监控采集器（PERF-1 M1）。

装在被测机 / 演示机宿主机，勿装到压测施压机冒充被测指标。
仅出站访问平台；Token 放配置文件，勿放 URL。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import signal
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    import psutil  # type: ignore
except ImportError:
    psutil = None

DEFAULT_INTERVAL = 5
DEFAULT_UPLOAD_EVERY = 15
DEFAULT_BUFFER_HOURS = 48
MAX_INTERVAL_SEC = 60
MAX_BUFFER_HOURS = 168
MAX_DB_BYTES = 80 * 1024 * 1024
# 压测 force 窗内：加快采样、延后上报，减少采集器自身流量对网卡指标的干扰
FORCE_SAMPLE_INTERVAL_SEC = 2
_STOP = False


def _pressure_active_from_payload(payload: dict[str, Any], *, now_ms: Optional[int] = None) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("pressure_active") is True:
        return True
    if payload.get("pressure_active") is False:
        return False
    raw = payload.get("force_until_ms")
    if raw is None:
        return False
    try:
        until = int(raw)
    except (TypeError, ValueError):
        return False
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    return until > now


def _effective_sample_interval(cfg: dict[str, Any], *, pressure_active: bool) -> int:
    base = max(2, min(MAX_INTERVAL_SEC, int(cfg.get("interval_sec") or DEFAULT_INTERVAL)))
    if pressure_active:
        return min(base, FORCE_SAMPLE_INTERVAL_SEC)
    return base


def _parse_runtime_settings(
    interval: Any,
    upload_every: Any,
    buffer_hours: Any,
) -> tuple[int, int, int]:
    try:
        interval_i = int(interval)
        upload_i = int(upload_every)
        buffer_i = int(buffer_hours)
    except (TypeError, ValueError) as e:
        raise ValueError(f"interval_sec / upload_every_sec / buffer_hours 须为整数: {e}") from e
    if interval_i < 2 or interval_i > MAX_INTERVAL_SEC:
        raise ValueError(f"interval_sec 须在 2～{MAX_INTERVAL_SEC}")
    if upload_i < interval_i:
        raise ValueError("upload_every_sec 不能小于 interval_sec")
    if buffer_i < 1 or buffer_i > MAX_BUFFER_HOURS:
        raise ValueError(f"buffer_hours 须在 1～{MAX_BUFFER_HOURS}")
    return interval_i, upload_i, buffer_i


def _load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("配置文件必须是 JSON 对象")
    platform = str(data.get("platform") or "").rstrip("/")
    token = str(data.get("token") or "").strip()
    if not platform or not token:
        raise SystemExit("配置需要 platform 与 token")
    parsed = urlparse(platform)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise SystemExit("platform 必须是 http(s)://host[:port] 形式")
    host = (parsed.hostname or "").lower()
    allow_insecure = bool(data.get("allow_insecure_http"))
    if parsed.scheme == "http" and host not in ("127.0.0.1", "localhost", "::1"):
        if not allow_insecure:
            raise SystemExit(
                "非本机 platform 须使用 HTTPS；本地演示可用 http://127.0.0.1，"
                "或显式设置 allow_insecure_http=true（Token 将明文传输）"
            )
        print(
            "[sut-agent] WARNING: allow_insecure_http=true，Token 经明文 HTTP 传输",
            flush=True,
        )
    if len(token) < 16:
        raise SystemExit("token 过短，请确认粘贴了完整一次性 Token")
    try:
        interval, upload_every, buffer_hours = _parse_runtime_settings(
            data.get("interval_sec") or DEFAULT_INTERVAL,
            data.get("upload_every_sec") or DEFAULT_UPLOAD_EVERY,
            data.get("buffer_hours") or DEFAULT_BUFFER_HOURS,
        )
    except ValueError as e:
        raise SystemExit(str(e)) from e
    data_dir = data.get("data_dir") or (path.parent / "data")
    return {
        "platform": platform,
        "token": token,
        "interval_sec": interval,
        "upload_every_sec": upload_every,
        "buffer_hours": buffer_hours,
        "data_dir": str(data_dir),
        "allow_insecure_http": allow_insecure,
        "_config_path": str(path.resolve()),
        "_raw": data,
    }


def _persist_runtime_to_config(cfg: dict[str, Any]) -> None:
    """把当前运行参数写回 agent_config.json（保留其它键）。"""
    path_s = cfg.get("_config_path")
    if not path_s:
        return
    path = Path(str(path_s))
    raw = cfg.get("_raw")
    if not isinstance(raw, dict):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
    raw["interval_sec"] = int(cfg["interval_sec"])
    raw["upload_every_sec"] = int(cfg["upload_every_sec"])
    raw["buffer_hours"] = int(cfg["buffer_hours"])
    try:
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cfg["_raw"] = raw
    except OSError as e:
        print(f"[sut-agent] 回写配置失败: {e}", flush=True)


def _apply_agent_settings_from_payload(
    cfg: dict[str, Any],
    payload: dict[str, Any],
) -> bool:
    """应用平台下发的 agent_settings；有变更返回 True。"""
    settings = payload.get("agent_settings")
    if not isinstance(settings, dict) or not settings:
        return False
    try:
        interval, upload_every, buffer_hours = _parse_runtime_settings(
            settings.get("interval_sec", cfg["interval_sec"]),
            settings.get("upload_every_sec", cfg["upload_every_sec"]),
            settings.get("buffer_hours", cfg["buffer_hours"]),
        )
    except ValueError as e:
        print(f"[sut-agent] 忽略非法 agent_settings: {e}", flush=True)
        return False
    if (
        interval == int(cfg["interval_sec"])
        and upload_every == int(cfg["upload_every_sec"])
        and buffer_hours == int(cfg["buffer_hours"])
    ):
        return False
    print(
        f"[sut-agent] agent_settings "
        f"interval={cfg['interval_sec']}→{interval} "
        f"upload={cfg['upload_every_sec']}→{upload_every} "
        f"buffer_h={cfg['buffer_hours']}→{buffer_hours}",
        flush=True,
    )
    cfg["interval_sec"] = interval
    cfg["upload_every_sec"] = upload_every
    cfg["buffer_hours"] = buffer_hours
    _persist_runtime_to_config(cfg)
    return True


def _agent_uid_path(data_dir: Path) -> Path:
    return data_dir / "agent_uid.txt"


def _ensure_agent_uid(data_dir: Path) -> str:
    data_dir.mkdir(parents=True, exist_ok=True)
    p = _agent_uid_path(data_dir)
    if p.exists():
        uid = p.read_text(encoding="utf-8").strip()
        if uid:
            return uid
    uid = uuid.uuid4().hex
    p.write_text(uid, encoding="utf-8")
    return uid


def _db_path(data_dir: Path) -> Path:
    return data_dir / "metrics.sqlite3"


def _connect_db(data_dir: Path) -> sqlite3.Connection:
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_db_path(data_dir)))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS samples (
            ts_ms INTEGER PRIMARY KEY,
            cpu_pct REAL,
            mem_pct REAL,
            mem_used_mb REAL,
            mem_total_mb REAL,
            load1 REAL,
            uploaded INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    cols = {r[1] for r in conn.execute("PRAGMA table_info(samples)").fetchall()}
    for name in (
        "disk_pct",
        "net_rx_kbps",
        "net_tx_kbps",
        "disk_read_kbps",
        "disk_write_kbps",
    ):
        if name not in cols:
            conn.execute(f"ALTER TABLE samples ADD COLUMN {name} REAL")
    conn.commit()
    return conn


_prev_io: dict[str, Any] = {"ts": None, "net": None, "disk": None}


def _rate_kbps(prev_bytes: Optional[int], cur_bytes: int, dt_sec: float) -> Optional[float]:
    if prev_bytes is None or dt_sec <= 0:
        return None
    delta = cur_bytes - prev_bytes
    if delta < 0:
        return None
    return round(delta / 1024.0 / dt_sec, 2)


def _trim_db(conn: sqlite3.Connection, buffer_hours: int) -> None:
    cutoff = int(time.time() * 1000) - max(1, buffer_hours) * 3600 * 1000
    conn.execute("DELETE FROM samples WHERE ts_ms < ?", (cutoff,))
    conn.commit()


def _checkpoint_wal(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error:
        pass


def _enforce_db_size(data_dir: Path, conn: sqlite3.Connection) -> None:
    p = _db_path(data_dir)
    if not p.exists() or p.stat().st_size <= MAX_DB_BYTES:
        return
    n_up = int(conn.execute("SELECT COUNT(*) FROM samples WHERE uploaded=1").fetchone()[0] or 0)
    if n_up > 0:
        limit = max(1, n_up // 2)
        conn.execute(
            "DELETE FROM samples WHERE ts_ms IN "
            "(SELECT ts_ms FROM samples WHERE uploaded=1 ORDER BY ts_ms ASC LIMIT ?)",
            (limit,),
        )
    else:
        n_all = int(conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0] or 0)
        if n_all > 0:
            limit = max(1, n_all // 4)
            conn.execute(
                "DELETE FROM samples WHERE ts_ms IN "
                "(SELECT ts_ms FROM samples ORDER BY ts_ms ASC LIMIT ?)",
                (limit,),
            )
    conn.commit()
    _checkpoint_wal(conn)
    try:
        conn.execute("VACUUM")
    except sqlite3.Error:
        pass


def _sample_once() -> dict[str, Any]:
    global _prev_io
    ts_ms = int(time.time() * 1000)
    cpu = None
    mem_pct = None
    mem_used = None
    mem_total = None
    load1 = None
    disk_pct = None
    net_rx = None
    net_tx = None
    disk_r = None
    disk_w = None
    if psutil is not None:
        cpu = float(psutil.cpu_percent(interval=0.2))
        vm = psutil.virtual_memory()
        mem_pct = float(vm.percent)
        mem_used = float(vm.used) / (1024 * 1024)
        mem_total = float(vm.total) / (1024 * 1024)
        try:
            load1 = float(os.getloadavg()[0])  # type: ignore[attr-defined]
            # 异常大数（如 2^32）视为无效，避免详情「load1 max」被脏点撑爆
            if not math.isfinite(load1) or load1 < 0 or load1 > 1_000_000:
                load1 = None
        except (AttributeError, OSError, ValueError, OverflowError):
            load1 = None
        try:
            root = os.environ.get("SystemDrive", "/")
            if os.name == "nt":
                if not str(root).endswith(("\\", "/")):
                    root = str(root) + "\\"
            else:
                root = "/"
            disk_pct = float(psutil.disk_usage(root).percent)
        except (OSError, ValueError):
            disk_pct = None
        now_sec = time.time()
        prev_ts = _prev_io.get("ts")
        dt = (now_sec - float(prev_ts)) if prev_ts else 0.0
        try:
            net = psutil.net_io_counters()
            prev_net = _prev_io.get("net")
            if net is not None and prev_net is not None:
                net_rx = _rate_kbps(int(prev_net.bytes_recv), int(net.bytes_recv), dt)
                net_tx = _rate_kbps(int(prev_net.bytes_sent), int(net.bytes_sent), dt)
            _prev_io["net"] = net
        except Exception:
            pass
        try:
            dio = psutil.disk_io_counters()
            prev_disk = _prev_io.get("disk")
            if dio is not None and prev_disk is not None:
                disk_r = _rate_kbps(int(prev_disk.read_bytes), int(dio.read_bytes), dt)
                disk_w = _rate_kbps(int(prev_disk.write_bytes), int(dio.write_bytes), dt)
            _prev_io["disk"] = dio
        except Exception:
            pass
        _prev_io["ts"] = now_sec
    else:
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                info = {}
                for line in f:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        info[parts[0].strip()] = parts[1].strip()
                total_kb = float(info.get("MemTotal", "0 kB").split()[0])
                avail_kb = float(info.get("MemAvailable", info.get("MemFree", "0 kB")).split()[0])
                mem_total = total_kb / 1024
                mem_used = (total_kb - avail_kb) / 1024
                mem_pct = (mem_used / mem_total * 100) if mem_total else None
        except OSError:
            pass
        try:
            with open("/proc/loadavg", "r", encoding="utf-8") as f:
                load1 = float(f.read().split()[0])
            if not math.isfinite(load1) or load1 < 0 or load1 > 1_000_000:
                load1 = None
        except (OSError, ValueError, OverflowError):
            load1 = None
        cpu = None
    return {
        "ts_ms": ts_ms,
        "cpu_pct": cpu,
        "mem_pct": mem_pct,
        "mem_used_mb": mem_used,
        "mem_total_mb": mem_total,
        "load1": load1,
        "disk_pct": disk_pct,
        "net_rx_kbps": net_rx,
        "net_tx_kbps": net_tx,
        "disk_read_kbps": disk_r,
        "disk_write_kbps": disk_w,
    }


def _insert_sample(conn: sqlite3.Connection, sample: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO samples(
            ts_ms, cpu_pct, mem_pct, mem_used_mb, mem_total_mb, load1,
            disk_pct, net_rx_kbps, net_tx_kbps, disk_read_kbps, disk_write_kbps, uploaded
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,0)
        """,
        (
            sample["ts_ms"],
            sample.get("cpu_pct"),
            sample.get("mem_pct"),
            sample.get("mem_used_mb"),
            sample.get("mem_total_mb"),
            sample.get("load1"),
            sample.get("disk_pct"),
            sample.get("net_rx_kbps"),
            sample.get("net_tx_kbps"),
            sample.get("disk_read_kbps"),
            sample.get("disk_write_kbps"),
        ),
    )
    conn.commit()


def _api_post(platform: str, path: str, token: str, body: dict[str, Any]) -> dict[str, Any]:
    url = f"{platform}{path}"
    data = json.dumps(body).encode("utf-8")
    req = Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-SUT-Token": token,
            "User-Agent": "BrickCore-SutAgent/1.0",
            "Content-Length": str(len(data)),
        },
    )
    with urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _host_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "platform": sys.platform,
        "python": sys.version.split()[0],
    }
    if psutil is not None:
        info["cpu_count"] = psutil.cpu_count()
        info["mem_total_mb"] = round(psutil.virtual_memory().total / (1024 * 1024), 1)
    return info


def _mark_uploaded(conn: sqlite3.Connection, ts_list: list[int]) -> None:
    if not ts_list:
        return
    conn.executemany("UPDATE samples SET uploaded=1 WHERE ts_ms=?", [(i,) for i in ts_list])
    conn.commit()


def _discard_samples(conn: sqlite3.Connection, ts_list: list[int]) -> None:
    """永久无效点：标记已传，避免阻塞队列（等价丢弃补传）。"""
    _mark_uploaded(conn, ts_list)


def _upload_pending(
    conn: sqlite3.Connection,
    platform: str,
    token: str,
    agent_uid: str,
    interval_sec: int,
    config_rev: Optional[int] = None,
) -> Optional[str]:
    rows = conn.execute(
        """
        SELECT ts_ms, cpu_pct, mem_pct, mem_used_mb, mem_total_mb, load1,
               disk_pct, net_rx_kbps, net_tx_kbps, disk_read_kbps, disk_write_kbps
        FROM samples WHERE uploaded=0 ORDER BY ts_ms ASC LIMIT 300
        """
    ).fetchall()
    if not rows:
        return None
    points = []
    for r in rows:
        item = {
            "ts_ms": int(r[0]),
            "cpu_pct": r[1],
            "mem_pct": r[2],
            "mem_used_mb": r[3],
            "mem_total_mb": r[4],
            "load1": r[5],
        }
        if r[6] is not None:
            item["disk_pct"] = r[6]
        if r[7] is not None:
            item["net_rx_kbps"] = r[7]
        if r[8] is not None:
            item["net_tx_kbps"] = r[8]
        if r[9] is not None:
            item["disk_read_kbps"] = r[9]
        if r[10] is not None:
            item["disk_write_kbps"] = r[10]
        points.append(item)
    ids = [p["ts_ms"] for p in points]
    start_ms = points[0]["ts_ms"]
    end_ms = points[-1]["ts_ms"]
    body: dict[str, Any] = {
        "agent_uid": agent_uid,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "interval_sec": interval_sec,
        "points": points,
    }
    if config_rev is not None:
        body["config_rev"] = int(config_rev)
    try:
        res = _api_post(
            platform,
            "/perf/sut-agent/metrics",
            token,
            body,
        )
    except HTTPError as e:
        body_txt = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        print(f"[sut-agent] upload HTTP {e.code}: {body_txt}", flush=True)
        return None
    except (URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"[sut-agent] upload failed: {e}", flush=True)
        return None

    if res.get("ok") and res.get("accepted") is not False:
        _mark_uploaded(conn, ids)
        acc = res.get("accepted_count", len(points))
        rej = res.get("rejected_count", 0)
        rej_ts = res.get("rejected_ts_ms") or []
        extra = f" rejected_ts={rej_ts[:5]}" if rej_ts else ""
        print(f"[sut-agent] uploaded accepted={acc} rejected={rej}{extra}", flush=True)
        return None

    reason = res.get("reason")
    if reason == "no_valid_points":
        _discard_samples(conn, ids)
        print(
            f"[sut-agent] discarded {len(ids)} invalid points (no_valid_points); "
            "若持续出现请检查本机时钟与 buffer_hours",
            flush=True,
        )
        return None
    if reason == "config_mismatch":
        # 监控开关/日程已变更：丢弃旧配置下缓冲，避免写入暂停时段
        _discard_samples(conn, ids)
        print(
            f"[sut-agent] config_rev mismatch (platform={res.get('config_rev')}); "
            f"discarded {len(ids)} buffered samples",
            flush=True,
        )
        return "config_mismatch"
    if reason == "monitoring_paused":
        print("[sut-agent] monitoring paused by platform", flush=True)
        return "monitoring_paused"
    return reason if isinstance(reason, str) else None


def _request_stop(signum=None, frame=None) -> None:
    global _STOP
    _STOP = True
    print(f"[sut-agent] received signal {signum}, shutting down…", flush=True)


def run_loop(cfg: dict[str, Any]) -> None:
    global _STOP
    _STOP = False
    try:
        signal.signal(signal.SIGINT, _request_stop)
        signal.signal(signal.SIGTERM, _request_stop)
    except (ValueError, OSError):
        pass

    data_dir = Path(cfg["data_dir"])
    if not data_dir.is_absolute():
        data_dir = (Path.cwd() / data_dir).resolve()
    agent_uid = _ensure_agent_uid(data_dir)
    conn = _connect_db(data_dir)
    hostname = os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "unknown"
    try:
        import socket

        hostname = socket.gethostname() or hostname
    except Exception:
        pass

    sample_allowed = True
    config_rev: Optional[int] = None
    pressure_active = False
    try:
        act = _api_post(
            cfg["platform"],
            "/perf/sut-agent/activate",
            cfg["token"],
            {"agent_uid": agent_uid, "hostname": hostname, "host_info": _host_info()},
        )
        sample_allowed = bool(act.get("sample_allowed", True))
        if act.get("config_rev") is not None:
            config_rev = int(act["config_rev"])
        _apply_agent_settings_from_payload(cfg, act if isinstance(act, dict) else {})
        pressure_active = _pressure_active_from_payload(act if isinstance(act, dict) else {})
        print(
            f"[sut-agent] activated server_id={act.get('server_id')} "
            f"sample_allowed={sample_allowed} config_rev={config_rev} "
            f"interval={cfg['interval_sec']}s upload={cfg['upload_every_sec']}s "
            f"buffer_h={cfg['buffer_hours']} pressure={pressure_active} "
            f"agent_uid={agent_uid[:8]}…",
            flush=True,
        )
    except Exception as e:
        print(f"[sut-agent] activate failed (will retry via heartbeat): {e}", flush=True)

    interval = int(cfg["interval_sec"])
    upload_every = int(cfg["upload_every_sec"])
    heartbeat_every = 30
    now = time.time()
    next_sample = now
    next_heartbeat = now
    next_upload = now

    try:
        while not _STOP:
            now = time.time()
            interval = _effective_sample_interval(cfg, pressure_active=pressure_active)
            upload_every = int(cfg["upload_every_sec"])
            if sample_allowed and now >= next_sample:
                sample = _sample_once()
                _insert_sample(conn, sample)
                _trim_db(conn, int(cfg["buffer_hours"]))
                _enforce_db_size(data_dir, conn)
                next_sample = now + interval

            if now >= next_heartbeat:
                try:
                    hb = _api_post(
                        cfg["platform"],
                        "/perf/sut-agent/heartbeat",
                        cfg["token"],
                        {
                            "agent_uid": agent_uid,
                            "hostname": hostname,
                            "host_info": _host_info(),
                        },
                    )
                    prev_allowed = sample_allowed
                    prev_pressure = pressure_active
                    sample_allowed = bool(hb.get("sample_allowed", hb.get("monitoring_enabled", True)))
                    pressure_active = _pressure_active_from_payload(hb if isinstance(hb, dict) else {})
                    _apply_agent_settings_from_payload(cfg, hb if isinstance(hb, dict) else {})
                    if pressure_active and not prev_pressure:
                        print(
                            f"[sut-agent] pressure window on: sample≤{FORCE_SAMPLE_INTERVAL_SEC}s, "
                            "defer upload until force ends",
                            flush=True,
                        )
                    if prev_pressure and not pressure_active:
                        print(
                            "[sut-agent] pressure window off: flushing deferred samples",
                            flush=True,
                        )
                        # 尽快抽干缓冲，避免与平台 90s/120s 再切片错过
                        for _round in range(40):
                            reason = _upload_pending(
                                conn,
                                cfg["platform"],
                                cfg["token"],
                                agent_uid,
                                interval,
                                config_rev=config_rev,
                            )
                            if reason == "monitoring_paused":
                                sample_allowed = False
                                break
                            if reason == "config_mismatch":
                                break
                            left = conn.execute(
                                "SELECT COUNT(1) FROM samples WHERE uploaded=0"
                            ).fetchone()
                            if not left or int(left[0] or 0) <= 0:
                                break
                        next_upload = now + upload_every
                    new_rev = hb.get("config_rev")
                    if new_rev is not None:
                        new_rev = int(new_rev)
                        # 仅暂停/关闭采样时丢弃未上传缓冲，避免 pause 时段补传；改间隔不丢
                        if (
                            config_rev is not None
                            and new_rev != config_rev
                            and not sample_allowed
                            and prev_allowed
                        ):
                            pending = conn.execute(
                                "SELECT ts_ms FROM samples WHERE uploaded=0"
                            ).fetchall()
                            if pending:
                                _discard_samples(conn, [int(r[0]) for r in pending])
                                print(
                                    f"[sut-agent] config_rev {config_rev}->{new_rev}; "
                                    f"sample paused; discarded {len(pending)} pending samples",
                                    flush=True,
                                )
                        elif config_rev is not None and new_rev != config_rev:
                            print(
                                f"[sut-agent] config_rev {config_rev}->{new_rev} "
                                f"(sample_allowed={sample_allowed})",
                                flush=True,
                            )
                        config_rev = new_rev
                except Exception as e:
                    print(f"[sut-agent] heartbeat failed: {e}", flush=True)
                # pause / force 窗内加快心跳，便于及时开关 pressure / force
                next_heartbeat = now + (
                    5 if (not sample_allowed or pressure_active) else heartbeat_every
                )

            # 压测 force 期间只采不报，结束后再整体补传，降低对网卡指标的自干扰
            if sample_allowed and (not pressure_active) and now >= next_upload:
                reason = _upload_pending(
                    conn,
                    cfg["platform"],
                    cfg["token"],
                    agent_uid,
                    interval,
                    config_rev=config_rev,
                )
                if reason == "monitoring_paused":
                    sample_allowed = False
                if reason == "config_mismatch":
                    # 下一心跳会同步新 rev
                    pass
                next_upload = now + upload_every

            wake = min(next_sample, next_heartbeat, next_upload) - time.time()
            time.sleep(max(0.2, min(1.0, wake if wake > 0 else 0.2)))
    finally:
        # 退出前尽量把 force 窗内积压点发出去
        if sample_allowed:
            try:
                _upload_pending(
                    conn,
                    cfg["platform"],
                    cfg["token"],
                    agent_uid,
                    int(cfg["interval_sec"]),
                    config_rev=config_rev,
                )
            except Exception as e:
                print(f"[sut-agent] final flush failed: {e}", flush=True)
        _checkpoint_wal(conn)
        conn.close()
        print("[sut-agent] stopped", flush=True)


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="BrickCore 被测监控采集器")
    parser.add_argument(
        "-c",
        "--config",
        default=str(Path(__file__).resolve().parent / "agent_config.json"),
        help="配置文件路径（JSON）",
    )
    args = parser.parse_args(argv)
    cfg_path = Path(args.config)
    if not cfg_path.exists():
        example = Path(__file__).resolve().parent / "agent_config.example.json"
        raise SystemExit(f"缺少配置 {cfg_path}，请复制 {example.name} 为 agent_config.json 并填写 token")
    cfg = _load_config(cfg_path)
    if psutil is None:
        print("[sut-agent] 未安装 psutil，将尽力使用 /proc；建议: pip install psutil", flush=True)
    run_loop(cfg)


if __name__ == "__main__":
    main()
