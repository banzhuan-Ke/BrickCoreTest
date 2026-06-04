"""问答准确性评测：多迭代 / 多跑批对比报告"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.core.qa_eval_report import _build_statistics_payload, _normalize_level_label
from app.core.qa_eval_service import collect_merged_case_results, effective_seq_no, list_ordered_cases
from app.models.ai import AiQaEvalCase, AiQaEvalResult, AiQaEvalRun, AiQaEvalSet, AiQaEvalTarget


@dataclass
class CompareGroupSpec:
    label: str
    run_ids: Optional[list[int]] = None
    batch_group_id: Optional[str] = None


async def _load_group_pairs(
    spec: CompareGroupSpec,
    *,
    set_id: int,
) -> tuple[list[tuple[AiQaEvalCase, AiQaEvalResult]], str]:
    if spec.batch_group_id:
        pairs, _ = await collect_merged_case_results(
            batch_group_id=spec.batch_group_id,
            set_id=set_id,
        )
        return pairs, f"分批 {spec.batch_group_id[:8]}"

    run_ids = [int(x) for x in (spec.run_ids or []) if x]
    if not run_ids:
        raise ValueError(f"对比组「{spec.label}」需指定 run_ids 或 batch_group_id")
    pairs, _ = await collect_merged_case_results(run_ids=run_ids, set_id=set_id)
    if len(run_ids) == 1:
        run = await AiQaEvalRun.get_or_none(id=run_ids[0])
        if run and run.target_id:
            t = await AiQaEvalTarget.get_or_none(id=run.target_id)
            return pairs, t.name if t else f"跑批 #{run_ids[0]}"
        return pairs, f"跑批 #{run_ids[0]}"
    return pairs, f"合并 {len(run_ids)} 批"


def _seq_result_map(
    pairs: list[tuple[AiQaEvalCase, AiQaEvalResult]],
    *,
    index_map: dict[int, int],
) -> dict[int, tuple[AiQaEvalCase, AiQaEvalResult]]:
    out: dict[int, tuple[AiQaEvalCase, AiQaEvalResult]] = {}
    for case, result in pairs:
        idx = index_map.get(case.id, 0)
        sn = effective_seq_no(case, idx)
        out[sn] = (case, result)
    return out


def _cell_from_result(case: AiQaEvalCase, result: AiQaEvalResult) -> dict[str, Any]:
    score = float(result.score or 0) if result.status == "judged" else None
    meta = result.api_meta if isinstance(result.api_meta, dict) else {}
    return {
        "score": result.score,
        "score_raw": round(score / 100, 4) if score is not None else None,
        "level": _normalize_level_label(result.level or "", score or 0) if score is not None else "",
        "passed": bool(result.passed),
        "actual_answer": (result.actual_answer or "")[:800],
        "status": result.status,
        "hallucination": bool(result.hallucination),
        "scenario_type": (case.scenario_type or "") if case else "",
        "thinking": (meta.get("thinking") or "")[:500],
    }


def _overview_metrics_table(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    defs = [
        ("judged_count", "评测题数"),
        ("avg_score_100", "均分(0~100)"),
        ("excellent_rate", "优秀率%"),
        ("good_or_above_rate", "良好率%"),
        ("unqualified_rate", "不合格率%"),
        ("platform_pass_rate", "自动校验率%"),
        ("hallucination_count", "幻觉条数"),
        ("api_failed_count", "API 失败数"),
    ]
    rows: list[dict[str, Any]] = []
    for key, title in defs:
        rows.append(
            {
                "metric": title,
                "metric_key": key,
                "values": [
                    {"label": g["label"], "value": g["overview"].get(key)}
                    for g in groups
                ],
            }
        )
    return rows


def _scenario_compare_table(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names: set[str] = set()
    for g in groups:
        for row in g.get("by_scenario_type") or []:
            names.add(row.get("name") or "未分类")
    out: list[dict[str, Any]] = []
    for name in sorted(names):
        cells = []
        for g in groups:
            hit = next((x for x in (g.get("by_scenario_type") or []) if x.get("name") == name), None)
            cells.append(
                {
                    "label": g["label"],
                    "count": hit.get("count") if hit else 0,
                    "avg_score_100": hit.get("avg_score_100") if hit else None,
                    "pass_rate": hit.get("pass_rate") if hit else None,
                }
            )
        out.append({"name": name, "cells": cells})
    out.sort(key=lambda x: (-max((c.get("count") or 0) for c in x["cells"]), x["name"]))
    return out


def _level_compare_table(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from app.core.qa_eval_report import LEVEL_BANDS

    rows: list[dict[str, Any]] = []
    for level_name, _, _ in LEVEL_BANDS:
        cells = []
        for g in groups:
            hit = next(
                (x for x in (g["overview"].get("level_distribution") or []) if x.get("level") == level_name),
                None,
            )
            cells.append(
                {
                    "label": g["label"],
                    "count": hit.get("count") if hit else 0,
                    "rate": hit.get("rate") if hit else 0,
                }
            )
        rows.append({"level": level_name, "cells": cells})
    return rows


def _question_compare_table(
    group_labels: list[str],
    seq_maps: list[dict[int, tuple[AiQaEvalCase, AiQaEvalResult]]],
) -> list[dict[str, Any]]:
    all_seqs: set[int] = set()
    for sm in seq_maps:
        all_seqs.update(sm.keys())
    rows: list[dict[str, Any]] = []
    for sn in sorted(all_seqs):
        cells: list[dict[str, Any]] = []
        scores: list[tuple[str, float]] = []
        question = ""
        for label, sm in zip(group_labels, seq_maps):
            if sn not in sm:
                cells.append({"label": label, "missing": True})
                continue
            case, result = sm[sn]
            if not question:
                question = case.question
            cell = _cell_from_result(case, result)
            cell["label"] = label
            cell["missing"] = False
            cells.append(cell)
            if result.status == "judged" and result.score is not None:
                scores.append((label, float(result.score)))
        best_label = ""
        score_spread = 0.0
        if len(scores) >= 2:
            scores.sort(key=lambda x: x[1], reverse=True)
            best_label = scores[0][0]
            score_spread = round(scores[0][1] - scores[-1][1], 2)
        elif len(scores) == 1:
            best_label = scores[0][0]
        rows.append(
            {
                "seq_no": sn,
                "question": (question or "")[:300],
                "cells": cells,
                "best_label": best_label,
                "score_spread": score_spread,
            }
        )
    return rows


async def build_compare_report(
    *,
    set_id: int,
    groups: list[CompareGroupSpec],
) -> dict[str, Any]:
    if len(groups) < 2:
        raise ValueError("至少需要 2 个对比组")
    if len(groups) > 10:
        raise ValueError("对比组最多 10 个")

    s = await AiQaEvalSet.get_or_none(id=set_id)
    all_cases = await list_ordered_cases(set_id)
    index_map = {c.id: i for i, c in enumerate(all_cases)}

    group_payloads: list[dict[str, Any]] = []
    seq_maps: list[dict[int, tuple[AiQaEvalCase, AiQaEvalResult]]] = []
    labels: list[str] = []

    for spec in groups:
        label = (spec.label or "").strip()
        if not label:
            raise ValueError("对比组名称不能为空")
        pairs, target_hint = await _load_group_pairs(spec, set_id=set_id)
        if not pairs:
            raise ValueError(f"对比组「{label}」没有可用结果")
        results = [r for _, r in pairs]
        case_map = {c.id: c for c, _ in pairs}
        stats = _build_statistics_payload(
            results,
            case_map,
            run_mode="auto",
            set_name=s.name if s else "",
            target_name=target_hint,
            status="completed",
            test_period={"started_at": "", "finished_at": ""},
            merged=True,
            merge_label=label,
        )
        stats["label"] = label
        stats["run_ids"] = spec.run_ids or []
        stats["batch_group_id"] = spec.batch_group_id
        group_payloads.append(stats)
        labels.append(label)
        seq_maps.append(_seq_result_map(pairs, index_map=index_map))

    return {
        "set_id": set_id,
        "set_name": s.name if s else "",
        "group_count": len(group_payloads),
        "groups": group_payloads,
        "overview_compare": _overview_metrics_table(group_payloads),
        "level_compare": _level_compare_table(group_payloads),
        "scenario_compare": _scenario_compare_table(group_payloads),
        "question_compare": _question_compare_table(labels, seq_maps),
    }
