"""压测单报告 / 对比报告 AI 分析（同步与后台异步）。"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# LLM 场景绑定 key（须与 ai_scene_config / Prompt 一致）
PERF_RECORD_AI_SCENE = "perf_report_analysis"
PERF_COMPARE_AI_SCENE = "perf_compare_analysis"

# 进程内互斥：同一 record/report 同时只跑一个 LLM，防止 force_refresh 并发烧钱
_inflight_records: set[int] = set()
_inflight_compares: set[int] = set()
_inflight_guard = asyncio.Lock()

# running 超过该秒数视为僵死，允许强刷重入（进程崩溃/LLM 挂死兜底）
RUNNING_STALE_SECONDS = 600


async def _try_begin_inflight(bucket: set[int], item_id: int) -> bool:
    async with _inflight_guard:
        if item_id in bucket:
            return False
        bucket.add(item_id)
        return True


async def _end_inflight(bucket: set[int], item_id: int) -> None:
    async with _inflight_guard:
        bucket.discard(item_id)


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def running_placeholder() -> dict[str, Any]:
    now = _now_str()
    return {
        "status": "running",
        "summary": None,
        "overview": None,
        "metric_notes": {},
        "case_notes": [],
        "highlights": [],
        "risks": [],
        "recommendations": [],
        "bottleneck_notes": [],
        "resource_notes": [],
        "error": None,
        "started_at": now,
        "generated_at": None,
    }


def is_analysis_in_progress(existing: Optional[dict], *, stale_seconds: int = RUNNING_STALE_SECONDS) -> bool:
    """是否视为进行中（含未过期的 running）。过期 running 返回 False，允许强刷。"""
    if not isinstance(existing, dict) or existing.get("status") != "running":
        return False
    started = existing.get("started_at") or existing.get("generated_at")
    if not started:
        return True
    try:
        t0 = datetime.strptime(str(started)[:19], "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return True
    return (datetime.now() - t0).total_seconds() < max(60, int(stale_seconds or RUNNING_STALE_SECONDS))



def failed_payload(error: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "summary": None,
        "overview": None,
        "metric_notes": {},
        "case_notes": [],
        "highlights": [],
        "risks": [],
        "recommendations": [],
        "bottleneck_notes": [],
        "resource_notes": [],
        "error": (error or "分析失败")[:500],
        "generated_at": _now_str(),
    }


_PHASE_KEY_RE = re.compile(
    r"\bphase_(?:mean|p95|min|max|median)_[a-zA-Z0-9_]+\b|"
    r"\bphase_key\b|"
    r"\b(?:total_time|answer_duration|answer_start|retrieval_duration|"
    r"retrieval_start|retrieval_end)_[a-zA-Z0-9_]*\b"
)


def metric_label_map_from_snapshot(snapshot: Optional[dict] = None) -> dict[str, str]:
    """从对比/单报告快照收集 metric key → 中文 label，供清洗 AI 文案。"""
    out: dict[str, str] = {
        "qps": "QPS",
        "success_qps": "成功 QPS",
        "avg_response_time": "平均响应时间",
        "avg_rt": "平均响应时间",
        "p95_response_time": "P95",
        "p95": "P95",
        "error_rate": "错误率",
        "total_requests": "总请求数",
        "total_time": "整体耗时",
        "answer_duration": "回答耗时",
        "answer_start": "回答开始",
        "retrieval_duration": "检索耗时",
        "retrieval_start": "检索开始",
        "retrieval_end": "检索结束",
    }
    snap = snapshot if isinstance(snapshot, dict) else {}
    for m in snap.get("metric_compare") or []:
        if not isinstance(m, dict):
            continue
        key = str(m.get("key") or "").strip()
        label = str(m.get("label") or "").strip()
        if key and label:
            out[key] = label
            pk = m.get("phase_key")
            if pk:
                # label 形如「检索开始 均值(s)」→ 裸 key 用前半段
                out[str(pk)] = re.split(r"\s+", label, maxsplit=1)[0] or str(pk)
    for st in ((snap.get("stepping_stage_compare") or {}).get("stages") or []):
        if not isinstance(st, dict):
            continue
        for m in st.get("metrics") or []:
            if isinstance(m, dict) and m.get("key") and m.get("label"):
                out[str(m["key"])] = str(m["label"])
    # 单报告：phase_metrics / schema
    pm = snap.get("phase_metrics")
    if isinstance(pm, dict):
        for pk, info in pm.items():
            if isinstance(info, dict):
                lab = str(info.get("label") or "").strip()
                if lab:
                    out[str(pk)] = lab
                    out[f"phase_mean_{pk}"] = f"{lab}均值"
                    out[f"phase_p95_{pk}"] = f"{lab}P95"
    return out


def _humanize_metric_token(token: str, label_map: dict[str, str]) -> str:
    if token in label_map:
        return label_map[token]
    # phase_mean_total_time → total_time / 整体耗时均值
    m = re.match(r"^phase_(mean|p95|min|max|median)_(.+)$", token)
    if m:
        full = token
        if full in label_map:
            return label_map[full]
        phase_key = m.group(2)
        stat = {"mean": "均值", "p95": "P95", "min": "最小", "max": "最大", "median": "中位"}.get(
            m.group(1), m.group(1)
        )
        base = label_map.get(phase_key) or phase_key.replace("_", " ")
        # 若 label_map 已是「xxx 均值(s)」类，直接用
        for k, lab in label_map.items():
            if k.endswith(phase_key) or k == f"phase_mean_{phase_key}":
                if "均值" in lab or "P95" in lab:
                    if m.group(1) == "mean" and "均值" in lab:
                        return lab
                    if m.group(1) == "p95" and "P95" in lab:
                        return lab
                return lab
        return f"{base}{stat}"
    return token.replace("_", " ")


def scrub_ai_text_keys(text: Any, label_map: Optional[dict[str, str]] = None) -> Any:
    """去掉 AI 文案中的 phase_* / 英文字段名，替换为中文指标名。"""
    if text is None:
        return text
    if not isinstance(text, str):
        return text
    s = text
    labels = label_map or {}

    def _repl(match: re.Match) -> str:
        return _humanize_metric_token(match.group(0), labels)

    s = _PHASE_KEY_RE.sub(_repl, s)
    # 再按最长 key 替换括号内残留英文
    for key in sorted(labels.keys(), key=len, reverse=True):
        if not key or key in ("qps", "p95") or len(key) < 4:
            continue
        if key in s:
            s = s.replace(key, labels[key])
    return s


def scrub_ai_payload(payload: dict[str, Any], label_map: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """递归清洗 AI 结构化结果中的英文字段名泄漏。"""
    if not isinstance(payload, dict):
        return payload
    labels = label_map or {}

    def _walk(obj: Any) -> Any:
        if isinstance(obj, str):
            return scrub_ai_text_keys(obj, labels)
        if isinstance(obj, list):
            return [_walk(x) for x in obj]
        if isinstance(obj, dict):
            return {k: _walk(v) for k, v in obj.items()}
        return obj

    cleaned = _walk(payload)
    return cleaned if isinstance(cleaned, dict) else payload


# 模型偶发仍输出的无目标套话 / 臆造达标语；写入前剥离
_SLA_UNCONFIGURED_PHRASES = (
    "未配置性能目标，无法按业务 SLA 判定",
    "未配置性能指标，无法按业务 SLA 判定",
    "未配置性能目标，无法判定是否达标",
    "未配置性能指标，无法判定是否达标",
)

# 无验收目标时模型爱写的「未达预期 / 理论最大」等；只剥判定词，保留实测数字
_INVENTED_EXPECTATION_RES = (
    re.compile(r"[，,；;]?\s*请求量与性能指标均未达预期"),
    re.compile(r"[，,；;]?\s*性能指标均未达预期"),
    re.compile(r"[，,；;]?\s*请求数量与QPS均未达预期"),
    re.compile(r"[，,；;]?\s*请求量与QPS均未达预期"),
    re.compile(r"[，,；;]?\s*均未达预期"),
    re.compile(r"[，,；;]?\s*未达(到)?(业务)?预期"),
    re.compile(r"[，,；;]?\s*未达(到)?SLA"),
    re.compile(r"[，,；;]?\s*指标不达标"),
    re.compile(r"[，,；;]?\s*性能不达标"),
    re.compile(r"[，,；;]?\s*未达到理论最大(值)?[（(][^）)]*[）)]"),
    re.compile(r"[，,；;]?\s*未达到理论最大(值)?"),
    re.compile(r"[，,；;]?\s*理论应达\s*\d+\s*请求"),
    re.compile(r"理论最大(值)?\s*[（(][^）)]*[）)]"),
    re.compile(r"需确认(压测)?时长和请求间隔设计的合理性[，,]?"),
)


def scrub_unconfigured_sla_boilerplate(text: Any) -> str:
    """去掉无目标套话与臆造「未达预期/理论最大」判定，保留其余常规解读。"""
    s = str(text or "")
    if not s.strip():
        return ""
    for phrase in _SLA_UNCONFIGURED_PHRASES:
        s = s.replace(phrase, "")
    for pat in _INVENTED_EXPECTATION_RES:
        s = pat.sub("", s)
    # 残留「但/且」后空句清理
    s = re.sub(r"(但|且|不过)\s*([。．.！!？?]|$)", r"\2", s)
    s = re.sub(r"[，,；;]\s*[，,；;]+", "，", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip(" ，,;；。.\n\t")


def done_payload(parsed: dict[str, Any], *, label_map: Optional[dict[str, str]] = None) -> dict[str, Any]:
    metric_notes = parsed.get("metric_notes") or {}
    if not isinstance(metric_notes, dict):
        metric_notes = {}
    case_notes = parsed.get("case_notes") or []
    if not isinstance(case_notes, list):
        case_notes = []
    cleaned_cases = []
    for item in case_notes[:40]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        note = scrub_unconfigured_sla_boilerplate(item.get("note") or "")[:500]
        if name and note:
            cleaned_cases.append({"name": name[:120], "note": note})
    chart_notes = parsed.get("chart_notes") or []
    if not isinstance(chart_notes, list):
        chart_notes = []
    cleaned_charts = []
    for item in chart_notes[:12]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("name") or "").strip()
        trend = scrub_unconfigured_sla_boilerplate(
            item.get("trend") or item.get("trend_note") or ""
        )[:500]
        dist = scrub_unconfigured_sla_boilerplate(
            item.get("distribution") or item.get("distribution_note") or ""
        )[:500]
        if label and (trend or dist):
            cleaned_charts.append({
                "label": label[:120],
                "trend": trend,
                "distribution": dist,
            })
    trend_note = scrub_unconfigured_sla_boilerplate(parsed.get("trend_note") or "")[:500]
    distribution_note = scrub_unconfigured_sla_boilerplate(
        parsed.get("distribution_note") or ""
    )[:500]
    allowed_metric_note_keys = {
        "qps", "avg_rt", "p95", "error_rate", "total_requests", "success_qps",
        "success_avg_rt", "success_p95", "p90", "p99",
    }
    cleaned_metric_notes = {}
    for k, v in metric_notes.items():
        if not v:
            continue
        key = str(k)
        if key in allowed_metric_note_keys or key.startswith("phase_"):
            note = scrub_unconfigured_sla_boilerplate(v)[:500]
            if note:
                cleaned_metric_notes[key] = note

    conclusion_points = parsed.get("conclusion_points") or parsed.get("metric_deltas") or []
    cleaned_points = []
    if isinstance(conclusion_points, list):
        for item in conclusion_points[:24]:
            if isinstance(item, str) and item.strip():
                text = scrub_unconfigured_sla_boilerplate(item)[:500]
                if text:
                    cleaned_points.append({"label": "", "text": text, "tone": "flat"})
                continue
            if not isinstance(item, dict):
                continue
            label = scrub_unconfigured_sla_boilerplate(item.get("label") or "")[:80]
            text = scrub_unconfigured_sla_boilerplate(
                item.get("text") or item.get("note") or ""
            )[:500]
            tone = str(item.get("tone") or "flat").strip().lower()
            if tone not in ("better", "worse", "flat", "improved", "degraded"):
                tone = "flat"
            if text or label:
                cleaned_points.append({"label": label, "text": text or label, "tone": tone})

    def _scrub_str_list(items: Any, *, limit: int = 20) -> list[str]:
        out_list: list[str] = []
        if not isinstance(items, list):
            return out_list
        for x in items[:limit]:
            t = scrub_unconfigured_sla_boilerplate(x)[:500]
            if t:
                out_list.append(t)
        return out_list

    summary = scrub_unconfigured_sla_boilerplate(parsed.get("summary") or "") or None
    overview_raw = parsed.get("overview") or parsed.get("summary")
    overview = scrub_unconfigured_sla_boilerplate(overview_raw or "") or summary

    out = {
        "status": "done",
        "summary": summary,
        "overview": overview,
        "metric_notes": cleaned_metric_notes,
        "conclusion_points": cleaned_points,
        "case_notes": cleaned_cases,
        "chart_notes": cleaned_charts,
        "trend_note": trend_note or None,
        "distribution_note": distribution_note or None,
        "highlights": _scrub_str_list(parsed.get("highlights") or []),
        "risks": _scrub_str_list(parsed.get("risks") or []),
        "recommendations": _scrub_str_list(parsed.get("recommendations") or []),
        "bottleneck_notes": _scrub_str_list(parsed.get("bottleneck_notes") or []),
        "resource_notes": _scrub_str_list(parsed.get("resource_notes") or [], limit=24),
        "error": None,
        "generated_at": _now_str(),
    }
    return scrub_ai_payload(out, label_map)


def _ms_to_seconds_text(ms: Any) -> str:
    """快照 RT 为毫秒，结论文案统一写成秒（一位小数）。"""
    try:
        v = float(ms)
    except (TypeError, ValueError):
        return "—"
    return f"{v / 1000.0:.1f}"


def _level_concurrent_users(lv: dict) -> int:
    try:
        return int(lv.get("concurrent_users") or 0)
    except (TypeError, ValueError):
        return 0


def enrich_ai_with_ladder_coverage(payload: dict[str, Any], snapshot: Optional[dict] = None) -> dict[str, Any]:
    """若 AI 漏写阶梯/分章中的并发档，用快照数字补全 conclusion_points，并修正 summary 档位列表。"""
    if not isinstance(payload, dict) or payload.get("status") != "done":
        return payload
    snap = snapshot if isinstance(snapshot, dict) else {}
    ladder = snap.get("ladder_summary") if isinstance(snap.get("ladder_summary"), dict) else {}
    levels = [lv for lv in (ladder.get("levels") or []) if isinstance(lv, dict)]
    roster = [r for r in (snap.get("chapter_roster") or []) if isinstance(r, dict)]

    # 优先用 ladder；否则用 roster 的 concurrent_users
    if len(levels) < 2 and len(roster) >= 2:
        levels = []
        for r in roster:
            cu = _level_concurrent_users(r)
            if cu <= 0:
                continue
            levels.append({
                "concurrent_users": cu,
                "label": r.get("label"),
                "avg_response_time": r.get("avg_response_time"),
                "p95_response_time": r.get("p95_response_time"),
                "qps": r.get("qps"),
                "error_rate": r.get("error_rate"),
                "total_requests": r.get("total_requests"),
            })

    levels = [lv for lv in levels if _level_concurrent_users(lv) > 0]
    levels.sort(key=_level_concurrent_users)
    if len(levels) < 2:
        return payload

    # 同并发多章时保留首条数字即可
    by_cu: dict[int, dict] = {}
    for lv in levels:
        cu = _level_concurrent_users(lv)
        by_cu.setdefault(cu, lv)
    levels = [by_cu[c] for c in sorted(by_cu)]
    cus = [ _level_concurrent_users(lv) for lv in levels ]
    full_phrase = "/".join(str(c) for c in cus)

    points = list(payload.get("conclusion_points") or [])
    blob_parts = [
        str(payload.get("summary") or ""),
        str(payload.get("overview") or ""),
    ]
    for p in points:
        if isinstance(p, dict):
            blob_parts.append(str(p.get("label") or ""))
            blob_parts.append(str(p.get("text") or ""))
        else:
            blob_parts.append(str(p))
    blob = "\n".join(blob_parts)

    # 认作「已提及」：出现「N并发」或在「a/b/c」档位枚举里
    mentioned: set[int] = set()
    for cu in cus:
        if (
            re.search(rf"(?<!\d){cu}\s*并发", blob)
            or re.search(rf"(?<!\d){cu}/", blob)
            or re.search(rf"/{cu}(?!\d)", blob)
        ):
            mentioned.add(cu)

    missing = [lv for lv in levels if _level_concurrent_users(lv) not in mentioned]
    for lv in missing:
        cu = _level_concurrent_users(lv)
        label = str(lv.get("label") or f"{cu}并发")
        short = re.sub(r"^.*?[-·]", "", label).strip() or f"{cu}并发"
        if str(cu) not in short:
            short = f"{cu}并发"
        avg_s = _ms_to_seconds_text(lv.get("avg_response_time"))
        p95_s = _ms_to_seconds_text(lv.get("p95_response_time"))
        qps = lv.get("qps")
        try:
            qps_t = f"{float(qps):.2f}" if qps is not None else "—"
        except (TypeError, ValueError):
            qps_t = "—"
        points.append({
            "label": short[:80],
            "text": f"平均响应时间{avg_s}秒，P95响应时间{p95_s}秒，QPS {qps_t}",
            "tone": "flat",
        })

    def _fix_cu_list(text: str) -> str:
        if not text:
            return text

        def repl(m: re.Match) -> str:
            parts = [int(x) for x in re.findall(r"\d+", m.group(0))]
            if len(parts) >= 2 and set(parts).issubset(set(cus)) and set(parts) != set(cus):
                return full_phrase
            return m.group(0)

        return re.sub(r"\d+(?:\s*/\s*\d+){1,12}", repl, text)

    summary = _fix_cu_list(str(payload.get("summary") or ""))
    overview = _fix_cu_list(str(payload.get("overview") or ""))
    if missing:
        prefix = f"本报告含并发 {full_phrase} 共 {len(cus)} 档实测。"
        if summary and prefix not in summary:
            summary = prefix + summary
        elif not summary:
            summary = prefix

    out = dict(payload)
    out["conclusion_points"] = points[:24]
    if summary:
        out["summary"] = summary
    if overview:
        out["overview"] = overview
    return out


# 被测资源写入 AI 上下文：只传摘要，不传全量曲线
SUT_AI_MAX_SERVERS = 5
SUT_AI_L1_MAX_CHAPTERS = 12
_SUT_GUIDANCE_COLLECTED = (
    "有被测资源摘要时须对照 CPU/内存/负载/磁盘IO/网络峰值与 RT/错误率写观察；"
    "若 servers[].baseline / during 存在：优先写「施压前基线 → 施压中」变化（avg/max）；"
    "仅 has_metrics=true 的机器可写指标结论；status=no_data/offline 或 has_metrics=false 禁止编造；"
    "相关不等于根因，禁止断言「就是这台机器导致」。"
    "若有 missing_roles / binding_incomplete：须声明结论仅覆盖已绑定机器，不代表全链路。"
    "未展开 servers 详表不等于资源正常。"
)
_SUT_GUIDANCE_NONE = (
    "本轮未采集被测资源，禁止编造 CPU/内存/磁盘/网卡/负载结论；"
    "勿写「资源充足/未打满」等无依据表述。"
)
_SUT_GUIDANCE_COMPARE = (
    "sut_metrics_l0 覆盖每一章是否采集及峰值；有 baseline/during 时写基线→施压中变化；"
    "结论须按章对照，禁止用部分章资源概括全书。"
    "某章 collected=false 时该章禁止写 CPU/内存结论。"
    "sut_metrics_l1 为可裁详表，缺失或 truncated 时不得臆造未列出的机器指标。"
)


def _sut_pct_pair(summary: Optional[dict], key: str) -> tuple[Any, Any]:
    block = (summary or {}).get(key) if isinstance(summary, dict) else None
    if not isinstance(block, dict):
        return None, None
    return block.get("avg"), block.get("max")


def _sut_has_metrics(detail: dict[str, Any]) -> bool:
    if detail.get("cpu_pct_max") is not None or detail.get("mem_pct_max") is not None:
        return True
    if detail.get("load1_max") is not None:
        return True
    if detail.get("disk_read_kbps_max") is not None or detail.get("disk_write_kbps_max") is not None:
        return True
    st = str(detail.get("status") or "")
    if st in ("no_data", "offline", "failed", "none"):
        return False
    try:
        return float(detail.get("coverage") or 0) > 0
    except (TypeError, ValueError):
        return False


def _sut_server_detail_from_row(row: dict[str, Any]) -> dict[str, Any]:
    summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
    _disk_avg, disk_max = _sut_pct_pair(summary, "disk_pct")
    cpu_avg, cpu_max = _sut_pct_pair(summary, "cpu_pct")
    mem_avg, mem_max = _sut_pct_pair(summary, "mem_pct")
    load_avg, load_max = _sut_pct_pair(summary, "load1")
    rx_avg, rx_max = _sut_pct_pair(summary, "net_rx_kbps")
    tx_avg, tx_max = _sut_pct_pair(summary, "net_tx_kbps")
    dr_avg, dr_max = _sut_pct_pair(summary, "disk_read_kbps")
    dw_avg, dw_max = _sut_pct_pair(summary, "disk_write_kbps")
    quality = summary.get("quality") if isinstance(summary.get("quality"), dict) else {}
    out: dict[str, Any] = {
        "name": str(row.get("display_name") or row.get("name") or "")[:80],
        "role": str(row.get("role") or "")[:40],
        "status": row.get("status"),
        "coverage": row.get("coverage"),
        "cpu_pct_avg": cpu_avg,
        "cpu_pct_max": cpu_max,
        "mem_pct_avg": mem_avg,
        "mem_pct_max": mem_max,
        "disk_pct_max": disk_max,
        "load1_avg": load_avg,
        "load1_max": load_max,
        "net_rx_kbps_avg": rx_avg,
        "net_rx_kbps_max": rx_max,
        "net_tx_kbps_avg": tx_avg,
        "net_tx_kbps_max": tx_max,
        "disk_read_kbps_avg": dr_avg,
        "disk_read_kbps_max": dr_max,
        "disk_write_kbps_avg": dw_avg,
        "disk_write_kbps_max": dw_max,
        "interval_sec": summary.get("interval_sec") or row.get("interval_sec"),
        "raw_point_count": summary.get("raw_point_count"),
    }
    if quality:
        out["bucket_coverage"] = quality.get("bucket_coverage")
        out["max_gap_sec"] = quality.get("max_gap_sec")
        out["first_point_delay_sec"] = quality.get("first_point_delay_sec")
        out["resolution_level"] = quality.get("resolution_level")
    phases = summary.get("phases") if isinstance(summary.get("phases"), dict) else {}
    baseline = phases.get("baseline") if isinstance(phases.get("baseline"), dict) else {}
    during = phases.get("during") if isinstance(phases.get("during"), dict) else {}
    if baseline or during:
        def _phase_snip(ph: dict) -> dict[str, Any]:
            def _m(key: str) -> dict:
                block = ph.get(key) if isinstance(ph.get(key), dict) else {}
                return {"avg": block.get("avg"), "max": block.get("max")}

            return {
                "cpu_pct_avg": _m("cpu_pct").get("avg"),
                "cpu_pct_max": _m("cpu_pct").get("max"),
                "mem_pct_avg": _m("mem_pct").get("avg"),
                "mem_pct_max": _m("mem_pct").get("max"),
                "load1_max": _m("load1").get("max"),
                "disk_read_kbps_max": _m("disk_read_kbps").get("max"),
                "disk_write_kbps_max": _m("disk_write_kbps").get("max"),
                "net_rx_kbps_max": _m("net_rx_kbps").get("max"),
                "net_tx_kbps_max": _m("net_tx_kbps").get("max"),
                "point_count": ph.get("point_count") or 0,
                "lookback_sec": ph.get("lookback_sec"),
            }
        out["baseline"] = _phase_snip(baseline)
        out["during"] = _phase_snip(during)
    out["has_metrics"] = _sut_has_metrics(out)
    return out


def _sut_aggregate_peaks(servers: list[dict[str, Any]]) -> dict[str, Any]:
    def _max_of(key: str) -> Any:
        vals = []
        for s in servers:
            v = s.get(key)
            if v is None:
                continue
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                continue
        return round(max(vals), 2) if vals else None

    return {
        "cpu_pct_max": _max_of("cpu_pct_max"),
        "mem_pct_max": _max_of("mem_pct_max"),
        "load1_max": _max_of("load1_max"),
        "disk_read_kbps_max": _max_of("disk_read_kbps_max"),
        "disk_write_kbps_max": _max_of("disk_write_kbps_max"),
    }


def build_sut_metrics_ai_block_from_rows(
    *,
    status: Optional[str],
    rows: Optional[list],
    max_servers: int = SUT_AI_MAX_SERVERS,
    binding: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """由切片行构建单报告/单章精简块（无曲线点）。"""
    st = str(status or "none").strip() or "none"
    raw_rows = [r for r in (rows or []) if isinstance(r, dict)]
    if st == "none" and not raw_rows:
        return {
            "status": "none",
            "collected": False,
            "guidance": _SUT_GUIDANCE_NONE,
            "servers": [],
            "cpu_pct_max": None,
            "mem_pct_max": None,
        }

    details = [_sut_server_detail_from_row(r) for r in raw_rows]
    details.sort(
        key=lambda s: (
            -(float(s["coverage"]) if s.get("coverage") is not None else -1.0),
            -(float(s["cpu_pct_max"]) if s.get("cpu_pct_max") is not None else -1.0),
        )
    )
    total = len(details)
    truncated = total > max_servers
    details = details[: max(1, int(max_servers or SUT_AI_MAX_SERVERS))]
    metric_servers = [s for s in details if s.get("has_metrics")]
    has_metric = bool(metric_servers)
    collected = st not in ("none",) and has_metric
    peaks = _sut_aggregate_peaks(metric_servers) if collected else {
        "cpu_pct_max": None,
        "mem_pct_max": None,
        "load1_max": None,
        "disk_read_kbps_max": None,
        "disk_write_kbps_max": None,
    }
    out: dict[str, Any] = {
        "status": st,
        "collected": collected,
        "guidance": _SUT_GUIDANCE_COLLECTED if collected else _SUT_GUIDANCE_NONE,
        "servers": details if collected else [],
        "cpu_pct_max": peaks.get("cpu_pct_max"),
        "mem_pct_max": peaks.get("mem_pct_max"),
        "load1_max": peaks.get("load1_max"),
        "disk_read_kbps_max": peaks.get("disk_read_kbps_max"),
        "disk_write_kbps_max": peaks.get("disk_write_kbps_max"),
        "server_count_total": total,
        "collected_server_count": len(metric_servers),
    }
    bind = binding if isinstance(binding, dict) else {}
    if bind:
        missing_roles = bind.get("missing_roles") or []
        missing_servers = bind.get("missing_server_ids") or []
        by_role = bind.get("by_role") if isinstance(bind.get("by_role"), dict) else {}
        out["binding"] = {
            "source": bind.get("source"),
            "missing_roles": missing_roles[:20] if isinstance(missing_roles, list) else [],
            "missing_server_ids": missing_servers[:20] if isinstance(missing_servers, list) else [],
            "bound_roles": list(by_role.keys())[:20],
            "binding_incomplete": bool(missing_roles or missing_servers),
        }
    if truncated and collected:
        out["truncated"] = True
    return out

def sut_l0_line_from_block(*, label: str, block: dict[str, Any]) -> dict[str, Any]:
    servers = block.get("servers") if isinstance(block.get("servers"), list) else []
    b_cpu: list[float] = []
    d_cpu: list[float] = []
    for s in servers:
        if not isinstance(s, dict):
            continue
        b = s.get("baseline") if isinstance(s.get("baseline"), dict) else {}
        d = s.get("during") if isinstance(s.get("during"), dict) else {}
        for src, bucket in ((b, b_cpu), (d, d_cpu)):
            v = src.get("cpu_pct_max")
            if v is None:
                continue
            try:
                bucket.append(float(v))
            except (TypeError, ValueError):
                pass
    return {
        "label": str(label or "")[:120],
        "collected": bool(block.get("collected")),
        "status": block.get("status") or "none",
        "cpu_pct_max": block.get("cpu_pct_max"),
        "mem_pct_max": block.get("mem_pct_max"),
        "baseline_cpu_max": round(max(b_cpu), 2) if b_cpu else None,
        "during_cpu_max": round(max(d_cpu), 2) if d_cpu else None,
    }


async def load_sut_metrics_ai_block(record: Any) -> dict[str, Any]:
    """异步加载单条压测记录的被测资源 AI 摘要。"""
    cfg = record.config_snapshot if isinstance(getattr(record, "config_snapshot", None), dict) else {}
    status = cfg.get("sut_metrics_status") or "none"
    binding = cfg.get("sut_binding_snapshot") if isinstance(cfg.get("sut_binding_snapshot"), dict) else None
    try:
        from app.modules.perf.sut_slice import load_sut_resource_series

        rows = await load_sut_resource_series(int(record.id))
    except Exception:
        rows = []
        if status not in ("none",):
            status = "failed"
    return build_sut_metrics_ai_block_from_rows(status=status, rows=rows, binding=binding)


async def load_sut_metrics_ai_blocks_by_record_ids(
    record_ids: list[int],
) -> dict[int, dict[str, Any]]:
    """批量：record_id → 精简块。"""
    ids = [int(x) for x in dict.fromkeys(record_ids) if x is not None]
    if not ids:
        return {}
    from app.models.perf import PerfRecord, PerfRecordSutMetric

    records = await PerfRecord.filter(id__in=ids).all()
    status_by: dict[int, str] = {}
    binding_by: dict[int, Optional[dict[str, Any]]] = {}
    for rec in records:
        cfg = rec.config_snapshot if isinstance(rec.config_snapshot, dict) else {}
        status_by[int(rec.id)] = str(cfg.get("sut_metrics_status") or "none")
        bind = cfg.get("sut_binding_snapshot")
        binding_by[int(rec.id)] = bind if isinstance(bind, dict) else None

    metric_rows = await PerfRecordSutMetric.filter(record_id__in=ids).prefetch_related("server").all()
    rows_by: dict[int, list[dict[str, Any]]] = {i: [] for i in ids}
    for r in metric_rows:
        snap = r.server_snapshot_json if isinstance(r.server_snapshot_json, dict) else {}
        summary = r.summary_json if isinstance(r.summary_json, dict) else {}
        rid = int(r.record_id)
        rows_by.setdefault(rid, []).append(
            {
                "server_id": r.server_id,
                "role": snap.get("role") or "",
                "display_name": snap.get("name")
                or (r.server.name if getattr(r, "server", None) else f"server-{r.server_id}"),
                "summary": summary,
                "coverage": r.coverage,
                "status": r.status,
            }
        )

    out: dict[int, dict[str, Any]] = {}
    for rid in ids:
        out[rid] = build_sut_metrics_ai_block_from_rows(
            status=status_by.get(rid, "none"),
            rows=rows_by.get(rid) or [],
            binding=binding_by.get(rid),
        )
    return out


def _compare_chapter_refs(full_snap: dict[str, Any]) -> list[tuple[str, Optional[int]]]:
    """从完整对比快照提取 (展示名, record_id)。"""
    refs: list[tuple[str, Optional[int]]] = []
    chapters = full_snap.get("chapters") or []
    if isinstance(chapters, list) and chapters:
        for c in chapters:
            if not isinstance(c, dict):
                continue
            label = str(c.get("display_name") or c.get("scene_name") or "").strip()
            rid = c.get("record_id")
            try:
                rid_i = int(rid) if rid is not None else None
            except (TypeError, ValueError):
                rid_i = None
            if not label and rid_i is not None:
                label = f"执行#{rid_i}"
            if label or rid_i is not None:
                refs.append((label or f"执行#{rid_i}", rid_i))
        return refs
    for r in full_snap.get("records") or []:
        if not isinstance(r, dict):
            continue
        rid = r.get("id")
        try:
            rid_i = int(rid) if rid is not None else None
        except (TypeError, ValueError):
            rid_i = None
        label = str(r.get("display_name") or r.get("scene_name") or "").strip()
        if not label and rid_i is not None:
            label = f"执行#{rid_i}"
        if label or rid_i is not None:
            refs.append((label or f"执行#{rid_i}", rid_i))
    return refs


async def enrich_compare_ctx_with_sut(
    ctx: dict[str, Any],
    full_snap: dict[str, Any],
    *,
    l1_max_chapters: int = SUT_AI_L1_MAX_CHAPTERS,
) -> dict[str, Any]:
    """多报告：L0 全章一行摘要；L1 有数据章节的 servers 详表（可裁）。"""
    refs = _compare_chapter_refs(full_snap if isinstance(full_snap, dict) else {})
    ids = [rid for _, rid in refs if rid is not None]
    blocks = await load_sut_metrics_ai_blocks_by_record_ids(ids)
    none_block = build_sut_metrics_ai_block_from_rows(status="none", rows=[])

    l0_chapters: list[dict[str, Any]] = []
    l1_candidates: list[dict[str, Any]] = []
    for label, rid in refs:
        block = blocks.get(rid) if rid is not None else none_block
        if not isinstance(block, dict):
            block = none_block
        l0_chapters.append(sut_l0_line_from_block(label=label, block=block))
        if block.get("collected") and block.get("servers"):
            l1_candidates.append(
                {
                    "label": label,
                    "status": block.get("status"),
                    "collected": True,
                    "cpu_pct_max": block.get("cpu_pct_max"),
                    "mem_pct_max": block.get("mem_pct_max"),
                    "servers": block.get("servers") or [],
                    **({"truncated": True, "server_count_total": block["server_count_total"]}
                       if block.get("truncated") else {}),
                }
            )

    cap = max(0, int(l1_max_chapters or SUT_AI_L1_MAX_CHAPTERS))
    l1_chapters = l1_candidates[:cap]
    out = dict(ctx)
    out["sut_metrics_l0"] = {
        "guidance": _SUT_GUIDANCE_COMPARE,
        "chapters": l0_chapters,
    }
    out["sut_metrics_l1"] = {
        "guidance": "可裁详表；预算不足时可能被省略。",
        "chapters": l1_chapters,
        "truncated": len(l1_candidates) > cap,
        "chapter_count_with_data": len(l1_candidates),
    }
    return out


def build_record_ai_context(record: Any, *, max_ts_points: int = 30) -> dict[str, Any]:
    """精简单条压测记录上下文，控制 token。"""
    ts = list(record.time_series_data or [])
    if len(ts) > max_ts_points:
        step = max(1, len(ts) // max_ts_points)
        ts = ts[::step][:max_ts_points]

    cases = []
    ag = record.case_aggregations or {}
    for cid, info in list(ag.items())[:40]:
        if not isinstance(info, dict):
            continue
        cases.append({
            "name": info.get("name") or f"接口-{cid}",
            "total": info.get("total", 0),
            "fail": info.get("fail", 0),
            "avg_rt": info.get("avg_rt"),
            "p95_rt": info.get("p95_rt"),
            "error_rate": info.get("error_rate"),
        })

    err = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
    hist = err.get("rt_histogram") or []
    hist_summary = []
    if isinstance(hist, list) and hist:
        ranked = sorted(
            [h for h in hist if isinstance(h, dict)],
            key=lambda x: -(int(x.get("count") or 0)),
        )[:5]
        hist_summary = [{"label": h.get("label"), "count": h.get("count")} for h in ranked]
    err_summary = {
        k: v for k, v in err.items()
        if not str(k).startswith("_")
        and k not in ("failed_samples", "request_traces", "rt_histogram")
    }
    # 失败采样仅保留少量摘要
    samples = err.get("failed_samples") or []
    if isinstance(samples, list) and samples:
        err_summary["failed_sample_count"] = len(samples)
        err_summary["failed_sample_preview"] = [
            {
                "url": s.get("url") or s.get("name"),
                "status_code": s.get("status_code"),
                "error": (s.get("error") or s.get("error_message") or "")[:200],
            }
            for s in samples[:8]
            if isinstance(s, dict)
        ]

    cfg = record.config_snapshot or {}
    from app.routers.perf.report_utils import (
        build_config_summary,
        summarize_stepping_stages,
        peak_users_from_config,
    )

    cfg_summary = build_config_summary(
        cfg,
        getattr(record, "distribution_info", None) or {},
        getattr(record, "scene_items_snapshot", None),
    )
    mode = cfg_summary.get("mode") or cfg.get("mode") or "fixed"
    ai_config: dict[str, Any] = {
        "mode": mode,
        "mode_label": cfg_summary.get("mode_label"),
        "concurrent_users": cfg.get("concurrent_users"),
        "peak_concurrent_users": cfg_summary.get("peak_concurrent_users") or peak_users_from_config(cfg),
        "ramp_up_seconds": cfg.get("ramp_up_seconds"),
        "duration_seconds": cfg.get("duration_seconds"),
        "warmup_seconds": cfg_summary.get("warmup_seconds"),
        "request_detail_level": cfg.get("request_detail_level"),
        "ai_analyze_on_complete": cfg.get("ai_analyze_on_complete"),
        "duration_label": cfg_summary.get("duration_label"),
        "steps_summary": cfg_summary.get("steps_summary"),
    }
    if mode == "stepping":
        ai_config["steps"] = cfg_summary.get("steps") or []

    ctx: dict[str, Any] = {
        "status": record.status,
        "started_at": record.started_at.strftime("%Y-%m-%d %H:%M:%S") if record.started_at else None,
        "duration": record.duration,
        "total_requests": record.total_requests,
        "success_count": record.success_count,
        "fail_count": record.fail_count,
        "qps": record.qps,
        "avg_response_time": record.avg_response_time,
        "p90_response_time": record.p90_response_time,
        "p95_response_time": record.p95_response_time,
        "p99_response_time": record.p99_response_time,
        "error_rate": record.error_rate,
        "config": ai_config,
        "case_aggregations": cases,
        "error_breakdown": err_summary,
        "rt_histogram_summary": hist_summary,
        "time_series_sample": [
            {
                "t": p.get("timestamp"),
                "qps": p.get("qps"),
                "avg_rt": p.get("avg_rt"),
                "p95": p.get("p95_rt"),
                "err": p.get("error_rate"),
                "users": p.get("active_users"),
            }
            for p in ts
            if isinstance(p, dict)
        ],
    }
    if mode == "stepping":
        stages = summarize_stepping_stages(cfg, record.time_series_data or [])
        ctx["stepping_stages"] = stages
        from app.routers.perf.report_utils import format_stepping_stages_narrative
        ctx["stepping_stages_summary"] = format_stepping_stages_narrative(stages)

    from app.modules.perf.perf_target_eval import evaluate_perf_targets, normalize_perf_targets

    raw_targets = cfg.get("perf_targets") if isinstance(cfg, dict) else None
    ctx["perf_targets"] = normalize_perf_targets(raw_targets if isinstance(raw_targets, dict) else None)
    ctx["target_evaluation"] = evaluate_perf_targets(record)
    return ctx


async def run_perf_record_analysis(
    record_id: int,
    *,
    username: str = "system",
    ai_config_id: Optional[int] = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """同步执行单报告分析并写回 PerfRecord.ai_analysis。"""
    from app.models.perf import PerfRecord
    from app.models.ai import AiGenerateRecord
    from app.modules.ai.ai_prompts import PromptManager
    from app.modules.ai.ai_project_settings import load_ai_project_settings
    from app.core.llm.ai_usage_log import log_ai_usage
    from app.routers.ai.generate import _call_llm, _get_ai_config
    from app.routers.ai.analyze import _extract_json_object

    record = await PerfRecord.get_or_none(id=record_id)
    if not record:
        raise ValueError("压测记录不存在")

    settings = await load_ai_project_settings(record.project_id)
    if not settings.get("perf_ai_analysis_enabled", False):
        raise ValueError("项目已关闭压测 AI 分析")

    existing = record.ai_analysis if isinstance(record.ai_analysis, dict) else None
    if (
        not force_refresh
        and existing
        and existing.get("status") == "done"
        and existing.get("summary")
    ):
        return {**existing, "cached": True, "record_id": record.id}

    # 仅「非强刷」时把 running 当进行中；强刷/后台任务必须继续执行（调用方已先写入 running）
    if not force_refresh and is_analysis_in_progress(existing):
        return {**existing, "record_id": record.id}

    if not await _try_begin_inflight(_inflight_records, record_id):
        record = await PerfRecord.get_or_none(id=record_id)
        existing = (record.ai_analysis if record and isinstance(record.ai_analysis, dict) else None) or running_placeholder()
        return {**existing, "record_id": record_id, "deduped": True}

    try:
        return await _run_perf_record_analysis_locked(
            record_id,
            username=username,
            ai_config_id=ai_config_id,
        )
    finally:
        await _end_inflight(_inflight_records, record_id)


def pack_record_snapshot_json_for_ai(ctx: dict[str, Any], *, max_chars: int = 14000) -> str:
    """单报告 AI 上下文：优先保留 sut_metrics，再压时序/用例详表，避免粗暴截断 JSON。"""

    def _dumps(obj: dict) -> str:
        return json.dumps(obj, ensure_ascii=False, indent=2)

    must_keys = (
        "scene_name",
        "mode",
        "concurrent_users",
        "duration",
        "total_requests",
        "success_rate",
        "error_rate",
        "avg_response_time",
        "p95_response_time",
        "qps",
        "acceptance_targets",
        "sut_metrics",
    )
    soft_keys = ("time_series_sample", "case_aggregations", "error_breakdown", "rt_histogram_summary", "config")
    must = {k: ctx[k] for k in must_keys if k in ctx and ctx[k] is not None}
    # acceptance_targets 可能在 perf_targets / target_evaluation
    if "acceptance_targets" not in must and ctx.get("perf_targets") is not None:
        must["perf_targets"] = ctx.get("perf_targets")
        must["target_evaluation"] = ctx.get("target_evaluation")
    soft = {k: ctx[k] for k in soft_keys if k in ctx and ctx[k] is not None}
    rest = {k: v for k, v in ctx.items() if k not in must and k not in soft}

    packed = dict(must)
    blob = _dumps(packed)
    if len(blob) > max_chars:
        # 极紧：只留核心指标 + sut 峰值
        sut = packed.get("sut_metrics") if isinstance(packed.get("sut_metrics"), dict) else {}
        slim_sut = {
            "collected": sut.get("collected"),
            "status": sut.get("status"),
            "guidance": sut.get("guidance"),
            "cpu_pct_max": sut.get("cpu_pct_max"),
            "mem_pct_max": sut.get("mem_pct_max"),
            "load1_max": sut.get("load1_max"),
            "binding": sut.get("binding"),
            "servers": (sut.get("servers") or [])[:3],
        }
        packed = {
            k: packed[k]
            for k in ("mode", "concurrent_users", "qps", "p95_response_time", "error_rate", "avg_response_time")
            if k in packed
        }
        packed["sut_metrics"] = slim_sut
        return _dumps(packed)[:max_chars]

    for k, v in soft.items():
        trial = dict(packed)
        trial[k] = v
        if len(_dumps(trial)) <= max_chars:
            packed = trial
        elif k == "time_series_sample" and isinstance(v, list):
            for n in (20, 10, 5):
                trial[k] = v[:n]
                if len(_dumps(trial)) <= max_chars:
                    packed = trial
                    break

    for k, v in rest.items():
        trial = dict(packed)
        trial[k] = v
        if len(_dumps(trial)) <= max_chars:
            packed = trial

    return _dumps(packed)


async def _run_perf_record_analysis_locked(
    record_id: int,
    *,
    username: str = "system",
    ai_config_id: Optional[int] = None,
) -> dict[str, Any]:
    from app.models.perf import PerfRecord
    from app.models.ai import AiGenerateRecord
    from app.modules.ai.ai_prompts import PromptManager
    from app.core.llm.ai_usage_log import log_ai_usage
    from app.routers.ai.generate import _call_llm, _get_ai_config
    from app.routers.ai.analyze import _extract_json_object

    record = await PerfRecord.get_or_none(id=record_id)
    if not record:
        raise ValueError("压测记录不存在")

    record.ai_analysis = running_placeholder()
    await record.save(update_fields=["ai_analysis"])

    ctx = build_record_ai_context(record)
    try:
        ctx["sut_metrics"] = await load_sut_metrics_ai_block(record)
    except Exception:
        ctx["sut_metrics"] = build_sut_metrics_ai_block_from_rows(status="failed", rows=[])
    prompt_ctx = {"report_snapshot": pack_record_snapshot_json_for_ai(ctx, max_chars=14000)}
    try:
        system_prompt, user_prompt = await PromptManager.render("perf_report_analysis", prompt_ctx)
    except ValueError as e:
        record.ai_analysis = failed_payload(str(e))
        await record.save(update_fields=["ai_analysis"])
        raise

    text_config = await _get_ai_config(ai_config_id, scene=PERF_RECORD_AI_SCENE)
    from app.modules.ai.ai_scene_config import get_scene_llm_overrides

    overrides = await get_scene_llm_overrides(PERF_RECORD_AI_SCENE)
    t0 = time.time()
    try:
        llm_resp = await _call_llm(
            system_prompt,
            user_prompt,
            text_config,
            min_timeout=90,
            max_retries=1,
            param_overrides=overrides or None,
        )
    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        await log_ai_usage(
            text_config,
            PERF_RECORD_AI_SCENE,
            username=username,
            project_id=record.project_id,
            tokens_used=0,
            duration_ms=duration_ms,
            status="failed",
            input_summary=f"perf_report#{record.id}"[:500],
            output_summary=str(e)[:500],
        )
        record.ai_analysis = failed_payload(str(e))
        await record.save(update_fields=["ai_analysis"])
        raise

    duration_ms = int((time.time() - t0) * 1000)
    raw_response = llm_resp.get("content") or ""
    tokens_used = int(llm_resp.get("tokens") or 0)
    parsed = _extract_json_object(raw_response)
    ok = bool(parsed.get("summary"))
    payload = done_payload(parsed, label_map=metric_label_map_from_snapshot(ctx)) if ok else failed_payload("LLM 返回未能解析为结构化分析")
    if not ok:
        payload["raw_preview"] = raw_response[:500]

    record.ai_analysis = payload
    await record.save(update_fields=["ai_analysis"])

    await AiGenerateRecord.create(
        project_id=record.project_id,
        generate_type="perf_report_analysis",
        input_summary={"record_id": record.id},
        output_content={**payload, "raw_response": raw_response[:4000]},
        status="accepted" if ok else "rejected",
        ai_config_id=text_config.id if text_config else None,
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        create_by=username or "system",
    )
    await log_ai_usage(
        text_config,
        PERF_RECORD_AI_SCENE,
        username=username,
        project_id=record.project_id,
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        input_summary=f"perf_report#{record.id}"[:500],
        output_summary=(payload.get("summary") or payload.get("error") or "")[:500],
    )
    return {**payload, "cached": False, "record_id": record.id}


async def run_perf_compare_analysis(
    report_id: int,
    *,
    username: str = "system",
    ai_config_id: Optional[int] = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """同步执行对比报告分析并写回 ai_analysis。"""
    from app.models.perf import PerfComparisonReport
    from app.modules.ai.ai_project_settings import load_ai_project_settings

    report = await PerfComparisonReport.get_or_none(id=report_id, is_del=False)
    if not report:
        raise ValueError("对比报告不存在")

    settings = await load_ai_project_settings(report.project_id)
    if not settings.get("perf_ai_analysis_enabled", False):
        raise ValueError("项目已关闭压测 AI 分析")

    existing = report.ai_analysis if isinstance(report.ai_analysis, dict) else None
    if (
        not force_refresh
        and existing
        and existing.get("status") == "done"
        and existing.get("summary")
    ):
        return {**existing, "cached": True, "comparison_report_id": report.id}
    # 兼容旧数据：有 summary 无 status
    if (
        not force_refresh
        and existing
        and existing.get("summary")
        and not existing.get("status")
    ):
        return {**existing, "status": "done", "cached": True, "comparison_report_id": report.id}

    # 仅非强刷时拦截进行中；后台 schedule 使用 force_refresh=True 必须继续执行
    if not force_refresh and is_analysis_in_progress(existing):
        return {**existing, "comparison_report_id": report.id}

    if not await _try_begin_inflight(_inflight_compares, report_id):
        report = await PerfComparisonReport.get_or_none(id=report_id, is_del=False)
        existing = (report.ai_analysis if report and isinstance(report.ai_analysis, dict) else None) or running_placeholder()
        return {**existing, "comparison_report_id": report_id, "deduped": True}

    try:
        return await _run_perf_compare_analysis_locked(
            report_id,
            username=username,
            ai_config_id=ai_config_id,
        )
    finally:
        await _end_inflight(_inflight_compares, report_id)


async def _run_perf_compare_analysis_locked(
    report_id: int,
    *,
    username: str = "system",
    ai_config_id: Optional[int] = None,
) -> dict[str, Any]:
    from app.models.perf import PerfComparisonReport
    from app.models.ai import AiGenerateRecord
    from app.modules.ai.ai_prompts import PromptManager
    from app.modules.perf.compare_report import hydrate_snapshot_chart_fields, trim_snapshot_for_ai
    from app.core.llm.ai_usage_log import log_ai_usage
    from app.routers.ai.generate import _call_llm, _get_ai_config
    from app.routers.ai.analyze import _extract_json_object

    report = await PerfComparisonReport.get_or_none(id=report_id, is_del=False)
    if not report:
        raise ValueError("对比报告不存在")

    report.ai_analysis = running_placeholder()
    await report.save(update_fields=["ai_analysis"])

    snap = await hydrate_snapshot_chart_fields(report.snapshot or {})
    ctx = trim_snapshot_for_ai(snap)
    try:
        ctx = await enrich_compare_ctx_with_sut(ctx, snap)
    except Exception:
        ctx["sut_metrics_l0"] = {
            "guidance": _SUT_GUIDANCE_COMPARE,
            "chapters": [],
        }
        ctx["sut_metrics_l1"] = {"guidance": "加载失败", "chapters": [], "truncated": False}
    # 多章节：优先保留 ladder/roster，再按预算塞 scenes；避免尾部截断漏掉低并发档
    n_ch = int(ctx.get("chapter_count") or 0)
    max_snap = 56000 if n_ch >= 6 else (40000 if n_ch >= 4 else 24000)
    from app.modules.perf.compare_report import pack_snapshot_json_for_ai
    snap_json = pack_snapshot_json_for_ai(ctx, max_chars=max_snap)
    prompt_ctx = {"compare_snapshot": snap_json}
    try:
        system_prompt, user_prompt = await PromptManager.render("perf_compare_analysis", prompt_ctx)
    except ValueError as e:
        report.ai_analysis = failed_payload(str(e))
        await report.save(update_fields=["ai_analysis"])
        raise

    extra = ((report.snapshot or {}).get("user_extra_prompt") or "").strip()
    if extra:
        user_prompt = (
            f"{user_prompt}\n\n"
            "## 用户补充说明（最高优先级，须严格遵循；仍不得编造未给出的数字）\n"
            "若补充说明要求「分组规格对照 / 组内互比 / 组间不硬比」，"
            "即使 analysis_mode=chapter_portrait，也必须按补充说明在同一份结论里完成分组对照。\n"
            "补充说明未给出明确数字门槛时，仍禁止写「未达预期/不达标/理论最大请求量」。\n"
            f"{extra[:2000]}"
        )

    text_config = await _get_ai_config(ai_config_id, scene=PERF_COMPARE_AI_SCENE)
    from app.modules.ai.ai_scene_config import get_scene_llm_overrides

    overrides = await get_scene_llm_overrides(PERF_COMPARE_AI_SCENE)
    t0 = time.time()
    try:
        llm_resp = await _call_llm(
            system_prompt,
            user_prompt,
            text_config,
            min_timeout=90,
            max_retries=1,
            param_overrides=overrides or None,
        )
    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        await log_ai_usage(
            text_config,
            PERF_COMPARE_AI_SCENE,
            username=username,
            project_id=report.project_id,
            tokens_used=0,
            duration_ms=duration_ms,
            status="failed",
            input_summary=f"perf_compare#{report.id}"[:500],
            output_summary=str(e)[:500],
        )
        report.ai_analysis = failed_payload(str(e))
        await report.save(update_fields=["ai_analysis"])
        raise

    duration_ms = int((time.time() - t0) * 1000)
    raw_response = llm_resp.get("content") or ""
    tokens_used = int(llm_resp.get("tokens") or 0)
    parsed = _extract_json_object(raw_response)
    ok = bool(parsed.get("summary"))
    payload = done_payload(parsed, label_map=metric_label_map_from_snapshot(ctx)) if ok else failed_payload("LLM 返回未能解析为结构化分析")
    if ok:
        payload = enrich_ai_with_ladder_coverage(payload, ctx)

    report.ai_analysis = payload
    await report.save(update_fields=["ai_analysis"])

    await AiGenerateRecord.create(
        project_id=report.project_id,
        generate_type="perf_compare_analysis",
        input_summary={"comparison_report_id": report.id, "record_ids": report.record_ids},
        output_content={**payload, "raw_response": raw_response[:4000]},
        status="accepted" if ok else "rejected",
        ai_config_id=text_config.id if text_config else None,
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        create_by=username or "system",
    )
    await log_ai_usage(
        text_config,
        PERF_COMPARE_AI_SCENE,
        username=username,
        project_id=report.project_id,
        tokens_used=tokens_used,
        duration_ms=duration_ms,
        input_summary=f"perf_compare#{report.id}"[:500],
        output_summary=(payload.get("summary") or payload.get("error") or "")[:500],
    )
    return {**payload, "cached": False, "comparison_report_id": report.id}


def schedule_perf_record_analysis(record_id: int, *, username: str = "system") -> None:
    """后台触发单报告分析（不阻塞 finalize）。

    调用方通常已写入 running；此处直接走 locked 执行，避免再被 running 短路。
    """

    async def _job():
        if not await _try_begin_inflight(_inflight_records, record_id):
            logger.info("跳过重复后台压测 AI 分析 record_id=%s", record_id)
            return
        try:
            from app.models.perf import PerfRecord
            from app.modules.ai.ai_project_settings import load_ai_project_settings

            record = await PerfRecord.get_or_none(id=record_id)
            if not record:
                return
            settings = await load_ai_project_settings(record.project_id)
            if not settings.get("perf_ai_analysis_enabled", False):
                return
            await _run_perf_record_analysis_locked(record_id, username=username)
        except Exception as e:
            logger.exception("后台压测报告 AI 分析失败 record_id=%s: %s", record_id, e)
        finally:
            await _end_inflight(_inflight_records, record_id)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_job())
    except RuntimeError:
        logger.warning("无事件循环，跳过后台压测 AI 分析 record_id=%s", record_id)


def schedule_perf_compare_analysis(report_id: int, *, username: str = "system") -> None:
    """后台触发对比报告分析。调用方通常已写入 running。"""

    async def _job():
        if not await _try_begin_inflight(_inflight_compares, report_id):
            logger.info("跳过重复后台对比 AI 分析 report_id=%s", report_id)
            return
        try:
            from app.models.perf import PerfComparisonReport
            from app.modules.ai.ai_project_settings import load_ai_project_settings

            report = await PerfComparisonReport.get_or_none(id=report_id, is_del=False)
            if not report:
                return
            settings = await load_ai_project_settings(report.project_id)
            if not settings.get("perf_ai_analysis_enabled", False):
                return
            await _run_perf_compare_analysis_locked(report_id, username=username)
        except Exception as e:
            logger.exception("后台对比报告 AI 分析失败 report_id=%s: %s", report_id, e)
        finally:
            await _end_inflight(_inflight_compares, report_id)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_job())
    except RuntimeError:
        logger.warning("无事件循环，跳过后台对比 AI 分析 report_id=%s", report_id)


async def maybe_trigger_record_ai_after_finalize(record: Any) -> None:
    """finalize 后：若 config 要求且项目开启，则后台分析。"""
    cfg = record.config_snapshot if isinstance(record.config_snapshot, dict) else {}
    if not cfg.get("ai_analyze_on_complete"):
        return
    from app.modules.ai.ai_project_settings import load_ai_project_settings

    settings = await load_ai_project_settings(record.project_id)
    if not settings.get("perf_ai_analysis_enabled", False):
        return
    # 先落 running，报告页可立刻看到 loading
    record.ai_analysis = running_placeholder()
    await record.save(update_fields=["ai_analysis"])
    schedule_perf_record_analysis(record.id, username=getattr(record, "run_by", None) or "system")
