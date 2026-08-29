"""版本 / 范围 / 资产映射服务"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, status
from tortoise import transactions
from tortoise.expressions import F, Q

from app.models.ai import AiFunctionalCase, AiRequirement
from app.models.app import AppCase
from app.models.http import ApiTestCase
from app.models.perf import PerfScene
from app.models.test_management import (
    CaseReview,
    CaseReviewItem,
    TestAssetLink,
    TestPlan,
    TestPlanItem,
    TestRelease,
    TestReleaseRequirement,
    TestReleaseScope,
)
from app.models.ui import Case
from app.modules.test_management.rules import (
    ASSET_TYPES,
    HEALTH_STATUSES,
    LINK_TYPES,
    RISK_LEVELS,
    SCOPE_STATUSES,
    can_transition_release,
    compute_automation_status,
    release_requirement_editable,
    release_defect_editable,
    release_scope_editable,
)
from app.modules.test_management.phase3_rules import validate_external_url

_REQ_KEY_RE = re.compile(r"^REQ-(\d+)$", re.I)


def parse_ai_requirement_id(requirement_key: str) -> Optional[int]:
    m = _REQ_KEY_RE.match((requirement_key or "").strip())
    return int(m.group(1)) if m else None


def resolve_release_requirement_ai_id(row: TestReleaseRequirement) -> Optional[int]:
    return row.ai_requirement_id or parse_ai_requirement_id(row.requirement_key)


def resolve_release_requirement_source_type(
    row: TestReleaseRequirement,
    *,
    ai_id: Optional[int] = None,
) -> str:
    """REQ-{id} 或已关联 ai_requirement_id 时一律视为项目需求，避免历史 external 默认值误判。"""
    resolved_ai_id = ai_id if ai_id is not None else resolve_release_requirement_ai_id(row)
    if resolved_ai_id:
        return "ai"
    stored = (row.source_type or "").strip()
    return stored or "external"


def _dt_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def release_to_dict(row: TestRelease) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "release_key": row.release_key,
        "name": row.name,
        "description": row.description,
        "status": row.status,
        "owner_id": row.owner_id,
        "planned_start_at": _dt_iso(row.planned_start_at),
        "planned_release_at": _dt_iso(row.planned_release_at),
        "actual_release_at": _dt_iso(row.actual_release_at),
        "external_url": row.external_url,
        "quality_status": row.quality_status,
        "create_by": row.create_by,
        "update_by": row.update_by,
        "create_time": _dt_iso(row.create_time),
        "update_time": _dt_iso(row.update_time),
    }


def requirement_to_dict(
    row: TestReleaseRequirement,
    *,
    ai_req: Optional[AiRequirement] = None,
) -> dict[str, Any]:
    ai_id = resolve_release_requirement_ai_id(row)
    source_type = resolve_release_requirement_source_type(row, ai_id=ai_id)
    data = {
        "id": row.id,
        "project_id": row.project_id,
        "release_id": row.release_id,
        "requirement_key": row.requirement_key,
        "title": row.title,
        "url": row.url,
        "note": row.note,
        "ai_requirement_id": ai_id,
        "source_type": source_type,
        "ai_review_status": None,
        "ai_parse_status": None,
        "create_by": row.create_by,
        "create_time": _dt_iso(row.create_time),
        "update_time": _dt_iso(row.update_time),
    }
    if ai_req is not None:
        data["ai_review_status"] = ai_req.review_status
        data["ai_parse_status"] = ai_req.parse_status
    return data


async def requirements_to_dicts(rows: list[TestReleaseRequirement]) -> list[dict[str, Any]]:
    ai_ids: list[int] = []
    for row in rows:
        aid = row.ai_requirement_id or parse_ai_requirement_id(row.requirement_key)
        if aid:
            ai_ids.append(aid)
    ai_map: dict[int, AiRequirement] = {}
    if ai_ids:
        ai_map = {
            r.id: r
            for r in await AiRequirement.filter(id__in=ai_ids, is_del=False)
        }
    out: list[dict[str, Any]] = []
    for row in rows:
        aid = row.ai_requirement_id or parse_ai_requirement_id(row.requirement_key)
        out.append(requirement_to_dict(row, ai_req=ai_map.get(aid) if aid else None))
    return out


def scope_to_dict(row: TestReleaseScope, case: Optional[AiFunctionalCase] = None) -> dict[str, Any]:
    data = {
        "id": row.id,
        "project_id": row.project_id,
        "release_id": row.release_id,
        "functional_case_id": row.functional_case_id,
        "scope_status": row.scope_status,
        "risk_level": row.risk_level,
        "requirement_key": row.requirement_key,
        "automation_status": row.automation_status,
        "owner_id": row.owner_id,
        "note": row.note,
        "create_by": row.create_by,
        "create_time": _dt_iso(row.create_time),
        "update_time": _dt_iso(row.update_time),
        "case_title": None,
        "case_module": None,
        "case_product": None,
        "case_priority": None,
    }
    if case is not None:
        data["case_title"] = case.title
        data["case_module"] = case.module
        data["case_product"] = case.product
        data["case_priority"] = case.priority
    return data


def asset_link_to_dict(row: TestAssetLink, *, asset_name: Optional[str] = None) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "functional_case_id": row.functional_case_id,
        "asset_type": row.asset_type,
        "asset_id": row.asset_id,
        "link_type": row.link_type,
        "coverage_note": row.coverage_note,
        "health_status": row.health_status,
        "asset_name": asset_name,
        "create_by": row.create_by,
        "create_time": _dt_iso(row.create_time),
        "update_time": _dt_iso(row.update_time),
    }


async def get_release_or_404(release_id: int, project_id: int) -> TestRelease:
    row = await TestRelease.get_or_none(id=release_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="版本不存在")
    return row


async def ensure_release_key_unique(project_id: int, release_key: str, *, exclude_id: Optional[int] = None) -> None:
    q = TestRelease.filter(project_id=project_id, release_key=release_key, is_del=False)
    if exclude_id:
        q = q.exclude(id=exclude_id)
    if await q.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"版本键已存在: {release_key}",
        )


def assert_scope_editable(release: TestRelease) -> None:
    if not release_scope_editable(release.status):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"版本状态为 {release.status}，不可修改测试范围",
        )


def assert_requirement_editable(release: TestRelease) -> None:
    if not release_requirement_editable(release.status):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"版本状态为 {release.status}，不可修改需求条目",
        )


def assert_defect_release_editable(release: TestRelease) -> None:
    if not release_defect_editable(release.status):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"版本状态为 {release.status}，不可维护缺陷",
        )


async def create_release(
    *,
    project_id: int,
    release_key: str,
    name: str,
    username: str,
    description: Optional[str] = None,
    owner_id: Optional[int] = None,
    planned_start_at: Optional[datetime] = None,
    planned_release_at: Optional[datetime] = None,
    external_url: Optional[str] = None,
) -> TestRelease:
    key = (release_key or "").strip()
    title = (name or "").strip()
    if not key or not title:
        raise HTTPException(status_code=400, detail="release_key 与 name 必填")
    await ensure_release_key_unique(project_id, key)
    return await TestRelease.create(
        project_id=project_id,
        release_key=key,
        name=title,
        description=description,
        owner_id=owner_id,
        planned_start_at=planned_start_at,
        planned_release_at=planned_release_at,
        external_url=(external_url or None),
        status="draft",
        create_by=username,
        update_by=username,
    )


async def update_release(release: TestRelease, payload: dict[str, Any], username: str) -> TestRelease:
    if release.status in ("released", "archived"):
        # 已发布仅允许改 external_url / description 等非范围字段
        allowed = {"description", "external_url", "name"}
        if set(payload.keys()) - allowed:
            raise HTTPException(status_code=400, detail="已发布/归档版本仅可更新名称、说明或外部链接")
    if "release_key" in payload and payload["release_key"] is not None:
        new_key = str(payload["release_key"]).strip()
        if new_key != release.release_key:
            if release.status in ("released", "archived"):
                raise HTTPException(status_code=400, detail="已发布/归档版本不可修改版本键")
            await ensure_release_key_unique(release.project_id, new_key, exclude_id=release.id)
            release.release_key = new_key
    nullable_fields = {
        "description",
        "external_url",
        "owner_id",
        "planned_start_at",
        "planned_release_at",
    }
    for field in (
        "name",
        "description",
        "owner_id",
        "planned_start_at",
        "planned_release_at",
        "external_url",
    ):
        if field not in payload:
            continue
        value = payload[field]
        if value is None and field not in nullable_fields:
            continue
        if field == "name" and value is not None:
            value = str(value).strip()
            if not value:
                raise HTTPException(status_code=400, detail="name 不能为空")
        setattr(release, field, value)
    release.update_by = username
    await release.save()
    return release


async def transition_release(release: TestRelease, target: str, username: str) -> tuple[TestRelease, list[str]]:
    target = (target or "").strip()
    if not can_transition_release(release.status, target):
        raise HTTPException(
            status_code=400,
            detail=f"不允许从 {release.status} 迁移到 {target}",
        )
    warnings: list[str] = []
    from app.modules.test_management.premium_gateway import tm_premium_ready

    if target == "ready" and tm_premium_ready():
        from app.modules.test_management.quality_service import assert_quality_allows_ready

        await assert_quality_allows_ready(release)
    if target == "released":
        from app.models.test_management import TestPlanRun

        active = await TestPlanRun.filter(
            release_id=release.id,
            project_id=release.project_id,
            is_del=False,
            status="running",
        ).exists()
        if active:
            raise HTTPException(
                status_code=400,
                detail="仍有进行中的计划运行，请先完成或取消后再发布版本",
            )
        if tm_premium_ready():
            from app.modules.test_management.quality_service import assert_quality_allows_release

            warnings = await assert_quality_allows_release(release)
    release.status = target
    if target == "released" and release.actual_release_at is None:
        release.actual_release_at = datetime.now(timezone.utc)
    release.update_by = username
    await release.save()
    return release, warnings


def apply_soft_delete(row, username: str | None = None) -> None:
    """软删并占用 delete_seq=id，释放自然键上的活跃唯一槽位 (delete_seq=0)。"""
    row.is_del = True
    if hasattr(row, "delete_seq") and getattr(row, "id", None) is not None:
        row.delete_seq = int(row.id)
    if username is not None and hasattr(row, "update_by"):
        row.update_by = username


async def soft_delete_release(release: TestRelease, username: str) -> None:
    if release.status in ("released", "archived"):
        raise HTTPException(status_code=400, detail="已发布/归档版本不可删除")
    async with transactions.in_transaction():
        apply_soft_delete(release, username)
        await release.save()
        await TestReleaseScope.filter(release_id=release.id, is_del=False).update(
            is_del=True, delete_seq=F("id"), update_by=username
        )
        await TestReleaseRequirement.filter(release_id=release.id, is_del=False).update(
            is_del=True, update_by=username
        )


async def list_releases(project_id: int, *, status: Optional[str] = None, keyword: Optional[str] = None):
    q = TestRelease.filter(project_id=project_id, is_del=False)
    if status:
        q = q.filter(status=status)
    if keyword:
        kw = keyword.strip()
        if kw:
            q = q.filter(Q(name__icontains=kw) | Q(release_key__icontains=kw))
    return await q.order_by("-id")


async def add_requirement(
    release: TestRelease,
    *,
    requirement_key: str,
    title: str = "",
    url: Optional[str] = None,
    note: Optional[str] = None,
    username: str,
) -> TestReleaseRequirement:
    assert_requirement_editable(release)
    key = (requirement_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="requirement_key 必填")
    dup = await TestReleaseRequirement.filter(
        release_id=release.id, requirement_key=key, is_del=False
    ).exists()
    if dup:
        raise HTTPException(status_code=400, detail=f"需求编号已存在: {key}")
    safe_url = validate_external_url(url)
    ai_id = parse_ai_requirement_id(key)
    source_type = "ai" if ai_id else "external"
    if ai_id:
        ai_row = await AiRequirement.get_or_none(
            id=ai_id, project_id=release.project_id, is_del=False
        )
        if not ai_row:
            raise HTTPException(status_code=400, detail=f"项目需求不存在: REQ-{ai_id}")
    return await TestReleaseRequirement.create(
        project_id=release.project_id,
        release_id=release.id,
        requirement_key=key,
        title=(title or "").strip(),
        url=safe_url,
        note=note,
        ai_requirement_id=ai_id,
        source_type=source_type,
        create_by=username,
        update_by=username,
    )


async def list_requirements(release_id: int, project_id: int):
    return await TestReleaseRequirement.filter(
        release_id=release_id, project_id=project_id, is_del=False
    ).order_by("id")


async def delete_requirement(req_id: int, release_id: int, project_id: int, username: str) -> None:
    release = await get_release_or_404(release_id, project_id)
    assert_requirement_editable(release)
    row = await TestReleaseRequirement.get_or_none(
        id=req_id, release_id=release_id, project_id=project_id, is_del=False
    )
    if not row:
        raise HTTPException(status_code=404, detail="需求条目不存在")
    row.is_del = True
    row.update_by = username
    await row.save()


async def update_release_requirement(
    req_id: int,
    release_id: int,
    project_id: int,
    *,
    title: Optional[str] = None,
    url: Optional[str] = None,
    note: Optional[str] = None,
    username: str,
) -> TestReleaseRequirement:
    release = await get_release_or_404(release_id, project_id)
    assert_requirement_editable(release)
    row = await TestReleaseRequirement.get_or_none(
        id=req_id, release_id=release_id, project_id=project_id, is_del=False
    )
    if not row:
        raise HTTPException(status_code=404, detail="需求条目不存在")
    if title is not None:
        row.title = (title or "").strip()
    if url is not None:
        u = (url or "").strip()
        row.url = validate_external_url(u) if u else None
    if note is not None:
        row.note = note
    row.update_by = username
    await row.save()
    return row


async def get_requirement_preview(row: TestReleaseRequirement, project_id: int) -> dict[str, Any]:
    ai_id = resolve_release_requirement_ai_id(row)
    source_type = resolve_release_requirement_source_type(row, ai_id=ai_id)
    data: dict[str, Any] = {
        "id": row.id,
        "requirement_key": row.requirement_key,
        "title": row.title,
        "url": row.url,
        "note": row.note,
        "source_type": source_type,
        "ai_requirement_id": ai_id,
    }
    if ai_id:
        req = await AiRequirement.get_or_none(id=ai_id, project_id=project_id, is_del=False)
        if req:
            meta = req.parsed_content if isinstance(req.parsed_content, dict) else {}
            sections = meta.get("sections") or []
            content = req.original_content or ""
            if len(content) > 12000:
                content = content[:12000] + "..."
            data.update(
                {
                    "name": req.name,
                    "original_content": content,
                    "sections": sections[:80],
                    "section_count": len(sections),
                    "file_name": meta.get("file_name", ""),
                    "review_status": req.review_status,
                    "parse_status": req.parse_status,
                    "text_length": len(req.original_content or ""),
                }
            )
    return data


async def upgrade_requirement_to_ai(
    row: TestReleaseRequirement,
    release: TestRelease,
    *,
    name: Optional[str] = None,
    initial_content: Optional[str] = None,
    username: str,
) -> TestReleaseRequirement:
    assert_requirement_editable(release)
    if row.source_type == "ai" or row.ai_requirement_id or parse_ai_requirement_id(row.requirement_key):
        raise HTTPException(status_code=400, detail="已是项目需求，无需升级")
    req_name = (name or row.title or row.requirement_key).strip()
    if not req_name:
        raise HTTPException(status_code=400, detail="需求名称必填")
    content = (initial_content or row.note or row.title or "").strip()
    ai_req = await AiRequirement.create(
        project_id=release.project_id,
        name=req_name,
        source_type="text",
        original_content=content,
        parsed_content={},
        parse_status="parsed" if content else "pending",
        create_by=username,
    )
    new_key = f"REQ-{ai_req.id}"
    dup = await TestReleaseRequirement.filter(
        release_id=release.id, requirement_key=new_key, is_del=False
    ).exists()
    if dup:
        ai_req.is_del = True
        await ai_req.save()
        raise HTTPException(status_code=400, detail=f"项目需求 {new_key} 已关联本版本")
    row.requirement_key = new_key
    row.ai_requirement_id = ai_req.id
    row.source_type = "ai"
    if not (row.title or "").strip():
        row.title = req_name
    row.update_by = username
    await row.save()
    return row


async def refresh_scope_automation_status(
    project_id: int,
    functional_case_ids: list[int] | set[int],
) -> None:
    ids = [int(i) for i in functional_case_ids if i]
    if not ids:
        return
    links = await TestAssetLink.filter(
        project_id=project_id,
        functional_case_id__in=ids,
        is_del=False,
    ).values("functional_case_id", "link_type")
    by_case: dict[int, list[str]] = defaultdict(list)
    for item in links:
        by_case[int(item["functional_case_id"])].append(item["link_type"])
    scopes = await TestReleaseScope.filter(
        project_id=project_id,
        functional_case_id__in=ids,
        is_del=False,
    )
    if not scopes:
        return
    release_ids = {s.release_id for s in scopes}
    releases = {
        r.id: r
        for r in await TestRelease.filter(id__in=list(release_ids), project_id=project_id, is_del=False)
    }
    for scope in scopes:
        release = releases.get(scope.release_id)
        if not release or not release_scope_editable(release.status):
            continue
        new_status = compute_automation_status(by_case.get(scope.functional_case_id, []))
        if scope.automation_status != new_status:
            scope.automation_status = new_status
            await scope.save(update_fields=["automation_status", "update_time"])


async def batch_add_scopes(
    release: TestRelease,
    *,
    functional_case_ids: list[int],
    risk_level: str = "medium",
    owner_id: Optional[int] = None,
    requirement_key: Optional[str] = None,
    username: str,
    actor_user_id: Optional[int] = None,
) -> dict[str, Any]:
    assert_scope_editable(release)
    risk = (risk_level or "medium").strip()
    if risk not in RISK_LEVELS:
        raise HTTPException(status_code=400, detail="risk_level 无效")
    ids = []
    seen = set()
    for raw in functional_case_ids or []:
        cid = int(raw)
        if cid in seen:
            continue
        seen.add(cid)
        ids.append(cid)
    if not ids:
        raise HTTPException(status_code=400, detail="functional_case_ids 不能为空")

    if owner_id is None:
        from app.modules.test_management.premium_gateway import tm_premium_ready

        if tm_premium_ready():
            from app.modules.test_management.tm_notify_settings import load_tm_notify_settings

            tm_settings = await load_tm_notify_settings(release.project_id)
            owner_id = tm_settings.get("default_scope_owner_id")

    cases = await AiFunctionalCase.filter(
        id__in=ids, project_id=release.project_id, is_del=False
    )
    found = {c.id for c in cases}
    missing = [i for i in ids if i not in found]
    if missing:
        raise HTTPException(status_code=400, detail=f"功能用例不存在或不属于本项目: {missing[:10]}")

    existing = await TestReleaseScope.filter(
        release_id=release.id, functional_case_id__in=ids, is_del=False
    ).values_list("functional_case_id", flat=True)
    existing_set = set(existing)

    # 预取映射类型
    links = await TestAssetLink.filter(
        project_id=release.project_id,
        functional_case_id__in=ids,
        is_del=False,
    ).values("functional_case_id", "link_type")
    by_case: dict[int, list[str]] = defaultdict(list)
    for item in links:
        by_case[int(item["functional_case_id"])].append(item["link_type"])

    created_ids: list[int] = []
    async with transactions.in_transaction():
        for cid in ids:
            if cid in existing_set:
                continue
            row = await TestReleaseScope.create(
                project_id=release.project_id,
                release_id=release.id,
                functional_case_id=cid,
                risk_level=risk,
                owner_id=owner_id,
                requirement_key=(requirement_key or None),
                automation_status=compute_automation_status(by_case.get(cid, [])),
                create_by=username,
                update_by=username,
            )
            created_ids.append(row.id)

    return {
        "created_scope_ids": created_ids,
        "existing_functional_case_ids": sorted(existing_set),
        "created_ids": created_ids,
        "existing_ids": sorted(existing_set),
        "created_count": len(created_ids),
        "existing_count": len(existing_set),
    }


async def list_scopes(
    release: TestRelease,
    *,
    keyword: Optional[str] = None,
    module: Optional[str] = None,
    risk_level: Optional[str] = None,
    automation_status: Optional[str] = None,
    owner_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    q = TestReleaseScope.filter(release_id=release.id, project_id=release.project_id, is_del=False)
    if risk_level:
        q = q.filter(risk_level=risk_level)
    if automation_status:
        q = q.filter(automation_status=automation_status)
    if owner_id is not None:
        q = q.filter(owner_id=owner_id)
    scopes = await q.order_by("id")
    if not scopes:
        return []

    case_ids = [s.functional_case_id for s in scopes]
    case_q = AiFunctionalCase.filter(id__in=case_ids, project_id=release.project_id, is_del=False)
    if module:
        case_q = case_q.filter(module__icontains=module.strip())
    if keyword:
        case_q = case_q.filter(title__icontains=keyword.strip())
    cases = {c.id: c for c in await case_q}
    active_case_ids = set(cases.keys())
    scopes = [s for s in scopes if s.functional_case_id in active_case_ids]
    from app.modules.test_management.review_service import functional_case_review_status_map

    review_map = await functional_case_review_status_map(
        release.project_id, [s.functional_case_id for s in scopes]
    )
    rows = []
    for s in scopes:
        data = scope_to_dict(s, cases.get(s.functional_case_id))
        data["review_decision"] = review_map.get(s.functional_case_id)
        rows.append(data)
    return rows


async def update_scope(
    scope_id: int,
    release: TestRelease,
    payload: dict[str, Any],
    username: str,
    actor_user_id: Optional[int] = None,
) -> TestReleaseScope:
    assert_scope_editable(release)
    row = await TestReleaseScope.get_or_none(
        id=scope_id, release_id=release.id, project_id=release.project_id, is_del=False
    )
    if not row:
        raise HTTPException(status_code=404, detail="范围项不存在")
    if "risk_level" in payload and payload["risk_level"] is not None:
        if payload["risk_level"] not in RISK_LEVELS:
            raise HTTPException(status_code=400, detail="risk_level 无效")
        row.risk_level = payload["risk_level"]
    if "scope_status" in payload and payload["scope_status"] is not None:
        if payload["scope_status"] not in SCOPE_STATUSES:
            raise HTTPException(status_code=400, detail="scope_status 无效")
        row.scope_status = payload["scope_status"]
    if "owner_id" in payload:
        row.owner_id = payload["owner_id"]
    if "requirement_key" in payload:
        row.requirement_key = payload["requirement_key"] or None
    if "note" in payload:
        row.note = payload["note"]
    row.update_by = username
    await row.save()
    return row


async def batch_update_scopes(
    release: TestRelease,
    *,
    scope_ids: list[int],
    risk_level: Optional[str] = None,
    owner_id: Optional[int] = None,
    clear_owner: bool = False,
    username: str,
    actor_user_id: Optional[int] = None,
) -> dict[str, Any]:
    assert_scope_editable(release)
    ids = []
    seen = set()
    for raw in scope_ids or []:
        sid = int(raw)
        if sid in seen:
            continue
        seen.add(sid)
        ids.append(sid)
    if not ids:
        raise HTTPException(status_code=400, detail="scope_ids 不能为空")
    if risk_level is None and owner_id is None and not clear_owner:
        raise HTTPException(status_code=400, detail="请至少指定风险或负责人变更")
    if risk_level is not None and risk_level not in RISK_LEVELS:
        raise HTTPException(status_code=400, detail="risk_level 无效")

    rows = await TestReleaseScope.filter(
        id__in=ids, release_id=release.id, project_id=release.project_id, is_del=False
    )
    found = {r.id for r in rows}
    missing = [i for i in ids if i not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"范围项不存在: {missing[:10]}")

    updated = 0
    case_ids = [r.functional_case_id for r in rows]
    cases = {
        c.id: c
        for c in await AiFunctionalCase.filter(
            id__in=case_ids, project_id=release.project_id, is_del=False
        )
    }
    for row in rows:
        changed = False
        old_owner = row.owner_id
        if risk_level is not None:
            row.risk_level = risk_level
            changed = True
        new_owner = old_owner
        if clear_owner:
            new_owner = None
            if old_owner is not None:
                changed = True
        elif owner_id is not None:
            new_owner = owner_id
            if old_owner != new_owner:
                changed = True
        row.owner_id = new_owner
        if changed:
            row.update_by = username
            await row.save()
            updated += 1
    return {"updated": updated, "notified": 0, "requested": len(ids)}


async def notify_scope_owners(
    release: TestRelease,
    *,
    actor_user_id: Optional[int] = None,
    owner_ids: Optional[list[int]] = None,
) -> dict[str, Any]:
    """分配完成后手动推送：按负责人汇总，每人一条站内信。"""
    from collections import defaultdict

    from app.modules.test_management.premium_gateway import soft_premium_call

    scopes = await TestReleaseScope.filter(
        release_id=release.id,
        project_id=release.project_id,
        is_del=False,
        owner_id__not_isnull=True,
    )
    if owner_ids:
        allow = {int(x) for x in owner_ids if x is not None}
        scopes = [s for s in scopes if s.owner_id in allow]
    if not scopes:
        return {"sent": 0, "skipped": 0, "owners": 0, "cases": 0}

    case_ids = [s.functional_case_id for s in scopes]
    cases = {
        c.id: c
        for c in await AiFunctionalCase.filter(
            id__in=case_ids, project_id=release.project_id, is_del=False
        )
    }
    assignments: dict[int, list[str]] = defaultdict(list)
    for s in scopes:
        title = ""
        case = cases.get(s.functional_case_id)
        if case and case.title:
            title = case.title
        else:
            title = f"用例 #{s.functional_case_id}"
        assignments[int(s.owner_id)].append(title)

    result = await soft_premium_call(
        "assignment_notify_service",
        "notify_scope_owners_digest",
        project_id=release.project_id,
        release_id=release.id,
        release_name=release.name,
        release_status=release.status,
        assignments=dict(assignments),
        actor_id=actor_user_id,
        default={"sent": 0, "skipped": 0, "reason": "premium_unavailable"},
    ) or {"sent": 0, "skipped": 0}
    return {
        **result,
        "owners": len(assignments),
        "cases": sum(len(v) for v in assignments.values()),
    }


async def scope_dict_with_case(scope: TestReleaseScope, project_id: int) -> dict[str, Any]:
    case = await AiFunctionalCase.get_or_none(
        id=scope.functional_case_id, project_id=project_id, is_del=False
    )
    return scope_to_dict(scope, case)


async def _cascade_scope_removal(
    release: TestRelease,
    scope: TestReleaseScope,
    username: str,
) -> dict[str, int]:
    """范围移除时同步清理进行中的评审项与可编辑计划项（保留已结束评审与历史运行）。"""
    fc_id = scope.functional_case_id
    scope_id = scope.id
    review_removed = 0
    plan_removed = 0

    active_reviews = await CaseReview.filter(
        release_id=release.id,
        project_id=release.project_id,
        is_del=False,
        status__in=["pending", "in_review"],
    )
    async with transactions.in_transaction():
        if active_reviews:
            review_ids = [r.id for r in active_reviews]
            updated = await CaseReviewItem.filter(
                review_id__in=review_ids,
                project_id=release.project_id,
                functional_case_id=fc_id,
                is_del=False,
            ).update(is_del=True, delete_seq=F("id"), update_by=username)
            review_removed = int(updated or 0)

        editable_plans = await TestPlan.filter(
            release_id=release.id,
            project_id=release.project_id,
            is_del=False,
            status__in=["draft", "ready"],
        )
        if editable_plans:
            plan_ids = [p.id for p in editable_plans]
            updated = await TestPlanItem.filter(
                plan_id__in=plan_ids,
                project_id=release.project_id,
                is_del=False,
            ).filter(Q(source_scope_id=scope_id) | Q(functional_case_id=fc_id)).update(
                is_del=True, update_by=username
            )
            plan_removed = int(updated or 0)

    return {
        "review_items_removed": review_removed,
        "plan_items_removed": plan_removed,
    }


async def remove_scope(scope_id: int, release: TestRelease, username: str) -> dict[str, int]:
    assert_scope_editable(release)
    row = await TestReleaseScope.get_or_none(
        id=scope_id, release_id=release.id, project_id=release.project_id, is_del=False
    )
    if not row:
        raise HTTPException(status_code=404, detail="范围项不存在")
    cascade = await _cascade_scope_removal(release, row, username)
    apply_soft_delete(row, username)
    await row.save()
    return cascade


async def release_overview(release: TestRelease) -> dict[str, Any]:
    scopes = await TestReleaseScope.filter(
        release_id=release.id, project_id=release.project_id, is_del=False
    )
    risk = Counter(s.risk_level for s in scopes)
    coverage = Counter(s.automation_status for s in scopes)
    reqs = await TestReleaseRequirement.filter(
        release_id=release.id, project_id=release.project_id, is_del=False
    )
    requirement_review_done = await compute_requirement_review_done(
        release.project_id, reqs
    )
    return {
        "release": release_to_dict(release),
        "scope_count": len(scopes),
        "requirement_count": len(reqs),
        "requirement_review_done": requirement_review_done,
        "risk_distribution": {
            "low": risk.get("low", 0),
            "medium": risk.get("medium", 0),
            "high": risk.get("high", 0),
            "critical": risk.get("critical", 0),
        },
        "coverage_distribution": {
            "none": coverage.get("none", 0),
            "partial": coverage.get("partial", 0),
            "covered": coverage.get("covered", 0),
            "unstable": coverage.get("unstable", 0),
        },
    }


async def compute_requirement_review_done(
    project_id: int,
    requirements: list[TestReleaseRequirement],
) -> bool:
    """
    向导 0.3：关联的内部需求（REQ-{id}）均已 review_status=approved 则自动完成。
    无内部需求链接时返回 False（仍可手动标记）。
    """
    import re

    ids: list[int] = []
    for row in requirements or []:
        key = (row.requirement_key or "").strip()
        m = re.fullmatch(r"REQ-(\d+)", key, flags=re.IGNORECASE)
        if m:
            ids.append(int(m.group(1)))
    if not ids:
        return False
    uniq = list(dict.fromkeys(ids))
    rows = await AiRequirement.filter(
        id__in=uniq, project_id=project_id, is_del=False
    ).all()
    by_id = {r.id: r for r in rows}
    if len(by_id) < len(uniq):
        return False
    return all((by_id[i].review_status or "").strip() == "approved" for i in uniq)


async def _assert_functional_case(project_id: int, functional_case_id: int) -> AiFunctionalCase:
    case = await AiFunctionalCase.get_or_none(
        id=functional_case_id, project_id=project_id, is_del=False
    )
    if not case:
        raise HTTPException(status_code=400, detail="功能用例不存在或不属于本项目")
    return case


async def _assert_asset(project_id: int, asset_type: str, asset_id: int) -> str:
    if asset_type not in ASSET_TYPES:
        raise HTTPException(status_code=400, detail="asset_type 无效")
    name = ""
    if asset_type == "ui_case":
        row = await Case.get_or_none(id=asset_id, project_id=project_id, is_del=False)
        if not row:
            raise HTTPException(status_code=400, detail="UI 用例不存在或不属于本项目")
        name = row.name
    elif asset_type == "app_case":
        row = await AppCase.get_or_none(id=asset_id, project_id=project_id, is_del=False)
        if not row:
            raise HTTPException(status_code=400, detail="App 用例不存在或不属于本项目")
        name = row.name
    elif asset_type == "api_case":
        row = await ApiTestCase.get_or_none(id=asset_id, project_id=project_id, is_del=False)
        if not row:
            raise HTTPException(status_code=400, detail="接口用例不存在或不属于本项目")
        name = row.name
    elif asset_type == "perf_scene":
        row = await PerfScene.get_or_none(id=asset_id, project_id=project_id, is_del=False)
        if not row:
            raise HTTPException(status_code=400, detail="压测场景不存在或不属于本项目")
        name = row.name
    return name


async def preview_asset_name(project_id: int, asset_type: str, asset_id: int) -> str:
    return await _assert_asset(project_id, asset_type, asset_id)


async def create_asset_link(
    *,
    project_id: int,
    functional_case_id: int,
    asset_type: str,
    asset_id: int,
    link_type: str = "primary",
    coverage_note: Optional[str] = None,
    username: str,
) -> TestAssetLink:
    await _assert_functional_case(project_id, functional_case_id)
    await _assert_asset(project_id, asset_type, asset_id)
    lt = (link_type or "primary").strip()
    if lt not in LINK_TYPES:
        raise HTTPException(status_code=400, detail="link_type 无效")

    existing = await TestAssetLink.get_or_none(
        project_id=project_id,
        functional_case_id=functional_case_id,
        asset_type=asset_type,
        asset_id=asset_id,
        is_del=False,
    )
    if existing:
        existing.link_type = lt
        existing.coverage_note = coverage_note
        existing.update_by = username
        await existing.save()
        await refresh_scope_automation_status(project_id, [functional_case_id])
        return existing

    row = await TestAssetLink.create(
        project_id=project_id,
        functional_case_id=functional_case_id,
        asset_type=asset_type,
        asset_id=asset_id,
        link_type=lt,
        coverage_note=coverage_note,
        create_by=username,
        update_by=username,
    )
    await refresh_scope_automation_status(project_id, [functional_case_id])
    return row


async def list_asset_links(
    project_id: int,
    *,
    functional_case_id: Optional[int] = None,
    asset_type: Optional[str] = None,
    asset_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    q = TestAssetLink.filter(project_id=project_id, is_del=False)
    if functional_case_id is not None:
        q = q.filter(functional_case_id=functional_case_id)
    if asset_type:
        q = q.filter(asset_type=asset_type)
    if asset_id is not None:
        q = q.filter(asset_id=asset_id)
    rows = await q.order_by("id")
    name_map = await _batch_asset_names(project_id, rows)
    result = []
    for row in rows:
        name = name_map.get((row.asset_type, int(row.asset_id)), "(已失效)")
        result.append(asset_link_to_dict(row, asset_name=name))
    return result


async def _batch_asset_names(
    project_id: int, rows: list[TestAssetLink]
) -> dict[tuple[str, int], str]:
    """按 asset_type 批量取名称，避免 list_asset_links N+1。"""
    by_type: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        if row.asset_type and row.asset_id is not None:
            by_type[str(row.asset_type)].add(int(row.asset_id))
    out: dict[tuple[str, int], str] = {}
    for atype, ids in by_type.items():
        id_list = list(ids)
        if not id_list:
            continue
        if atype == "ui_case":
            found = await Case.filter(id__in=id_list, project_id=project_id, is_del=False)
            for c in found:
                out[(atype, int(c.id))] = c.name or ""
        elif atype == "app_case":
            found = await AppCase.filter(id__in=id_list, project_id=project_id, is_del=False)
            for c in found:
                out[(atype, int(c.id))] = c.name or ""
        elif atype == "api_case":
            found = await ApiTestCase.filter(id__in=id_list, project_id=project_id, is_del=False)
            for c in found:
                out[(atype, int(c.id))] = c.name or ""
        elif atype == "perf_scene":
            found = await PerfScene.filter(id__in=id_list, project_id=project_id, is_del=False)
            for c in found:
                out[(atype, int(c.id))] = c.name or ""
    return out


async def update_asset_link(
    link_id: int,
    project_id: int,
    payload: dict[str, Any],
    username: str,
) -> TestAssetLink:
    row = await TestAssetLink.get_or_none(id=link_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="映射不存在")
    if "link_type" in payload and payload["link_type"] is not None:
        if payload["link_type"] not in LINK_TYPES:
            raise HTTPException(status_code=400, detail="link_type 无效")
        row.link_type = payload["link_type"]
    if "coverage_note" in payload:
        row.coverage_note = payload["coverage_note"]
    if "health_status" in payload and payload["health_status"] is not None:
        if payload["health_status"] not in HEALTH_STATUSES:
            raise HTTPException(status_code=400, detail="health_status 无效")
        row.health_status = payload["health_status"]
    row.update_by = username
    await row.save()
    await refresh_scope_automation_status(project_id, [row.functional_case_id])
    return row


async def delete_asset_link(link_id: int, project_id: int, username: str) -> None:
    row = await TestAssetLink.get_or_none(id=link_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="映射不存在")
    case_id = row.functional_case_id
    apply_soft_delete(row, username)
    await row.save()
    await refresh_scope_automation_status(project_id, [case_id])


async def seed_asset_links_from_imports(project_id: int, username: str) -> dict[str, int]:
    """从 UI source 字段与功能用例 extra.ui_import/app_import 回填映射。"""
    created = 0
    skipped = 0
    touched_cases: set[int] = set()

    existing_rows = await TestAssetLink.filter(
        project_id=project_id, is_del=False, asset_type__in=["ui_case", "app_case"]
    ).values_list("functional_case_id", "asset_type", "asset_id")
    existing: set[tuple[int, str, int]] = {
        (int(fc), str(at), int(aid)) for fc, at, aid in existing_rows
    }

    valid_fc_ids = set(
        await AiFunctionalCase.filter(project_id=project_id, is_del=False).values_list("id", flat=True)
    )
    ui_id_set = set(
        await Case.filter(project_id=project_id, is_del=False).values_list("id", flat=True)
    )
    app_id_set = set(
        await AppCase.filter(project_id=project_id, is_del=False).values_list("id", flat=True)
    )

    ui_cases = await Case.filter(
        project_id=project_id,
        is_del=False,
        source_functional_case_id__not_isnull=True,
    )
    for ui in ui_cases:
        fc_id = ui.source_functional_case_id
        if not fc_id or int(fc_id) not in valid_fc_ids:
            skipped += 1
            continue
        key = (int(fc_id), "ui_case", int(ui.id))
        if key in existing:
            skipped += 1
            continue
        await TestAssetLink.create(
            project_id=project_id,
            functional_case_id=int(fc_id),
            asset_type="ui_case",
            asset_id=int(ui.id),
            link_type="primary",
            coverage_note="seeded from case.source_functional_case_id",
            create_by=username,
            update_by=username,
        )
        existing.add(key)
        created += 1
        touched_cases.add(int(fc_id))

    func_cases = await AiFunctionalCase.filter(project_id=project_id, is_del=False)
    for fc in func_cases:
        extra = fc.extra or {}
        ui_import = extra.get("ui_import") or {}
        ui_case_id = ui_import.get("ui_case_id")
        if ui_case_id:
            aid = int(ui_case_id)
            key = (int(fc.id), "ui_case", aid)
            if key in existing:
                skipped += 1
            elif aid not in ui_id_set:
                skipped += 1
            else:
                await TestAssetLink.create(
                    project_id=project_id,
                    functional_case_id=fc.id,
                    asset_type="ui_case",
                    asset_id=aid,
                    link_type="primary",
                    coverage_note="seeded from extra.ui_import",
                    create_by=username,
                    update_by=username,
                )
                existing.add(key)
                created += 1
                touched_cases.add(fc.id)

        app_import = extra.get("app_import") or {}
        app_case_id = app_import.get("app_case_id")
        if app_case_id:
            aid = int(app_case_id)
            key = (int(fc.id), "app_case", aid)
            if key in existing:
                skipped += 1
            elif aid not in app_id_set:
                skipped += 1
            else:
                await TestAssetLink.create(
                    project_id=project_id,
                    functional_case_id=fc.id,
                    asset_type="app_case",
                    asset_id=aid,
                    link_type="primary",
                    coverage_note="seeded from extra.app_import",
                    create_by=username,
                    update_by=username,
                )
                existing.add(key)
                created += 1
                touched_cases.add(fc.id)

    await refresh_scope_automation_status(project_id, touched_cases)
    return {"created": created, "skipped": skipped, "touched_cases": len(touched_cases)}
