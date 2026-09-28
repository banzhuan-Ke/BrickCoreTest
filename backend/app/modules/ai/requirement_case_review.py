"""需求工作区用例审核闭环（AI-REQ MVP）。

状态机：needs_review → approved | rejected
兼容旧 draft：队列与待审口径视同 needs_review；入库仅允许 approved。
"""
from __future__ import annotations

from typing import Any

from app.core.platform.datetime_utils import now_app
from app.models.ai import AiRequirement, AiRequirementCase

STATUS_DRAFT = "draft"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_CONFIRMED = "confirmed"  # 历史值，视同已通过
STATUS_EXPORTED = "exported"  # 历史值，视同已通过

PENDING_STATUSES = frozenset({STATUS_DRAFT, STATUS_NEEDS_REVIEW})
APPROVED_STATUSES = frozenset({STATUS_APPROVED, STATUS_CONFIRMED, STATUS_EXPORTED})
REVIEWABLE_DECISIONS = frozenset({STATUS_APPROVED, STATUS_REJECTED})

# 驳回原因标签（AI-REQ Phase 1 §5.3）
REVIEW_REASON_TAGS = (
    "规则理解错误",
    "遗漏场景",
    "重复",
    "步骤不可执行",
    "预期不可验证",
    "优先级不合理",
    "需求本身不明确",
    "其他",
)

CASE_STATUS_LABELS = {
    STATUS_DRAFT: "待审核(旧草稿)",
    STATUS_NEEDS_REVIEW: "待审核",
    STATUS_APPROVED: "已通过",
    STATUS_REJECTED: "已驳回",
    STATUS_CONFIRMED: "已确认",
    STATUS_EXPORTED: "已导出",
}


def is_pending_review(status: str | None) -> bool:
    return (status or "").strip().lower() in PENDING_STATUSES


def is_approved_for_library(status: str | None) -> bool:
    return (status or "").strip().lower() in APPROVED_STATUSES


def status_label(status: str | None) -> str:
    s = (status or "").strip().lower()
    return CASE_STATUS_LABELS.get(s, s or "未知")


def _review_meta(case: AiRequirementCase) -> dict[str, Any]:
    extra = case.extra if isinstance(case.extra, dict) else {}
    return {
        "review_note": (getattr(case, "review_note", None) or extra.get("review_note") or "")[:500],
        "reviewed_by": getattr(case, "reviewed_by", None) or extra.get("reviewed_by") or "",
        "reviewed_at": (
            case.reviewed_at.isoformat()
            if getattr(case, "reviewed_at", None)
            else (extra.get("reviewed_at") or None)
        ),
    }


def case_review_dict(case: AiRequirementCase, *, requirement_name: str = "") -> dict[str, Any]:
    from app.modules.ai.requirement_case_quality import (
        first_issue_message,
        quality_summary_from_extra,
    )

    meta = _review_meta(case)
    extra = case.extra if isinstance(case.extra, dict) else {}
    quality = quality_summary_from_extra(extra)
    return {
        "id": case.id,
        "requirement_id": case.requirement_id,
        "requirement_name": requirement_name or "",
        "project_id": case.project_id,
        "title": case.title,
        "module": case.module,
        "priority": case.priority,
        "status": case.status,
        "status_label": status_label(case.status),
        "source_ref": case.source_ref,
        "create_by": case.create_by,
        "create_time": case.create_time.strftime("%Y-%m-%d %H:%M:%S") if case.create_time else "",
        "quality_checks": quality,
        "quality_summary": first_issue_message(quality) if quality else "",
        "quality_severity": (quality or {}).get("severity") if quality else None,
        "review_reason_tag": extra.get("review_reason_tag") or "",
        **meta,
    }


async def list_review_queue(
    *,
    project_id: int,
    status: str | None = None,
    requirement_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    qs = AiRequirementCase.filter(project_id=int(project_id), is_del=False)
    if requirement_id is not None:
        qs = qs.filter(requirement_id=int(requirement_id))
    st = (status or "").strip().lower()
    if st == "pending" or st == STATUS_NEEDS_REVIEW:
        qs = qs.filter(status__in=list(PENDING_STATUSES))
    elif st == STATUS_APPROVED:
        qs = qs.filter(status__in=list(APPROVED_STATUSES))
    elif st == STATUS_REJECTED:
        qs = qs.filter(status=STATUS_REJECTED)
    elif st:
        qs = qs.filter(status=st)
    else:
        qs = qs.filter(status__in=list(PENDING_STATUSES))

    total = await qs.count()
    rows = await qs.order_by("-update_time", "-id").offset(max(0, offset)).limit(min(max(limit, 1), 200))
    req_ids = {r.requirement_id for r in rows}
    name_map: dict[int, str] = {}
    if req_ids:
        for req in await AiRequirement.filter(id__in=list(req_ids), is_del=False).only("id", "name"):
            name_map[int(req.id)] = req.name or ""
    items = [
        case_review_dict(r, requirement_name=name_map.get(int(r.requirement_id), ""))
        for r in rows
    ]
    return {"total": total, "items": items, "pending_statuses": sorted(PENDING_STATUSES)}


async def apply_case_review(
    *,
    project_id: int,
    case_ids: list[int],
    decision: str,
    note: str = "",
    username: str = "",
    requirement_id: int | None = None,
    reason_tag: str = "",
) -> dict[str, Any]:
    decision_s = (decision or "").strip().lower()
    if decision_s not in REVIEWABLE_DECISIONS:
        raise ValueError("decision 仅支持 approved / rejected")
    ids = [int(x) for x in case_ids if x]
    if not ids:
        raise ValueError("请选择用例")
    if len(ids) > 200:
        raise ValueError("单次最多审核 200 条")

    tag = (reason_tag or "").strip()
    if decision_s == STATUS_REJECTED and tag and tag not in REVIEW_REASON_TAGS:
        raise ValueError(f"驳回原因标签无效，可选：{'、'.join(REVIEW_REASON_TAGS)}")
    if decision_s == STATUS_REJECTED and not tag and not (note or "").strip():
        raise ValueError("驳回时请选择原因标签或填写备注")

    qs = AiRequirementCase.filter(project_id=int(project_id), id__in=ids, is_del=False)
    if requirement_id is not None:
        qs = qs.filter(requirement_id=int(requirement_id))
    rows = await qs.all()
    if not rows:
        raise ValueError("未找到可审核的用例")

    note_s = (note or "").strip()[:500] or None
    now = now_app()
    updated = 0
    skipped = 0
    for case in rows:
        # 已终态同决策则跳过；已通过再驳回 / 已驳回再通过允许改判
        if case.status == decision_s:
            skipped += 1
            continue
        case.status = decision_s
        case.review_note = note_s
        case.reviewed_by = (username or "")[:50] or None
        case.reviewed_at = now
        extra = dict(case.extra) if isinstance(case.extra, dict) else {}
        extra["review_decision"] = decision_s
        if note_s:
            extra["review_note"] = note_s
        if username:
            extra["reviewed_by"] = username
        extra["reviewed_at"] = now.isoformat()
        if decision_s == STATUS_REJECTED and tag:
            extra["review_reason_tag"] = tag
        elif decision_s == STATUS_APPROVED:
            extra.pop("review_reason_tag", None)
        case.extra = extra
        await case.save(
            update_fields=["status", "review_note", "reviewed_by", "reviewed_at", "extra", "update_time"]
        )
        updated += 1

    return {
        "updated": updated,
        "skipped": skipped,
        "not_found": len(ids) - len(rows),
        "decision": decision_s,
        "case_ids": [r.id for r in rows],
        "reason_tag": tag or None,
    }


def assert_cases_approved_for_library(cases: list[AiRequirementCase]) -> None:
    bad = [c for c in cases if not is_approved_for_library(c.status)]
    if not bad:
        return
    titles = "、".join((c.title or f"#{c.id}")[:40] for c in bad[:5])
    more = f" 等 {len(bad)} 条" if len(bad) > 5 else ""
    raise ValueError(
        f"仅「已通过」的用例可入库；以下仍待审核或已驳回：{titles}{more}。"
        "请先在审核队列通过后再入库。"
    )
