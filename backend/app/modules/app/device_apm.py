"""App 设备性能（A-5）契约：校验、归一化、结果落库辅助。"""

from __future__ import annotations

import re
from typing import Any, Optional

ALLOWED_METRICS = ("cpu", "memory", "network", "fps", "jank", "battery", "gpu", "disk", "thermal")
# 默认轻量集合，降低 dumpsys 开销；全量由前端/调用方显式传入
DEFAULT_METRICS = ["cpu", "memory", "fps", "jank", "battery"]
MAX_SERIES_POINTS = 300

DEFAULT_THRESHOLDS: dict[str, float] = {
    "cpu_pct": 80.0,
    "mem_pss_mb": 512.0,
    "fps": 45.0,
    "janky_pct": 10.0,
    "gpu_busy_pct": 90.0,
}

# Android 包名：段以字母开头，仅字母数字下划线，至少一段点分
ANDROID_PKG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$")

_PEAK_KEYS = (
    "cpu_pct",
    "mem_pss_mb",
    "mem_rss_mb",
    "mem_java_heap_mb",
    "mem_native_heap_mb",
    "mem_graphics_mb",
    "janky_pct",
    "gpu_busy_pct",
    "temp_c",
    "net_rx_kb",
    "net_tx_kb",
)
_VALLEY_KEYS = ("fps", "disk_free_mb", "battery_pct")

_THERMAL_RANK = {
    "none": 0,
    "light": 1,
    "moderate": 2,
    "severe": 3,
    "critical": 4,
    "emergency": 5,
    "shutdown": 6,
}


def is_valid_android_pkg(pkg: str | None) -> bool:
    value = str(pkg or "").strip()
    return bool(value) and len(value) <= 255 and bool(ANDROID_PKG_RE.match(value))


def _extreme_idx(points: list[dict[str, Any]], key: str, *, prefer_max: bool) -> int | None:
    best_i = None
    best_v = None
    for i, p in enumerate(points):
        if not isinstance(p, dict):
            continue
        v = p.get(key)
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if best_v is None or (fv > best_v if prefer_max else fv < best_v):
            best_v = fv
            best_i = i
    return best_i


def downsample_series(points: list[dict[str, Any]], *, max_points: int = MAX_SERIES_POINTS) -> list[dict[str, Any]]:
    """等距抽样 + 强制保留 summary 相关极值与 step/case 边界，最终裁剪到 max_points。"""
    raw = [p for p in (points or []) if isinstance(p, dict)]
    n = len(raw)
    if n <= max_points or max_points < 2:
        return list(raw)

    priority: set[int] = {0, n - 1}
    for key in _PEAK_KEYS:
        idx = _extreme_idx(raw, key, prefer_max=True)
        if idx is not None:
            priority.add(idx)
    for key in _VALLEY_KEYS:
        idx = _extreme_idx(raw, key, prefer_max=False)
        if idx is not None:
            priority.add(idx)

    for i, p in enumerate(raw):
        if not (p.get("step_id") or p.get("case_id")):
            continue
        prev = raw[i - 1] if i > 0 else {}
        if p.get("step_id") != prev.get("step_id") or p.get("case_id") != prev.get("case_id"):
            priority.add(i)

    # 先等距取满，再并入 priority
    seen: set[int] = set()
    step = (n - 1) / (max_points - 1)
    for i in range(max_points):
        seen.add(int(round(i * step)))
    seen |= priority

    if len(seen) > max_points:
        # priority 优先；剩余名额从等距候选中补
        keep = set(priority)
        if len(keep) > max_points:
            # 边界过多：只保留首尾 + 极值
            keep = {0, n - 1}
            for key in _PEAK_KEYS:
                idx = _extreme_idx(raw, key, prefer_max=True)
                if idx is not None:
                    keep.add(idx)
                if len(keep) >= max_points:
                    break
            for key in _VALLEY_KEYS:
                if len(keep) >= max_points:
                    break
                idx = _extreme_idx(raw, key, prefer_max=False)
                if idx is not None:
                    keep.add(idx)
            while len(keep) > max_points:
                # 丢弃中间极值（保留首尾）
                extras = sorted(i for i in keep if i not in (0, n - 1))
                if not extras:
                    break
                keep.discard(extras[len(extras) // 2])
        else:
            fillers = sorted(i for i in seen if i not in keep)
            slots = max_points - len(keep)
            if slots > 0 and fillers:
                if len(fillers) <= slots:
                    keep.update(fillers)
                else:
                    fstep = (len(fillers) - 1) / (slots - 1) if slots > 1 else 0
                    for i in range(slots):
                        keep.add(fillers[int(round(i * fstep))])
        seen = keep

    return [raw[i] for i in sorted(seen)]


def normalize_thresholds(raw: dict[str, Any] | None = None) -> dict[str, float]:
    out = dict(DEFAULT_THRESHOLDS)
    if not isinstance(raw, dict):
        return out
    for key in DEFAULT_THRESHOLDS:
        if key not in raw:
            continue
        try:
            val = float(raw[key])
        except (TypeError, ValueError):
            continue
        if val != val or val < 0 or val > 1e6:  # NaN / negative / absurd
            continue
        out[key] = val
    return out


def normalize_device_apm_option(
    *,
    enabled: bool = False,
    pkg_name: str = "",
    interval_ms: int | None = 1000,
    metrics: list[str] | None = None,
    thresholds: dict[str, Any] | None = None,
    fallback_pkg: str = "",
) -> Optional[dict[str, Any]]:
    """构造派发用 device_apm；未开启返回 None。"""
    if not enabled:
        return None
    pkg = (pkg_name or fallback_pkg or "").strip()
    try:
        interval = int(interval_ms if interval_ms is not None else 1000)
    except (TypeError, ValueError):
        interval = 1000
    interval = max(200, min(interval, 10000))
    cleaned: list[str] = []
    for m in metrics or DEFAULT_METRICS:
        key = str(m or "").strip().lower()
        if key in ALLOWED_METRICS and key not in cleaned:
            cleaned.append(key)
    if not cleaned:
        cleaned = list(DEFAULT_METRICS)
    return {
        "enabled": True,
        "mode": "attach_exec",
        "pkg_name": pkg,
        "interval_ms": interval,
        "metrics": cleaned,
        "thresholds": normalize_thresholds(thresholds),
    }


def validate_device_apm_for_dispatch(
    device_apm: Optional[dict[str, Any]],
    *,
    udid: str,
    platform: str | None = None,
) -> Optional[str]:
    """返回错误文案；None 表示通过。"""
    if not device_apm or not device_apm.get("enabled"):
        return None
    plat_err = assert_android_only_platform(platform)
    if plat_err:
        return plat_err
    if not (udid or "").strip():
        return "开启设备性能采集时必须指定设备 UDID"
    pkg = str(device_apm.get("pkg_name") or "").strip()
    if not pkg:
        return "开启设备性能采集时必须填写应用包名"
    if not is_valid_android_pkg(pkg):
        return "应用包名格式无效（需形如 com.example.app，仅字母数字下划线与点）"
    metrics = device_apm.get("metrics") or []
    bad = [m for m in metrics if m not in ALLOWED_METRICS]
    if bad:
        return f"不支持的设备性能指标: {', '.join(bad)}"
    return None


def extract_device_apm_from_result(result: dict[str, Any] | None) -> tuple[Optional[dict], Optional[list]]:
    """从 Runner 结果中取出 summary / series。"""
    if not isinstance(result, dict):
        return None, None
    blob = result.get("device_apm")
    if not isinstance(blob, dict):
        return None, None
    summary = blob.get("summary") if isinstance(blob.get("summary"), dict) else None
    series = blob.get("series") if isinstance(blob.get("series"), list) else None
    if series:
        series = downsample_series(series)
    if summary is not None:
        summary = dict(summary)
        thr = blob.get("thresholds")
        if isinstance(thr, dict):
            summary["thresholds"] = normalize_thresholds(thr)
        elif "thresholds" not in summary:
            summary["thresholds"] = dict(DEFAULT_THRESHOLDS)
    return summary, series


def apply_device_apm_to_execution(record: Any, result: dict[str, Any] | None) -> list[str]:
    """写入 execution 的 device_apm_* 字段，返回需 save 的 update_fields。"""
    summary, series = extract_device_apm_from_result(result)
    if summary is None and series is None:
        return []
    fields: list[str] = []
    if hasattr(record, "device_apm_summary"):
        record.device_apm_summary = summary
        fields.append("device_apm_summary")
    if hasattr(record, "device_apm_series"):
        record.device_apm_series = series
        fields.append("device_apm_series")
    return fields


def _case_vals(sliced: list[dict], attr: str, *, quality_key: str | None = None) -> list[float]:
    out: list[float] = []
    for p in sliced:
        if quality_key:
            q = p.get("quality") if isinstance(p.get("quality"), dict) else {}
            if q.get(quality_key) not in (None, "ok"):
                continue
        v = p.get(attr)
        if v is None:
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            continue
    return out


def _net_window_delta(vals: list[float]) -> float | None:
    """case/step 窗口内流量：last - first；遇 reset（下降）则分段累加。"""
    if not vals:
        return None
    total = 0.0
    prev = vals[0]
    for cur in vals[1:]:
        if cur < prev:
            # counter reset：上一窗口累计清零，从 0 重新计
            prev = cur
            continue
        total += cur - prev
        prev = cur
    return round(total, 2)


def _thermal_worst(sliced: list[dict]) -> str | None:
    best = None
    best_rank = -1
    for p in sliced:
        name = str(p.get("thermal_status") or "").strip().lower()
        if not name:
            continue
        rank = _THERMAL_RANK.get(name, -1)
        if rank > best_rank:
            best_rank = rank
            best = name
    return best


def slice_device_apm_for_case(
    suite_result: dict[str, Any] | None,
    *,
    case_id: str | None,
) -> Optional[dict[str, Any]]:
    """从套件级 device_apm series 按 case_id 切分用例窗口。"""
    if not isinstance(suite_result, dict):
        return None
    blob = suite_result.get("device_apm")
    if not isinstance(blob, dict):
        return None
    cid = str(case_id or "").strip()
    if not cid:
        return None
    series = blob.get("series") if isinstance(blob.get("series"), list) else []
    sliced = [p for p in series if isinstance(p, dict) and str(p.get("case_id") or "") == cid]
    suite_summary = blob.get("summary") if isinstance(blob.get("summary"), dict) else {}
    # Runner 精确 case summary：即使降采样后该 case 点被裁掉，仍可落库
    precise = None
    cs_map = suite_summary.get("case_summaries")
    if isinstance(cs_map, dict):
        precise = cs_map.get(cid)
        if precise is None:
            precise = cs_map.get(str(cid))
    if isinstance(precise, dict) and (
        precise.get("sample_count") is not None or precise.get("first_ts_ms") is not None
    ):
        summary = dict(precise)
        summary["scope"] = "case"
        summary["case_id"] = cid
        summary["approximate_from_downsampled_series"] = False
        summary.setdefault("device_udid", suite_summary.get("device_udid") or "")
        summary.setdefault("pkg_name", suite_summary.get("pkg_name") or "")
        thr = blob.get("thresholds") if isinstance(blob.get("thresholds"), dict) else suite_summary.get("thresholds")
        return {
            "device_apm": {
                "summary": summary,
                "series": downsample_series(sliced) if sliced else [],
                "thresholds": normalize_thresholds(thr if isinstance(thr, dict) else None),
                "enabled": True,
            }
        }
    if not sliced:
        return None

    def _avg(vals: list[float]) -> float | None:
        return round(sum(vals) / len(vals), 2) if vals else None

    def _peak(vals: list[float], reducer) -> float | None:
        return round(reducer(vals), 2) if vals else None

    cpus = _case_vals(sliced, "cpu_pct")
    pss = _case_vals(sliced, "mem_pss_mb")
    rss = _case_vals(sliced, "mem_rss_mb")
    java_h = _case_vals(sliced, "mem_java_heap_mb")
    native_h = _case_vals(sliced, "mem_native_heap_mb")
    graphics = _case_vals(sliced, "mem_graphics_mb")
    fps = [v for v in _case_vals(sliced, "fps", quality_key="fps") if v > 0]
    jank = _case_vals(sliced, "janky_pct", quality_key="jank")
    gpu = _case_vals(sliced, "gpu_busy_pct", quality_key="gpu")
    disk = _case_vals(sliced, "disk_free_mb")
    batt = _case_vals(sliced, "battery_pct")
    temps = _case_vals(sliced, "temp_c")
    rx = _case_vals(sliced, "net_rx_kb")
    tx = _case_vals(sliced, "net_tx_kb")
    jank_frames = []
    for p in sliced:
        v = p.get("janky_frames_delta")
        if v is None:
            continue
        try:
            jank_frames.append(int(v))
        except (TypeError, ValueError):
            continue

    gap_count = 0
    ok_n = 0
    degraded_n = 0
    for p in sliced:
        q = p.get("quality") if isinstance(p.get("quality"), dict) else {}
        if p.get("error") or (q and all(v == "unsupported" for v in q.values() if v)):
            gap_count += 1
        qvals = list(q.values()) if q else []
        if qvals and any(v == "ok" for v in qvals):
            ok_n += 1
        elif qvals and any(v == "degraded" for v in qvals):
            degraded_n += 1

    first_ts = sliced[0].get("ts_ms")
    last_ts = sliced[-1].get("ts_ms")
    duration_sec = None
    try:
        first = int(first_ts or 0)
        last = int(last_ts or 0)
        if last >= first:
            duration_sec = round((last - first) / 1000.0, 3)
    except (TypeError, ValueError):
        pass

    cpus_sorted = sorted(cpus)
    p95 = None
    if cpus_sorted:
        if len(cpus_sorted) == 1:
            p95 = round(cpus_sorted[0], 2)
        else:
            k = (len(cpus_sorted) - 1) * 0.95
            f = int(k)
            c = min(f + 1, len(cpus_sorted) - 1)
            p95 = round(cpus_sorted[f] + (cpus_sorted[c] - cpus_sorted[f]) * (k - f), 2)

    summary = {
        "sample_count": len(sliced),
        "gap_count": gap_count,
        "device_udid": suite_summary.get("device_udid") or "",
        "pkg_name": suite_summary.get("pkg_name") or "",
        "scope": "case",
        "case_id": cid,
        "first_ts_ms": first_ts,
        "last_ts_ms": last_ts,
        "duration_sec": duration_sec,
        "cpu_pct_avg": _avg(cpus),
        "cpu_pct_max": _peak(cpus, max),
        "cpu_pct_p95": p95,
        "mem_pss_mb_avg": _avg(pss),
        "mem_pss_mb_max": _peak(pss, max),
        "mem_rss_mb_max": _peak(rss, max),
        "mem_java_heap_mb_max": _peak(java_h, max),
        "mem_native_heap_mb_max": _peak(native_h, max),
        "mem_graphics_mb_max": _peak(graphics, max),
        "fps_avg": _avg(fps),
        "fps_min": _peak(fps, min),
        "janky_pct_avg": _avg(jank),
        "janky_pct_max": _peak(jank, max),
        "janky_frames_total": sum(jank_frames) if jank_frames else None,
        "gpu_busy_pct_avg": _avg(gpu),
        "gpu_busy_pct_max": _peak(gpu, max),
        "disk_free_mb_min": _peak(disk, min),
        "battery_pct_min": _peak(batt, min),
        "battery_pct_last": batt[-1] if batt else None,
        "temp_c_max": _peak(temps, max),
        "thermal_status_worst": _thermal_worst(sliced),
        "net_rx_kb_delta": _net_window_delta(rx),
        "net_tx_kb_delta": _net_window_delta(tx),
        "sample_ok_count": ok_n,
        "sample_degraded_count": degraded_n,
        "unsupported_metrics": list(suite_summary.get("unsupported_metrics") or []),
        "quality_notes": dict(suite_summary.get("quality_notes") or {}),
        "cpu_basis": "single_core_100pct",
        "approximate_from_downsampled_series": True,
    }
    thr = blob.get("thresholds") if isinstance(blob.get("thresholds"), dict) else suite_summary.get("thresholds")
    return {
        "device_apm": {
            "summary": summary,
            "series": downsample_series(sliced),
            "thresholds": normalize_thresholds(thr if isinstance(thr, dict) else None),
            "enabled": True,
        }
    }


_COMPARE_KEYS = (
    "cpu_pct_max",
    "cpu_pct_avg",
    "mem_pss_mb_max",
    "mem_rss_mb_max",
    "mem_java_heap_mb_max",
    "mem_native_heap_mb_max",
    "mem_graphics_mb_max",
    "fps_avg",
    "fps_min",
    "janky_pct_max",
    "janky_pct_avg",
    "gpu_busy_pct_max",
    "disk_free_mb_min",
    "battery_pct_min",
    "temp_c_max",
    "net_rx_kb_delta",
    "net_tx_kb_delta",
    "sample_count",
    "duration_sec",
)

_COMPARE_BETTER = {
    "cpu_pct_max": "lower",
    "cpu_pct_avg": "lower",
    "mem_pss_mb_max": "lower",
    "mem_rss_mb_max": "lower",
    "mem_java_heap_mb_max": "lower",
    "mem_native_heap_mb_max": "lower",
    "mem_graphics_mb_max": "lower",
    "fps_avg": "higher",
    "fps_min": "higher",
    "janky_pct_max": "lower",
    "janky_pct_avg": "lower",
    "gpu_busy_pct_max": "lower",
    "disk_free_mb_min": "higher",
    "battery_pct_min": "higher",
    "temp_c_max": "lower",
    "net_rx_kb_delta": "n/a",
    "net_tx_kb_delta": "n/a",
    "sample_count": "n/a",
    "duration_sec": "n/a",
}

_COMPARE_UNITS = {
    "cpu_pct_max": "%",
    "cpu_pct_avg": "%",
    "mem_pss_mb_max": "MB",
    "mem_rss_mb_max": "MB",
    "mem_java_heap_mb_max": "MB",
    "mem_native_heap_mb_max": "MB",
    "mem_graphics_mb_max": "MB",
    "fps_min": "fps",
    "fps_avg": "fps",
    "janky_pct_max": "%",
    "janky_pct_avg": "%",
    "gpu_busy_pct_max": "%",
    "disk_free_mb_min": "MB",
    "battery_pct_min": "%",
    "temp_c_max": "℃",
    "net_rx_kb_delta": "KB",
    "net_tx_kb_delta": "KB",
    "sample_count": "",
    "duration_sec": "s",
}


def compare_device_apm_payloads(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
    *,
    left_label: str = "A",
    right_label: str = "B",
) -> dict[str, Any]:
    left_s = (left or {}).get("summary") if isinstance(left, dict) else None
    right_s = (right or {}).get("summary") if isinstance(right, dict) else None
    if not isinstance(left_s, dict):
        left_s = {}
    if not isinstance(right_s, dict):
        right_s = {}
    rows = []
    for key in _COMPARE_KEYS:
        lv = left_s.get(key)
        rv = right_s.get(key)
        delta = None
        try:
            if lv is not None and rv is not None:
                delta = round(float(rv) - float(lv), 4)
        except (TypeError, ValueError):
            delta = None
        rows.append(
            {
                "metric": key,
                "left": lv,
                "right": rv,
                "delta": delta,
                "unit": _COMPARE_UNITS.get(key, ""),
                "better_direction": _COMPARE_BETTER.get(key, "n/a"),
            }
        )
    return {
        "left_label": left_label,
        "right_label": right_label,
        "rows": rows,
        "left_udid": (left_s or {}).get("device_udid"),
        "right_udid": (right_s or {}).get("device_udid"),
        "left_pkg": (left_s or {}).get("pkg_name"),
        "right_pkg": (right_s or {}).get("pkg_name"),
        "left_duration_sec": (left_s or {}).get("duration_sec"),
        "right_duration_sec": (right_s or {}).get("duration_sec"),
        "comparable_hint": (
            "同包名、相近采集时长更可比；sample_count/delta 仅供参考"
        ),
    }


def assert_android_only_platform(platform: str | None) -> Optional[str]:
    """当前仅允许 Android（空值按 Android）。"""
    p = (platform or "android").strip().lower()
    if p in ("", "android"):
        return None
    if p in ("ios", "iphone", "ipad"):
        return "设备性能采集暂仅支持 Android（iOS 尚未开放）"
    if p in ("harmony", "harmonyos"):
        return "设备性能采集暂仅支持 Android"
    return f"设备性能采集暂仅支持 Android（当前平台={platform}）"
