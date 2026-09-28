"""小测回复反馈（W6）。"""
from __future__ import annotations

from typing import Any

from app.models.ai import AssistantFeedback, AssistantSession

ALLOWED_SCORES = frozenset({1, -1})


async def upsert_feedback(
    *,
    user_id: int,
    session_id: int,
    message_id: str,
    score: int,
    note: str = "",
    project_id: int | None = None,
) -> dict[str, Any]:
    mid = (message_id or "").strip()[:64]
    if not mid:
        raise ValueError("message_id 不能为空")
    if int(score) not in ALLOWED_SCORES:
        raise ValueError("score 仅支持 1（赞）或 -1（踩）")
    session = await AssistantSession.get_or_none(id=int(session_id), user_id=int(user_id))
    if not session:
        raise ValueError("会话不存在或无权访问")
    pid = project_id if project_id is not None else session.project_id
    note_s = (note or "").strip()[:500] or None
    row = await AssistantFeedback.get_or_none(
        session_id=int(session_id),
        message_id=mid,
        user_id=int(user_id),
    )
    if row:
        row.score = int(score)
        row.note = note_s
        row.project_id = pid
        await row.save(update_fields=["score", "note", "project_id", "update_time"])
    else:
        row = await AssistantFeedback.create(
            session_id=int(session_id),
            message_id=mid,
            user_id=int(user_id),
            project_id=pid,
            score=int(score),
            note=note_s,
        )
    return {
        "id": row.id,
        "session_id": row.session_id,
        "message_id": row.message_id,
        "score": row.score,
        "note": row.note or "",
    }


async def map_scores_for_session(*, user_id: int, session_id: int) -> dict[str, int]:
    """会话内 message_id → score，供重开会话回填反馈状态。"""
    rows = await AssistantFeedback.filter(
        user_id=int(user_id),
        session_id=int(session_id),
    ).only("message_id", "score")
    out: dict[str, int] = {}
    for row in rows:
        mid = (row.message_id or "").strip()
        if mid and int(row.score) in ALLOWED_SCORES:
            out[mid] = int(row.score)
    return out


def apply_feedback_scores(
    messages: list[dict[str, Any]] | None,
    score_map: dict[str, int] | None,
) -> list[dict[str, Any]]:
    """把反馈分写回消息列表（不改动无 message_id 的项）。"""
    if not isinstance(messages, list):
        return []
    if not score_map:
        return list(messages)
    out: list[dict[str, Any]] = []
    for raw in messages:
        if not isinstance(raw, dict):
            continue
        msg = dict(raw)
        mid = str(msg.get("message_id") or "").strip()
        if mid and mid in score_map:
            msg["feedback_score"] = score_map[mid]
        out.append(msg)
    return out


async def summarize_feedback_effectiveness(
    *,
    days: int = 30,
    project_id: int | None = None,
) -> dict[str, Any]:
    """赞踩率 + 同期小测/Skill 用量，供 AI-2 效果运营。"""
    from datetime import timedelta

    from tortoise.functions import Count, Sum

    from app.core.platform.datetime_utils import now_app
    from app.models.ai import AiSkillRunRecord, AiUsageLog, AssistantTurnTrace

    since = now_app() - timedelta(days=max(1, min(int(days), 90)))
    fb_qs = AssistantFeedback.filter(create_time__gte=since)
    if project_id is not None:
        fb_qs = fb_qs.filter(project_id=int(project_id))

    up = await fb_qs.filter(score=1).count()
    down = await fb_qs.filter(score=-1).count()
    total_fb = up + down
    rate = round(up / total_fb, 4) if total_fb else None

    usage_qs = AiUsageLog.filter(create_time__gte=since, scene="platform_assistant")
    if project_id is not None:
        usage_qs = usage_qs.filter(project_id=int(project_id))
    usage_calls = await usage_qs.count()
    usage_token_rows = await usage_qs.annotate(total=Sum("tokens_used")).values("total")
    usage_tokens = int((usage_token_rows[0].get("total") if usage_token_rows else 0) or 0)

    skill_qs = AiSkillRunRecord.filter(create_time__gte=since)
    if project_id is not None:
        skill_qs = skill_qs.filter(project_id=int(project_id))
    by_prompt: list[dict[str, Any]] = []
    try:
        rows = (
            await skill_qs.group_by("skill_code", "prompt_key", "prompt_version")
            .annotate(calls=Count("id"), tokens=Sum("tokens_used"))
            .values("skill_code", "prompt_key", "prompt_version", "calls", "tokens")
        )
        fail_map: dict[tuple, int] = {}
        fail_rows = (
            await skill_qs.filter(status="failed")
            .group_by("skill_code", "prompt_key", "prompt_version")
            .annotate(failed_calls=Count("id"))
            .values("skill_code", "prompt_key", "prompt_version", "failed_calls")
        )
        for fr in fail_rows or []:
            key = (
                str(fr.get("skill_code") or ""),
                str(fr.get("prompt_key") or ""),
                str(fr.get("prompt_version") or ""),
            )
            fail_map[key] = int(fr.get("failed_calls") or 0)
        for row in rows or []:
            code = str(row.get("skill_code") or "")
            pk = str(row.get("prompt_key") or "")
            pv = str(row.get("prompt_version") or "")
            calls = int(row.get("calls") or 0)
            failed = fail_map.get((code, pk, pv), 0)
            by_prompt.append(
                {
                    "skill_code": code,
                    "prompt_key": pk or None,
                    "prompt_version": pv or None,
                    "calls": calls,
                    "tokens_used": int(row.get("tokens") or 0),
                    "failed_calls": failed,
                    "success_rate": round((calls - failed) / calls, 4) if calls else None,
                }
            )
        by_prompt.sort(key=lambda x: (-(x["tokens_used"] or 0), -(x["calls"] or 0)))
    except Exception:
        by_prompt = []

    trace_qs = AssistantTurnTrace.filter(create_time__gte=since)
    if project_id is not None:
        trace_qs = trace_qs.filter(project_id=int(project_id))
    trace_n = await trace_qs.count()
    avg_rounds = None
    if trace_n:
        round_rows = await trace_qs.filter(rounds__not_isnull=True).values_list("rounds", flat=True)
        vals = [int(x) for x in round_rows if x is not None]
        if vals:
            avg_rounds = round(sum(vals) / len(vals), 2)

    return {
        "days": int(days),
        "project_id": project_id,
        "feedback": {
            "up": up,
            "down": down,
            "total": total_fb,
            "up_rate": rate,
        },
        "assistant_usage": {
            "calls": usage_calls,
            "tokens_used": usage_tokens,
        },
        "avg_rounds": avg_rounds,
        "by_prompt_version": by_prompt[:40],
    }
