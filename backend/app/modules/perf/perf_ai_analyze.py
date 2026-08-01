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
        note = str(item.get("note") or "").strip()
        if name and note:
            cleaned_cases.append({"name": name[:120], "note": note[:500]})
    chart_notes = parsed.get("chart_notes") or []
    if not isinstance(chart_notes, list):
        chart_notes = []
    cleaned_charts = []
    for item in chart_notes[:12]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("name") or "").strip()
        trend = str(item.get("trend") or item.get("trend_note") or "").strip()
        dist = str(item.get("distribution") or item.get("distribution_note") or "").strip()
        if label and (trend or dist):
            cleaned_charts.append({
                "label": label[:120],
                "trend": trend[:500],
                "distribution": dist[:500],
            })
    trend_note = str(parsed.get("trend_note") or "").strip()[:500]
    distribution_note = str(parsed.get("distribution_note") or "").strip()[:500]
    allowed_metric_note_keys = {
        "qps", "avg_rt", "p95", "error_rate", "total_requests", "success_qps",
    }
    cleaned_metric_notes = {}
    for k, v in metric_notes.items():
        if not v:
            continue
        key = str(k)
        if key in allowed_metric_note_keys or key.startswith("phase_"):
            cleaned_metric_notes[key] = str(v)[:500]

    conclusion_points = parsed.get("conclusion_points") or parsed.get("metric_deltas") or []
    cleaned_points = []
    if isinstance(conclusion_points, list):
        for item in conclusion_points[:12]:
            if isinstance(item, str) and item.strip():
                cleaned_points.append({"label": "", "text": item.strip()[:500], "tone": "flat"})
                continue
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()[:80]
            text = str(item.get("text") or item.get("note") or "").strip()[:500]
            tone = str(item.get("tone") or "flat").strip().lower()
            if tone not in ("better", "worse", "flat", "improved", "degraded"):
                tone = "flat"
            if text or label:
                cleaned_points.append({"label": label, "text": text or label, "tone": tone})

    out = {
        "status": "done",
        "summary": parsed.get("summary"),
        "overview": parsed.get("overview") or parsed.get("summary"),
        "metric_notes": cleaned_metric_notes,
        "conclusion_points": cleaned_points,
        "case_notes": cleaned_cases,
        "chart_notes": cleaned_charts,
        "trend_note": trend_note or None,
        "distribution_note": distribution_note or None,
        "highlights": parsed.get("highlights") or [],
        "risks": parsed.get("risks") or [],
        "recommendations": parsed.get("recommendations") or [],
        "bottleneck_notes": parsed.get("bottleneck_notes") or [],
        "error": None,
        "generated_at": _now_str(),
    }
    return scrub_ai_payload(out, label_map)


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

    cfg_summary = build_config_summary(cfg, getattr(record, "distribution_info", None) or {})
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
    prompt_ctx = {"report_snapshot": json.dumps(ctx, ensure_ascii=False, indent=2)[:14000]}
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
    prompt_ctx = {"compare_snapshot": json.dumps(ctx, ensure_ascii=False, indent=2)[:14000]}
    try:
        system_prompt, user_prompt = await PromptManager.render("perf_compare_analysis", prompt_ctx)
    except ValueError as e:
        report.ai_analysis = failed_payload(str(e))
        await report.save(update_fields=["ai_analysis"])
        raise

    extra = ((report.snapshot or {}).get("user_extra_prompt") or "").strip()
    if extra:
        user_prompt = (
            f"{user_prompt}\n\n## 用户补充说明（请优先遵循，但仍不得编造未给出的数字）\n{extra[:2000]}"
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
