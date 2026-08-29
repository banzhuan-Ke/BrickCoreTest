"""测试计划与手工运行服务"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from tortoise import transactions

from app.models.ai import AiFunctionalCase
from app.models.sys import Environment
from app.models.test_management import (
    TestAssetLink,
    TestPlan,
    TestPlanItem,
    TestPlanRun,
    TestPlanRunItem,
    TestPlanRunItemAttempt,
    TestRelease,
    TestReleaseScope,
)
from app.modules.test_management.rules import ASSET_TYPES
from app.modules.test_management.phase2_rules import (
    MANUAL_RESULTS,
    PLAN_STATUSES,
    PLAN_TYPES,
    RESULTS_NEED_MESSAGE,
)
from app.modules.test_management.service import (
    _dt_iso,
    assert_scope_editable,
    get_release_or_404,
    release_to_dict,
)


def plan_to_dict(row: TestPlan) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "release_id": row.release_id,
        "name": row.name,
        "plan_type": row.plan_type,
        "environment_id": row.environment_id,
        "entry_criteria": row.entry_criteria,
        "exit_criteria": row.exit_criteria,
        "status": row.status,
        "description": row.description,
        "create_by": row.create_by,
        "create_time": _dt_iso(row.create_time),
        "update_time": _dt_iso(row.update_time),
    }


def plan_item_to_dict(row: TestPlanItem) -> dict[str, Any]:
    return {
        "id": row.id,
        "plan_id": row.plan_id,
        "item_type": row.item_type,
        "source_scope_id": row.source_scope_id,
        "functional_case_id": row.functional_case_id,
        "asset_id": row.asset_id,
        "title": row.title,
        "execution_mode": row.execution_mode,
        "order_no": row.order_no,
        "required": row.required,
    }


def run_to_dict(row: TestPlanRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "plan_id": row.plan_id,
        "release_id": row.release_id,
        "environment_id": row.environment_id,
        "status": row.status,
        "trigger_source": row.trigger_source,
        "snapshot_json": row.snapshot_json or {},
        "started_at": _dt_iso(row.started_at),
        "finished_at": _dt_iso(row.finished_at),
        "create_by": row.create_by,
        "create_time": _dt_iso(row.create_time),
    }


def run_item_to_dict(
    row: TestPlanRunItem,
    *,
    case: Optional[AiFunctionalCase] = None,
) -> dict[str, Any]:
    data = {
        "id": row.id,
        "run_id": row.run_id,
        "plan_item_id": row.plan_item_id,
        "item_type": row.item_type,
        "functional_case_id": row.functional_case_id,
        "asset_id": row.asset_id,
        "title": row.title,
        "execution_mode": row.execution_mode,
        "required": row.required,
        "order_no": row.order_no,
        "status": row.status,
        "result_status": row.result_status,
        "assignee_id": row.assignee_id,
        "started_at": _dt_iso(row.started_at),
        "finished_at": _dt_iso(row.finished_at),
        "result_message": row.result_message,
        "evidence_json": row.evidence_json or {},
        "original_record_type": row.original_record_type,
        "original_record_id": row.original_record_id,
        "attempt_count": row.attempt_count,
        "case_precondition": None,
        "case_steps": None,
        "case_module": None,
        "source_requirement_id": None,
    }
    if case is not None:
        data["case_precondition"] = case.precondition or ""
        data["case_steps"] = case.steps or []
        data["case_module"] = case.module
        data["source_requirement_id"] = case.source_requirement_id
    return data


async def run_items_to_dicts(
    items: list[TestPlanRunItem],
    project_id: int,
) -> list[dict[str, Any]]:
    case_ids = [i.functional_case_id for i in items if i.functional_case_id]
    cases: dict[int, AiFunctionalCase] = {}
    if case_ids:
        cases = {
            c.id: c
            for c in await AiFunctionalCase.filter(
                id__in=case_ids, project_id=project_id, is_del=False
            )
        }
    return [run_item_to_dict(i, case=cases.get(i.functional_case_id)) for i in items]


async def run_item_to_dict_enriched(item: TestPlanRunItem, project_id: int) -> dict[str, Any]:
    rows = await run_items_to_dicts([item], project_id)
    return rows[0] if rows else run_item_to_dict(item)


async def get_plan_or_404(plan_id: int, project_id: int) -> TestPlan:
    row = await TestPlan.get_or_none(id=plan_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="测试计划不存在")
    return row


async def list_plans(project_id: int, release_id: int) -> list[TestPlan]:
    return await TestPlan.filter(
        project_id=project_id, release_id=release_id, is_del=False
    ).order_by("-id")


async def create_plan(
    *,
    project_id: int,
    release_id: int,
    name: str,
    username: str,
    plan_type: str = "regression",
    environment_id: Optional[int] = None,
    entry_criteria: Optional[str] = None,
    exit_criteria: Optional[str] = None,
    description: Optional[str] = None,
    from_scope: bool = True,
    scope_ids: Optional[list[int]] = None,
    include_automation: bool = False,
) -> TestPlan:
    release = await get_release_or_404(release_id, project_id)
    assert_scope_editable(release)
    title = (name or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="计划名称必填")
    pt = (plan_type or "regression").strip()
    if pt not in PLAN_TYPES:
        raise HTTPException(status_code=400, detail="plan_type 无效")
    if environment_id is not None:
        env = await Environment.get_or_none(
            id=environment_id, project_id=project_id, is_del=False
        )
        if not env:
            raise HTTPException(status_code=400, detail="环境不存在")

    plan = await TestPlan.create(
        project_id=project_id,
        release_id=release_id,
        name=title,
        plan_type=pt,
        environment_id=environment_id,
        entry_criteria=entry_criteria,
        exit_criteria=exit_criteria,
        description=description,
        status="draft",
        create_by=username,
        update_by=username,
    )

    if from_scope:
        await generate_manual_items_from_scope(
            plan, release, username, scope_ids=scope_ids
        )
        if include_automation:
            await generate_automation_items_from_scope(
                plan, release, username, scope_ids=scope_ids
            )
    return plan


async def generate_manual_items_from_scope(
    plan: TestPlan,
    release: TestRelease,
    username: str,
    *,
    scope_ids: Optional[list[int]] = None,
) -> dict[str, int]:
    assert_scope_editable(release)
    if plan.status in ("running", "completed"):
        raise HTTPException(status_code=400, detail="运行中或已完成的计划不可再生成项")
    q = TestReleaseScope.filter(
        release_id=release.id, project_id=plan.project_id, is_del=False
    )
    if scope_ids:
        q = q.filter(id__in=[int(x) for x in scope_ids])
    scopes = await q.order_by("id")
    case_ids = [s.functional_case_id for s in scopes]
    cases = {
        c.id: c
        for c in await AiFunctionalCase.filter(
            id__in=case_ids, project_id=plan.project_id, is_del=False
        )
    }
    existing = set(
        await TestPlanItem.filter(
            plan_id=plan.id, is_del=False, functional_case_id__not_isnull=True
        ).values_list("functional_case_id", flat=True)
    )
    created = 0
    order = await TestPlanItem.filter(plan_id=plan.id, is_del=False).count()
    for scope in scopes:
        if scope.functional_case_id in existing:
            continue
        case = cases.get(scope.functional_case_id)
        if not case:
            continue
        order += 1
        await TestPlanItem.create(
            project_id=plan.project_id,
            plan_id=plan.id,
            item_type="functional_manual",
            source_scope_id=scope.id,
            functional_case_id=case.id,
            title=case.title,
            execution_mode="manual",
            order_no=order,
            required=True,
            create_by=username,
            update_by=username,
        )
        created += 1
    return {"created": created}


async def generate_automation_items_from_scope(
    plan: TestPlan,
    release: TestRelease,
    username: str,
    *,
    scope_ids: Optional[list[int]] = None,
    link_types: Optional[list[str]] = None,
) -> dict[str, int]:
    """从范围功能用例的资产映射生成自动化计划项（primary/regression）。"""
    assert_scope_editable(release)
    if plan.status in ("running", "completed"):
        raise HTTPException(status_code=400, detail="运行中或已完成的计划不可再生成项")
    q = TestReleaseScope.filter(
        release_id=release.id, project_id=plan.project_id, is_del=False
    )
    if scope_ids:
        q = q.filter(id__in=[int(x) for x in scope_ids])
    scopes = await q.order_by("id")
    case_ids = [s.functional_case_id for s in scopes]
    if not case_ids:
        return {"created": 0}

    allowed_lt = set(link_types or ("primary", "regression"))
    links = await TestAssetLink.filter(
        project_id=plan.project_id,
        functional_case_id__in=case_ids,
        is_del=False,
        link_type__in=list(allowed_lt),
    ).order_by("functional_case_id", "id")

    existing_keys = set()
    for row in await TestPlanItem.filter(plan_id=plan.id, is_del=False, execution_mode="automation"):
        existing_keys.add((row.functional_case_id, row.item_type, row.asset_id))

    scope_by_case = {s.functional_case_id: s for s in scopes}
    created = 0
    order = await TestPlanItem.filter(plan_id=plan.id, is_del=False).count()
    for link in links:
        if link.asset_type not in ASSET_TYPES:
            continue
        scope = scope_by_case.get(link.functional_case_id)
        if not scope:
            continue
        key = (link.functional_case_id, link.asset_type, link.asset_id)
        if key in existing_keys:
            continue
        from app.modules.test_management.service import preview_asset_name

        try:
            asset_name = await preview_asset_name(
                plan.project_id, link.asset_type, link.asset_id
            )
        except HTTPException:
            continue
        order += 1
        title = asset_name or f"{link.asset_type}#{link.asset_id}"
        await TestPlanItem.create(
            project_id=plan.project_id,
            plan_id=plan.id,
            item_type=link.asset_type,
            source_scope_id=scope.id,
            functional_case_id=link.functional_case_id,
            asset_id=link.asset_id,
            title=title,
            execution_mode="automation",
            order_no=order,
            required=link.link_type == "primary",
            create_by=username,
            update_by=username,
        )
        existing_keys.add(key)
        created += 1
    return {"created": created}


async def list_plan_items(plan: TestPlan) -> list[TestPlanItem]:
    return await TestPlanItem.filter(
        plan_id=plan.id, project_id=plan.project_id, is_del=False
    ).order_by("order_no", "id")


async def remove_plan_item(plan: TestPlan, item_id: int, username: str) -> None:
    release = await get_release_or_404(plan.release_id, plan.project_id)
    if release.status in ("released", "archived"):
        raise HTTPException(status_code=400, detail="版本已发布/归档，不可改计划项")
    if plan.status in ("running", "completed"):
        raise HTTPException(status_code=400, detail="运行中或已完成的计划不可删除项")
    row = await TestPlanItem.get_or_none(
        id=item_id, plan_id=plan.id, project_id=plan.project_id, is_del=False
    )
    if not row:
        raise HTTPException(status_code=404, detail="计划项不存在")
    from app.modules.test_management.service import apply_soft_delete

    apply_soft_delete(row, username)
    await row.save()


async def update_plan(plan: TestPlan, payload: dict[str, Any], username: str) -> TestPlan:
    release = await get_release_or_404(plan.release_id, plan.project_id)
    if release.status in ("released", "archived"):
        raise HTTPException(status_code=400, detail="版本已发布/归档，不可改计划")
    if plan.status in ("running", "completed"):
        raise HTTPException(status_code=400, detail="运行中或已完成的计划不可改")
    if "name" in payload and payload["name"] is not None:
        name = str(payload["name"]).strip()
        if not name:
            raise HTTPException(status_code=400, detail="名称不能为空")
        plan.name = name
    if "plan_type" in payload and payload["plan_type"] is not None:
        if payload["plan_type"] not in PLAN_TYPES:
            raise HTTPException(status_code=400, detail="plan_type 无效")
        plan.plan_type = payload["plan_type"]
    if "status" in payload and payload["status"] is not None:
        raise HTTPException(status_code=400, detail="计划状态请通过运行/取消接口变更，不可直接修改")
    for field in ("environment_id", "entry_criteria", "exit_criteria", "description"):
        if field in payload:
            if field == "environment_id" and payload[field] is not None:
                env = await Environment.get_or_none(
                    id=payload[field], project_id=plan.project_id, is_del=False
                )
                if not env:
                    raise HTTPException(status_code=400, detail="环境不存在")
            setattr(plan, field, payload[field])
    plan.update_by = username
    await plan.save()
    return plan


async def soft_delete_plan(plan: TestPlan, username: str) -> None:
    if plan.status == "running":
        raise HTTPException(status_code=400, detail="运行中的计划不可删除")
    release = await get_release_or_404(plan.release_id, plan.project_id)
    if release.status in ("released", "archived"):
        raise HTTPException(status_code=400, detail="版本已发布/归档，不可删除计划")
    plan.is_del = True
    plan.update_by = username
    await plan.save()
    await TestPlanItem.filter(plan_id=plan.id, is_del=False).update(
        is_del=True, update_by=username
    )


async def create_plan_run(
    plan: TestPlan,
    *,
    username: str,
    environment_id: Optional[int] = None,
    item_ids: Optional[list[int]] = None,
    trigger_source: str = "web",
    dispatch_automation: bool = False,
    device_id: Optional[str] = None,
    user_permissions: Optional[set[str]] = None,
    is_superuser: bool = False,
) -> TestPlanRun:
    async with transactions.in_transaction():
        plan = await TestPlan.select_for_update().get(
            id=plan.id, project_id=plan.project_id, is_del=False
        )
        release = await get_release_or_404(plan.release_id, plan.project_id)
        if release.status in ("released", "archived"):
            raise HTTPException(status_code=400, detail="版本已发布/归档，不可创建运行")
        if plan.status == "cancelled":
            raise HTTPException(status_code=400, detail="已取消的计划不可运行")
        if plan.status == "running":
            raise HTTPException(status_code=400, detail="计划已有运行中的批次，请先完成或取消")
        other_running = await TestPlanRun.filter(
            plan_id=plan.id, project_id=plan.project_id, is_del=False, status="running"
        ).exists()
        if other_running:
            raise HTTPException(status_code=400, detail="计划已有运行中的批次，请先完成或取消")

        env_id = environment_id if environment_id is not None else plan.environment_id
        env_snap = None
        if env_id is not None:
            env = await Environment.get_or_none(
                id=env_id, project_id=plan.project_id, is_del=False
            )
            if not env:
                raise HTTPException(status_code=400, detail="环境不存在")
            env_snap = {"id": env.id, "name": env.name, "host": env.host, "base_url": env.host}

        items_q = TestPlanItem.filter(plan_id=plan.id, project_id=plan.project_id, is_del=False)
        if item_ids:
            items_q = items_q.filter(id__in=[int(x) for x in item_ids])
        items = await items_q.order_by("order_no", "id")
        if not items:
            raise HTTPException(status_code=400, detail="计划无待测项")

        from app.modules.test_management.premium_gateway import tm_premium_ready

        if tm_premium_ready():
            from app.modules.test_management.tm_quality_gate_settings import load_tm_quality_gate_settings

            quality_rules = await load_tm_quality_gate_settings(plan.project_id)
        else:
            quality_rules = {}
        now = datetime.now(timezone.utc)
        run = await TestPlanRun.create(
            project_id=plan.project_id,
            plan_id=plan.id,
            release_id=release.id,
            environment_id=env_id,
            status="running",
            trigger_source=trigger_source or "web",
            snapshot_json={
                "release": release_to_dict(release),
                "plan": {"id": plan.id, "name": plan.name, "plan_type": plan.plan_type},
                "environment": env_snap,
                "quality_rules": quality_rules,
            },
            started_at=now,
            create_by=username,
            update_by=username,
        )
        for it in items:
            await TestPlanRunItem.create(
                project_id=plan.project_id,
                run_id=run.id,
                plan_item_id=it.id,
                item_type=it.item_type,
                functional_case_id=it.functional_case_id,
                asset_id=it.asset_id,
                title=it.title,
                execution_mode=it.execution_mode,
                required=it.required,
                order_no=it.order_no,
                status="pending",
                result_status="not_run",
                create_by=username,
                update_by=username,
            )
        plan.status = "running"
        plan.update_by = username
        await plan.save()

    if dispatch_automation:
        from app.modules.test_management.execution_bridge import dispatch_run_automation_items

        try:
            await dispatch_run_automation_items(
                run,
                username=username,
                device_id=device_id,
                user_permissions=user_permissions,
                is_superuser=is_superuser,
            )
            run = await TestPlanRun.get(id=run.id)
        except Exception as exc:
            # 派发失败时避免留下永远 running 的空批次
            try:
                fresh = await TestPlanRun.get_or_none(
                    id=run.id, project_id=run.project_id, is_del=False
                )
                if fresh and fresh.status == "running":
                    await cancel_run(fresh, username)
            except Exception:
                pass
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(
                status_code=500,
                detail=f"自动化派发失败，已取消本批运行：{exc}",
            ) from exc
    return run


async def get_run_or_404(run_id: int, project_id: int) -> TestPlanRun:
    row = await TestPlanRun.get_or_none(id=run_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="计划运行不存在")
    return row


async def list_runs(plan_id: int, project_id: int) -> list[TestPlanRun]:
    return await TestPlanRun.filter(
        plan_id=plan_id, project_id=project_id, is_del=False
    ).order_by("-id")


async def list_run_items(run: TestPlanRun) -> list[TestPlanRunItem]:
    return await TestPlanRunItem.filter(
        run_id=run.id, project_id=run.project_id, is_del=False
    ).order_by("order_no", "id")


async def submit_manual_result(
    run: TestPlanRun,
    item_id: int,
    *,
    result_status: str,
    result_message: Optional[str],
    username: str,
    assignee_id: Optional[int] = None,
    evidence_json: Optional[dict] = None,
    actor_user_id: Optional[int] = None,
) -> TestPlanRunItem:
    if run.status != "running":
        raise HTTPException(status_code=400, detail="仅运行中的批次可提交结果")
    result = (result_status or "").strip()
    if result not in MANUAL_RESULTS or result == "not_run":
        raise HTTPException(status_code=400, detail="result_status 无效")
    if result in RESULTS_NEED_MESSAGE and not (result_message or "").strip():
        raise HTTPException(status_code=400, detail="失败/阻塞必须填写结果说明")

    item = await TestPlanRunItem.get_or_none(
        id=item_id, run_id=run.id, project_id=run.project_id, is_del=False
    )
    if not item:
        raise HTTPException(status_code=404, detail="运行项不存在")
    if item.execution_mode != "manual":
        raise HTTPException(status_code=400, detail="非手工项不可手工提交")

    old_assignee_id = item.assignee_id
    now = datetime.now(timezone.utc)
    item.attempt_count = int(item.attempt_count or 0) + 1
    item.result_status = result
    item.result_message = result_message
    item.evidence_json = evidence_json or {}
    item.status = "done"
    item.finished_at = now
    if item.started_at is None:
        item.started_at = now
    if assignee_id is not None:
        item.assignee_id = assignee_id
    item.update_by = username
    await item.save()

    await TestPlanRunItemAttempt.create(
        project_id=run.project_id,
        run_item_id=item.id,
        attempt_no=item.attempt_count,
        result_status=result,
        result_message=result_message,
        evidence_json=evidence_json or {},
        operator=username,
    )

    await _maybe_complete_run(run, username)

    if assignee_id is not None and assignee_id != old_assignee_id:
        await _notify_run_item_assignee_if_needed(
            run=run,
            item=item,
            assignee_id=assignee_id,
            actor_user_id=actor_user_id,
        )

    return item


async def update_run_item_assignee(
    run: TestPlanRun,
    item_id: int,
    *,
    assignee_id: Optional[int],
    clear_assignee: bool,
    username: str,
    actor_user_id: Optional[int] = None,
) -> TestPlanRunItem:
    if run.status != "running":
        raise HTTPException(status_code=400, detail="仅运行中的批次可指派执行人")
    item = await TestPlanRunItem.get_or_none(
        id=item_id, run_id=run.id, project_id=run.project_id, is_del=False
    )
    if not item:
        raise HTTPException(status_code=404, detail="运行项不存在")

    old_assignee = item.assignee_id
    new_assignee = None if clear_assignee else assignee_id
    if clear_assignee:
        item.assignee_id = None
    elif assignee_id is not None:
        item.assignee_id = assignee_id
    else:
        raise HTTPException(status_code=400, detail="请指定 assignee_id 或 clear_assignee")

    if new_assignee == old_assignee:
        return item

    item.update_by = username
    await item.save(update_fields=["assignee_id", "update_by", "update_time"])

    if new_assignee:
        await _notify_run_item_assignee_if_needed(
            run=run,
            item=item,
            assignee_id=new_assignee,
            actor_user_id=actor_user_id,
        )
    return item


async def _notify_run_item_assignee_if_needed(
    *,
    run: TestPlanRun,
    item: TestPlanRunItem,
    assignee_id: int,
    actor_user_id: Optional[int],
) -> None:
    from app.modules.test_management.premium_gateway import soft_premium_call

    plan = await TestPlan.get_or_none(id=run.plan_id, is_del=False)
    release = None
    if run.release_id:
        release = await TestRelease.get_or_none(
            id=run.release_id, project_id=run.project_id, is_del=False
        )
    await soft_premium_call(
        "assignment_notify_service",
        "notify_plan_run_item_assigned",
        project_id=run.project_id,
        run_id=run.id,
        run_item_id=item.id,
        item_title=item.title or "",
        assignee_id=assignee_id,
        actor_id=actor_user_id,
        release_id=run.release_id,
        release_name=release.name if release else None,
        release_status=release.status if release else None,
        plan_name=plan.name if plan else None,
    )


async def cancel_run(run: TestPlanRun, username: str) -> tuple[TestPlanRun, dict[str, int]]:
    if run.status != "running":
        raise HTTPException(status_code=400, detail="仅运行中的批次可取消")
    from app.modules.test_management.execution_bridge import stop_dispatched_automation_for_run
    from app.modules.test_management.result_normalizer import TERMINAL_RESULTS

    stop_summary = await stop_dispatched_automation_for_run(run)
    async with transactions.in_transaction():
        locked = await TestPlanRun.select_for_update().get_or_none(
            id=run.id, project_id=run.project_id, is_del=False
        )
        if not locked or locked.status != "running":
            raise HTTPException(status_code=400, detail="仅运行中的批次可取消")
        locked.status = "cancelled"
        locked.finished_at = datetime.now(timezone.utc)
        locked.update_by = username
        await locked.save()
        # 仅跳过非终态项；已通过/失败等保留。与 runner 回写竞态靠 sync 侧拒绝覆盖 skipped。
        await TestPlanRunItem.filter(
            run_id=locked.id, is_del=False
        ).exclude(result_status__in=list(TERMINAL_RESULTS)).update(
            status="done",
            result_status="skipped",
            result_message="运行已取消",
            update_by=username,
        )
        run = locked
    await _sync_plan_status_after_run(run.plan_id, username, prefer="ready")
    return run, stop_summary


async def _maybe_complete_run(run: TestPlanRun, username: str) -> None:
    from app.modules.test_management.result_normalizer import TERMINAL_RESULTS

    # 仍有非终态则不收口（COUNT，避免全量加载）
    pending = await TestPlanRunItem.filter(run_id=run.id, is_del=False).exclude(
        result_status__in=list(TERMINAL_RESULTS)
    ).count()
    if pending > 0:
        return
    total = await TestPlanRunItem.filter(run_id=run.id, is_del=False).count()
    if total == 0:
        return
    run.status = "completed"
    run.finished_at = datetime.now(timezone.utc)
    run.update_by = username
    await run.save()
    await _sync_plan_status_after_run(run.plan_id, username, prefer="completed")


async def _sync_plan_status_after_run(
    plan_id: int, username: str, *, prefer: str
) -> None:
    """运行结束后把计划从 running 收口；若还有进行中运行则保持 running。"""
    plan = await TestPlan.get_or_none(id=plan_id, is_del=False)
    if not plan or plan.status != "running":
        return
    other = await TestPlanRun.filter(
        plan_id=plan.id, is_del=False, status="running"
    ).exists()
    if other:
        return
    if prefer not in PLAN_STATUSES:
        prefer = "completed"
    plan.status = prefer
    plan.update_by = username
    await plan.save()


async def list_attempts(
    run_item_id: int, project_id: int, *, run_id: Optional[int] = None
) -> list[dict[str, Any]]:
    item_q = TestPlanRunItem.filter(
        id=run_item_id, project_id=project_id, is_del=False
    )
    if run_id is not None:
        item_q = item_q.filter(run_id=run_id)
    item = await item_q.first()
    if not item:
        raise HTTPException(status_code=404, detail="运行项不存在")
    rows = await TestPlanRunItemAttempt.filter(
        run_item_id=item.id, project_id=project_id
    ).order_by("attempt_no")
    return [
        {
            "id": r.id,
            "attempt_no": r.attempt_no,
            "result_status": r.result_status,
            "result_message": r.result_message,
            "evidence_json": r.evidence_json or {},
            "operator": r.operator,
            "create_time": _dt_iso(r.create_time),
        }
        for r in rows
    ]
