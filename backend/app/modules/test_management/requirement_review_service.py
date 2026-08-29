"""需求可测性评审服务"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from tortoise import transactions

from app.models.ai import AiRequirement
from app.models.test_management import RequirementReview, RequirementReviewItem
from app.modules.test_management.phase2_rules import aggregate_item_decision
from app.modules.test_management.requirement_review_rules import (
    REQUIREMENT_REVIEW_CATEGORIES,
    REQUIREMENT_REVIEW_STATUSES,
    requirement_design_allowed,
)
from app.modules.test_management.service import _dt_iso


def review_to_dict(row: RequirementReview) -> dict[str, Any]:
    decisions = list(getattr(row, "decisions_json", None) or [])
    required = [int(x) for x in (row.reviewer_ids or []) if x is not None]
    return {
        "id": row.id,
        "project_id": row.project_id,
        "requirement_id": row.requirement_id,
        "status": row.status,
        "reviewer_ids": row.reviewer_ids or [],
        "round": row.round,
        "ai_assist_summary": row.ai_assist_summary,
        "summary": row.summary,
        "decisions_json": decisions,
        "aggregate_decision": aggregate_item_decision(decisions, required),
        "create_by": row.create_by,
        "create_time": _dt_iso(row.create_time),
        "update_time": _dt_iso(row.update_time),
    }


def item_to_dict(row: RequirementReviewItem) -> dict[str, Any]:
    return {
        "id": row.id,
        "review_id": row.review_id,
        "section_id": row.section_id,
        "category": row.category,
        "severity": row.severity,
        "comment": row.comment,
        "suggested_fix": row.suggested_fix,
        "create_by": row.create_by,
        "create_time": _dt_iso(row.create_time),
    }


def build_reviewer_stats(review: RequirementReview) -> dict[str, Any]:
    required = [int(x) for x in (review.reviewer_ids or []) if x is not None]
    decisions = list(getattr(review, "decisions_json", None) or [])
    by_user = {
        int(d["reviewer_id"]): d
        for d in decisions
        if d.get("reviewer_id") is not None
    }
    reviewers = []
    for rid in required:
        d = by_user.get(rid)
        reviewers.append(
            {
                "reviewer_id": rid,
                "decision": (d or {}).get("decision") or "pending",
                "comment": (d or {}).get("comment") or "",
                "done": bool(d and (d.get("decision") or "pending") != "pending"),
            }
        )
    done = sum(1 for r in reviewers if r["done"])
    return {
        "total": len(required),
        "done": done,
        "pending": max(0, len(required) - done),
        "aggregate": aggregate_item_decision(decisions, required),
        "reviewers": reviewers,
    }


async def get_ai_requirement_or_404(requirement_id: int, project_id: int) -> AiRequirement:
    req = await AiRequirement.get_or_none(id=requirement_id, project_id=project_id, is_del=False)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    return req


async def build_requirement_preview(requirement_id: int, project_id: int) -> dict[str, Any]:
    req = await get_ai_requirement_or_404(requirement_id, project_id)
    meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
    sections = meta.get("sections") or []
    content = req.original_content or ""
    if len(content) > 12000:
        content = content[:12000] + "..."
    return {
        "id": req.id,
        "name": req.name,
        "requirement_key": f"REQ-{req.id}",
        "source_type": "ai",
        "ai_requirement_id": req.id,
        "original_content": content,
        "sections": sections[:80],
        "section_count": len(sections),
        "file_name": meta.get("file_name", ""),
        "review_status": req.review_status,
        "parse_status": req.parse_status,
        "text_length": len(req.original_content or ""),
    }


async def assert_requirement_design_allowed(req: AiRequirement) -> None:
    if not requirement_design_allowed(getattr(req, "review_status", None) or "pending"):
        raise HTTPException(
            status_code=400,
            detail="需求尚未通过可测性评审，请先完成需求评审后再提取测试点或生成用例",
        )


async def get_latest_review(requirement_id: int, project_id: int) -> Optional[RequirementReview]:
    return await RequirementReview.filter(
        requirement_id=requirement_id,
        project_id=project_id,
        is_del=False,
    ).order_by("-id").first()


async def list_reviews(
    project_id: int,
    requirement_id: Optional[int] = None,
    release_id: Optional[int] = None,
) -> list[RequirementReview]:
    q = RequirementReview.filter(project_id=project_id, is_del=False)
    if requirement_id is not None:
        q = q.filter(requirement_id=requirement_id)
    elif release_id is not None:
        import re

        from app.modules.test_management.service import list_requirements

        req_rows = await list_requirements(release_id, project_id)
        req_ids: list[int] = []
        for row in req_rows:
            key = (row.requirement_key or "").strip()
            m = re.fullmatch(r"REQ-(\d+)", key, flags=re.IGNORECASE)
            if m:
                req_ids.append(int(m.group(1)))
        if not req_ids:
            return []
        q = q.filter(requirement_id__in=list(dict.fromkeys(req_ids)))
    return await q.order_by("-id")


async def create_review(
    *,
    project_id: int,
    requirement_id: int,
    reviewer_ids: list[int],
    username: str,
    ai_assist_summary: Optional[str] = None,
) -> RequirementReview:
    req = await get_ai_requirement_or_404(requirement_id, project_id)
    if req.parse_status != "parsed":
        raise HTTPException(status_code=400, detail="需求尚未解析完成，请等待解析成功后再发起评审")

    active = await RequirementReview.filter(
        requirement_id=requirement_id,
        project_id=project_id,
        is_del=False,
        status__in=["pending", "in_review"],
    ).exists()
    if active:
        raise HTTPException(status_code=400, detail="该需求已有进行中的评审，请先完成或关闭")

    prev_count = await RequirementReview.filter(
        requirement_id=requirement_id, project_id=project_id, is_del=False
    ).count()
    reviewers = [int(x) for x in reviewer_ids if x is not None]
    if not reviewers:
        raise HTTPException(status_code=400, detail="请至少指定一名评审人")

    async with transactions.in_transaction():
        review = await RequirementReview.create(
            project_id=project_id,
            requirement_id=requirement_id,
            status="in_review",
            reviewer_ids=reviewers,
            round=prev_count + 1,
            ai_assist_summary=ai_assist_summary,
            decisions_json=[],
            create_by=username,
            update_by=username,
        )
        req.review_status = "in_review"
        await req.save(update_fields=["review_status", "update_time"])
    return review


async def notify_requirement_review_created(
    review: RequirementReview,
    *,
    actor_user_id: Optional[int] = None,
    requirement_name: Optional[str] = None,
) -> None:
    from app.modules.test_management.premium_gateway import soft_premium_call

    name = requirement_name
    if not name:
        req = await AiRequirement.get_or_none(
            id=review.requirement_id, project_id=review.project_id, is_del=False
        )
        name = (req.name if req else None) or f"需求 #{review.requirement_id}"
    await soft_premium_call(
        "assignment_notify_service",
        "notify_requirement_review_invited",
        project_id=review.project_id,
        review_id=review.id,
        requirement_id=review.requirement_id,
        requirement_name=name,
        reviewer_ids=list(review.reviewer_ids or []),
        actor_id=actor_user_id,
    )


def _assert_reviewer_or_manager(
    review: RequirementReview,
    *,
    user_id: Optional[int],
    username: str,
    is_manager: bool = False,
) -> None:
    if is_manager:
        return
    required = {int(x) for x in (review.reviewer_ids or []) if x is not None}
    if user_id is not None and int(user_id) in required:
        return
    if username and review.create_by and review.create_by == username:
        return
    raise HTTPException(status_code=403, detail="仅本批评审人、发起人或管理员可操作")


async def add_review_item(
    review: RequirementReview,
    *,
    category: str,
    comment: Optional[str],
    suggested_fix: Optional[str],
    section_id: Optional[str],
    severity: str,
    username: str,
    actor_user_id: Optional[int] = None,
    is_manager: bool = False,
) -> RequirementReviewItem:
    if review.status not in ("pending", "in_review", "changes_requested"):
        raise HTTPException(status_code=400, detail="评审已结束，不可再添加意见")
    _assert_reviewer_or_manager(
        review, user_id=actor_user_id, username=username, is_manager=is_manager
    )
    cat = (category or "other").strip()
    if cat not in REQUIREMENT_REVIEW_CATEGORIES:
        raise HTTPException(status_code=400, detail="category 无效")
    return await RequirementReviewItem.create(
        project_id=review.project_id,
        review_id=review.id,
        section_id=section_id,
        category=cat,
        severity=(severity or "medium").strip(),
        comment=comment,
        suggested_fix=suggested_fix,
        create_by=username,
        update_by=username,
    )


async def list_review_items(review: RequirementReview) -> list[dict[str, Any]]:
    rows = await RequirementReviewItem.filter(
        review_id=review.id, project_id=review.project_id, is_del=False
    ).order_by("id")
    return [item_to_dict(r) for r in rows]


async def submit_reviewer_decision(
    review: RequirementReview,
    *,
    reviewer_id: int,
    decision: str,
    comment: Optional[str],
    username: str,
    auth_user_id: Optional[int] = None,
    allow_delegate: bool = False,
) -> RequirementReview:
    """评审人提交个人结论；多人聚合，不覆盖他人。"""
    if review.status in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="评审已结束，不可再提交结论")
    if review.status not in ("pending", "in_review", "changes_requested"):
        raise HTTPException(status_code=400, detail="当前状态不可提交结论")
    decision = (decision or "").strip()
    if decision not in ("approved", "changes_requested", "rejected"):
        raise HTTPException(status_code=400, detail="decision 无效")

    if auth_user_id is not None and not allow_delegate and int(reviewer_id) != int(auth_user_id):
        raise HTTPException(status_code=403, detail="只能以本人身份提交评审结论")

    required = [int(x) for x in (review.reviewer_ids or []) if x is not None]
    if not required:
        raise HTTPException(status_code=400, detail="评审未指定评审人")
    if int(reviewer_id) not in required:
        raise HTTPException(status_code=403, detail="你不在本批评审人名单中")

    decisions = list(getattr(review, "decisions_json", None) or [])
    decisions = [d for d in decisions if int(d.get("reviewer_id", -1)) != int(reviewer_id)]
    decisions.append(
        {
            "reviewer_id": int(reviewer_id),
            "decision": decision,
            "comment": comment or "",
            "at": datetime.now(timezone.utc).isoformat(),
            "operator": username,
        }
    )
    review.decisions_json = decisions
    agg = aggregate_item_decision(decisions, required)
    # 个人提交只推进到 in_review / changes_requested；最终通过须管理员完成定版
    if agg in ("rejected", "changes_requested"):
        review.status = "changes_requested"
    else:
        review.status = "in_review"
    review.update_by = username
    await review.save()
    return review


async def complete_review(
    review: RequirementReview,
    *,
    decision: str,
    summary: Optional[str],
    username: str,
) -> RequirementReview:
    """管理员最终定版：写入需求 review_status，解锁后续设计。"""
    if review.status in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="评审已结束，不可重复完成")
    if review.status not in ("pending", "in_review", "changes_requested"):
        raise HTTPException(status_code=400, detail="当前状态不可完成评审")
    decision = (decision or "").strip()
    if decision not in REQUIREMENT_REVIEW_STATUSES or decision in ("pending", "in_review"):
        raise HTTPException(status_code=400, detail="decision 须为 approved/changes_requested/rejected")

    async with transactions.in_transaction():
        locked = await RequirementReview.select_for_update().get_or_none(
            id=review.id, project_id=review.project_id, is_del=False
        )
        if not locked:
            raise HTTPException(status_code=404, detail="评审不存在")
        if locked.status in ("approved", "rejected"):
            raise HTTPException(status_code=400, detail="评审已结束，不可重复完成")
        if locked.status not in ("pending", "in_review", "changes_requested"):
            raise HTTPException(status_code=400, detail="当前状态不可完成评审")
        locked.status = decision
        locked.summary = summary
        locked.update_by = username
        await locked.save(update_fields=["status", "summary", "update_by", "update_time"])

        req = await get_ai_requirement_or_404(locked.requirement_id, locked.project_id)
        req.review_status = decision
        await req.save(update_fields=["review_status", "update_time"])
        review = locked
    return review


async def reopen_for_revise(requirement_id: int, project_id: int, username: str) -> AiRequirement:
    """驳回或需修改后，重新进入待评审。"""
    req = await get_ai_requirement_or_404(requirement_id, project_id)
    if req.review_status not in ("rejected", "changes_requested"):
        raise HTTPException(status_code=400, detail="仅已驳回或需修改的需求可重新提交评审")
    req.review_status = "pending"
    await req.save(update_fields=["review_status", "update_time"])
    return req
