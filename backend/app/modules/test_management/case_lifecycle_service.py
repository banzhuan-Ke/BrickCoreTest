"""功能用例生命周期聚合（只读）"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException

from app.models.ai import AiFunctionalCase, AiRequirement
from app.models.test_management import (
    TestAssetLink,
    TestDefect,
    TestDefectLink,
    TestPlan,
    TestPlanRun,
    TestPlanRunItem,
    TestRelease,
    TestReleaseScope,
)
from app.modules.test_management.service import _dt_iso


async def get_functional_case_or_404(case_id: int, project_id: int) -> AiFunctionalCase:
    row = await AiFunctionalCase.get_or_none(id=case_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="功能用例不存在")
    return row


def _case_brief(row: AiFunctionalCase) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "product": row.product,
        "module": row.module,
        "priority": row.priority,
        "status": row.status,
        "precondition": row.precondition,
        "steps": list(row.steps or []),
        "related_story": row.related_story,
        "source_requirement_id": row.source_requirement_id,
        "zentao_case_id": row.zentao_case_id,
        "create_time": _dt_iso(row.create_time),
        "update_time": _dt_iso(row.update_time),
    }


async def build_functional_case_lifecycle(
    project_id: int,
    case_id: int,
) -> dict[str, Any]:
    case = await get_functional_case_or_404(case_id, project_id)

    requirement: Optional[dict[str, Any]] = None
    if case.source_requirement_id:
        req = await AiRequirement.get_or_none(
            id=case.source_requirement_id, project_id=project_id, is_del=False
        )
        if req:
            requirement = {
                "id": req.id,
                "name": req.name,
                "review_status": getattr(req, "review_status", None),
                "parse_status": getattr(req, "parse_status", None),
            }

    scopes = await TestReleaseScope.filter(
        project_id=project_id, functional_case_id=case_id, is_del=False
    )
    release_ids = list({s.release_id for s in scopes if s.release_id})
    releases_by_id: dict[int, TestRelease] = {}
    if release_ids:
        releases = await TestRelease.filter(
            id__in=release_ids, project_id=project_id, is_del=False
        )
        releases_by_id = {r.id: r for r in releases}
    scope_rows = []
    for s in scopes:
        rel = releases_by_id.get(s.release_id)
        scope_rows.append(
            {
                "release_id": s.release_id,
                "release_key": rel.release_key if rel else None,
                "release_name": rel.name if rel else None,
                "scope_status": s.scope_status,
                "risk_level": s.risk_level,
            }
        )

    defect_links = await TestDefectLink.filter(
        project_id=project_id,
        functional_case_id=case_id,
        is_del=False,
        link_type="functional_case",
    )
    # also defects linked via run_item of this case
    run_items = await TestPlanRunItem.filter(
        project_id=project_id, functional_case_id=case_id, is_del=False
    ).order_by("-id")
    run_item_ids = [i.id for i in run_items]
    if run_item_ids:
        extra_links = await TestDefectLink.filter(
            project_id=project_id,
            run_item_id__in=run_item_ids,
            is_del=False,
            link_type="run_item",
        )
        defect_links = list(defect_links) + list(extra_links)

    defect_ids = list({lk.defect_id for lk in defect_links})
    defects: list[dict[str, Any]] = []
    if defect_ids:
        rows = await TestDefect.filter(
            id__in=defect_ids, project_id=project_id, is_del=False
        ).order_by("-id")
        defects = [
            {
                "id": d.id,
                "defect_key": d.defect_key,
                "title": d.title,
                "status": d.status,
                "severity": d.severity,
                "priority": d.priority,
                "release_id": d.release_id,
            }
            for d in rows
        ]

    runs_by_id: dict[int, TestPlanRun] = {}
    plans_by_id: dict[int, TestPlan] = {}
    run_ids = list({i.run_id for i in run_items if i.run_id})
    if run_ids:
        runs = await TestPlanRun.filter(id__in=run_ids, project_id=project_id, is_del=False)
        runs_by_id = {r.id: r for r in runs}
        plan_ids = list({r.plan_id for r in runs if r.plan_id})
        if plan_ids:
            plans = await TestPlan.filter(id__in=plan_ids, project_id=project_id, is_del=False)
            plans_by_id = {p.id: p for p in plans}

    plan_runs: list[dict[str, Any]] = []
    seen_run: set[int] = set()
    for item in run_items:
        if item.run_id in seen_run:
            # keep latest item result per run already ordered by -id; skip duplicates
            continue
        seen_run.add(item.run_id)
        run = runs_by_id.get(item.run_id)
        plan = plans_by_id.get(run.plan_id) if run else None
        plan_runs.append(
            {
                "plan_id": run.plan_id if run else None,
                "plan_name": plan.name if plan else None,
                "run_id": item.run_id,
                "run_item_id": item.id,
                "result_status": item.result_status,
                "release_id": run.release_id if run else None,
                "title": item.title,
            }
        )

    asset_links = await TestAssetLink.filter(
        project_id=project_id, functional_case_id=case_id, is_del=False
    )
    assets = [
        {
            "id": a.id,
            "asset_type": a.asset_type,
            "asset_id": a.asset_id,
            "link_type": a.link_type,
            "coverage_note": a.coverage_note,
        }
        for a in asset_links
    ]

    return {
        "case": _case_brief(case),
        "requirement": requirement,
        "releases": scope_rows,
        "defects": defects,
        "plan_runs": plan_runs[:50],
        "asset_links": assets,
    }
