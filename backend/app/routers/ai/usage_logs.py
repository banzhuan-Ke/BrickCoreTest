"""AI 模型使用记录查询"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from tortoise.functions import Count, Sum

from app.core.llm.ai_usage_log import summarize_usage_path
from app.modules.ai.ai_scene_config import AI_SCENE_DEFINITIONS, resolve_scene_label
from app.core.platform.auth import require_permissions
from app.core.platform.permissions import AI_TEST_VIEW
from app.models.ai import AiUsageLog
from app.schemas.ai import StandardResponse

router = APIRouter(prefix="/usage-logs", tags=["AI使用记录"])

EXPORT_MAX_ROWS = 5000


def _scene_label(scene: str) -> str:
    return resolve_scene_label(scene)


async def _enrich_username_display(items: list[dict]) -> list[dict]:
    from app.modules.ai.ai_dashboard_stats import format_usernames_display

    usernames = [(i.get("username") or "").strip() for i in items]
    display_map = await format_usernames_display([u for u in usernames if u])
    for item in items:
        raw = (item.get("username") or "").strip()
        if raw:
            item["username_display"] = display_map.get(raw, raw)
        else:
            item["username_display"] = "系统（后台任务）"
    return items


def _build_usage_queryset(
    *,
    project_id: Optional[int] = None,
    scene: Optional[str] = None,
    username: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
):
    qs = AiUsageLog.all()
    if project_id:
        qs = qs.filter(project_id=project_id)
    if scene:
        qs = qs.filter(scene=scene)
    if username:
        qs = qs.filter(username__icontains=username.strip())
    if status in ("success", "failed"):
        qs = qs.filter(status=status)
    if date_from:
        qs = qs.filter(create_time__gte=date_from)
    if date_to:
        qs = qs.filter(create_time__lte=date_to)
    return qs


def _row_to_dict(row: AiUsageLog) -> dict:
    extra = row.extra or {}
    path = summarize_usage_path(
        scene=row.scene or "",
        input_summary=row.input_summary or "",
        extra=extra if isinstance(extra, dict) else {},
    )
    return {
        "id": row.id,
        "scene": row.scene,
        "scene_label": resolve_scene_label(row.scene, row.scene_label or ""),
        "user_id": row.user_id,
        "username": row.username,
        "project_id": row.project_id,
        "project_name": row.project_name,
        "ai_config_id": row.ai_config_id,
        "model": row.model,
        "provider": row.provider,
        "tokens_used": row.tokens_used,
        "duration_ms": row.duration_ms,
        "status": row.status,
        "input_summary": row.input_summary,
        "output_summary": row.output_summary,
        "extra": extra,
        "path_kind": path["path_kind"],
        "path_label": path["path_label"],
        "path_mode": path["mode"],
        "path_skills": path["skill_labels"],
        "path_tools": path["tools"],
        "create_time": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else "",
    }


async def _enrich_project_names(items: list[dict]) -> list[dict]:
    """历史记录可能只有 project_id 无 project_name，查询时补全。"""
    missing = {
        i["project_id"]
        for i in items
        if i.get("project_id") and not (i.get("project_name") or "").strip()
    }
    if not missing:
        return items
    from app.models.sys import Project

    rows = await Project.filter(id__in=list(missing), is_del=False).values("id", "name")
    name_map = {r["id"]: r["name"] for r in rows}
    for item in items:
        pid = item.get("project_id")
        if pid and not (item.get("project_name") or "").strip():
            item["project_name"] = name_map.get(pid, "")
    return items


async def _sum_tokens(qs) -> int:
    rows = await qs.annotate(total=Sum("tokens_used")).values("total")
    if not rows:
        return 0
    return int(rows[0].get("total") or 0)


@router.get(
    "/summary",
    summary="模型使用汇总统计",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def usage_logs_summary(
    project_id: Optional[int] = None,
    days: int = Query(7, ge=1, le=90),
):
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    period_start = today_start - timedelta(days=days - 1)

    today_qs = _build_usage_queryset(project_id=project_id, date_from=today_start)
    period_qs = _build_usage_queryset(project_id=project_id, date_from=period_start)

    today_calls = await today_qs.count()
    period_calls = await period_qs.count()
    today_tokens = await _sum_tokens(today_qs)
    period_tokens = await _sum_tokens(period_qs)
    period_failed = await period_qs.filter(status="failed").count()

    top_rows = (
        await period_qs.annotate(call_count=Count("id"), token_sum=Sum("tokens_used"))
        .group_by("scene")
        .order_by("-token_sum")
        .limit(12)
        .values("scene", "call_count", "token_sum")
    )
    top_scenes = [
        {
            "scene": r["scene"],
            "scene_label": _scene_label(r["scene"]),
            "call_count": int(r["call_count"] or 0),
            "tokens_used": int(r["token_sum"] or 0),
        }
        for r in top_rows
    ]

    by_skill: list[dict] = []
    by_rounds: list[dict] = []
    try:
        from tortoise.functions import Count as TCount
        from tortoise.functions import Sum as TSum

        from app.models.ai import AiSkillRunRecord, AssistantTurnTrace

        skill_qs = AiSkillRunRecord.filter(create_time__gte=period_start)
        if project_id:
            skill_qs = skill_qs.filter(project_id=int(project_id))
        skill_rows = (
            await skill_qs.group_by("skill_code")
            .annotate(call_count=TCount("id"), token_sum=TSum("tokens_used"))
            .order_by("-token_sum")
            .limit(20)
            .values("skill_code", "call_count", "token_sum")
        )
        by_skill = [
            {
                "skill_code": str(r.get("skill_code") or ""),
                "call_count": int(r.get("call_count") or 0),
                "tokens_used": int(r.get("token_sum") or 0),
            }
            for r in skill_rows or []
            if r.get("skill_code")
        ]
        skill_name_map: dict[str, str] = {}
        try:
            from brickcore_assist.skills.registry import list_skill_manifests

            for m in list_skill_manifests() or []:
                code = str(m.get("code") or "").strip()
                name = str(m.get("name") or "").strip()
                if code and name:
                    skill_name_map[code] = name
        except Exception:
            skill_name_map = {}
        for item in by_skill:
            code = item["skill_code"]
            item["skill_name"] = skill_name_map.get(code) or code

        trace_qs = AssistantTurnTrace.filter(create_time__gte=period_start, rounds__not_isnull=True)
        if project_id:
            trace_qs = trace_qs.filter(project_id=int(project_id))
        round_vals = await trace_qs.values_list("rounds", flat=True)
        bucket_map: dict[str, dict] = {}
        for raw in round_vals or []:
            try:
                n = int(raw)
            except (TypeError, ValueError):
                continue
            if n <= 1:
                key, label = "1", "1 轮"
            elif n == 2:
                key, label = "2", "2 轮"
            elif n <= 4:
                key, label = "3-4", "3～4 轮"
            else:
                key, label = "5+", "5+ 轮"
            slot = bucket_map.setdefault(key, {"bucket": key, "label": label, "calls": 0})
            slot["calls"] += 1
        order = ["1", "2", "3-4", "5+"]
        by_rounds = [bucket_map[k] for k in order if k in bucket_map]
    except Exception:
        by_skill = []
        by_rounds = []

    return StandardResponse(
        data={
            "days": days,
            "today": {
                "calls": today_calls,
                "tokens_used": today_tokens,
            },
            "period": {
                "calls": period_calls,
                "tokens_used": period_tokens,
                "failed_calls": period_failed,
                "start_date": period_start.strftime("%Y-%m-%d"),
                "end_date": today_start.strftime("%Y-%m-%d"),
            },
            "top_scenes": top_scenes,
            "by_skill": by_skill,
            "by_rounds": by_rounds,
        }
    )


@router.get(
    "/trend",
    summary="模型使用按日趋势",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def usage_logs_trend(
    project_id: Optional[int] = None,
    days: int = Query(7, ge=1, le=90),
):
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    items: list[dict] = []
    for offset in range(days - 1, -1, -1):
        day_start = today_start - timedelta(days=offset)
        day_end = day_start + timedelta(days=1) - timedelta(microseconds=1)
        qs = _build_usage_queryset(
            project_id=project_id,
            date_from=day_start,
            date_to=day_end,
        )
        calls = await qs.count()
        tokens = await _sum_tokens(qs)
        failed = await qs.filter(status="failed").count()
        items.append(
            {
                "date": day_start.strftime("%Y-%m-%d"),
                "calls": calls,
                "tokens_used": tokens,
                "failed_calls": failed,
            }
        )
    return StandardResponse(data={"days": days, "items": items})


@router.get(
    "/export",
    summary="导出模型使用记录 CSV",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def export_usage_logs(
    project_id: Optional[int] = None,
    scene: Optional[str] = None,
    username: Optional[str] = None,
    status: Optional[str] = None,
    days: int = Query(30, ge=1, le=90),
):
    period_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    qs = _build_usage_queryset(
        project_id=project_id,
        scene=scene,
        username=username,
        status=status,
        date_from=period_start,
    )
    rows = await qs.order_by("-id").limit(EXPORT_MAX_ROWS)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "时间",
            "场景",
            "用户",
            "项目",
            "模型",
            "供应商",
            "Tokens",
            "耗时(ms)",
            "状态",
            "路径",
            "Skill",
            "工具",
            "输入摘要",
            "输出摘要",
        ]
    )
    for row in rows:
        path = summarize_usage_path(
            scene=row.scene or "",
            input_summary=row.input_summary or "",
            extra=row.extra if isinstance(row.extra, dict) else {},
        )
        writer.writerow(
            [
                row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else "",
                resolve_scene_label(row.scene, row.scene_label or ""),
                row.username,
                row.project_name or (str(row.project_id) if row.project_id else ""),
                row.model,
                row.provider,
                row.tokens_used,
                row.duration_ms,
                row.status,
                path.get("path_label") or "",
                "、".join(path.get("skill_labels") or []),
                "、".join(path.get("tools") or []),
                (row.input_summary or "").replace("\n", " ")[:500],
                (row.output_summary or "").replace("\n", " ")[:500],
            ]
        )

    filename = f"ai_usage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    content = "\ufeff" + buffer.getvalue()
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "",
    summary="模型使用记录列表",
    dependencies=[Depends(require_permissions(AI_TEST_VIEW))],
)
async def list_usage_logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    project_id: Optional[int] = None,
    scene: Optional[str] = None,
    username: Optional[str] = None,
    status: Optional[str] = None,
    days: Optional[int] = Query(None, ge=1, le=90),
):
    date_from = None
    if days:
        date_from = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)

    qs = _build_usage_queryset(
        project_id=project_id,
        scene=scene,
        username=username,
        status=status,
        date_from=date_from,
    )

    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    items = await _enrich_project_names([_row_to_dict(row) for row in rows])
    items = await _enrich_username_display(items)
    scene_keys = {k for k in AI_SCENE_DEFINITIONS}
    if date_from:
        db_scenes = await qs.distinct().values_list("scene", flat=True)
        scene_keys.update(s for s in db_scenes if s)
    scenes = sorted(
        [{"scene": k, "label": _scene_label(k)} for k in scene_keys],
        key=lambda x: x["label"],
    )
    return StandardResponse(
        data={
            "list": items,
            "total": total,
            "page": page,
            "size": size,
            "scenes": scenes,
        }
    )
