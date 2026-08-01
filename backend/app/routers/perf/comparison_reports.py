"""性能测试对比报告 API"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.core.platform.auth import get_current_username, is_authenticated, require_permissions
from app.core.platform.permissions import PERF_RECORD_VIEW, PERF_SCENE_EDIT
from app.core.platform.project_access import PROJECT_ROLE_MEMBER, PROJECT_ROLE_VIEWER, assert_project_access
from app.models.perf import PerfComparisonReport, PerfRecord
from app.modules.perf.compare_report import (
    MAX_COMPARE_RECORDS,
    MIN_COMPARE_RECORDS,
    REPORT_KIND_COMPARE,
    REPORT_KIND_HYBRID,
    REPORT_KIND_MERGE,
    REPORT_KINDS,
    build_report_snapshot,
    hydrate_snapshot_chart_fields,
    trim_snapshot_for_ai,
)

router = APIRouter(
    prefix="/comparison-reports",
    tags=["性能测试对比报告"],
    dependencies=[Depends(is_authenticated), Depends(require_permissions(PERF_RECORD_VIEW))],
)


class CreateComparisonBody(BaseModel):
    project_id: int
    record_ids: List[int] = Field(..., min_length=MIN_COMPARE_RECORDS, max_length=MAX_COMPARE_RECORDS)
    reference_record_id: Optional[int] = None
    title: Optional[str] = None
    kind: Optional[str] = Field(
        None,
        description="compare=对比 / merge=汇总 / hybrid=合并+对比；空则按场景自动选择",
    )
    display_names: Optional[dict] = Field(
        None,
        description="记录展示名，key 为 record_id 字符串，如 {\"37\": \"瞬间峰值\"}",
    )
    user_extra_prompt: Optional[str] = Field(
        None,
        max_length=2000,
        description="附加给 AI 的用户提示（仅本报告）",
    )
    ai_analyze: Optional[bool] = Field(None, description="创建后是否自动 AI 分析")


async def _load_ordered_records(record_ids: List[int]) -> list[PerfRecord]:
    unique = list(dict.fromkeys(record_ids))
    if len(unique) < MIN_COMPARE_RECORDS:
        raise HTTPException(status_code=400, detail=f"请至少选择 {MIN_COMPARE_RECORDS} 条不重复记录")
    if len(unique) > MAX_COMPARE_RECORDS:
        raise HTTPException(status_code=400, detail=f"最多支持对比 {MAX_COMPARE_RECORDS} 条记录")
    rows = await PerfRecord.filter(id__in=unique).all()
    by_id = {r.id: r for r in rows}
    missing = [i for i in unique if i not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"记录不存在: {missing[:10]}")
    return [by_id[i] for i in unique]


def _serialize(report: PerfComparisonReport) -> dict:
    snap = report.snapshot or {}
    kind = (getattr(report, "kind", None) or snap.get("kind") or REPORT_KIND_COMPARE)
    return {
        "id": report.id,
        "project_id": report.project_id,
        "title": report.title,
        "kind": kind,
        "record_ids": report.record_ids or [],
        "reference_record_id": report.reference_record_id,
        "snapshot": snap,
        "ai_analysis": report.ai_analysis,
        "create_by": report.create_by,
        "create_time": report.create_time.strftime("%Y-%m-%d %H:%M:%S") if report.create_time else None,
        "update_time": report.update_time.strftime("%Y-%m-%d %H:%M:%S") if report.update_time else None,
    }


@router.get("", summary="增强报告列表")
async def list_comparison_reports(
    project_id: int = Query(...),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    kind: Optional[str] = Query(None, description="compare / merge / hybrid；空=全部"),
    create_by: Optional[str] = Query(None, description="创建人关键字"),
    start_date: Optional[str] = Query(None, description="开始日期(YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期(YYYY-MM-DD)"),
    user_info: dict = Depends(is_authenticated),
):
    await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_VIEWER)
    qs = PerfComparisonReport.filter(project_id=project_id, is_del=False)
    if kind in REPORT_KINDS:
        qs = qs.filter(kind=kind)
    if create_by and create_by.strip():
        qs = qs.filter(create_by__icontains=create_by.strip())
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            qs = qs.filter(create_time__gte=start_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="start_date 格式须为 YYYY-MM-DD")
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            qs = qs.filter(create_time__lte=end_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="end_date 格式须为 YYYY-MM-DD")
    total = await qs.count()
    rows = await qs.order_by("-id").offset((page - 1) * size).limit(size)
    return {
        "data": [_serialize(r) for r in rows],
        "total": total,
        "page": page,
        "size": size,
    }


@router.post(
    "/batch-delete",
    summary="批量删除增强报告",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def batch_delete_comparison_reports(
    report_ids: List[int],
    user_info: dict = Depends(is_authenticated),
):
    """批量软删除增强报告：先全量鉴权，再事务更新。"""
    if not report_ids:
        raise HTTPException(status_code=400, detail="请选择要删除的报告")

    unique_ids = list(dict.fromkeys(report_ids))
    reports = await PerfComparisonReport.filter(id__in=unique_ids, is_del=False).all()
    found = {r.id: r for r in reports}
    missing = [rid for rid in unique_ids if rid not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"报告不存在: {missing[:10]}")

    for report in reports:
        await assert_project_access(user_info, report.project_id, min_role=PROJECT_ROLE_MEMBER)

    from tortoise.transactions import in_transaction

    async with in_transaction():
        await PerfComparisonReport.filter(id__in=unique_ids, is_del=False).update(is_del=True)


@router.post("", summary="创建增强报告（对比/汇总/合并+对比）", dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))])
async def create_comparison_report(
    body: CreateComparisonBody,
    user_info: dict = Depends(is_authenticated),
    username: str = Depends(get_current_username),
):
    await assert_project_access(user_info, body.project_id, min_role=PROJECT_ROLE_MEMBER)
    records = await _load_ordered_records(body.record_ids)
    for r in records:
        if r.project_id != body.project_id:
            raise HTTPException(status_code=400, detail="记录与项目不匹配")
        await assert_project_access(user_info, r.project_id, min_role=PROJECT_ROLE_VIEWER)

    scene_names: dict[int, str] = {}
    for r in records:
        scene = await r.scene
        scene_names[r.id] = scene.name if scene else "未知场景"

    snapshot = build_report_snapshot(
        records,
        reference_record_id=body.reference_record_id,
        scene_names=scene_names,
        kind=body.kind,
        display_names=body.display_names,
        user_extra_prompt=body.user_extra_prompt,
    )
    kind = snapshot.get("kind") or REPORT_KIND_COMPARE
    title = (body.title or "").strip()
    if not title:
        ids = ",".join(str(i) for i in snapshot["record_ids"][:5])
        prefix = {
            REPORT_KIND_MERGE: "汇总报告",
            REPORT_KIND_HYBRID: "合并+对比报告",
        }.get(kind, "对比报告")
        title = f"{prefix} #{ids}" + ("…" if len(snapshot["record_ids"]) > 5 else "")
        title = f"{title} · {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    report = await PerfComparisonReport.create(
        project_id=body.project_id,
        title=title[:200],
        kind=kind,
        record_ids=snapshot["record_ids"],
        reference_record_id=snapshot["reference_record_id"],
        snapshot=snapshot,
        create_by=username or str(user_info.get("username") or ""),
    )

    from app.modules.ai.ai_project_settings import resolve_perf_ai_for_run
    from app.modules.perf.perf_ai_analyze import (
        running_placeholder,
        schedule_perf_compare_analysis,
    )

    should_ai = await resolve_perf_ai_for_run(body.project_id, user_override=body.ai_analyze)
    if should_ai:
        report.ai_analysis = running_placeholder()
        await report.save(update_fields=["ai_analysis"])
        schedule_perf_compare_analysis(
            report.id,
            username=username or str(user_info.get("username") or "system"),
        )

    return _serialize(report)


@router.get("/{report_id}", summary="对比报告详情")
async def get_comparison_report(
    report_id: int,
    user_info: dict = Depends(is_authenticated),
):
    report = await PerfComparisonReport.get_or_none(id=report_id, is_del=False)
    if not report:
        raise HTTPException(status_code=404, detail="对比报告不存在")
    await assert_project_access(user_info, report.project_id, min_role=PROJECT_ROLE_VIEWER)
    data = _serialize(report)
    data["snapshot"] = await hydrate_snapshot_chart_fields(data.get("snapshot"))
    ai = data.get("ai_analysis")
    if isinstance(ai, dict) and ai.get("status") == "done":
        try:
            from app.modules.perf.perf_ai_analyze import (
                metric_label_map_from_snapshot,
                scrub_ai_payload,
            )
            data["ai_analysis"] = scrub_ai_payload(
                dict(ai),
                metric_label_map_from_snapshot(data.get("snapshot") or {}),
            )
        except Exception:
            pass
    return data


@router.delete(
    "/{report_id}",
    summary="删除对比报告",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def delete_comparison_report(
    report_id: int,
    user_info: dict = Depends(is_authenticated),
):
    report = await PerfComparisonReport.get_or_none(id=report_id, is_del=False)
    if not report:
        raise HTTPException(status_code=404, detail="对比报告不存在")
    await assert_project_access(user_info, report.project_id, min_role=PROJECT_ROLE_MEMBER)
    report.is_del = True
    await report.save()
    return {"message": "已删除"}


@router.get("/{report_id}/export-html", summary="导出对比报告 HTML")
async def export_comparison_html(
    report_id: int,
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.perf.compare_html import render_comparison_html
    from app.core.shared.download_headers import content_disposition_attachment, sanitize_download_basename
    from types import SimpleNamespace

    report = await PerfComparisonReport.get_or_none(id=report_id, is_del=False)
    if not report:
        raise HTTPException(status_code=404, detail="对比报告不存在")
    await assert_project_access(user_info, report.project_id, min_role=PROJECT_ROLE_VIEWER)
    snap = await hydrate_snapshot_chart_fields(report.snapshot or {})
    view = SimpleNamespace(
        id=report.id,
        title=report.title,
        kind=getattr(report, "kind", None),
        snapshot=snap,
        ai_analysis=report.ai_analysis,
    )
    html = render_comparison_html(view)
    kind = (getattr(report, "kind", None) or snap.get("kind") or "compare")
    kind_cn = {"merge": "汇总报告", "hybrid": "合并对比报告", "compare": "对比报告"}.get(kind, "对比报告")
    title = sanitize_download_basename((report.title or "").strip() or kind_cn, fallback=kind_cn)
    filename = f"{title}.html"
    ascii_fallback = f"perf_{kind}_{report_id}.html"
    return HTMLResponse(
        content=html,
        headers=content_disposition_attachment(filename, ascii_fallback=ascii_fallback),
    )


@router.get("/{report_id}/ai-context", summary="AI 分析用精简上下文")
async def get_ai_context(
    report_id: int,
    user_info: dict = Depends(is_authenticated),
):
    report = await PerfComparisonReport.get_or_none(id=report_id, is_del=False)
    if not report:
        raise HTTPException(status_code=404, detail="对比报告不存在")
    await assert_project_access(user_info, report.project_id, min_role=PROJECT_ROLE_VIEWER)
    snap = await hydrate_snapshot_chart_fields(report.snapshot or {})
    return {
        "report_id": report.id,
        "title": report.title,
        "context": trim_snapshot_for_ai(snap),
        "ai_analysis": report.ai_analysis,
    }
