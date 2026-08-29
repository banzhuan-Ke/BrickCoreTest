"""用例评审服务"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from app.models.ai import AiFunctionalCase
from app.models.test_management import CaseReview, CaseReviewItem, CaseReviewTemplate, TestRelease
from app.modules.test_management.phase2_rules import (
    DEFAULT_CHECKLIST,
    REVIEW_DECISIONS,
    aggregate_item_decision,
    aggregate_review_status,
)
from app.modules.test_management.service import _dt_iso, assert_scope_editable, get_release_or_404


def template_to_dict(row: CaseReviewTemplate) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "name": row.name,
        "description": row.description,
        "checklist": row.checklist or [],
        "is_default": row.is_default,
        "create_by": row.create_by,
        "create_time": _dt_iso(row.create_time),
    }


def review_to_dict(row: CaseReview) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "release_id": row.release_id,
        "template_id": row.template_id,
        "title": row.title,
        "status": row.status,
        "due_at": _dt_iso(row.due_at),
        "reviewer_ids": row.reviewer_ids or [],
        "summary": row.summary,
        "final_decision": row.final_decision,
        "final_decision_by": row.final_decision_by,
        "final_decision_at": _dt_iso(row.final_decision_at),
        "final_comment": row.final_comment,
        "checklist_snapshot": row.checklist_snapshot or [],
        "create_by": row.create_by,
        "create_time": _dt_iso(row.create_time),
        "update_time": _dt_iso(row.update_time),
    }


def review_item_to_dict(row: CaseReviewItem, case: Optional[AiFunctionalCase] = None) -> dict[str, Any]:
    decisions = list(row.decisions_json or [])
    data = {
        "id": row.id,
        "review_id": row.review_id,
        "functional_case_id": row.functional_case_id,
        "decision": row.decision,
        "comment": row.comment,
        "checklist_result": row.checklist_result or {},
        "owner_decision": getattr(row, "owner_decision", None),
        "owner_decision_by": getattr(row, "owner_decision_by", None),
        "owner_decision_at": _dt_iso(getattr(row, "owner_decision_at", None)),
        "owner_comment": getattr(row, "owner_comment", None),
        "decisions_json": decisions,
        "decision_stats": _item_decision_stats(decisions, []),
        "case_title": None,
        "case_module": None,
        "case_precondition": None,
        "case_steps": None,
        "source_requirement_id": None,
        "update_time": _dt_iso(row.update_time),
    }
    if case is not None:
        data["case_title"] = case.title
        data["case_module"] = case.module
        data["case_precondition"] = case.precondition or ""
        data["case_steps"] = case.steps or []
        data["source_requirement_id"] = case.source_requirement_id
    return data


def _item_decision_stats(decisions: list[dict], required_ids: list[int]) -> dict[str, Any]:
    by = {}
    for d in decisions or []:
        rid = d.get("reviewer_id")
        if rid is None:
            continue
        by[int(rid)] = (d.get("decision") or "pending").strip()
    counts = {"approved": 0, "changes_requested": 0, "rejected": 0, "pending": 0}
    required = [int(x) for x in (required_ids or [])]
    if required:
        for rid in required:
            key = by.get(rid, "pending")
            counts[key] = counts.get(key, 0) + 1
        submitted = sum(1 for rid in required if by.get(rid) and by.get(rid) != "pending")
        return {
            **counts,
            "required": len(required),
            "submitted": submitted,
            "pending_reviewer_ids": [rid for rid in required if by.get(rid, "pending") == "pending"],
        }
    for v in by.values():
        counts[v] = counts.get(v, 0) + 1
    return {**counts, "required": len(by), "submitted": len(by), "pending_reviewer_ids": []}


def build_review_stats(review: CaseReview, items: list[dict[str, Any]]) -> dict[str, Any]:
    required = [int(x) for x in (review.reviewer_ids or []) if x is not None]
    item_counts = {
        "total": len(items),
        "approved": 0,
        "changes_requested": 0,
        "rejected": 0,
        "pending": 0,
    }
    for it in items:
        key = (it.get("decision") or "pending").strip()
        if key in item_counts:
            item_counts[key] += 1
        else:
            item_counts["pending"] += 1
    reviewer_progress = []
    for rid in required:
        done = 0
        for it in items:
            decided = {
                int(d.get("reviewer_id"))
                for d in (it.get("decisions_json") or [])
                if d.get("reviewer_id") is not None
                and (d.get("decision") or "pending") != "pending"
            }
            if rid in decided:
                done += 1
        reviewer_progress.append(
            {
                "reviewer_id": rid,
                "done": done,
                "total": len(items),
                "complete": len(items) > 0 and done >= len(items),
            }
        )
    return {
        "items": item_counts,
        "reviewers": reviewer_progress,
        "required_reviewer_ids": required,
        "aggregate_status": review.status,
        "final_decision": review.final_decision,
    }


async def list_templates(project_id: int) -> list[CaseReviewTemplate]:
    return await CaseReviewTemplate.filter(project_id=project_id, is_del=False).order_by("-is_default", "id")


async def create_template(
    *,
    project_id: int,
    name: str,
    checklist: list | None,
    description: Optional[str],
    is_default: bool,
    username: str,
) -> CaseReviewTemplate:
    title = (name or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="模板名称必填")
    items = checklist if checklist is not None else list(DEFAULT_CHECKLIST)
    if is_default:
        await CaseReviewTemplate.filter(project_id=project_id, is_del=False, is_default=True).update(
            is_default=False
        )
    return await CaseReviewTemplate.create(
        project_id=project_id,
        name=title,
        description=description,
        checklist=items,
        is_default=is_default,
        create_by=username,
        update_by=username,
    )


async def ensure_default_template(project_id: int, username: str) -> CaseReviewTemplate:
    rows = await list_templates(project_id)
    for r in rows:
        if r.is_default:
            return r
    if rows:
        return rows[0]
    return await create_template(
        project_id=project_id,
        name="默认评审清单",
        checklist=list(DEFAULT_CHECKLIST),
        description="系统内置",
        is_default=True,
        username=username,
    )


async def update_template(
    template: CaseReviewTemplate,
    payload: dict[str, Any],
    username: str,
) -> CaseReviewTemplate:
    if "name" in payload and payload["name"] is not None:
        name = str(payload["name"]).strip()
        if not name:
            raise HTTPException(status_code=400, detail="模板名称不能为空")
        template.name = name
    if "description" in payload:
        template.description = payload["description"]
    if "checklist" in payload and payload["checklist"] is not None:
        template.checklist = payload["checklist"]
    if payload.get("is_default"):
        await CaseReviewTemplate.filter(
            project_id=template.project_id, is_del=False, is_default=True
        ).update(is_default=False)
        template.is_default = True
    elif payload.get("is_default") is False:
        template.is_default = False
    template.update_by = username
    await template.save()
    return template


async def soft_delete_template(template: CaseReviewTemplate, username: str) -> None:
    template.is_del = True
    template.update_by = username
    await template.save()


async def create_review(
    *,
    project_id: int,
    title: str,
    functional_case_ids: list[int],
    reviewer_ids: list[int],
    username: str,
    release_id: Optional[int] = None,
    template_id: Optional[int] = None,
    due_at: Optional[datetime] = None,
) -> CaseReview:
    name = (title or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="评审标题必填")
    ids = []
    seen = set()
    for raw in functional_case_ids or []:
        cid = int(raw)
        if cid in seen:
            continue
        seen.add(cid)
        ids.append(cid)
    if not ids:
        raise HTTPException(status_code=400, detail="请选择功能用例")

    if release_id:
        release = await get_release_or_404(release_id, project_id)
        assert_scope_editable(release)

    cases = await AiFunctionalCase.filter(id__in=ids, project_id=project_id, is_del=False)
    found = {c.id for c in cases}
    missing = [i for i in ids if i not in found]
    if missing:
        raise HTTPException(status_code=400, detail=f"功能用例不存在: {missing[:10]}")

    template = None
    if template_id:
        template = await CaseReviewTemplate.get_or_none(
            id=template_id, project_id=project_id, is_del=False
        )
        if not template:
            raise HTTPException(status_code=400, detail="评审模板不存在")
    else:
        template = await ensure_default_template(project_id, username)

    reviewers = [int(x) for x in (reviewer_ids or []) if x is not None]
    if not reviewers:
        raise HTTPException(status_code=400, detail="请至少指定一名评审人")
    review = await CaseReview.create(
        project_id=project_id,
        release_id=release_id,
        template_id=template.id if template else None,
        title=name,
        status="pending",
        due_at=due_at,
        reviewer_ids=reviewers,
        checklist_snapshot=list(template.checklist or DEFAULT_CHECKLIST),
        create_by=username,
        update_by=username,
    )
    for cid in ids:
        await CaseReviewItem.create(
            project_id=project_id,
            review_id=review.id,
            functional_case_id=cid,
            create_by=username,
            update_by=username,
        )
    return review


async def notify_review_created(
    review: CaseReview,
    *,
    actor_user_id: Optional[int] = None,
) -> None:
    from app.modules.test_management.premium_gateway import soft_premium_call

    release_status = None
    if review.release_id:
        release = await get_release_or_404(review.release_id, review.project_id)
        release_status = release.status
    await soft_premium_call(
        "assignment_notify_service",
        "notify_review_invited",
        project_id=review.project_id,
        review_id=review.id,
        review_title=review.title,
        reviewer_ids=list(review.reviewer_ids or []),
        actor_id=actor_user_id,
        release_id=review.release_id,
        release_status=release_status,
    )


async def get_review_or_404(review_id: int, project_id: int) -> CaseReview:
    row = await CaseReview.get_or_none(id=review_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="评审不存在")
    return row


async def list_reviews(
    project_id: int,
    *,
    release_id: Optional[int] = None,
    status: Optional[str] = None,
) -> list[CaseReview]:
    q = CaseReview.filter(project_id=project_id, is_del=False)
    if release_id is not None:
        q = q.filter(release_id=release_id)
    if status:
        q = q.filter(status=status)
    return await q.order_by("-id")


async def list_review_items(review: CaseReview) -> list[dict[str, Any]]:
    items = await CaseReviewItem.filter(
        review_id=review.id, project_id=review.project_id, is_del=False
    ).order_by("id")
    case_ids = [i.functional_case_id for i in items]
    cases = {
        c.id: c
        for c in await AiFunctionalCase.filter(
            id__in=case_ids, project_id=review.project_id, is_del=False
        )
    }
    required = [int(x) for x in (review.reviewer_ids or []) if x is not None]
    out = []
    for i in items:
        data = review_item_to_dict(i, cases.get(i.functional_case_id))
        data["decision_stats"] = _item_decision_stats(data.get("decisions_json") or [], required)
        out.append(data)
    return out


async def submit_item_decision(
    *,
    review: CaseReview,
    item_id: int,
    reviewer_id: int,
    decision: str,
    comment: Optional[str],
    checklist_result: Optional[dict],
    username: str,
    auth_user_id: Optional[int] = None,
    allow_delegate: bool = False,
    attachments: Optional[list] = None,
) -> CaseReviewItem:
    if review.final_decision:
        raise HTTPException(status_code=400, detail="版本负责人已最终裁定，不可再提交")
    item = await CaseReviewItem.get_or_none(
        id=item_id, review_id=review.id, project_id=review.project_id, is_del=False
    )
    if not item:
        raise HTTPException(status_code=404, detail="评审项不存在")
    if getattr(item, "owner_decision", None):
        raise HTTPException(status_code=400, detail="该用例已由负责人定版，不可再提交")
    if review.status in ("approved", "cancelled"):
        raise HTTPException(status_code=400, detail="评审已结束，不可再提交")
    decision = (decision or "").strip()
    if decision not in REVIEW_DECISIONS or decision == "pending":
        raise HTTPException(status_code=400, detail="decision 无效")

    if auth_user_id is not None and not allow_delegate and int(reviewer_id) != int(auth_user_id):
        raise HTTPException(status_code=403, detail="只能以本人身份提交评审结论")

    required = [int(x) for x in (review.reviewer_ids or [])]
    if not required:
        raise HTTPException(status_code=400, detail="评审未指定评审人，不可提交结论")
    if int(reviewer_id) not in required:
        raise HTTPException(status_code=403, detail="你不在本批评审人名单中")

    checklist = list(review.checklist_snapshot or DEFAULT_CHECKLIST)
    if checklist:
        cr = checklist_result or {}
        missing = [
            str(c.get("label") or c.get("key") or "")
            for c in checklist
            if c.get("required") and not cr.get(c.get("key"))
        ]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"必填检查项未完成：{', '.join(x for x in missing if x)}",
            )

    att = []
    for raw in attachments or []:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()
        if not key:
            continue
        att.append(
            {
                "uid": raw.get("uid"),
                "name": raw.get("name") or "file",
                "key": key,
                "bucket": raw.get("bucket"),
                "mime": raw.get("mime"),
                "size": raw.get("size"),
                "kind": raw.get("kind") or "file",
            }
        )

    decisions = list(item.decisions_json or [])
    decisions = [d for d in decisions if int(d.get("reviewer_id", -1)) != int(reviewer_id)]
    decisions.append(
        {
            "reviewer_id": int(reviewer_id),
            "decision": decision,
            "comment": comment or "",
            "attachments": att,
            "at": datetime.now(timezone.utc).isoformat(),
            "operator": username,
        }
    )
    item.decisions_json = decisions
    item.decision = aggregate_item_decision(decisions, required)
    # 摘要意见：拼接各人一句话，避免只显示最后一人
    summaries = []
    for d in decisions:
        c = (d.get("comment") or "").strip()
        if c:
            summaries.append(f"#{d.get('reviewer_id')}: {c}")
    item.comment = "\n".join(summaries[-5:]) if summaries else (comment or None)
    if checklist_result is not None:
        item.checklist_result = checklist_result
    item.update_by = username
    await item.save()

    all_items = await CaseReviewItem.filter(
        review_id=review.id, project_id=review.project_id, is_del=False
    )
    if not review.final_decision:
        review.status = aggregate_review_status([i.decision for i in all_items])
    review.update_by = username
    await review.save()

    if review.status in ("pending", "in_review"):
        pending_ids = _pending_reviewer_ids(review, all_items)
        # 不提醒刚提交的人
        pending_ids = [x for x in pending_ids if int(x) != int(reviewer_id)]
        if pending_ids:
            try:
                from app.modules.test_management.premium_gateway import soft_premium_call

                release_status = None
                if review.release_id:
                    rel = await get_release_or_404(review.release_id, review.project_id)
                    release_status = rel.status
                await soft_premium_call(
                    "assignment_notify_service",
                    "notify_review_pending_reminders",
                    project_id=review.project_id,
                    review_id=review.id,
                    review_title=review.title,
                    pending_reviewer_ids=pending_ids,
                    actor_id=auth_user_id if auth_user_id is not None else reviewer_id,
                    release_id=review.release_id,
                    release_status=release_status,
                )
            except Exception:
                pass
    return item


async def finalize_review(
    review: CaseReview,
    *,
    decision: str,
    comment: Optional[str],
    username: str,
    actor_user_id: Optional[int],
    is_manager: bool = False,
) -> CaseReview:
    """版本负责人（或具备 manage 权限者）对用例评审批次做最终定版。"""
    decision = (decision or "").strip()
    if decision not in ("approved", "changes_requested", "rejected"):
        raise HTTPException(status_code=400, detail="decision 无效")
    if review.status == "cancelled":
        raise HTTPException(status_code=400, detail="已取消的评审不可裁定")
    if review.final_decision:
        raise HTTPException(status_code=400, detail="已最终裁定，不可重复操作")

    release_owner_id = None
    if review.release_id:
        release = await get_release_or_404(review.release_id, review.project_id)
        release_owner_id = release.owner_id
    allowed = is_manager
    if actor_user_id is not None and release_owner_id is not None:
        if int(actor_user_id) == int(release_owner_id):
            allowed = True
    if not allowed:
        raise HTTPException(status_code=403, detail="仅版本负责人或评审管理员可最终定版")

    review.final_decision = decision
    review.final_decision_by = actor_user_id
    review.final_decision_at = datetime.now(timezone.utc)
    review.final_comment = comment
    # 批次状态：拒绝归入需修改，与聚合规则一致
    review.status = "approved" if decision == "approved" else "changes_requested"
    review.summary = comment or review.summary
    review.update_by = username
    await review.save()
    return review


async def finalize_review_item(
    review: CaseReview,
    item: CaseReviewItem,
    *,
    decision: str,
    comment: Optional[str],
    username: str,
    actor_user_id: Optional[int],
    is_manager: bool = False,
) -> CaseReviewItem:
    """版本负责人对单条用例做最终裁定（非整批评审）。"""
    decision = (decision or "").strip()
    if decision not in ("approved", "changes_requested", "rejected"):
        raise HTTPException(status_code=400, detail="decision 无效")
    if review.status == "cancelled":
        raise HTTPException(status_code=400, detail="已取消的评审不可裁定")
    if getattr(item, "owner_decision", None):
        raise HTTPException(status_code=400, detail="该用例已裁定，不可重复操作")

    release_owner_id = None
    if review.release_id:
        release = await get_release_or_404(review.release_id, review.project_id)
        release_owner_id = release.owner_id
    allowed = is_manager
    if actor_user_id is not None and release_owner_id is not None:
        if int(actor_user_id) == int(release_owner_id):
            allowed = True
    if not allowed:
        raise HTTPException(status_code=403, detail="仅版本负责人或评审管理员可对该用例定版")

    item.owner_decision = decision
    item.owner_decision_by = actor_user_id
    item.owner_decision_at = datetime.now(timezone.utc)
    item.owner_comment = comment
    item.decision = decision
    item.update_by = username
    await item.save()

    all_items = await CaseReviewItem.filter(
        review_id=review.id, project_id=review.project_id, is_del=False
    )
    decisions = [it.decision for it in all_items]
    review.status = aggregate_review_status(decisions)
    review.update_by = username
    await review.save()
    return item


def _pending_reviewer_ids(review: CaseReview, items: list[CaseReviewItem]) -> list[int]:
    """仍有至少一项未提交结论的评审人。"""
    required = [int(x) for x in (review.reviewer_ids or []) if x is not None]
    if not required or not items:
        return []
    pending: list[int] = []
    for rid in required:
        for it in items:
            decided = {
                int(d.get("reviewer_id"))
                for d in (it.decisions_json or [])
                if d.get("reviewer_id") is not None
            }
            if rid not in decided:
                pending.append(rid)
                break
    return pending


async def cancel_review(
    review: CaseReview,
    username: str,
    *,
    user_id: Optional[int] = None,
) -> CaseReview:
    if review.status == "approved":
        raise HTTPException(status_code=400, detail="已通过的评审不可取消")
    if review.status not in ("pending", "in_review"):
        raise HTTPException(status_code=400, detail="当前状态不可取消")
    reviewer_ids = {int(x) for x in (review.reviewer_ids or []) if x is not None}
    is_creator = bool(username and review.create_by and review.create_by == username)
    is_reviewer = user_id is not None and int(user_id) in reviewer_ids
    if not is_creator and not is_reviewer:
        raise HTTPException(status_code=403, detail="仅评审发起人或指定评审人可取消评审")
    review.status = "cancelled"
    review.update_by = username
    await review.save()
    return review


async def functional_case_review_status_map(
    project_id: int, functional_case_ids: list[int]
) -> dict[int, str]:
    """取每个用例最近一次未取消评审的聚合结论。"""
    if not functional_case_ids:
        return {}
    active_review_ids = await CaseReview.filter(
        project_id=project_id, is_del=False
    ).exclude(status="cancelled").values_list("id", flat=True)
    if not active_review_ids:
        return {}
    items = await CaseReviewItem.filter(
        project_id=project_id,
        functional_case_id__in=functional_case_ids,
        review_id__in=list(active_review_ids),
        is_del=False,
    ).order_by("-review_id", "-id")
    result: dict[int, str] = {}
    for item in items:
        if item.functional_case_id in result:
            continue
        result[item.functional_case_id] = item.decision
    return result
