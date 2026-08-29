"""测试计划与手工运行 API"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.platform.auth import _load_user_permission_codes, is_authenticated, require_permissions
from app.core.platform.permissions import (
    TEST_MANUAL_EXECUTE,
    TEST_PLAN_EDIT,
    TEST_PLAN_RUN,
    TEST_PLAN_VIEW,
)
from app.modules.test_management import plan_service as svc
from app.schemas.test_management import (
    AutomationDispatchBody,
    ManualResultBody,
    PlanCreateBody,
    PlanRunCreateBody,
    PlanUpdateBody,
    RunItemAssigneeBody,
    StandardResponse,
)

router = APIRouter(tags=["测试管理-计划"])


def _username(user_info: dict) -> str:
    return user_info.get("username") or user_info.get("sub") or "system"


def _user_id(user_info: dict) -> Optional[int]:
    uid = user_info.get("id")
    return int(uid) if uid is not None else None


async def _dispatch_auth_context(user_info: dict) -> tuple[set[str], bool]:
    if user_info.get("is_superuser"):
        return set(), True
    uid = user_info.get("id")
    if uid is None:
        return set(), False
    return await _load_user_permission_codes(int(uid)), False


@router.get(
    "/plans",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_PLAN_VIEW))],
)
async def list_plans(
    project_id: int = Query(...),
    release_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    rows = await svc.list_plans(project_id, release_id)
    return StandardResponse(data=[svc.plan_to_dict(r) for r in rows])


@router.post(
    "/plans",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_PLAN_EDIT))],
)
async def create_plan(
    body: PlanCreateBody,
    user_info: dict = Depends(is_authenticated),
):
    row = await svc.create_plan(
        project_id=body.project_id,
        release_id=body.release_id,
        name=body.name,
        plan_type=body.plan_type,
        environment_id=body.environment_id,
        entry_criteria=body.entry_criteria,
        exit_criteria=body.exit_criteria,
        description=body.description,
        from_scope=body.from_scope,
        scope_ids=body.scope_ids,
        include_automation=body.include_automation,
        username=_username(user_info),
    )
    return StandardResponse(data=svc.plan_to_dict(row))


@router.get(
    "/plans/{plan_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_PLAN_VIEW))],
)
async def get_plan(
    plan_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    plan = await svc.get_plan_or_404(plan_id, project_id)
    items = await svc.list_plan_items(plan)
    runs = await svc.list_runs(plan_id, project_id)
    return StandardResponse(
        data={
            "plan": svc.plan_to_dict(plan),
            "items": [svc.plan_item_to_dict(i) for i in items],
            "runs": [svc.run_to_dict(r) for r in runs],
        }
    )


@router.patch(
    "/plans/{plan_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_PLAN_EDIT))],
)
async def update_plan(
    plan_id: int,
    body: PlanUpdateBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    plan = await svc.get_plan_or_404(plan_id, project_id)
    plan = await svc.update_plan(plan, body.model_dump(exclude_unset=True), _username(user_info))
    return StandardResponse(data=svc.plan_to_dict(plan))


@router.delete(
    "/plans/{plan_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_PLAN_EDIT))],
)
async def delete_plan(
    plan_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    plan = await svc.get_plan_or_404(plan_id, project_id)
    await svc.soft_delete_plan(plan, _username(user_info))
    return StandardResponse(message="已删除")


@router.delete(
    "/plans/{plan_id}/items/{item_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_PLAN_EDIT))],
)
async def delete_plan_item(
    plan_id: int,
    item_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    plan = await svc.get_plan_or_404(plan_id, project_id)
    await svc.remove_plan_item(plan, item_id, _username(user_info))
    return StandardResponse(message="已删除")


@router.post(
    "/plans/{plan_id}/generate-from-scope",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_PLAN_EDIT))],
)
async def generate_from_scope(
    plan_id: int,
    project_id: int = Query(...),
    scope_ids: Optional[str] = Query(None, description="逗号分隔 scope id"),
    user_info: dict = Depends(is_authenticated),
):
    plan = await svc.get_plan_or_404(plan_id, project_id)
    from app.modules.test_management.service import assert_scope_editable, get_release_or_404

    release = await get_release_or_404(plan.release_id, project_id)
    assert_scope_editable(release)
    if plan.status in ("running", "completed"):
        raise HTTPException(status_code=400, detail="运行中或已完成的计划不可再生成项")
    ids = None
    if scope_ids:
        ids = [int(x) for x in scope_ids.split(",") if x.strip()]
    data = await svc.generate_manual_items_from_scope(
        plan, release, _username(user_info), scope_ids=ids
    )
    return StandardResponse(data=data)


@router.post(
    "/plans/{plan_id}/generate-automation-from-scope",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_PLAN_EDIT))],
)
async def generate_automation_from_scope(
    plan_id: int,
    project_id: int = Query(...),
    scope_ids: Optional[str] = Query(None, description="逗号分隔 scope id"),
    user_info: dict = Depends(is_authenticated),
):
    plan = await svc.get_plan_or_404(plan_id, project_id)
    from app.modules.test_management.service import assert_scope_editable, get_release_or_404

    release = await get_release_or_404(plan.release_id, project_id)
    assert_scope_editable(release)
    if plan.status in ("running", "completed"):
        raise HTTPException(status_code=400, detail="运行中或已完成的计划不可再生成项")
    ids = None
    if scope_ids:
        ids = [int(x) for x in scope_ids.split(",") if x.strip()]
    data = await svc.generate_automation_items_from_scope(
        plan, release, _username(user_info), scope_ids=ids
    )
    return StandardResponse(data=data)


@router.post(
    "/plans/{plan_id}/runs",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_PLAN_RUN))],
)
async def create_run(
    plan_id: int,
    body: PlanRunCreateBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    plan = await svc.get_plan_or_404(plan_id, project_id)
    perms, is_superuser = await _dispatch_auth_context(user_info)
    run = await svc.create_plan_run(
        plan,
        username=_username(user_info),
        environment_id=body.environment_id,
        item_ids=body.item_ids,
        trigger_source=body.trigger_source,
        dispatch_automation=body.dispatch_automation,
        device_id=body.device_id,
        user_permissions=perms,
        is_superuser=is_superuser,
    )
    return StandardResponse(data=svc.run_to_dict(run))


@router.post(
    "/plan-runs/{run_id}/dispatch-automation",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_PLAN_RUN))],
)
async def dispatch_automation(
    run_id: int,
    body: AutomationDispatchBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.test_management.execution_bridge import dispatch_run_automation_items

    run = await svc.get_run_or_404(run_id, project_id)
    if run.status != "running":
        raise HTTPException(status_code=400, detail="仅运行中的批次可派发自动化")
    perms, is_superuser = await _dispatch_auth_context(user_info)
    data = await dispatch_run_automation_items(
        run,
        username=_username(user_info),
        device_id=body.device_id,
        user_permissions=perms,
        is_superuser=is_superuser,
    )
    run = await svc.get_run_or_404(run_id, project_id)
    items = await svc.list_run_items(run)
    return StandardResponse(
        data={
            "run": svc.run_to_dict(run),
            **data,
            "items": await svc.run_items_to_dicts(items, project_id),
        }
    )


@router.post(
    "/plan-runs/{run_id}/sync-automation",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_PLAN_RUN))],
)
async def sync_automation(
    run_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    from app.modules.test_management.execution_bridge import sync_run_automation_items

    run = await svc.get_run_or_404(run_id, project_id)
    data = await sync_run_automation_items(run, username=_username(user_info))
    run = await svc.get_run_or_404(run_id, project_id)
    items = await svc.list_run_items(run)
    return StandardResponse(
        data={
            "run": svc.run_to_dict(run),
            "items": await svc.run_items_to_dicts(items, project_id),
            **data,
        }
    )


@router.get(
    "/plan-runs/{run_id}",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_PLAN_VIEW))],
)
async def get_run(
    run_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    run = await svc.get_run_or_404(run_id, project_id)
    items = await svc.list_run_items(run)
    return StandardResponse(
        data={
            "run": svc.run_to_dict(run),
            "items": await svc.run_items_to_dicts(items, project_id),
        }
    )


@router.post(
    "/plan-runs/{run_id}/items/{item_id}/manual-result",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_MANUAL_EXECUTE))],
)
async def submit_manual_result(
    run_id: int,
    item_id: int,
    body: ManualResultBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    run = await svc.get_run_or_404(run_id, project_id)
    item = await svc.submit_manual_result(
        run,
        item_id,
        result_status=body.result_status,
        result_message=body.result_message,
        username=_username(user_info),
        assignee_id=body.assignee_id,
        evidence_json=body.evidence_json,
        actor_user_id=_user_id(user_info),
    )
    run = await svc.get_run_or_404(run_id, project_id)
    return StandardResponse(
        data={
            "item": await svc.run_item_to_dict_enriched(item, project_id),
            "run": svc.run_to_dict(run),
        }
    )


@router.patch(
    "/plan-runs/{run_id}/items/{item_id}/assignee",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_PLAN_RUN))],
)
async def update_run_item_assignee(
    run_id: int,
    item_id: int,
    body: RunItemAssigneeBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    run = await svc.get_run_or_404(run_id, project_id)
    item = await svc.update_run_item_assignee(
        run,
        item_id,
        assignee_id=body.assignee_id,
        clear_assignee=body.clear_assignee,
        username=_username(user_info),
        actor_user_id=_user_id(user_info),
    )
    return StandardResponse(data=await svc.run_item_to_dict_enriched(item, project_id))


@router.get(
    "/plan-runs/{run_id}/items/{item_id}/attempts",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_PLAN_VIEW))],
)
async def list_attempts(
    run_id: int,
    item_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    await svc.get_run_or_404(run_id, project_id)
    data = await svc.list_attempts(item_id, project_id, run_id=run_id)
    return StandardResponse(data=data)


@router.post(
    "/plan-runs/{run_id}/cancel",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_PLAN_RUN))],
)
async def cancel_run(
    run_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    run = await svc.get_run_or_404(run_id, project_id)
    run, stop_summary = await svc.cancel_run(run, _username(user_info))
    return StandardResponse(
        data={"run": svc.run_to_dict(run), "automation_stop": stop_summary}
    )
