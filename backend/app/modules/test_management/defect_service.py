"""缺陷台账服务"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException
from tortoise import transactions
from tortoise.exceptions import IntegrityError
from tortoise.functions import Count

from app.core.platform.config import TEST_DEFECT_ATTACHMENTS_MAX
from app.models.test_management import (
    TestDefect,
    TestDefectActivity,
    TestDefectComment,
    TestDefectLink,
    TestPlan,
    TestPlanRun,
    TestPlanRunItem,
    TestRelease,
)
from app.models.ai import AiFunctionalCase, AiRequirement
from app.modules.test_management import result_normalizer as norm
from app.modules.test_management.phase3_rules import (
    format_defect_key,
    parse_defect_key_seq,
    validate_external_url,
)
from app.modules.test_management.service import (
    _dt_iso,
    assert_defect_release_editable,
    apply_soft_delete,
    get_release_or_404,
)

DEFECT_KEY_RETRY_LIMIT = 12
DEFECT_LINK_TYPES = frozenset({"run_item", "functional_case", "requirement", "asset", "external"})
DEFECT_STATUSES = frozenset({
    "open",
    "in_progress",
    "resolved",
    "verified",
    "closed",
    "rejected",
})
DEFECT_SEVERITIES = frozenset({"blocker", "critical", "major", "minor"})
DEFECT_PRIORITIES = frozenset({"p0", "p1", "p2", "p3"})
DEFECT_RESOLUTION_TYPES = frozenset({
    "fixed",
    "not_repro",
    "duplicate",
    "by_design",
    "external",
    "will_not_fix",
    "postponed",
    "invalid",
})

# 合法状态迁移（含 reopen / reject）
DEFECT_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset({"in_progress", "rejected", "closed"}),
    "in_progress": frozenset({"resolved", "rejected", "open", "closed"}),
    "resolved": frozenset({"verified", "in_progress", "open"}),
    "verified": frozenset({"closed", "in_progress"}),
    "closed": frozenset({"open"}),
    "rejected": frozenset({"open"}),
}


def assert_status_transition(from_status: str, to_status: str) -> None:
    if from_status == to_status:
        return
    allowed = DEFECT_STATUS_TRANSITIONS.get(from_status) or frozenset()
    if to_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"不允许从 {from_status} 迁移到 {to_status}",
        )


async def _record_activity(
    defect: TestDefect,
    *,
    action: str,
    actor: str,
    from_value: Optional[str] = None,
    to_value: Optional[str] = None,
    note: Optional[str] = None,
) -> TestDefectActivity:
    return await TestDefectActivity.create(
        project_id=defect.project_id,
        defect_id=defect.id,
        action=action,
        from_value=(from_value[:255] if from_value else None),
        to_value=(to_value[:255] if to_value else None),
        note=note,
        actor=actor or "system",
    )


def comment_to_dict(row: TestDefectComment) -> dict[str, Any]:
    return {
        "id": row.id,
        "defect_id": row.defect_id,
        "body": row.body,
        "create_by": row.create_by,
        "create_time": _dt_iso(row.create_time),
    }


def activity_to_dict(row: TestDefectActivity) -> dict[str, Any]:
    return {
        "id": row.id,
        "defect_id": row.defect_id,
        "action": row.action,
        "from_value": row.from_value,
        "to_value": row.to_value,
        "note": row.note,
        "actor": row.actor,
        "create_time": _dt_iso(row.create_time),
    }


def normalize_attachments(raw: Any) -> list[dict[str, Any]]:
    """校验并归一化缺陷附件列表（MeterSphere 风格：图片 + 普通附件）。"""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="attachments 须为数组")
    if len(raw) > TEST_DEFECT_ATTACHMENTS_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"附件最多 {TEST_DEFECT_ATTACHMENTS_MAX} 个",
        )
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="附件项格式无效")
        uid = str(item.get("uid") or "").strip()
        name = str(item.get("name") or "").strip()
        key = str(item.get("key") or "").strip()
        bucket = str(item.get("bucket") or "").strip()
        if not uid or not name or not key or not bucket:
            raise HTTPException(status_code=400, detail="附件缺少 uid/name/key/bucket")
        if uid in seen:
            continue
        seen.add(uid)
        mime = str(item.get("mime") or "application/octet-stream").strip()
        kind = str(item.get("kind") or "").strip().lower()
        if kind not in ("image", "file"):
            kind = "image" if mime.startswith("image/") else "file"
        try:
            size = int(item.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        out.append(
            {
                "uid": uid,
                "name": name[:200],
                "key": key[:500],
                "bucket": bucket[:100],
                "mime": mime[:120],
                "size": max(0, size),
                "kind": kind,
            }
        )
    return out


def defect_to_dict(row: TestDefect, *, links: Optional[list[dict]] = None) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "release_id": row.release_id,
        "defect_key": row.defect_key,
        "title": row.title,
        "description": row.description,
        "severity": row.severity,
        "priority": row.priority,
        "status": row.status,
        "found_in": row.found_in,
        "fixed_in": row.fixed_in,
        "assignee_id": row.assignee_id,
        "reporter_id": row.reporter_id,
        "handler_id": getattr(row, "handler_id", None),
        "attributor_id": getattr(row, "attributor_id", None),
        "external_system": row.external_system,
        "external_key": row.external_key,
        "external_url": row.external_url,
        "resolution_type": getattr(row, "resolution_type", None),
        "resolution_detail": getattr(row, "resolution_detail", None),
        "root_cause": getattr(row, "root_cause", None),
        "attachments": list(row.attachments or []),
        "create_by": row.create_by,
        "create_time": _dt_iso(row.create_time),
        "update_time": _dt_iso(row.update_time),
        "links": links if links is not None else [],
    }


def link_to_dict(row: TestDefectLink, *, enrich: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    data = {
        "id": row.id,
        "link_type": row.link_type,
        "run_item_id": row.run_item_id,
        "functional_case_id": row.functional_case_id,
        "requirement_id": getattr(row, "requirement_id", None),
        "asset_type": row.asset_type,
        "asset_id": row.asset_id,
        "external_url": row.external_url,
        "note": row.note,
        "create_time": _dt_iso(row.create_time),
    }
    if enrich:
        data.update(enrich)
    return data


async def _enrich_links(links: list[TestDefectLink], project_id: int) -> list[dict[str, Any]]:
    if not links:
        return []
    run_item_ids = [lk.run_item_id for lk in links if lk.run_item_id]
    case_ids = [lk.functional_case_id for lk in links if lk.functional_case_id]
    req_ids = [getattr(lk, "requirement_id", None) for lk in links if getattr(lk, "requirement_id", None)]
    items_by_id: dict[int, TestPlanRunItem] = {}
    cases_by_id: dict[int, AiFunctionalCase] = {}
    reqs_by_id: dict[int, AiRequirement] = {}
    runs_by_id: dict[int, TestPlanRun] = {}
    plans_by_id: dict[int, TestPlan] = {}

    if run_item_ids:
        items = await TestPlanRunItem.filter(
            id__in=run_item_ids, project_id=project_id, is_del=False
        )
        items_by_id = {i.id: i for i in items}
        run_ids = list({i.run_id for i in items if i.run_id})
        if run_ids:
            runs = await TestPlanRun.filter(id__in=run_ids, project_id=project_id, is_del=False)
            runs_by_id = {r.id: r for r in runs}
            plan_ids = list({r.plan_id for r in runs if r.plan_id})
            if plan_ids:
                plans = await TestPlan.filter(id__in=plan_ids, project_id=project_id, is_del=False)
                plans_by_id = {p.id: p for p in plans}

    if case_ids:
        cases = await AiFunctionalCase.filter(
            id__in=case_ids, project_id=project_id, is_del=False
        )
        cases_by_id = {c.id: c for c in cases}

    if req_ids:
        reqs = await AiRequirement.filter(id__in=req_ids, project_id=project_id, is_del=False)
        reqs_by_id = {r.id: r for r in reqs}

    out: list[dict[str, Any]] = []
    for lk in links:
        enrich: dict[str, Any] = {}
        if lk.run_item_id and lk.run_item_id in items_by_id:
            item = items_by_id[lk.run_item_id]
            run = runs_by_id.get(item.run_id)
            plan = plans_by_id.get(run.plan_id) if run else None
            enrich.update(
                {
                    "run_item_title": item.title,
                    "run_item_result": item.result_status,
                    "run_id": item.run_id,
                    "plan_id": run.plan_id if run else None,
                    "plan_name": plan.name if plan else None,
                    "release_id": run.release_id if run else None,
                }
            )
        if lk.functional_case_id and lk.functional_case_id in cases_by_id:
            case = cases_by_id[lk.functional_case_id]
            enrich["functional_case_title"] = case.title
            enrich["functional_case_module"] = case.module
        rid = getattr(lk, "requirement_id", None)
        if rid and rid in reqs_by_id:
            req = reqs_by_id[rid]
            enrich["requirement_title"] = req.name
        out.append(link_to_dict(lk, enrich=enrich))
    return out


async def _related_plans_from_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, Any]] = set()
    rows: list[dict[str, Any]] = []
    for lk in links:
        plan_id = lk.get("plan_id")
        run_id = lk.get("run_id")
        if not plan_id and not run_id:
            continue
        key = (plan_id, run_id)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "plan_id": plan_id,
                "plan_name": lk.get("plan_name"),
                "run_id": run_id,
                "run_item_id": lk.get("run_item_id"),
                "run_item_title": lk.get("run_item_title"),
                "release_id": lk.get("release_id"),
            }
        )
    return rows


async def get_defect_detail(defect: TestDefect) -> dict[str, Any]:
    links_raw = await TestDefectLink.filter(
        defect_id=defect.id, project_id=defect.project_id, is_del=False
    ).order_by("id")
    links = await _enrich_links(list(links_raw), defect.project_id)
    comments = await TestDefectComment.filter(
        defect_id=defect.id, project_id=defect.project_id, is_del=False
    ).order_by("id")
    activities = await TestDefectActivity.filter(
        defect_id=defect.id, project_id=defect.project_id
    ).order_by("-id")
    data = defect_to_dict(defect, links=links)
    data["comments"] = [comment_to_dict(c) for c in comments]
    data["activities"] = [activity_to_dict(a) for a in activities]
    data["related_plans"] = await _related_plans_from_links(links)
    return data


async def _max_defect_seq(project_id: int) -> int:
    """取项目内缺陷序号上界。按 id 近序抽样解析，避免全表 keys 进内存。"""
    keys = await TestDefect.filter(project_id=project_id).order_by("-id").limit(500).values_list(
        "defect_key", flat=True
    )
    max_seq = 0
    for key in keys:
        seq = parse_defect_key_seq(key or "")
        if seq is not None:
            max_seq = max(max_seq, seq)
    return max_seq


async def _next_defect_key(project_id: int) -> str:
    return format_defect_key(await _max_defect_seq(project_id) + 1)

async def get_defect_or_404(defect_id: int, project_id: int) -> TestDefect:
    row = await TestDefect.get_or_none(id=defect_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="缺陷不存在")
    return row


async def list_defects(
    project_id: int,
    *,
    release_id: Optional[int] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    severity: Optional[str] = None,
    assignee_id: Optional[int] = None,
    functional_case_id: Optional[int] = None,
    with_links: bool = True,
) -> list[dict[str, Any]] | list[TestDefect]:
    q = TestDefect.filter(project_id=project_id, is_del=False)
    if release_id is not None:
        q = q.filter(release_id=release_id)
    if status:
        q = q.filter(status=status.strip())
    if severity:
        q = q.filter(severity=severity.strip())
    if assignee_id is not None:
        q = q.filter(assignee_id=assignee_id)
    if keyword:
        kw = keyword.strip()
        q = q.filter(title__icontains=kw)
    if functional_case_id is not None:
        linked_ids = await TestDefectLink.filter(
            project_id=project_id,
            is_del=False,
            functional_case_id=int(functional_case_id),
        ).values_list("defect_id", flat=True)
        if not linked_ids:
            return [] if with_links else []
        q = q.filter(id__in=list(linked_ids))
    rows = await q.order_by("-id")
    if not with_links:
        return rows
    if not rows:
        return []
    defect_ids = [r.id for r in rows]
    links = await TestDefectLink.filter(
        defect_id__in=defect_ids, project_id=project_id, is_del=False
    ).order_by("id")
    links_by_defect: dict[int, list[dict]] = {}
    for lk in links:
        links_by_defect.setdefault(lk.defect_id, []).append(link_to_dict(lk))
    return [
        defect_to_dict(r, links=links_by_defect.get(r.id, []))
        for r in rows
    ]


async def count_open_defects_for_release(release_id: int, project_id: int) -> dict[str, int]:
    rows = await TestDefect.filter(
        release_id=release_id,
        project_id=project_id,
        is_del=False,
        status__in=list(norm.OPEN_DEFECT_STATUSES),
    )
    by_severity: dict[str, int] = {}
    for r in rows:
        by_severity[r.severity] = by_severity.get(r.severity, 0) + 1
    return {"open_count": len(rows), "by_severity": by_severity}


async def create_defect(
    *,
    project_id: int,
    title: str,
    username: str,
    release_id: Optional[int] = None,
    description: Optional[str] = None,
    severity: str = "major",
    priority: str = "p2",
    status: str = "open",
    found_in: Optional[str] = None,
    assignee_id: Optional[int] = None,
    reporter_id: Optional[int] = None,
    external_system: Optional[str] = None,
    external_key: Optional[str] = None,
    external_url: Optional[str] = None,
    attachments: Optional[list] = None,
    links: Optional[list[dict]] = None,
    actor_user_id: Optional[int] = None,
) -> TestDefect:
    t = (title or "").strip()
    if not t:
        raise HTTPException(status_code=400, detail="标题必填")
    sev = (severity or "major").strip()
    pri = (priority or "p2").strip()
    st = (status or "open").strip()
    if sev not in DEFECT_SEVERITIES:
        raise HTTPException(status_code=400, detail="severity 无效")
    if pri not in DEFECT_PRIORITIES:
        raise HTTPException(status_code=400, detail="priority 无效")
    if st not in DEFECT_STATUSES:
        raise HTTPException(status_code=400, detail="status 无效")
    if release_id is not None:
        release = await get_release_or_404(release_id, project_id)
        assert_defect_release_editable(release)
    external_url = validate_external_url(external_url)
    normalized_attachments = normalize_attachments(attachments)

    last_exc: Exception | None = None
    row: TestDefect | None = None
    for _attempt in range(DEFECT_KEY_RETRY_LIMIT):
        # 每次重试重新查 max，避免 +attempt 与其它并发交错产生空洞冲突
        defect_key = format_defect_key(await _max_defect_seq(project_id) + 1)
        try:
            async with transactions.in_transaction():
                row = await TestDefect.create(
                    project_id=project_id,
                    release_id=release_id,
                    defect_key=defect_key,
                    title=t,
                    description=description,
                    severity=sev,
                    priority=pri,
                    status=st,
                    found_in=found_in,
                    assignee_id=assignee_id,
                    reporter_id=reporter_id,
                    external_system=external_system,
                    external_key=external_key,
                    external_url=external_url,
                    attachments=normalized_attachments,
                    create_by=username,
                    update_by=username,
                )
                if links:
                    for lk in links:
                        await _create_link(row, lk)
            break
        except IntegrityError as exc:
            last_exc = exc
            row = None
            continue
    if row is None:
        raise HTTPException(
            status_code=409,
            detail="缺陷编号生成冲突，请重试",
        ) from last_exc

    await _record_activity(row, action="created", actor=username, to_value=row.status)
    if assignee_id:
        from app.modules.test_management.premium_gateway import soft_premium_call

        release_status = None
        if release_id is not None:
            release = await get_release_or_404(release_id, project_id)
            release_status = release.status
        await soft_premium_call(
            "assignment_notify_service",
            "notify_defect_assigned",
            project_id=project_id,
            defect_id=row.id,
            defect_key=row.defect_key,
            defect_title=row.title,
            assignee_id=assignee_id,
            actor_id=actor_user_id,
            release_id=release_id,
            release_status=release_status,
        )
    return row


async def _create_link(defect: TestDefect, payload: dict) -> TestDefectLink:
    lt = (payload.get("link_type") or "run_item").strip()
    if lt not in DEFECT_LINK_TYPES:
        raise HTTPException(status_code=400, detail="link_type 无效")
    ext_url = validate_external_url(payload.get("external_url"))
    pid = defect.project_id

    run_item_id = payload.get("run_item_id")
    functional_case_id = payload.get("functional_case_id")
    requirement_id = payload.get("requirement_id")
    asset_type = payload.get("asset_type")
    asset_id = payload.get("asset_id")

    if lt == "run_item":
        if run_item_id is None:
            raise HTTPException(status_code=400, detail="run_item 类型须提供 run_item_id")
    elif lt == "functional_case":
        if functional_case_id is None:
            raise HTTPException(status_code=400, detail="functional_case 类型须提供 functional_case_id")
    elif lt == "requirement":
        if requirement_id is None:
            raise HTTPException(status_code=400, detail="requirement 类型须提供 requirement_id")
    elif lt == "asset":
        if not asset_type or asset_id is None:
            raise HTTPException(status_code=400, detail="asset 类型须提供 asset_type 与 asset_id")
    elif lt == "external":
        if not ext_url:
            raise HTTPException(status_code=400, detail="external 类型须提供有效 external_url")

    if run_item_id is not None:
        row = await TestPlanRunItem.get_or_none(
            id=int(run_item_id), project_id=pid, is_del=False
        )
        if not row:
            raise HTTPException(status_code=400, detail="运行项不存在或不属于本项目")

    if functional_case_id is not None:
        row = await AiFunctionalCase.get_or_none(
            id=int(functional_case_id), project_id=pid, is_del=False
        )
        if not row:
            raise HTTPException(status_code=400, detail="功能用例不存在或不属于本项目")

    if requirement_id is not None:
        row = await AiRequirement.get_or_none(
            id=int(requirement_id), project_id=pid, is_del=False
        )
        if not row:
            raise HTTPException(status_code=400, detail="需求不存在或不属于本项目")

    if asset_id is not None:
        if not asset_type:
            raise HTTPException(status_code=400, detail="关联资产需指定 asset_type")
        from app.modules.test_management.service import _assert_asset

        await _assert_asset(pid, str(asset_type), int(asset_id))

    return await TestDefectLink.create(
        project_id=pid,
        defect_id=defect.id,
        link_type=lt,
        run_item_id=run_item_id,
        functional_case_id=functional_case_id,
        requirement_id=requirement_id,
        asset_type=asset_type,
        asset_id=asset_id,
        external_url=ext_url,
        note=payload.get("note"),
    )


async def update_defect(
    defect: TestDefect,
    payload: dict[str, Any],
    username: str,
    actor_user_id: Optional[int] = None,
) -> TestDefect:
    if defect.release_id:
        release = await TestRelease.get_or_none(
            id=defect.release_id, project_id=defect.project_id, is_del=False
        )
        if release:
            assert_defect_release_editable(release)
    pending_activities: list[tuple[str, Optional[str], Optional[str]]] = []
    if "title" in payload and payload["title"] is not None:
        t = str(payload["title"]).strip()
        if not t:
            raise HTTPException(status_code=400, detail="标题不能为空")
        defect.title = t
    if "release_id" in payload:
        rid = payload["release_id"]
        if rid is not None:
            release = await get_release_or_404(int(rid), defect.project_id)
            assert_defect_release_editable(release)
        defect.release_id = rid
    for field in (
        "description",
        "found_in",
        "fixed_in",
        "reporter_id",
        "handler_id",
        "attributor_id",
        "resolution_detail",
        "root_cause",
        "external_system",
        "external_key",
    ):
        if field in payload:
            setattr(defect, field, payload[field])
    if "resolution_type" in payload:
        rt = payload.get("resolution_type")
        if rt is not None and rt != "" and rt not in DEFECT_RESOLUTION_TYPES:
            raise HTTPException(status_code=400, detail="resolution_type 无效")
        old_rt = getattr(defect, "resolution_type", None)
        defect.resolution_type = rt or None
        if old_rt != defect.resolution_type:
            pending_activities.append(
                (
                    "resolution_change",
                    str(old_rt) if old_rt else None,
                    str(defect.resolution_type) if defect.resolution_type else None,
                )
            )
    if "handler_id" in payload:
        old_handler = getattr(defect, "handler_id", None)
        new_handler = payload.get("handler_id")
        if old_handler != new_handler:
            setattr(defect, "handler_id", new_handler)
            pending_activities.append(
                (
                    "handler_change",
                    str(old_handler) if old_handler is not None else None,
                    str(new_handler) if new_handler is not None else None,
                )
            )
    if "attributor_id" in payload:
        old_attr = getattr(defect, "attributor_id", None)
        new_attr = payload.get("attributor_id")
        if old_attr != new_attr:
            setattr(defect, "attributor_id", new_attr)
            pending_activities.append(
                (
                    "attributor_change",
                    str(old_attr) if old_attr is not None else None,
                    str(new_attr) if new_attr is not None else None,
                )
            )
    if "assignee_id" in payload:
        old_assignee = defect.assignee_id
        new_assignee = payload["assignee_id"]
        if old_assignee != new_assignee:
            defect.assignee_id = new_assignee
            pending_activities.append(
                ("assignee_change", str(old_assignee) if old_assignee is not None else None, str(new_assignee) if new_assignee is not None else None)
            )
    if "external_url" in payload:
        defect.external_url = validate_external_url(payload.get("external_url"))
    if "severity" in payload and payload["severity"] is not None:
        if payload["severity"] not in DEFECT_SEVERITIES:
            raise HTTPException(status_code=400, detail="severity 无效")
        defect.severity = payload["severity"]
    if "priority" in payload and payload["priority"] is not None:
        if payload["priority"] not in DEFECT_PRIORITIES:
            raise HTTPException(status_code=400, detail="priority 无效")
        defect.priority = payload["priority"]
    if "status" in payload and payload["status"] is not None:
        if payload["status"] not in DEFECT_STATUSES:
            raise HTTPException(status_code=400, detail="status 无效")
        old_status = defect.status
        new_status = payload["status"]
        assert_status_transition(old_status, new_status)
        if old_status != new_status:
            defect.status = new_status
            pending_activities.append(("status_change", old_status, new_status))
    if "attachments" in payload:
        defect.attachments = normalize_attachments(payload.get("attachments"))
    defect.update_by = username
    await defect.save()
    for action, from_v, to_v in pending_activities:
        await _record_activity(
            defect,
            action=action,
            actor=username,
            from_value=from_v,
            to_value=to_v,
        )
    assignee_changed = any(a[0] == "assignee_change" for a in pending_activities)
    if assignee_changed and defect.assignee_id:
        from app.modules.test_management.premium_gateway import soft_premium_call

        release_status = None
        if defect.release_id:
            release = await TestRelease.get_or_none(
                id=defect.release_id, project_id=defect.project_id, is_del=False
            )
            release_status = release.status if release else None
        await soft_premium_call(
            "assignment_notify_service",
            "notify_defect_assigned",
            project_id=defect.project_id,
            defect_id=defect.id,
            defect_key=defect.defect_key,
            defect_title=defect.title,
            assignee_id=defect.assignee_id,
            actor_id=actor_user_id,
            release_id=defect.release_id,
            release_status=release_status,
        )
    return defect


def _is_defect_handler(defect: TestDefect, actor_user_id: Optional[int]) -> bool:
    if actor_user_id is None:
        return False
    uid = int(actor_user_id)
    owners = []
    if defect.assignee_id is not None:
        owners.append(int(defect.assignee_id))
    if getattr(defect, "handler_id", None) is not None:
        owners.append(int(defect.handler_id))
    if not owners:
        # 未指定负责人时，有编辑权的人可通过流转认领
        return True
    return uid in owners


async def transition_defect(
    defect: TestDefect,
    *,
    to_status: str,
    username: str,
    actor_user_id: Optional[int],
    comment: Optional[str] = None,
    assignee_id: Optional[int] = None,
    handler_id: Optional[int] = None,
    attributor_id: Optional[int] = None,
    resolution_type: Optional[str] = None,
    resolution_detail: Optional[str] = None,
    force: bool = False,
) -> TestDefect:
    """负责人处理流转（弹窗提交）。force=True 时供超管强制改派/改状态。"""
    if not force and not _is_defect_handler(defect, actor_user_id):
        raise HTTPException(status_code=403, detail="仅当前负责人/处理人可进行流转处理")
    payload: dict[str, Any] = {"status": to_status}
    if assignee_id is not None:
        payload["assignee_id"] = assignee_id
    if handler_id is not None:
        payload["handler_id"] = handler_id
    if attributor_id is not None:
        payload["attributor_id"] = attributor_id
    if resolution_type is not None:
        payload["resolution_type"] = resolution_type
    if resolution_detail is not None:
        payload["resolution_detail"] = resolution_detail
    # 未指定处理人且当前为空：流转后默认落到操作者
    if (
        handler_id is None
        and getattr(defect, "handler_id", None) is None
        and actor_user_id is not None
    ):
        payload["handler_id"] = int(actor_user_id)
    if assignee_id is None and defect.assignee_id is None and actor_user_id is not None:
        payload["assignee_id"] = int(actor_user_id)

    row = await update_defect(defect, payload, username, actor_user_id=actor_user_id)
    note = (comment or "").strip()
    if note:
        await add_defect_comment(row, note, username)
    return row


async def soft_delete_defect(defect: TestDefect, username: str) -> None:
    if defect.release_id:
        release = await TestRelease.get_or_none(
            id=defect.release_id, project_id=defect.project_id, is_del=False
        )
        if release:
            assert_defect_release_editable(release)
    apply_soft_delete(defect, username)
    await defect.save()
    await TestDefectLink.filter(defect_id=defect.id, is_del=False).update(is_del=True)
    await TestDefectComment.filter(defect_id=defect.id, is_del=False).update(is_del=True)


async def add_defect_link(
    defect: TestDefect,
    payload: dict[str, Any],
    username: str,
) -> TestDefectLink:
    link = await _create_link(defect, payload)
    await _record_activity(
        defect,
        action="link_add",
        actor=username,
        to_value=link.link_type,
        note=str(link.id),
    )
    return link


async def remove_defect_link(
    defect: TestDefect,
    link_id: int,
    username: str,
) -> None:
    link = await TestDefectLink.get_or_none(
        id=link_id, defect_id=defect.id, project_id=defect.project_id, is_del=False
    )
    if not link:
        raise HTTPException(status_code=404, detail="关联不存在")
    link.is_del = True
    await link.save()
    await _record_activity(
        defect,
        action="link_remove",
        actor=username,
        from_value=link.link_type,
        note=str(link.id),
    )


async def add_defect_comment(
    defect: TestDefect,
    body: str,
    username: str,
) -> TestDefectComment:
    text = (body or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="评论内容不能为空")
    if len(text) > 10000:
        raise HTTPException(status_code=400, detail="评论过长")
    comment = await TestDefectComment.create(
        project_id=defect.project_id,
        defect_id=defect.id,
        body=text,
        create_by=username,
    )
    await _record_activity(
        defect,
        action="comment",
        actor=username,
        note=text[:200],
    )
    return comment


async def soft_delete_comment(
    defect: TestDefect,
    comment_id: int,
    username: str,
) -> None:
    comment = await TestDefectComment.get_or_none(
        id=comment_id, defect_id=defect.id, project_id=defect.project_id, is_del=False
    )
    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")
    comment.is_del = True
    await comment.save()


async def _open_defects_for_run_item(run_item_id: int, project_id: int) -> list[TestDefect]:
    link_ids = await TestDefectLink.filter(
        run_item_id=run_item_id,
        project_id=project_id,
        is_del=False,
        link_type="run_item",
    ).values_list("defect_id", flat=True)
    if not link_ids:
        return []
    return await TestDefect.filter(
        id__in=list(link_ids),
        project_id=project_id,
        is_del=False,
        status__in=list(norm.OPEN_DEFECT_STATUSES),
    )


async def create_defect_from_run_item(
    run: TestPlanRun,
    run_item_id: int,
    *,
    username: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    severity: str = "major",
    priority: str = "p2",
    assignee_id: Optional[int] = None,
    reporter_id: Optional[int] = None,
) -> dict[str, Any]:
    item = await TestPlanRunItem.get_or_none(
        id=run_item_id, run_id=run.id, project_id=run.project_id, is_del=False
    )
    if not item:
        raise HTTPException(status_code=404, detail="运行项不存在")
    result = (item.result_status or "").strip()
    if result not in norm.DEFECT_CREATABLE_RESULTS:
        raise HTTPException(
            status_code=400,
            detail=f"仅失败/错误/阻塞状态可建缺陷，当前为 {result or 'unknown'}",
        )

    existing_open = await _open_defects_for_run_item(item.id, run.project_id)
    release = await TestRelease.get_or_none(
        id=run.release_id, project_id=run.project_id, is_del=False
    )
    if release:
        assert_defect_release_editable(release)
    found_in = release.release_key if release else None

    auto_title = (title or "").strip() or f"[{result}] {item.title}"
    parts = []
    if item.result_message:
        parts.append(item.result_message.strip())
    if description:
        parts.append(description.strip())
    ev = item.evidence_json or {}
    if ev.get("report_url"):
        parts.append(f"报告: {ev['report_url']}")
    if ev.get("error_summary"):
        parts.append(f"错误: {ev['error_summary']}")
    auto_desc = "\n".join(parts) if parts else None

    asset_type = None
    if item.item_type in ("ui_case", "app_case", "api_case", "perf_scene"):
        asset_type = item.item_type
    elif item.original_record_type:
        rt = item.original_record_type.replace("_execution", "").replace("_record", "")
        if rt in ("ui_case", "app_case", "api_case", "perf_scene"):
            asset_type = rt

    defect = await create_defect(
        project_id=run.project_id,
        release_id=run.release_id,
        title=auto_title,
        description=auto_desc,
        severity=severity,
        priority=priority,
        found_in=found_in,
        assignee_id=assignee_id,
        reporter_id=reporter_id,
        username=username,
        links=[
            {
                "link_type": "run_item",
                "run_item_id": item.id,
                "functional_case_id": item.functional_case_id,
                "asset_type": asset_type,
                "asset_id": item.asset_id,
            }
        ],
    )
    detail = await get_defect_detail(defect)
    detail["existing_open_defects"] = [defect_to_dict(d) for d in existing_open]
    detail["warn_duplicate"] = len(existing_open) > 0
    return detail


async def get_defect_stats(
    project_id: int,
    *,
    release_id: Optional[int] = None,
) -> dict[str, Any]:
    def _base():
        q = TestDefect.filter(project_id=project_id, is_del=False)
        if release_id is not None:
            q = q.filter(release_id=release_id)
        return q

    total = await _base().count()
    by_severity: dict[str, int] = {}
    for row in await _base().annotate(c=Count("id")).group_by("severity").values("severity", "c"):
        by_severity[row.get("severity") or "major"] = int(row.get("c") or 0)
    by_status: dict[str, int] = {}
    for row in await _base().annotate(c=Count("id")).group_by("status").values("status", "c"):
        by_status[row.get("status") or "open"] = int(row.get("c") or 0)
    by_resolution: dict[str, int] = {}
    for row in await _base().exclude(resolution_type__isnull=True).exclude(resolution_type="").annotate(
        c=Count("id")
    ).group_by("resolution_type").values("resolution_type", "c"):
        rt = row.get("resolution_type")
        if rt:
            by_resolution[str(rt)] = int(row.get("c") or 0)
    return {
        "total": total,
        "by_severity": by_severity,
        "by_status": by_status,
        "by_resolution": by_resolution,
    }


async def _defect_user_counts(
    project_id: int,
    release_id: int,
    field: str,
) -> list[dict[str, Any]]:
    q = TestDefect.filter(project_id=project_id, release_id=release_id, is_del=False)
    q = q.exclude(**{f"{field}__isnull": True})
    rows = await q.annotate(c=Count("id")).group_by(field).values(field, "c")
    out = []
    for row in rows:
        uid = row.get(field)
        if uid is None:
            continue
        out.append({"user_id": int(uid), "count": int(row.get("c") or 0)})
    out.sort(key=lambda x: (-x["count"], x["user_id"]))
    return out


async def build_release_defect_report(
    project_id: int,
    release_id: int,
    *,
    limit: int = 200,
) -> dict[str, Any]:
    """版本缺陷测试报告：汇总 + 按人统计 + 明细列表。"""
    await get_release_or_404(release_id, project_id)
    summary = await get_defect_stats(project_id, release_id=release_id)
    lim = max(1, min(int(limit or 200), 500))
    open_count = await TestDefect.filter(
        project_id=project_id,
        release_id=release_id,
        is_del=False,
        status__in=list(norm.OPEN_DEFECT_STATUSES),
    ).count()
    rows = await TestDefect.filter(
        project_id=project_id,
        release_id=release_id,
        is_del=False,
    ).order_by("-id").limit(lim)
    items = [defect_to_dict(r) for r in rows]
    return {
        "summary": summary,
        "open_count": open_count,
        "closed_count": max(0, int(summary.get("total") or 0) - open_count),
        "by_reporter": await _defect_user_counts(project_id, release_id, "reporter_id"),
        "by_handler": await _defect_user_counts(project_id, release_id, "handler_id"),
        "by_attributor": await _defect_user_counts(project_id, release_id, "attributor_id"),
        "items": items,
        "limited": len(items) >= lim,
    }
