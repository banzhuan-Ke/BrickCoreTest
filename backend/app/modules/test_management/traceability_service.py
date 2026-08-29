"""追溯矩阵 — 基于已有关系链的只读聚合"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Optional

from fastapi import HTTPException

from app.models.ai import AiFunctionalCase, AiRequirement, AiRequirementTestPoint
from app.models.test_management import (
    TestAssetLink,
    TestDefect,
    TestDefectLink,
    TestPlanRunItem,
    TestRelease,
    TestReleaseScope,
)
from app.modules.test_management.review_service import functional_case_review_status_map
from app.modules.test_management.result_normalizer import GATE_OPEN_DEFECT_STATUSES
from app.modules.test_management.service import get_release_or_404


def _trace_cell_status(
    *,
    has_case: bool,
    review_decision: Optional[str],
    has_run: bool,
    run_result: Optional[str],
    defect_open: int,
) -> str:
    if not has_case:
        return "red"
    if review_decision in ("changes_requested", "rejected", "pending"):
        return "yellow"
    if defect_open > 0:
        return "yellow"
    if has_run:
        if run_result == "passed":
            return "green"
        if run_result in ("failed", "blocked", "error"):
            return "red"
        return "yellow"
    return "yellow"


async def build_traceability_matrix(
    project_id: int,
    *,
    release_id: Optional[int] = None,
) -> dict[str, Any]:
    release: Optional[TestRelease] = None
    scope_case_ids: set[int] = set()
    if release_id is not None:
        release = await get_release_or_404(release_id, project_id)
        scopes = await TestReleaseScope.filter(
            release_id=release.id, project_id=project_id, is_del=False
        )
        scope_case_ids = {s.functional_case_id for s in scopes}

    case_q = AiFunctionalCase.filter(project_id=project_id, is_del=False)
    if scope_case_ids:
        case_q = case_q.filter(id__in=list(scope_case_ids))
    cases = await case_q.order_by("id")
    if not cases:
        return {
            "release_id": release_id,
            "rows": [],
            "coverage": _empty_coverage(),
        }

    case_ids = [c.id for c in cases]
    req_ids = {c.source_requirement_id for c in cases if c.source_requirement_id}
    requirements = {
        r.id: r
        for r in await AiRequirement.filter(id__in=list(req_ids), project_id=project_id, is_del=False)
    }

    test_points_by_req: dict[int, list[dict]] = defaultdict(list)
    if req_ids:
        for tp in await AiRequirementTestPoint.filter(
            requirement_id__in=list(req_ids), project_id=project_id, is_del=False
        ).order_by("sort_order", "id"):
            test_points_by_req[tp.requirement_id].append(
                {
                    "id": tp.id,
                    "title": tp.title,
                    "status": tp.status,
                    "priority": tp.priority,
                }
            )

    links = await TestAssetLink.filter(
        project_id=project_id, functional_case_id__in=case_ids, is_del=False
    )
    links_by_case: dict[int, list[dict]] = defaultdict(list)
    for link in links:
        links_by_case[link.functional_case_id].append(
            {
                "asset_type": link.asset_type,
                "asset_id": link.asset_id,
                "link_type": link.link_type,
            }
        )

    review_map = await functional_case_review_status_map(project_id, case_ids)

    req_review_map: dict[int, dict[str, Any]] = {}
    if req_ids:
        from app.models.test_management import RequirementReview

        latest_rows = await RequirementReview.filter(
            project_id=project_id,
            requirement_id__in=list(req_ids),
            is_del=False,
        ).order_by("-id")
        for rv in latest_rows:
            rid = rv.requirement_id
            if rid not in req_review_map:
                req_review_map[rid] = {
                    "requirement_review_id": rv.id,
                    "requirement_review_status": rv.status,
                    "requirement_review_round": rv.round,
                }

    run_q = TestPlanRunItem.filter(project_id=project_id, is_del=False)
    if release_id is not None:
        run_q = run_q.filter(run__release_id=release_id)
    run_items = await run_q.filter(functional_case_id__in=case_ids).order_by("-id")
    latest_run: dict[int, dict] = {}
    for item in run_items:
        fid = item.functional_case_id
        if fid and fid not in latest_run:
            latest_run[fid] = {
                "result_status": item.result_status,
                "run_item_id": item.id,
                "run_id": item.run_id,
            }

    defect_links = await TestDefectLink.filter(
        project_id=project_id,
        functional_case_id__in=case_ids,
        is_del=False,
    )
    defect_ids = {dl.defect_id for dl in defect_links}
    open_defects: set[int] = set()
    if defect_ids:
        open_defects = set(
            await TestDefect.filter(
                id__in=list(defect_ids),
                project_id=project_id,
                is_del=False,
                status__in=list(GATE_OPEN_DEFECT_STATUSES),
            ).values_list("id", flat=True)
        )
    defect_count_by_case: dict[int, int] = defaultdict(int)
    seen_case_defect: set[tuple[int, int]] = set()
    for dl in defect_links:
        if dl.defect_id in open_defects and dl.functional_case_id:
            key = (dl.functional_case_id, dl.defect_id)
            if key in seen_case_defect:
                continue
            seen_case_defect.add(key)
            defect_count_by_case[dl.functional_case_id] += 1

    rows_by_req: dict[Optional[int], list[dict]] = defaultdict(list)
    for case in cases:
        rid = case.source_requirement_id
        rev = review_map.get(case.id, "pending")
        run_info = latest_run.get(case.id)
        open_cnt = defect_count_by_case.get(case.id, 0)
        cell = _trace_cell_status(
            has_case=True,
            review_decision=rev,
            has_run=run_info is not None,
            run_result=run_info.get("result_status") if run_info else None,
            defect_open=open_cnt,
        )
        rows_by_req[rid].append(
            {
                "functional_case_id": case.id,
                "case_title": case.title,
                "case_module": case.module,
                "review_decision": rev,
                "automation_links": links_by_case.get(case.id, []),
                "latest_run": run_info,
                "open_defect_count": open_cnt,
                "trace_status": cell,
            }
        )

    matrix_rows: list[dict[str, Any]] = []
    ordered_req_ids = sorted(req_ids, key=lambda x: x or 0)
    for rid in ordered_req_ids:
        req = requirements.get(rid)
        rv_info = req_review_map.get(rid, {})
        req_review_status = (
            getattr(req, "review_status", None) if req else None
        ) or rv_info.get("requirement_review_status")
        matrix_rows.append(
            {
                "requirement_id": rid,
                "requirement_name": req.name if req else f"需求 #{rid}",
                "review_status": req_review_status,
                "requirement_review_id": rv_info.get("requirement_review_id"),
                "requirement_review_round": rv_info.get("requirement_review_round"),
                "test_points": test_points_by_req.get(rid, []),
                "cases": rows_by_req.get(rid, []),
            }
        )
    if None in rows_by_req:
        matrix_rows.append(
            {
                "requirement_id": None,
                "requirement_name": "无关联需求",
                "review_status": None,
                "requirement_review_id": None,
                "requirement_review_round": None,
                "test_points": [],
                "cases": rows_by_req[None],
            }
        )

    coverage = _compute_coverage(matrix_rows, requirements, test_points_by_req)
    return {
        "release_id": release_id,
        "release_key": release.release_key if release else None,
        "rows": matrix_rows,
        "coverage": coverage,
    }


def _empty_coverage() -> dict[str, Any]:
    return {
        "requirement_total": 0,
        "requirement_with_cases": 0,
        "test_point_total": 0,
        "functional_case_total": 0,
        "cases_executed": 0,
        "cases_passed": 0,
        "cases_with_open_defects": 0,
    }


def _latest_run_result(case_row: dict) -> Optional[str]:
    latest_run = case_row.get("latest_run")
    if not isinstance(latest_run, dict):
        return None
    return latest_run.get("result_status")


def _compute_coverage(
    matrix_rows: list[dict],
    requirements: dict[int, AiRequirement],
    test_points_by_req: dict[int, list],
) -> dict[str, Any]:
    req_with_cases = sum(1 for row in matrix_rows if row.get("requirement_id") and row.get("cases"))
    tp_total = sum(len(test_points_by_req.get(rid, [])) for rid in requirements)
    all_cases = []
    for row in matrix_rows:
        all_cases.extend(row.get("cases") or [])
    executed = sum(1 for c in all_cases if isinstance(c.get("latest_run"), dict))
    passed = sum(1 for c in all_cases if _latest_run_result(c) == "passed")
    with_defects = sum(1 for c in all_cases if c.get("open_defect_count", 0) > 0)
    return {
        "requirement_total": len(requirements),
        "requirement_with_cases": req_with_cases,
        "test_point_total": tp_total,
        "functional_case_total": len(all_cases),
        "cases_executed": executed,
        "cases_passed": passed,
        "cases_with_open_defects": with_defects,
    }


async def build_coverage_report(project_id: int, release_id: Optional[int] = None) -> dict[str, Any]:
    data = await build_traceability_matrix(project_id, release_id=release_id)
    cov = data.get("coverage") or {}
    total_cases = cov.get("functional_case_total") or 0
    executed = cov.get("cases_executed") or 0
    cov["execution_rate"] = round(executed / total_cases, 4) if total_cases else 0.0
    req_total = cov.get("requirement_total") or 0
    req_cov = cov.get("requirement_with_cases") or 0
    cov["requirement_coverage_rate"] = round(req_cov / req_total, 4) if req_total else 0.0
    return {"release_id": release_id, "coverage": cov}


async def build_traceability_matrix_page(
    project_id: int,
    *,
    release_id: Optional[int] = None,
    page: int = 1,
    size: int = 50,
    keyword: Optional[str] = None,
    trace_status: Optional[str] = None,
    review_decision: Optional[str] = None,
    all_rows: bool = False,
) -> dict[str, Any]:
    """展平 + 过滤 + 分页；coverage 仍基于全量矩阵。"""
    from app.modules.test_management.matrix_export_utils import filter_flat_rows, flatten_matrix_rows

    data = await build_traceability_matrix(project_id, release_id=release_id)
    flat = flatten_matrix_rows(data.get("rows") or [])
    filtered = filter_flat_rows(
        flat,
        keyword=keyword,
        trace_status=trace_status,
        review_decision=review_decision,
    )
    total = len(filtered)
    page = max(1, int(page or 1))
    size = max(1, min(int(size or 50), 500))
    if all_rows:
        page_rows = filtered
        size = total or size
        page = 1
    else:
        start = (page - 1) * size
        page_rows = filtered[start : start + size]
    return {
        "release_id": data.get("release_id"),
        "release_key": data.get("release_key"),
        "rows": page_rows,
        "format": "flat",
        "coverage": data.get("coverage") or _empty_coverage(),
        "pagination": {"page": page, "size": size, "total": total},
    }
