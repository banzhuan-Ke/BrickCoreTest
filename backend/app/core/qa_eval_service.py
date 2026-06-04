"""问答准确性评测：调用被测 API + LLM 评判"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from app.core.qa_eval_target_client import invoke_target_api, new_session_id
from app.core.ai_prompts import PromptManager
from app.core.ai_scene_config import get_scene_llm_overrides, resolve_config_for_scene
from app.core.ai_usage_log import log_ai_usage
from app.models.ai import (
    AiQaEvalCase,
    AiQaEvalResult,
    AiQaEvalRun,
    AiQaEvalSet,
    AiQaEvalTarget,
)

logger = logging.getLogger(__name__)

MAX_CASES_PER_RUN = 500
DEFAULT_BATCH_CHUNK_SIZE = 100
API_CONCURRENCY = 1
JUDGE_CONCURRENCY = 2

CASE_SCOPE_ALL = "all"
CASE_SCOPE_RANGE = "range"
CASE_SCOPE_RETRY_FAILED = "retry_failed"
CASE_SCOPE_LABELS = {
    CASE_SCOPE_ALL: "全部用例",
    CASE_SCOPE_RANGE: "指定序号范围",
    CASE_SCOPE_RETRY_FAILED: "仅重跑 API 失败",
}

RUN_MODE_AUTO = "auto"
RUN_MODE_JUDGE_ONLY = "judge_only"
RUN_MODE_FETCH_ONLY = "fetch_only"
RUN_MODE_LABELS = {
    RUN_MODE_AUTO: "自动调 API + LLM 评判",
    RUN_MODE_JUDGE_ONLY: "仅 LLM 评判（使用预置实际回答）",
    RUN_MODE_FETCH_ONLY: "仅批量拉取回答并导出",
}

RUN_STATUS_LABELS = {
    "pending": "等待中",
    "running": "执行中",
    "completed": "已完成",
    "failed": "失败",
}

QA_FETCH_EXPORT_COLUMNS = [
    "序号",
    "问题",
    "标准答案",
    "实际回答",
    "意图识别",
    "参考文件",
    "得分",
    "等级",
    "自动校验",
    "评判理由",
    "问答目录",
    "是否多轮",
    "问题类型",
    "文件",
    "文件类型",
    "处理状态",
    "耗时ms",
    "错误信息",
]


def _extract_json_object(text: str) -> dict[str, Any]:
    if not text:
        return {}
    text = text.strip()
    code_block_pattern = r"```(?:json)?\s*([\s\S]*?)```"
    for match in re.findall(code_block_pattern, text):
        try:
            data = json.loads(match.strip())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


def _build_ground_truth(case: AiQaEvalCase) -> str:
    """与 RAG 评测一致：ground_truth 以标准答案为主，要点仅作可选补充"""
    ans = (case.expected_answer or "").strip()
    if ans:
        points = case.expected_points if isinstance(case.expected_points, list) else []
        lines = [str(p).strip() for p in points if str(p).strip()]
        if lines:
            return ans + "\n\n【补充要点】\n" + "\n".join(f"- {p}" for p in lines)
        return ans
    points = case.expected_points if isinstance(case.expected_points, list) else []
    lines = [str(p).strip() for p in points if str(p).strip()]
    return "\n".join(lines) if lines else "（无参考答案）"


def _detect_hallucination(reason: str, parsed: dict[str, Any]) -> bool:
    if parsed.get("hallucination") is True:
        return True
    text = (reason or "") + str(parsed.get("reason") or "")
    markers = ("虚构", "无依据信息", "严重误导", "错误添加无依据", "捏造", "胡编")
    return any(m in text for m in markers)


def _normalize_judge_result(parsed: dict[str, Any]) -> dict[str, Any]:
    """RAG v2 输出 score 为 0~1，平台展示与通过线为 0~100（≥80 通过）"""
    reason = (parsed.get("reason") or "").strip()
    raw_score = parsed.get("score")
    if raw_score is None and reason:
        m = re.search(r"最终总分=[^\d]*([\d.]+)", reason)
        if m:
            raw_score = m.group(1)
    try:
        score_01 = float(raw_score) if raw_score is not None else 0.0
    except (TypeError, ValueError):
        score_01 = 0.0
    if score_01 > 1.0:
        score_100 = int(round(score_01))
        score_01 = score_100 / 100.0
    else:
        score_100 = int(round(score_01 * 100))
    score_100 = max(0, min(100, score_100))

    level = (parsed.get("level") or "").strip()
    if not level:
        if score_01 >= 0.9:
            level = "优秀"
        elif score_01 >= 0.75:
            level = "良好"
        elif score_01 >= 0.5:
            level = "合格"
        elif score_01 >= 0.3:
            level = "较差"
        else:
            level = "不合格"

    hallucination = _detect_hallucination(reason, parsed)
    # 自动校验：仅标记幻觉等风险，不以分数 ≥80 作为通过条件
    passed = not hallucination

    dim = parsed.get("dimension_scores") if isinstance(parsed.get("dimension_scores"), dict) else {}
    return {
        "score": score_100,
        "score_raw": round(score_01, 4),
        "passed": passed,
        "hallucination": hallucination,
        "level": level,
        "dimension_scores": dim,
        "missed_points": parsed.get("missed_points") if isinstance(parsed.get("missed_points"), list) else [],
        "extra_issues": parsed.get("extra_issues") if isinstance(parsed.get("extra_issues"), list) else [],
        "reason": reason,
    }


def _render_body_template(template: str, question: str) -> str:
    """兼容旧引用；新逻辑见 qa_eval_target_client"""
    body = template or "{}"
    return (
        body.replace("{{question}}", question)
        .replace("{{ question }}", question)
        .replace("{question}", question)
    )


async def call_target_api(
    target: AiQaEvalTarget,
    question: str,
    *,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """调用被测问答 API，返回 actual_answer / error / latency_ms"""
    cfg = target.config if isinstance(target.config, dict) else {}
    out = await invoke_target_api(cfg, question, extra=extra)
    return {
        "actual_answer": out.get("actual_answer"),
        "api_error": out.get("api_error"),
        "api_latency_ms": out.get("api_latency_ms") or 0,
        "parsed_fields": out.get("parsed_fields") if isinstance(out.get("parsed_fields"), dict) else {},
    }


async def test_target_api(
    cfg: dict[str, Any],
    question: str,
    *,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """调试被测 API（含原始响应预览）"""
    out = await invoke_target_api(cfg, question, extra=extra)
    return {
        "success": bool(out.get("success")),
        "actual_answer": out.get("actual_answer"),
        "api_error": out.get("api_error"),
        "api_latency_ms": out.get("api_latency_ms") or 0,
        "raw_preview": out.get("raw_preview") or "",
        "parsed_fields": out.get("parsed_fields") if isinstance(out.get("parsed_fields"), dict) else {},
        "request_body": out.get("request_body"),
    }


async def judge_answer(
    case: AiQaEvalCase,
    actual_answer: str,
    *,
    judge_config_id: Optional[int],
    user_info: dict,
    project_id: int,
) -> dict[str, Any]:
    from app.routers.ai.generate import _call_llm

    config = await resolve_config_for_scene("qa_judge", judge_config_id)
    scene_overrides = await get_scene_llm_overrides("qa_judge")
    ctx = {
        "question": case.question,
        "ground_truth": _build_ground_truth(case),
        "answer": actual_answer or "（无回答）",
    }
    system_prompt, user_prompt = await PromptManager.render("qa_judge", ctx)
    t0 = time.perf_counter()
    min_timeout = int(scene_overrides.get("min_timeout") or 180)
    llm_resp = await _call_llm(
        system_prompt,
        user_prompt,
        config,
        min_timeout=min_timeout,
        max_retries=1,
        param_overrides=scene_overrides,
    )
    raw = llm_resp.get("content") or ""
    tokens = int(llm_resp.get("tokens") or 0)
    duration_ms = int((time.perf_counter() - t0) * 1000)
    parsed = _normalize_judge_result(_extract_json_object(raw))
    await log_ai_usage(
        config,
        "qa_judge",
        user_info=user_info,
        project_id=project_id,
        tokens_used=tokens,
        duration_ms=duration_ms,
        status="success",
        input_summary=case.question[:200],
        output_summary=f"score={parsed['score']}",
    )
    parsed["judge_raw"] = raw[:12000]
    parsed["judge_tokens"] = tokens
    return parsed


def effective_seq_no(case: AiQaEvalCase, index_in_list: int = 0) -> int:
    if case.seq_no is not None:
        return int(case.seq_no)
    return index_in_list + 1


def analyze_seq_numbers(seq_nos: list[Any]) -> dict[str, Any]:
    """根据 Excel 序号分析缺口与重复（题数为实际条数，可与最大序号不一致）。"""
    raw = [int(x) for x in seq_nos if x is not None]
    if not raw:
        return {
            "max_seq_no": None,
            "min_seq_no": None,
            "missing_seq_nos": [],
            "duplicate_seq_count": 0,
        }
    seq_set = set(raw)
    ordered = sorted(seq_set)
    missing = [i for i in range(ordered[0], ordered[-1] + 1) if i not in seq_set]
    return {
        "max_seq_no": ordered[-1],
        "min_seq_no": ordered[0],
        "missing_seq_nos": missing,
        "duplicate_seq_count": len(raw) - len(seq_set),
    }


async def list_ordered_cases(set_id: int) -> list[AiQaEvalCase]:
    return await AiQaEvalCase.filter(set_id=set_id, is_del=False).order_by("seq_no", "sort_order", "id")


async def resolve_cases_for_run(run: AiQaEvalRun) -> list[AiQaEvalCase]:
    extra = run.extra if isinstance(run.extra, dict) else {}
    scope = extra.get("case_scope") or CASE_SCOPE_ALL
    all_cases = await list_ordered_cases(run.set_id)

    if scope == CASE_SCOPE_RANGE:
        start = int(extra.get("range_start") or 1)
        end = int(extra.get("range_end") or 999999)
        out: list[AiQaEvalCase] = []
        for i, c in enumerate(all_cases):
            sn = effective_seq_no(c, i)
            if start <= sn <= end:
                out.append(c)
        return out

    if scope == CASE_SCOPE_RETRY_FAILED:
        source_id = extra.get("retry_source_run_id")
        if not source_id:
            return []
        from tortoise.expressions import Q

        failed_ids = set(
            await AiQaEvalResult.filter(
                Q(run_id=int(source_id))
                & (Q(status="api_failed") | Q(status="judged", passed=False))
            ).values_list("case_id", flat=True)
        )
        return [c for c in all_cases if c.id in failed_ids]

    return all_cases


def _resolve_chat_path(
    case: AiQaEvalCase,
    target: Optional[AiQaEvalTarget],
) -> list[str]:
    chat_path = case.chat_path if isinstance(case.chat_path, list) else []
    chat_path = [str(x).strip() for x in chat_path if str(x).strip()]
    if chat_path or not target:
        return chat_path
    cfg = target.config if isinstance(target.config, dict) else {}
    fallback = cfg.get("default_chat_path")
    if isinstance(fallback, list):
        return [str(x).strip() for x in fallback if str(x).strip()]
    if isinstance(fallback, str) and fallback.strip():
        text = fallback.strip()
        if text.startswith("["):
            try:
                data = json.loads(text)
                if isinstance(data, list):
                    return [str(x).strip() for x in data if str(x).strip()]
            except json.JSONDecodeError:
                pass
        return [p.strip() for p in re.split(r"[;,，/；]", text) if p.strip()]
    return []


def _case_api_extra(
    case: AiQaEvalCase,
    session_state: dict[str, Any],
    *,
    target: Optional[AiQaEvalTarget] = None,
) -> dict[str, Any]:
    multi = bool(case.multi_turn)
    if multi:
        if not session_state.get("prev_multi"):
            session_state["session_id"] = new_session_id()
    else:
        session_state["session_id"] = ""
    session_state["prev_multi"] = multi
    return {
        "chatPath": _resolve_chat_path(case, target),
        "sessionId": session_state.get("session_id") or "",
        "historyFlag": multi,
    }


def _export_row_from_case_result(
    case: AiQaEvalCase,
    result: Optional[AiQaEvalResult],
    *,
    index_in_list: int = 0,
) -> dict[str, Any]:
    meta = {}
    if result and isinstance(result.api_meta, dict):
        meta = result.api_meta
    if result:
        status = "成功" if result.status in ("fetched", "judged") and not result.api_error else "失败"
        if result.status == "api_failed":
            status = "失败"
        actual = (result.actual_answer or case.preset_answer or "")[:32000]
        latency = result.api_latency_ms or 0
        err = (result.api_error or "")[:2000]
    else:
        status = "预置" if (case.preset_answer or "").strip() else ""
        actual = (case.preset_answer or "")[:32000]
        latency = ""
        err = ""
    scenario = (case.scenario_type or "").strip()
    chat_path = case.chat_path if isinstance(case.chat_path, list) else []
    chat_path_str = " / ".join(str(x) for x in chat_path if str(x).strip())
    level_label = ""
    score_val = ""
    passed_label = ""
    reason_text = ""
    if result:
        from app.core.qa_eval_report import score_to_level

        score_val = result.score if result.score is not None else ""
        level_label = (result.level or "").strip()
        if level_label == "较差":
            level_label = "不合格"
        elif not level_label and score_val != "":
            level_label = score_to_level(float(score_val or 0))
        passed_label = "是" if result.passed else "否"
        reason_text = (result.reason or "")[:8000]
    return {
        "序号": effective_seq_no(case, index_in_list),
        "问题": case.question,
        "标准答案": (case.expected_answer or "")[:32000],
        "实际回答": actual,
        "意图识别": (meta.get("thinking") or "")[:8000],
        "参考文件": (meta.get("references_all") or "")[:4000],
        "得分": score_val,
        "等级": level_label,
        "自动校验": passed_label,
        "评判理由": reason_text,
        "问答目录": chat_path_str[:500],
        "是否多轮": "是" if case.multi_turn else "否",
        "问题类型": scenario,
        "文件": (case.source_file or "")[:500],
        "文件类型": (case.file_type or "")[:200],
        "处理状态": status,
        "耗时ms": latency,
        "错误信息": err,
    }


async def build_qa_fetch_export_rows(run_id: int) -> list[dict[str, Any]]:
    results = await AiQaEvalResult.filter(run_id=run_id).order_by("id")
    if not results:
        return []
    case_ids = [r.case_id for r in results]
    cases = await AiQaEvalCase.filter(id__in=case_ids)
    case_map = {c.id: c for c in cases}
    return [_export_row_from_case_result(case_map[r.case_id], r) for r in results if r.case_id in case_map]


async def build_qa_cases_export_rows(set_id: int) -> list[dict[str, Any]]:
    cases = await list_ordered_cases(set_id)
    return [_export_row_from_case_result(c, None, index_in_list=i) for i, c in enumerate(cases)]


async def collect_merged_case_results(
    *,
    run_ids: Optional[list[int]] = None,
    batch_group_id: Optional[str] = None,
    set_id: Optional[int] = None,
) -> tuple[list[tuple[AiQaEvalCase, AiQaEvalResult]], dict[str, Any]]:
    """按题目序号合并多批跑批结果（同序号后者覆盖前者，非条数累加）。"""
    ids = list(run_ids or [])
    if batch_group_id:
        if not set_id:
            raise ValueError("分批合并需指定评测集")
        all_runs = await AiQaEvalRun.filter(set_id=set_id).order_by("id")
        matched = [
            r
            for r in all_runs
            if (r.extra if isinstance(r.extra, dict) else {}).get("batch_group_id") == batch_group_id
        ]
        ids = [r.id for r in matched]
    empty_meta: dict[str, Any] = {
        "mode": "by_seq_no",
        "mode_desc": "按题目序号合并；同一序号有多批结果时，跑批 ID 较大的覆盖较小的（非简单相加条数）",
        "run_ids": [],
        "runs_detail": [],
        "raw_result_count": 0,
        "merged_unique_count": 0,
        "overwritten_count": 0,
        "set_case_count": 0,
    }
    if not ids:
        return [], empty_meta

    sorted_ids = sorted(ids)
    index_map_cache: dict[int, dict[int, int]] = {}
    set_case_count_cache: dict[int, int] = {}
    pairs_by_seq: dict[int, tuple[AiQaEvalCase, AiQaEvalResult]] = {}
    runs_detail: list[dict[str, Any]] = []
    raw_result_count = 0
    overwritten_count = 0

    for run_id in sorted_ids:
        run = await AiQaEvalRun.get_or_none(id=run_id)
        if not run:
            continue
        results = await AiQaEvalResult.filter(run_id=run_id).order_by("id")
        if not results:
            continue
        raw_result_count += len(results)
        case_ids = [r.case_id for r in results]
        cases = await AiQaEvalCase.filter(id__in=case_ids)
        case_map = {c.id: c for c in cases}
        if run.set_id not in index_map_cache:
            all_cases = await list_ordered_cases(run.set_id)
            index_map_cache[run.set_id] = {c.id: i for i, c in enumerate(all_cases)}
            set_case_count_cache[run.set_id] = len(all_cases)
        index_map = index_map_cache[run.set_id]
        seq_nos_in_run: list[int] = []
        for r in results:
            case = case_map.get(r.case_id)
            if not case:
                continue
            idx = index_map.get(case.id, 0)
            sn = effective_seq_no(case, idx)
            seq_nos_in_run.append(sn)
            if sn in pairs_by_seq:
                overwritten_count += 1
            pairs_by_seq[sn] = (case, r)
        runs_detail.append(
            {
                "run_id": run_id,
                "result_count": len(results),
                "seq_nos": sorted(set(seq_nos_in_run)),
            }
        )

    set_case_count = 0
    if set_id and set_id in set_case_count_cache:
        set_case_count = set_case_count_cache[set_id]
    elif set_case_count_cache:
        set_case_count = next(iter(set_case_count_cache.values()))

    pairs = [pairs_by_seq[k] for k in sorted(pairs_by_seq.keys())]
    merge_info = {
        "mode": "by_seq_no",
        "mode_desc": "按题目序号合并；同一序号有多批结果时，跑批 ID 较大的覆盖较小的（非简单相加条数）",
        "run_ids": sorted_ids,
        "runs_detail": runs_detail,
        "raw_result_count": raw_result_count,
        "merged_unique_count": len(pairs),
        "overwritten_count": overwritten_count,
        "set_case_count": set_case_count,
    }
    return pairs, merge_info


async def build_merged_export_rows(
    *,
    run_ids: Optional[list[int]] = None,
    batch_group_id: Optional[str] = None,
    set_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    """按序号合并多批跑批结果（同序号后者覆盖前者）"""
    pairs, _ = await collect_merged_case_results(
        run_ids=run_ids,
        batch_group_id=batch_group_id,
        set_id=set_id,
    )
    if not pairs:
        return []
    set_id_resolved = set_id or pairs[0][0].set_id
    all_cases = await list_ordered_cases(set_id_resolved)
    index_map = {c.id: i for i, c in enumerate(all_cases)}
    return [
        _export_row_from_case_result(case, result, index_in_list=index_map.get(case.id, 0))
        for case, result in pairs
    ]


async def _process_one_case(
    case: AiQaEvalCase,
    run: AiQaEvalRun,
    *,
    run_mode: str,
    target: Optional[AiQaEvalTarget],
    judge_config_id: Optional[int],
    user_info: dict,
    api_sem: asyncio.Semaphore,
    judge_sem: asyncio.Semaphore,
    session_state: Optional[dict[str, Any]] = None,
) -> AiQaEvalResult:
    if run_mode == RUN_MODE_JUDGE_ONLY:
        actual = (case.preset_answer or "").strip()
        api_error = None if actual else "未导入/填写实际回答（预置回答）"
        api_out = {
            "actual_answer": actual or None,
            "api_error": api_error,
            "api_latency_ms": 0,
        }
    else:
        if not target:
            return await AiQaEvalResult.create(
                run_id=run.id,
                case_id=case.id,
                question=case.question,
                api_error="被测 API 未配置",
                status="api_failed",
                score=0,
                passed=False,
            )
        st = session_state if session_state is not None else {}
        extra_api = _case_api_extra(case, st, target=target)
        async with api_sem:
            api_out = await call_target_api(target, case.question, extra=extra_api)

    result = await AiQaEvalResult.create(
        run_id=run.id,
        case_id=case.id,
        question=case.question,
        actual_answer=api_out.get("actual_answer"),
        api_error=api_out.get("api_error"),
        api_latency_ms=api_out.get("api_latency_ms") or 0,
        status="api_failed" if api_out.get("api_error") else "pending",
    )
    parsed_fields = api_out.get("parsed_fields") if isinstance(api_out.get("parsed_fields"), dict) else {}
    if parsed_fields:
        result.api_meta = {
            "thinking": parsed_fields.get("thinking"),
            "references_all": parsed_fields.get("references_all"),
            "references_high": parsed_fields.get("references_high"),
        }

    if api_out.get("api_error"):
        result.score = 0
        result.passed = False
        result.status = "api_failed"
        await result.save()
        return result

    actual = (api_out.get("actual_answer") or "").strip()
    if run_mode == RUN_MODE_FETCH_ONLY:
        case.preset_answer = actual[:16000]
        await case.save()
        result.actual_answer = actual[:16000]
        result.status = "fetched"
        result.passed = True
        result.score = 0
        await result.save()
        return result

    async with judge_sem:
        try:
            judged = await judge_answer(
                case,
                actual,
                judge_config_id=judge_config_id,
                user_info=user_info,
                project_id=run.project_id,
            )
        except Exception as e:
            logger.exception("qa judge failed case_id=%s", case.id)
            result.status = "judge_failed"
            result.api_error = (result.api_error or "") + f" | judge: {str(e)[:500]}"
            result.score = 0
            result.passed = False
            await result.save()
            return result

    result.score = judged["score"]
    result.passed = judged["passed"]
    result.hallucination = judged["hallucination"]
    result.level = judged["level"]
    result.dimension_scores = judged["dimension_scores"]
    result.missed_points = judged["missed_points"]
    result.extra_issues = judged["extra_issues"]
    result.reason = judged["reason"]
    result.judge_raw = judged.get("judge_raw")
    result.judge_tokens = judged.get("judge_tokens") or 0
    result.status = "judged"
    await result.save()
    return result


def _user_info_from_run(run: AiQaEvalRun) -> dict:
    extra = run.extra if isinstance(run.extra, dict) else {}
    return {
        "id": extra.get("user_id"),
        "username": extra.get("username") or run.create_by or "",
        "project_id": run.project_id,
    }


async def _update_run_progress(
    run_id: int,
    *,
    done: int,
    total: int,
    current_question: str = "",
    passed: int = 0,
    failed: int = 0,
) -> None:
    run = await AiQaEvalRun.get(id=run_id)
    extra = dict(run.extra) if isinstance(run.extra, dict) else {}
    extra["done_count"] = done
    extra["progress_percent"] = int(done / total * 100) if total else 0
    extra["current_question"] = (current_question or "")[:300]
    run.extra = extra
    run.passed_count = passed
    run.failed_count = failed
    if total:
        run.total_count = total
    await run.save()


async def execute_run(
    run: AiQaEvalRun,
    *,
    judge_config_id: Optional[int],
    user_info: dict,
) -> AiQaEvalRun:
    """执行评测跑批（后台任务调用，批量≤200，边跑边写进度）"""
    run_id = run.id
    extra0 = run.extra if isinstance(run.extra, dict) else {}
    run_mode = extra0.get("run_mode") or RUN_MODE_AUTO

    target: Optional[AiQaEvalTarget] = None
    if run_mode in (RUN_MODE_AUTO, RUN_MODE_FETCH_ONLY):
        if not run.target_id:
            run.status = "failed"
            run.error = "该模式需选择被测 API"
            run.finished_at = datetime.now()
            await run.save()
            return run
        target = await AiQaEvalTarget.get_or_none(id=run.target_id, is_del=False)
        if not target:
            run.status = "failed"
            run.error = "被测 API 配置不存在"
            run.finished_at = datetime.now()
            await run.save()
            return run
    elif run_mode == RUN_MODE_JUDGE_ONLY:
        cases_pre = await resolve_cases_for_run(run)
        missing = [c for c in cases_pre if not (c.preset_answer or "").strip()]
        if missing:
            run.status = "failed"
            run.error = f"{len(missing)} 条用例缺少实际回答，请 Excel 导入「实际回答」列或在用例中填写"
            run.finished_at = datetime.now()
            await run.save()
            return run

    cases = await resolve_cases_for_run(run)
    if len(cases) > MAX_CASES_PER_RUN:
        run.status = "failed"
        run.error = f"用例数超过上限 {MAX_CASES_PER_RUN}"
        run.finished_at = datetime.now()
        await run.save()
        return run

    run.status = "running"
    run.started_at = datetime.now()
    run.total_count = len(cases)
    await run.save()
    await _update_run_progress(run_id, done=0, total=len(cases), current_question="准备中…")

    api_sem = asyncio.Semaphore(API_CONCURRENCY)
    judge_sem = asyncio.Semaphore(JUDGE_CONCURRENCY)
    results: list[AiQaEvalResult] = []
    session_state: dict[str, Any] = {"session_id": "", "prev_multi": False}
    interval_ms = int(extra0.get("request_interval_ms") or 0)
    if target and isinstance(target.config, dict):
        interval_ms = int(target.config.get("request_interval_ms") or interval_ms)

    def _count_progress(rs: list[AiQaEvalResult]) -> tuple[int, int]:
        if run_mode == RUN_MODE_FETCH_ONLY:
            ok = sum(1 for x in rs if x.status == "fetched")
            return ok, len(rs) - ok
        return sum(1 for x in rs if x.passed), sum(1 for x in rs if not x.passed)

    for idx, case in enumerate(cases):
        r = await _process_one_case(
            case,
            run,
            run_mode=run_mode,
            target=target,
            judge_config_id=judge_config_id,
            user_info=user_info,
            api_sem=api_sem,
            judge_sem=judge_sem,
            session_state=session_state,
        )
        results.append(r)
        done = len(results)
        passed_n, failed_n = _count_progress(results)
        await _update_run_progress(
            run_id,
            done=done,
            total=len(cases),
            current_question=case.question,
            passed=passed_n,
            failed=failed_n,
        )
        if (
            interval_ms > 0
            and idx < len(cases) - 1
            and run_mode in (RUN_MODE_AUTO, RUN_MODE_FETCH_ONLY)
        ):
            await asyncio.sleep(interval_ms / 1000.0)

    run = await AiQaEvalRun.get(id=run_id)
    if run_mode == RUN_MODE_FETCH_ONLY:
        passed = sum(1 for r in results if r.status == "fetched")
        run.passed_count = passed
        run.failed_count = len(results) - passed
        run.avg_score = 0
        run.pass_rate = round((passed / len(results) * 100) if results else 0, 2)
    else:
        passed = sum(1 for r in results if r.passed)
        judged = [r for r in results if r.status == "judged"]
        avg = sum(r.score for r in judged) / len(judged) if judged else 0
        run.passed_count = passed
        run.failed_count = len(results) - passed
        run.avg_score = round(avg, 2)
        run.pass_rate = round((passed / len(results) * 100) if results else 0, 2)
    run.status = "completed"
    run.finished_at = datetime.now()
    extra = dict(run.extra) if isinstance(run.extra, dict) else {}
    extra["done_count"] = len(results)
    extra["progress_percent"] = 100
    extra["current_question"] = ""
    if results:
        extra["export_ready"] = True
    run.extra = extra
    await run.save()
    return run


async def _recalculate_run_stats(run_id: int) -> None:
    run = await AiQaEvalRun.get_or_none(id=run_id)
    if not run:
        return
    results = await AiQaEvalResult.filter(run_id=run_id).order_by("id")
    extra = run.extra if isinstance(run.extra, dict) else {}
    run_mode = extra.get("run_mode") or RUN_MODE_AUTO
    if run_mode == RUN_MODE_FETCH_ONLY:
        passed = sum(1 for r in results if r.status == "fetched")
        run.passed_count = passed
        run.failed_count = len(results) - passed
        run.avg_score = 0
        run.pass_rate = round((passed / len(results) * 100) if results else 0, 2)
    else:
        passed = sum(1 for r in results if r.passed)
        judged = [r for r in results if r.status == "judged"]
        avg = sum(r.score for r in judged) / len(judged) if judged else 0
        run.passed_count = passed
        run.failed_count = len(results) - passed
        run.avg_score = round(avg, 2)
        run.pass_rate = round((passed / len(results) * 100) if results else 0, 2)
    run.total_count = len(results)
    await run.save()


async def regenerate_result(
    run_id: int,
    result_id: int,
    *,
    user_info: dict,
) -> AiQaEvalResult:
    """重新调用被测 API（+ 评判）并更新单条结果"""
    run = await AiQaEvalRun.get_or_none(id=run_id)
    if not run:
        raise ValueError("跑批记录不存在")
    result = await AiQaEvalResult.get_or_none(id=result_id, run_id=run_id)
    if not result:
        raise ValueError("结果不存在")
    case = await AiQaEvalCase.get_or_none(id=result.case_id, is_del=False)
    if not case:
        raise ValueError("用例不存在")

    extra = run.extra if isinstance(run.extra, dict) else {}
    run_mode = extra.get("run_mode") or RUN_MODE_AUTO
    if run_mode == RUN_MODE_JUDGE_ONLY:
        raise ValueError("仅评判模式请重新跑批或使用编辑预置回答")

    target: Optional[AiQaEvalTarget] = None
    if run_mode in (RUN_MODE_AUTO, RUN_MODE_FETCH_ONLY):
        if not run.target_id:
            raise ValueError("被测 API 未配置")
        target = await AiQaEvalTarget.get_or_none(id=run.target_id, is_del=False)
        if not target:
            raise ValueError("被测 API 配置不存在")

    judge_config_id = run.judge_config_id or extra.get("judge_config_id")
    extra_api = _case_api_extra(case, {}, target=target)
    api_out = await call_target_api(target, case.question, extra=extra_api)

    result.question = case.question
    result.actual_answer = api_out.get("actual_answer")
    result.api_error = api_out.get("api_error")
    result.api_latency_ms = api_out.get("api_latency_ms") or 0
    result.reason = None
    result.missed_points = []
    result.extra_issues = []
    result.dimension_scores = {}
    result.judge_raw = None
    result.judge_tokens = 0
    result.hallucination = False
    result.manual_status = "pending"
    result.manual_comment = None
    result.manual_reviewed_by = None
    result.manual_reviewed_at = None

    parsed_fields = api_out.get("parsed_fields") if isinstance(api_out.get("parsed_fields"), dict) else {}
    if parsed_fields:
        result.api_meta = {
            "thinking": parsed_fields.get("thinking"),
            "references_all": parsed_fields.get("references_all"),
            "references_high": parsed_fields.get("references_high"),
        }
    else:
        result.api_meta = {}

    if api_out.get("api_error"):
        result.score = 0
        result.passed = False
        result.level = "严重不合格"
        result.status = "api_failed"
        await result.save()
        await _recalculate_run_stats(run_id)
        return result

    actual = (api_out.get("actual_answer") or "").strip()
    if run_mode == RUN_MODE_FETCH_ONLY:
        case.preset_answer = actual[:16000]
        await case.save()
        result.actual_answer = actual[:16000]
        result.status = "fetched"
        result.passed = True
        result.score = 0
        result.level = ""
        await result.save()
        await _recalculate_run_stats(run_id)
        return result

    try:
        judged = await judge_answer(
            case,
            actual,
            judge_config_id=judge_config_id,
            user_info=user_info,
            project_id=run.project_id,
        )
    except Exception as e:
        logger.exception("qa regenerate judge failed result_id=%s", result_id)
        result.status = "judge_failed"
        result.api_error = (result.api_error or "") + f" | judge: {str(e)[:500]}"
        result.score = 0
        result.passed = False
        result.level = "严重不合格"
        await result.save()
        await _recalculate_run_stats(run_id)
        return result

    result.score = judged["score"]
    result.passed = judged["passed"]
    result.hallucination = judged["hallucination"]
    result.level = judged["level"]
    result.dimension_scores = judged["dimension_scores"]
    result.missed_points = judged["missed_points"]
    result.extra_issues = judged["extra_issues"]
    result.reason = judged["reason"]
    result.judge_raw = judged.get("judge_raw")
    result.judge_tokens = judged.get("judge_tokens") or 0
    result.status = "judged"
    await result.save()
    await _recalculate_run_stats(run_id)
    return result


async def execute_run_by_id(run_id: int) -> None:
    run = await AiQaEvalRun.get_or_none(id=run_id)
    if not run:
        return
    if run.status not in ("pending", "running"):
        return
    extra = run.extra if isinstance(run.extra, dict) else {}
    judge_config_id = run.judge_config_id or extra.get("judge_config_id")
    user_info = _user_info_from_run(run)
    await execute_run(run, judge_config_id=judge_config_id, user_info=user_info)


async def delete_eval_run(run_id: int, *, project_id: int) -> None:
    run = await AiQaEvalRun.get_or_none(id=run_id, project_id=project_id)
    if not run:
        raise ValueError("跑批记录不存在")
    if run.status in ("pending", "running"):
        raise ValueError("跑批进行中，无法删除")
    await AiQaEvalResult.filter(run_id=run_id).delete()
    await run.delete()


async def has_active_run(set_id: int, project_id: int) -> Optional[AiQaEvalRun]:
    return await AiQaEvalRun.filter(
        set_id=set_id,
        project_id=project_id,
        status__in=["pending", "running"],
    ).order_by("-id").first()


async def create_batch_runs(
    *,
    set_id: int,
    project_id: int,
    username: str,
    user_info: dict,
    run_mode: str,
    target_id: Optional[int],
    judge_config_id: Optional[int],
    chunk_size: int = DEFAULT_BATCH_CHUNK_SIZE,
    request_interval_ms: int = 0,
    run_name: str = "",
) -> dict[str, Any]:
    """将评测集拆成多批顺序执行（适合 550 题长时间拉取）"""
    all_cases = await list_ordered_cases(set_id)
    if not all_cases:
        raise ValueError("评测集没有用例")
    chunk_size = max(1, min(chunk_size, MAX_CASES_PER_RUN))
    batch_group_id = uuid.uuid4().hex
    chunks: list[list[AiQaEvalCase]] = [
        all_cases[i : i + chunk_size] for i in range(0, len(all_cases), chunk_size)
    ]
    run_ids: list[int] = []
    batch_total = len(chunks)
    for batch_index, chunk in enumerate(chunks, start=1):
        base_i = (batch_index - 1) * chunk_size
        start_sn = effective_seq_no(chunk[0], base_i)
        end_sn = effective_seq_no(chunk[-1], base_i + len(chunk) - 1)
        extra = {
            "user_id": user_info.get("id"),
            "username": username,
            "run_name": (run_name or "").strip()[:100],
            "judge_config_id": judge_config_id,
            "run_mode": run_mode,
            "case_scope": CASE_SCOPE_RANGE,
            "range_start": start_sn,
            "range_end": end_sn,
            "batch_group_id": batch_group_id,
            "batch_index": batch_index,
            "batch_total": batch_total,
            "request_interval_ms": request_interval_ms,
            "done_count": 0,
            "progress_percent": 0,
            "current_question": "",
        }
        run = await AiQaEvalRun.create(
            project_id=project_id,
            set_id=set_id,
            target_id=target_id,
            judge_config_id=judge_config_id,
            status="pending",
            create_by=username,
            extra=extra,
        )
        run_ids.append(run.id)
    asyncio.create_task(run_batch_group_sequential(run_ids))
    return {
        "batch_group_id": batch_group_id,
        "run_ids": run_ids,
        "batch_total": batch_total,
        "chunk_size": chunk_size,
        "total_cases": len(all_cases),
    }


async def run_batch_group_sequential(run_ids: list[int]) -> None:
    for run_id in run_ids:
        try:
            await execute_run_by_id(run_id)
        except Exception as e:
            logger.exception("batch run %s failed: %s", run_id, e)
            run = await AiQaEvalRun.get_or_none(id=run_id)
            if run and run.status not in ("completed", "failed"):
                run.status = "failed"
                run.error = str(e)[:1000]
                run.finished_at = datetime.now()
                await run.save()


async def run_qa_eval_background(run_id: int) -> None:
    try:
        await execute_run_by_id(run_id)
    except Exception as e:
        logger.exception("qa eval background run %s failed: %s", run_id, e)
        run = await AiQaEvalRun.get_or_none(id=run_id)
        if run and run.status not in ("completed", "failed"):
            run.status = "failed"
            run.error = str(e)[:1000]
            run.finished_at = datetime.now()
            await run.save()


def case_to_dict(c: AiQaEvalCase) -> dict[str, Any]:
    chat_path = c.chat_path if isinstance(c.chat_path, list) else []
    return {
        "id": c.id,
        "set_id": c.set_id,
        "seq_no": c.seq_no,
        "question": c.question,
        "expected_points": c.expected_points if isinstance(c.expected_points, list) else [],
        "expected_answer": c.expected_answer,
        "preset_answer": c.preset_answer,
        "has_preset_answer": bool((c.preset_answer or "").strip()),
        "chat_path": chat_path,
        "multi_turn": bool(c.multi_turn),
        "scenario_type": c.scenario_type or "",
        "source_file": c.source_file or "",
        "file_type": c.file_type or "",
        "category": c.category,
        "case_type": c.case_type,
        "sort_order": c.sort_order,
        "create_time": c.create_time.strftime("%Y-%m-%d %H:%M:%S") if c.create_time else "",
        "update_time": c.update_time.strftime("%Y-%m-%d %H:%M:%S") if c.update_time else "",
    }


def set_to_dict(
    s: AiQaEvalSet,
    *,
    case_count: int = 0,
    max_seq_no: Optional[int] = None,
) -> dict[str, Any]:
    return {
        "id": s.id,
        "project_id": s.project_id,
        "name": s.name,
        "description": s.description,
        "case_count": case_count,
        "max_seq_no": max_seq_no,
        "create_by": s.create_by,
        "create_time": s.create_time.strftime("%Y-%m-%d %H:%M:%S") if s.create_time else "",
        "update_time": s.update_time.strftime("%Y-%m-%d %H:%M:%S") if s.update_time else "",
    }


def target_to_dict(t: AiQaEvalTarget) -> dict[str, Any]:
    from app.core.qa_eval_target_client import normalize_sse_parser

    cfg = dict(t.config) if isinstance(t.config, dict) else {}
    if cfg.get("sse_parser"):
        cfg["sse_parser"] = normalize_sse_parser(cfg.get("sse_parser"))
    return {
        "id": t.id,
        "project_id": t.project_id,
        "name": t.name,
        "config": cfg,
        "create_by": t.create_by,
        "create_time": t.create_time.strftime("%Y-%m-%d %H:%M:%S") if t.create_time else "",
        "update_time": t.update_time.strftime("%Y-%m-%d %H:%M:%S") if t.update_time else "",
    }


def run_to_dict(r: AiQaEvalRun, *, set_name: str = "", target_name: str = "") -> dict[str, Any]:
    extra = r.extra if isinstance(r.extra, dict) else {}
    total = r.total_count or 0
    done = int(extra.get("done_count") or 0)
    if r.status == "completed":
        done = total
    pct = int(extra.get("progress_percent") or 0)
    if r.status == "completed":
        pct = 100
    elif total and not pct:
        pct = int(done / total * 100)
    run_mode = extra.get("run_mode") or RUN_MODE_AUTO
    case_scope = extra.get("case_scope") or CASE_SCOPE_ALL
    scope_label = CASE_SCOPE_LABELS.get(case_scope, case_scope)
    if case_scope == CASE_SCOPE_RANGE:
        rs = extra.get("range_start")
        re = extra.get("range_end")
        if rs is not None and re is not None:
            scope_label = f"序号 {rs}–{re}"
    batch_group_id = extra.get("batch_group_id") or ""
    batch_index = extra.get("batch_index")
    batch_total = extra.get("batch_total")
    batch_label = ""
    if batch_group_id and batch_index and batch_total:
        batch_label = f"分批 {batch_index}/{batch_total}"
    run_name = (extra.get("run_name") or "").strip()
    display_name = run_name or (set_name if set_name else f"跑批 #{r.id}")
    trigger_source = (extra.get("trigger_source") or "manual").strip()
    trigger_labels = {"manual": "手动", "assistant": "小测"}
    return {
        "id": r.id,
        "project_id": r.project_id,
        "set_id": r.set_id,
        "set_name": set_name,
        "run_name": run_name,
        "display_name": display_name,
        "trigger_source": trigger_source,
        "trigger_source_label": trigger_labels.get(trigger_source, trigger_source),
        "run_mode": run_mode,
        "run_mode_label": RUN_MODE_LABELS.get(run_mode, run_mode),
        "case_scope": case_scope,
        "case_scope_label": scope_label,
        "range_start": extra.get("range_start"),
        "range_end": extra.get("range_end"),
        "batch_group_id": batch_group_id or None,
        "batch_label": batch_label,
        "retry_source_run_id": extra.get("retry_source_run_id"),
        "export_ready": bool(extra.get("export_ready")),
        "target_id": r.target_id,
        "target_name": target_name,
        "judge_config_id": r.judge_config_id,
        "status": r.status,
        "status_label": RUN_STATUS_LABELS.get(r.status, r.status),
        "total_count": total,
        "done_count": done,
        "progress_percent": pct,
        "current_question": extra.get("current_question") or "",
        "passed_count": r.passed_count,
        "failed_count": r.failed_count,
        "avg_score": r.avg_score,
        "pass_rate": r.pass_rate,
        "error": r.error,
        "create_by": r.create_by,
        "started_at": r.started_at.strftime("%Y-%m-%d %H:%M:%S") if r.started_at else "",
        "finished_at": r.finished_at.strftime("%Y-%m-%d %H:%M:%S") if r.finished_at else "",
        "create_time": r.create_time.strftime("%Y-%m-%d %H:%M:%S") if r.create_time else "",
    }


def result_to_dict(r: AiQaEvalResult, *, case: Optional[AiQaEvalCase] = None) -> dict[str, Any]:
    ms = (r.manual_status or "pending").strip()
    from app.core.qa_eval_report import MANUAL_STATUS_LABELS, score_to_level

    level_label = (r.level or "").strip()
    score = float(r.score or 0)
    if level_label == "较差":
        display_level = "不合格"
    elif level_label in ("优秀", "良好", "合格", "不合格", "严重不合格"):
        display_level = level_label
    else:
        display_level = score_to_level(score)

    row: dict[str, Any] = {
        "id": r.id,
        "run_id": r.run_id,
        "case_id": r.case_id,
        "question": r.question,
        "actual_answer": r.actual_answer,
        "score": r.score,
        "score_raw": round(score / 100, 4) if score else 0,
        "passed": r.passed,
        "hallucination": r.hallucination,
        "level": display_level,
        "dimension_scores": r.dimension_scores if isinstance(r.dimension_scores, dict) else {},
        "missed_points": r.missed_points if isinstance(r.missed_points, list) else [],
        "extra_issues": r.extra_issues if isinstance(r.extra_issues, list) else [],
        "reason": r.reason,
        "api_error": r.api_error,
        "api_latency_ms": r.api_latency_ms,
        "judge_tokens": r.judge_tokens,
        "status": r.status,
        "manual_status": ms,
        "manual_status_label": MANUAL_STATUS_LABELS.get(ms, ms),
        "manual_comment": r.manual_comment or "",
        "manual_reviewed_by": r.manual_reviewed_by or "",
        "manual_reviewed_at": r.manual_reviewed_at.strftime("%Y-%m-%d %H:%M:%S")
        if r.manual_reviewed_at
        else "",
    }
    meta = r.api_meta if isinstance(r.api_meta, dict) else {}
    row["thinking"] = meta.get("thinking") or ""
    row["references_all"] = meta.get("references_all") or ""
    row["references_high"] = meta.get("references_high") or ""
    if case:
        row["seq_no"] = case.seq_no
        row["scenario_type"] = case.scenario_type or ""
        row["file_type"] = case.file_type or ""
        row["expected_answer"] = case.expected_answer or ""
    return row
