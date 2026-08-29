"""追溯矩阵展平/筛选（开源面，不依赖 brickcore_tm）。"""
from __future__ import annotations

from typing import Any, Optional


def flatten_matrix_rows(matrix_rows: list[dict]) -> list[dict[str, Any]]:
    """将嵌套矩阵展平为表格行（与前端 TraceabilityMatrix 一致）。"""
    out: list[dict[str, Any]] = []
    for group in matrix_rows or []:
        req_name = group.get("requirement_name") or "—"
        req_review_status = group.get("review_status")
        tps = group.get("test_points") or []
        tp_titles = "、".join(t.get("title") or "" for t in tps) or "—"
        cases = group.get("cases") or []
        for c in cases:
            links = c.get("automation_links") or []
            link_sum = ", ".join(
                f"{l.get('asset_type')}#{l.get('asset_id')}" for l in links
            ) or "无"
            latest = c.get("latest_run") if isinstance(c.get("latest_run"), dict) else None
            out.append({
                "rowKey": f"{group.get('requirement_id')}-{c.get('functional_case_id')}",
                "requirement_id": group.get("requirement_id"),
                "functional_case_id": c.get("functional_case_id"),
                "requirement_name": req_name,
                "requirement_review_status": req_review_status,
                "requirement_review_id": group.get("requirement_review_id"),
                "requirement_review_round": group.get("requirement_review_round"),
                "test_point_title": tp_titles,
                "case_title": c.get("case_title") or "—",
                "review_decision": c.get("review_decision"),
                "automation_summary": link_sum,
                "automation_links": links,
                "run_result": (latest or {}).get("result_status") or "—",
                "run_id": (latest or {}).get("run_id"),
                "open_defect_count": c.get("open_defect_count") or 0,
                "trace_status": c.get("trace_status"),
            })
        if not cases:
            out.append({
                "rowKey": f"req-{group.get('requirement_id')}",
                "requirement_id": group.get("requirement_id"),
                "functional_case_id": None,
                "requirement_name": req_name,
                "requirement_review_status": req_review_status,
                "requirement_review_id": group.get("requirement_review_id"),
                "requirement_review_round": group.get("requirement_review_round"),
                "test_point_title": tp_titles,
                "case_title": "—",
                "review_decision": None,
                "automation_summary": "—",
                "automation_links": [],
                "run_result": "—",
                "run_id": None,
                "open_defect_count": 0,
                "trace_status": "red",
            })
    return out


def filter_flat_rows(
    rows: list[dict[str, Any]],
    *,
    keyword: Optional[str] = None,
    trace_status: Optional[str] = None,
    review_decision: Optional[str] = None,
) -> list[dict[str, Any]]:
    kw = (keyword or "").strip().lower()
    out = []
    for r in rows:
        if trace_status and r.get("trace_status") != trace_status:
            continue
        if review_decision and r.get("review_decision") != review_decision:
            continue
        if kw:
            hay = f"{r.get('requirement_name')} {r.get('case_title')} {r.get('test_point_title')}".lower()
            if kw not in hay:
                continue
        out.append(r)
    return out
