"""App 计划 CRUD"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.platform.auth import get_current_username, is_authenticated, require_permissions
from app.core.shared.catalog_utils import resolve_catalog
from app.core.platform.permissions import APP_PLAN_EDIT, APP_PLAN_VIEW
from app.modules.ui.ui_project_guard import assert_user_project_member, assert_user_project_viewer
from app.models.app import AppPlan, AppPlanExecution, AppSuite
from app.models.sys import Project
from app.schemas.app import AddAppPlanForm, AppPlanSchemas, UpdateAppPlanForm, UpdateAppPlanSuitesForm

router = APIRouter(prefix="/plans", dependencies=[Depends(is_authenticated)], tags=["App计划"])


@router.post("", response_model=AppPlanSchemas, status_code=201, dependencies=[Depends(require_permissions(APP_PLAN_EDIT))])
async def create_plan(
    item: AddAppPlanForm,
    user_info: dict = Depends(require_permissions(APP_PLAN_EDIT)),
    username: str = Depends(get_current_username),
):
    await assert_user_project_member(user_info, item.project_id)
    if not await Project.get_or_none(id=item.project_id, is_del=False):
        raise HTTPException(status_code=422, detail="项目不存在")
    if item.catalog_id is not None:
        await resolve_catalog(item.project_id, item.catalog_id)
    payload = item.model_dump()
    payload["username"] = username
    return await AppPlan.create(**payload, is_del=False, update_by=username)


@router.get("", dependencies=[Depends(require_permissions(APP_PLAN_VIEW))])
async def list_plans(
    project_id: int,
    page: int = 1,
    size: int = 10,
    name: str | None = None,
    user_info: dict = Depends(require_permissions(APP_PLAN_VIEW)),
):
    await assert_user_project_viewer(user_info, project_id)
    query = AppPlan.filter(project_id=project_id, is_del=False).order_by("-id")
    if name:
        query = query.filter(name__icontains=name)
    total = await query.count()
    data = []
    for plan in await query.offset((page - 1) * size).limit(size).prefetch_related("suites"):
        suites = [s for s in plan.suites if not s.is_del]
        last = await AppPlanExecution.filter(plan_id=plan.id, is_del=False).order_by("-id").first()
        data.append({
            "id": plan.id,
            "name": plan.name,
            "username": plan.username,
            "suites_count": len(suites),
            "parallel": plan.parallel,
            "status": last.status if last else "等待执行",
            "create_time": plan.create_time,
        })
    return {"data": data, "total": total}


@router.get("/{plan_id}", response_model=AppPlanSchemas, dependencies=[Depends(require_permissions(APP_PLAN_VIEW))])
async def get_plan(plan_id: int, user_info: dict = Depends(require_permissions(APP_PLAN_VIEW))):
    plan = await AppPlan.get_or_none(id=plan_id, is_del=False)
    if not plan:
        raise HTTPException(status_code=422, detail="计划不存在")
    await assert_user_project_viewer(user_info, plan.project_id)
    return plan


@router.put("/{plan_id}", response_model=AppPlanSchemas, dependencies=[Depends(require_permissions(APP_PLAN_EDIT))])
async def update_plan(
    plan_id: int,
    item: UpdateAppPlanForm,
    user_info: dict = Depends(require_permissions(APP_PLAN_EDIT)),
    username: str = Depends(get_current_username),
):
    plan = await AppPlan.get_or_none(id=plan_id, is_del=False)
    if not plan:
        raise HTTPException(status_code=422, detail="计划不存在")
    await assert_user_project_member(user_info, plan.project_id)
    if item.catalog_id is not None:
        await resolve_catalog(plan.project_id, item.catalog_id)
    await plan.update_from_dict(item.model_dump(exclude_unset=True))
    plan.update_by = username
    await plan.save()
    return plan


@router.put("/{plan_id}/suites", dependencies=[Depends(require_permissions(APP_PLAN_EDIT))])
async def update_plan_suites(
    plan_id: int,
    item: UpdateAppPlanSuitesForm,
    user_info: dict = Depends(require_permissions(APP_PLAN_EDIT)),
):
    plan = await AppPlan.get_or_none(id=plan_id, is_del=False)
    if not plan:
        raise HTTPException(status_code=422, detail="计划不存在")
    await assert_user_project_member(user_info, plan.project_id)

    suite_ids = item.suite_ids or []
    suites: list[AppSuite] = []
    if suite_ids:
        suites = await AppSuite.filter(id__in=suite_ids, project_id=plan.project_id, is_del=False).all()
        found = {s.id for s in suites}
        missing = [sid for sid in suite_ids if sid not in found]
        if missing:
            raise HTTPException(status_code=422, detail=f"套件不存在或不属于当前项目: {missing}")

    await plan.suites.clear()
    if suites:
        await plan.suites.add(*suites)
    return {"ok": True, "suite_ids": [s.id for s in suites]}


@router.get("/{plan_id}/suites", dependencies=[Depends(require_permissions(APP_PLAN_VIEW))])
async def get_plan_suites(plan_id: int, user_info: dict = Depends(require_permissions(APP_PLAN_VIEW))):
    plan = await AppPlan.get_or_none(id=plan_id, is_del=False).prefetch_related("suites")
    if not plan:
        raise HTTPException(status_code=422, detail="计划不存在")
    await assert_user_project_viewer(user_info, plan.project_id)
    suite_list = []
    for su in plan.suites:
        if su.is_del:
            continue
        suite_list.append({
            "suite_id": su.id,
            "suite_name": su.name,
            "create_time": su.create_time,
            "update_time": su.update_time,
        })
    return {"suite_ids": [s["suite_id"] for s in suite_list], "suites": suite_list}


@router.delete("/{plan_id}", status_code=204, dependencies=[Depends(require_permissions(APP_PLAN_EDIT))])
async def delete_plan(plan_id: int, user_info: dict = Depends(require_permissions(APP_PLAN_EDIT))):
    plan = await AppPlan.get_or_none(id=plan_id, is_del=False)
    if not plan:
        raise HTTPException(status_code=422, detail="计划不存在")
    await assert_user_project_member(user_info, plan.project_id)
    plan.is_del = True
    await plan.save()
