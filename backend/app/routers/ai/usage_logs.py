"""AI 模型使用记录查询"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from tortoise.functions import Count, Sum

from app.core.ai_scene_config import AI_SCENE_DEFINITIONS
from app.core.auth import require_permissions
from app.core.permissions import AI_TEST_VIEW
from app.models.ai import AiUsageLog
from app.schemas.ai import StandardResponse

router = APIRouter(prefix="/usage-logs", tags=["AI使用记录"])

EXPORT_MAX_ROWS = 5000


def _scene_label(scene: str) -> str:
    return AI_SCENE_DEFINITIONS.get(scene, (scene, ""))[0]


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
    return {
        "id": row.id,
        "scene": row.scene,
        "scene_label": row.scene_label or _scene_label(row.scene),
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
        "extra": row.extra or {},
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
        .limit(5)
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
            "top_scenes": top_scenes[:8],
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
            "输入摘要",
            "输出摘要",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else "",
                row.scene_label or _scene_label(row.scene),
                row.username,
                row.project_name or (str(row.project_id) if row.project_id else ""),
                row.model,
                row.provider,
                row.tokens_used,
                row.duration_ms,
                row.status,
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
    scenes = [{"scene": k, "label": v[0]} for k, v in AI_SCENE_DEFINITIONS.items()]
    return StandardResponse(
        data={
            "list": items,
            "total": total,
            "page": page,
            "size": size,
            "scenes": scenes,
        }
    )
