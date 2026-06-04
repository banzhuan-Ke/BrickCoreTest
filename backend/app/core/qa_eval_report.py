"""问答准确性评测：统计报告（对齐 RAG 测试总结 docx 结构）"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional

from app.models.ai import AiQaEvalCase, AiQaEvalResult, AiQaEvalRun, AiQaEvalSet, AiQaEvalTarget

# 与 docx 报告一致的 0~1 等级划分（平台 score 为 0~100）
LEVEL_BANDS = (
    ("优秀", 90, 100),
    ("良好", 75, 89),
    ("合格", 50, 74),
    ("不合格", 25, 49),
    ("严重不合格", 0, 24),
)

MANUAL_STATUS_LABELS = {
    "pending": "待审核",
    "approved": "已通过",
    "rejected": "已驳回",
}

QA_IMPORT_TEMPLATE_COLUMNS = [
    "序号",
    "问题",
    "问答目录",
    "是否开启多轮",
    "问题类型",
    "标准答案",
    "文件",
    "文件类型",
    "实际回答",
    "标准要点",
]

QA_IMPORT_TEMPLATE_SAMPLES = [
    {
        "序号": 1,
        "问题": "概括 SOP-5000 项目团队的人员配置情况。",
        "问答目录": "[]",
        "是否开启多轮": "否",
        "问题类型": "事实性问答类",
        "标准答案": "项目团队由项目经理、硬件、软件、测试等组成…（完整参考答案）",
        "文件": "",
        "文件类型": "项目立项类",
        "实际回答": "",
        "标准要点": "",
    },
    {
        "序号": 2,
        "问题": "对比 A 公司与 B 公司采购流程的差异。",
        "问答目录": '["目录ID示例"]',
        "是否开启多轮": "是",
        "问题类型": "对比分析类",
        "标准答案": "A 公司…；B 公司…（完整对比要点）",
        "文件": "采购制度.pdf",
        "文件类型": "合规制度类",
        "实际回答": "",
        "标准要点": "",
    },
]


def score_to_level(score: float) -> str:
    s = int(round(float(score or 0)))
    for name, lo, hi in LEVEL_BANDS:
        if lo <= s <= hi:
            return name
    return "严重不合格"


def _normalize_level_label(level: str, score: float) -> str:
    lv = (level or "").strip()
    if lv in ("优秀", "良好", "合格", "不合格", "严重不合格"):
        return lv
    if lv == "较差":
        return "不合格"
    return score_to_level(score)


def _pct(n: int, total: int) -> float:
    return round((n / total * 100) if total else 0, 2)


def _group_stats(
    items: list[tuple[Any, float, bool]],
) -> list[dict[str, Any]]:
    """items: (group_key, score_100, passed)"""
    buckets: dict[str, list[tuple[float, bool]]] = defaultdict(list)
    for key, score, passed in items:
        k = (str(key) or "").strip() or "未分类"
        buckets[k].append((score, passed))
    rows: list[dict[str, Any]] = []
    for key in sorted(buckets.keys()):
        vals = buckets[key]
        scores = [v[0] for v in vals]
        passed_n = sum(1 for _, p in vals if p)
        cnt = len(vals)
        avg_100 = sum(scores) / cnt if cnt else 0
        excellent_n = sum(1 for s in scores if s >= 90)
        good_n = sum(1 for s in scores if s >= 75)
        rows.append(
            {
                "name": key,
                "count": cnt,
                "avg_score": round(avg_100 / 100, 4),
                "avg_score_100": round(avg_100, 2),
                "excellent_rate": _pct(excellent_n, cnt),
                "good_or_above_rate": _pct(good_n, cnt),
                "pass_rate": _pct(passed_n, cnt),
                "excellent_count": excellent_n,
                "good_or_above_count": good_n,
                "passed_count": passed_n,
            }
        )
    rows.sort(key=lambda x: (-x["count"], x["name"]))
    return rows


async def build_run_statistics_report(run_id: int) -> dict[str, Any]:
    run = await AiQaEvalRun.get_or_none(id=run_id)
    if not run:
        raise ValueError("跑批记录不存在")

    results = await AiQaEvalResult.filter(run_id=run_id).order_by("id")
    case_ids = [r.case_id for r in results]
    cases = await AiQaEvalCase.filter(id__in=case_ids) if case_ids else []
    case_map = {c.id: c for c in cases}

    extra = run.extra if isinstance(run.extra, dict) else {}
    run_mode = extra.get("run_mode") or "auto"
    s = await AiQaEvalSet.get_or_none(id=run.set_id)
    t = await AiQaEvalTarget.get_or_none(id=run.target_id)

    return _build_statistics_payload(
        results,
        case_map,
        run_mode=run_mode,
        set_name=s.name if s else "",
        target_name=t.name if t else "",
        status=run.status,
        test_period={
            "started_at": run.started_at.strftime("%Y-%m-%d %H:%M:%S") if run.started_at else "",
            "finished_at": run.finished_at.strftime("%Y-%m-%d %H:%M:%S") if run.finished_at else "",
        },
        run_id=run.id,
        merged=False,
    )


def build_import_template_rows() -> list[dict[str, Any]]:
    return list(QA_IMPORT_TEMPLATE_SAMPLES)


def _build_statistics_payload(
    results: list[AiQaEvalResult],
    case_map: dict[int, AiQaEvalCase],
    *,
    run_mode: str,
    set_name: str,
    target_name: str,
    status: str,
    test_period: dict[str, str],
    run_id: Optional[int] = None,
    merged: bool = False,
    merge_label: str = "",
    merge_info: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    judged = [r for r in results if r.status == "judged"]
    fetched = [r for r in results if r.status == "fetched"]
    api_failed = [r for r in results if r.status == "api_failed"]
    total = len(results)
    level_counts = {name: 0 for name, _, _ in LEVEL_BANDS}
    scenario_items: list[tuple[Any, float, bool]] = []
    file_type_items: list[tuple[Any, float, bool]] = []
    total_score_100 = 0
    excellent_n = good_n = unqualified_n = 0
    hallucination_n = 0
    manual_pending = manual_approved = manual_rejected = 0
    auto_passed = sum(1 for r in results if r.passed)

    for r in results:
        ms = (r.manual_status or "pending").strip()
        if ms == "approved":
            manual_approved += 1
        elif ms == "rejected":
            manual_rejected += 1
        else:
            manual_pending += 1

    for r in judged:
        score = float(r.score or 0)
        total_score_100 += score
        lv = _normalize_level_label(r.level or "", score)
        if lv in level_counts:
            level_counts[lv] += 1
        else:
            level_counts[score_to_level(score)] += 1
        if score >= 90:
            excellent_n += 1
        if score >= 75:
            good_n += 1
        if score < 50:
            unqualified_n += 1
        if r.hallucination:
            hallucination_n += 1
        case = case_map.get(r.case_id)
        scenario_items.append(
            ((case.scenario_type if case else "") or "未分类", score, r.passed)
        )
        file_type_items.append(((case.file_type if case else ""), score, r.passed))

    judged_cnt = len(judged)
    max_score = judged_cnt * 100
    avg_score_01 = round(total_score_100 / max_score, 4) if max_score else 0
    level_distribution = [
        {
            "level": name,
            "count": level_counts.get(name, 0),
            "rate": _pct(level_counts.get(name, 0), judged_cnt),
            "score_range": f"{lo/100:.2f}~{hi/100:.2f}" if hi < 100 else f">={lo/100:.2f}",
        }
        for name, lo, hi in LEVEL_BANDS
    ]

    failed_samples = []
    for r in judged:
        if r.passed:
            continue
        case = case_map.get(r.case_id)
        failed_samples.append(
            {
                "case_id": r.case_id,
                "seq_no": case.seq_no if case else None,
                "question": (r.question or "")[:200],
                "score": r.score,
                "level": _normalize_level_label(r.level or "", r.score),
                "scenario_type": (case.scenario_type if case else "") or "",
                "file_type": (case.file_type if case else "") or "",
                "reason": (r.reason or "")[:500],
                "api_error": (r.api_error or "")[:300],
            }
        )
    failed_samples.sort(key=lambda x: x["score"])
    failed_samples = failed_samples[:30]

    payload: dict[str, Any] = {
        "run_id": run_id,
        "merged": merged,
        "merge_label": merge_label,
        "set_name": set_name,
        "target_name": target_name,
        "run_mode": run_mode,
        "status": status,
        "test_period": test_period,
        "overview": {
            "total_count": total,
            "judged_count": judged_cnt,
            "fetched_count": len(fetched),
            "api_failed_count": len(api_failed),
            "total_score": round(total_score_100, 2),
            "max_score": max_score,
            "avg_score": avg_score_01,
            "avg_score_100": round(total_score_100 / judged_cnt, 2) if judged_cnt else 0,
            "excellent_rate": _pct(excellent_n, judged_cnt),
            "good_or_above_rate": _pct(good_n, judged_cnt),
            "unqualified_rate": _pct(unqualified_n, judged_cnt),
            "platform_pass_rate": _pct(auto_passed, total),
            "platform_passed_count": auto_passed,
            "hallucination_count": hallucination_n,
            "level_distribution": level_distribution,
        },
        "by_scenario_type": _group_stats(scenario_items),
        "by_file_type": _group_stats(file_type_items),
        "manual_review": {
            "pending": manual_pending,
            "approved": manual_approved,
            "rejected": manual_rejected,
        },
        "failed_samples": failed_samples,
        "report_sections": [
            "评分等级体系",
            "成绩分布概况",
            "问题类型分析",
            "文件类型分析",
            "人工审核汇总",
            "自动校验未过样例",
        ],
    }
    if merge_info:
        payload["merge_info"] = merge_info
    return payload


async def build_merged_statistics_report(
    *,
    set_id: int,
    run_ids: Optional[list[int]] = None,
    batch_group_id: Optional[str] = None,
) -> dict[str, Any]:
    from app.core.qa_eval_service import collect_merged_case_results

    pairs, merge_info = await collect_merged_case_results(
        run_ids=run_ids,
        batch_group_id=batch_group_id,
        set_id=set_id,
    )
    if not pairs:
        raise ValueError("没有可合并的结果")
    results = [r for _, r in pairs]
    case_map = {c.id: c for c, _ in pairs}
    s = await AiQaEvalSet.get_or_none(id=set_id)
    merge_label = batch_group_id or f"runs:{','.join(str(x) for x in (run_ids or []))}"
    return _build_statistics_payload(
        results,
        case_map,
        run_mode="auto",
        set_name=s.name if s else "",
        target_name="（合并）",
        status="completed",
        test_period={"started_at": "", "finished_at": ""},
        run_id=None,
        merged=True,
        merge_label=merge_label[:120],
        merge_info=merge_info,
    )
