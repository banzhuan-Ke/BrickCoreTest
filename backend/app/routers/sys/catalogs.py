from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends, status, Query
from tortoise.functions import Count

from app.schemas.sys import TestCatalogOut, TestCatalogCreate, TestCatalogUpdate, TestCatalogTreeNode
from app.models.sys import TestCatalog, Project
from app.models.ui import Case, Suite, Task
from app.models.http import ApiDefinition, ApiTestCase, ApiTestSuite, ApiTestPlan
from app.models.perf import PerfScene
from app.models.app import AppCase, AppSuite, AppPlan
from app.core.auth import is_authenticated, require_permissions, get_current_username
from app.core.permissions import MODULE_VIEW, MODULE_EDIT
from app.core.catalog_utils import build_catalog_tree, resolve_catalog, apply_catalog_filter

router = APIRouter(prefix="/catalogs", tags=["测试目录"], dependencies=[Depends(is_authenticated)])


def _catalog_to_dict(catalog: TestCatalog) -> dict:
    return {
        "id": catalog.id,
        "name": catalog.name,
        "project_id": catalog.project_id,
        "parent_id": catalog.parent_id,
        "sort": catalog.sort,
        "description": catalog.description,
        "username": catalog.username,
        "is_del": catalog.is_del,
        "create_time": catalog.create_time,
        "update_time": catalog.update_time,
    }


async def _count_by_catalog(model, catalog_ids: List[int], project_id: Optional[int] = None) -> Dict[int, int]:
    """按 catalog_id 聚合 COUNT，避免逐目录查询。"""
    if not catalog_ids:
        return {}
    qs = model.filter(catalog_id__in=catalog_ids, is_del=False)
    if project_id is not None and hasattr(model, "project_id"):
        qs = qs.filter(project_id=project_id)
    rows = await qs.annotate(cnt=Count("id")).group_by("catalog_id").values("catalog_id", "cnt")
    return {int(r["catalog_id"]): int(r["cnt"]) for r in rows if r.get("catalog_id")}


def _counts_to_row_fields(
    catalog_id: int,
    api_counts: Dict[int, int],
    case_counts: Dict[int, int],
    ui_case_counts: Dict[int, int],
    app_case_counts: Dict[int, int],
    ui_suite_counts: Dict[int, int],
    app_suite_counts: Dict[int, int],
    api_suite_counts: Dict[int, int],
    ui_task_counts: Dict[int, int],
    app_plan_counts: Dict[int, int],
    api_plan_counts: Dict[int, int],
    perf_scene_counts: Dict[int, int],
) -> dict:
    api_n = api_counts.get(catalog_id, 0)
    case_n = case_counts.get(catalog_id, 0)
    web_case_n = ui_case_counts.get(catalog_id, 0)
    app_case_n = app_case_counts.get(catalog_id, 0)
    web_suite_n = ui_suite_counts.get(catalog_id, 0)
    app_suite_n = app_suite_counts.get(catalog_id, 0)
    api_suite_n = api_suite_counts.get(catalog_id, 0)
    suite_n = web_suite_n + app_suite_n + api_suite_n
    return {
        "api_count": api_n,
        "case_count": case_n,
        "ui_case_count": web_case_n,
        "web_case_count": web_case_n,
        "app_case_count": app_case_n,
        "suite_count": suite_n,
        "web_suite_count": web_suite_n,
        "app_suite_count": app_suite_n,
        "ui_task_count": ui_task_counts.get(catalog_id, 0),
        "web_task_count": ui_task_counts.get(catalog_id, 0),
        "app_plan_count": app_plan_counts.get(catalog_id, 0),
        "api_plan_count": api_plan_counts.get(catalog_id, 0),
        "perf_scene_count": perf_scene_counts.get(catalog_id, 0),
        "api_defs": api_n,
        "api_cases": case_n,
        "ui_cases": web_case_n,
        "app_cases": app_case_n,
        "ui_suites": web_suite_n,
        "app_suites": app_suite_n,
        "api_suites": api_suite_n,
        "ui_tasks": ui_task_counts.get(catalog_id, 0),
        "app_plans": app_plan_counts.get(catalog_id, 0),
        "api_plans": api_plan_counts.get(catalog_id, 0),
        "perf_scenes": perf_scene_counts.get(catalog_id, 0),
    }


async def _attach_parent_names(flat: List[dict]) -> None:
    id_to_name = {item["id"]: item["name"] for item in flat}
    for item in flat:
        pid = item.get("parent_id")
        item["parent_name"] = id_to_name.get(pid) if pid else None


async def _attach_counts_to_catalog_rows(flat: List[dict], project_id: Optional[int] = None) -> None:
    catalog_ids = [item["id"] for item in flat]
    if not catalog_ids:
        return
    api_counts = await _count_by_catalog(ApiDefinition, catalog_ids, project_id)
    case_counts = await _count_by_catalog(ApiTestCase, catalog_ids, project_id)
    ui_case_counts = await _count_by_catalog(Case, catalog_ids, project_id)
    app_case_counts = await _count_by_catalog(AppCase, catalog_ids, project_id)
    ui_suite_counts = await _count_by_catalog(Suite, catalog_ids, project_id)
    app_suite_counts = await _count_by_catalog(AppSuite, catalog_ids, project_id)
    api_suite_counts = await _count_by_catalog(ApiTestSuite, catalog_ids, project_id)
    ui_task_counts = await _count_by_catalog(Task, catalog_ids, project_id)
    app_plan_counts = await _count_by_catalog(AppPlan, catalog_ids, project_id)
    api_plan_counts = await _count_by_catalog(ApiTestPlan, catalog_ids, project_id)
    perf_scene_counts = await _count_by_catalog(PerfScene, catalog_ids, project_id)
    for item in flat:
        item.update(_counts_to_row_fields(
            item["id"], api_counts, case_counts, ui_case_counts, app_case_counts,
            ui_suite_counts, app_suite_counts, api_suite_counts,
            ui_task_counts, app_plan_counts, api_plan_counts, perf_scene_counts,
        ))


async def _get_asset_counts(catalog_id: int) -> dict:
    api_n = await ApiDefinition.filter(catalog_id=catalog_id, is_del=False).count()
    case_n = await ApiTestCase.filter(catalog_id=catalog_id, is_del=False).count()
    ui_case_n = await Case.filter(catalog_id=catalog_id, is_del=False).count()
    app_case_n = await AppCase.filter(catalog_id=catalog_id, is_del=False).count()
    ui_suite_n = await Suite.filter(catalog_id=catalog_id, is_del=False).count()
    app_suite_n = await AppSuite.filter(catalog_id=catalog_id, is_del=False).count()
    api_suite_n = await ApiTestSuite.filter(catalog_id=catalog_id, is_del=False).count()
    ui_task_n = await Task.filter(catalog_id=catalog_id, is_del=False).count()
    app_plan_n = await AppPlan.filter(catalog_id=catalog_id, is_del=False).count()
    api_plan_n = await ApiTestPlan.filter(catalog_id=catalog_id, is_del=False).count()
    perf_scene_n = await PerfScene.filter(catalog_id=catalog_id, is_del=False).count()
    return {
        "api_count": api_n,
        "case_count": case_n,
        "ui_case_count": ui_case_n,
        "web_case_count": ui_case_n,
        "app_case_count": app_case_n,
        "suite_count": ui_suite_n + app_suite_n + api_suite_n,
        "web_suite_count": ui_suite_n,
        "app_suite_count": app_suite_n,
        "ui_task_count": ui_task_n,
        "web_task_count": ui_task_n,
        "app_plan_count": app_plan_n,
        "api_plan_count": api_plan_n,
        "perf_scene_count": perf_scene_n,
        "ui_cases": ui_case_n,
        "app_cases": app_case_n,
        "ui_suites": ui_suite_n,
        "app_suites": app_suite_n,
        "api_defs": api_n,
        "api_cases": case_n,
        "api_suites": api_suite_n,
        "ui_tasks": ui_task_n,
        "app_plans": app_plan_n,
        "api_plans": api_plan_n,
        "perf_scenes": perf_scene_n,
    }


def _asset_row(asset_type: str, row_id: int, name: str, username: str, create_time, api_id: int | None = None) -> dict:
    return {
        "id": row_id,
        "name": name,
        "asset_type": asset_type,
        "username": username or "—",
        "create_time": create_time,
        "api_id": api_id,
    }


async def _list_catalog_assets(catalog_id: int, project_id: int, include_children: bool) -> List[dict]:
    items: List[dict] = []

    async def fetch(model):
        qs = model.filter(is_del=False)
        if hasattr(model, "project_id"):
            qs = qs.filter(project_id=project_id)
        qs = await apply_catalog_filter(qs, project_id, catalog_id, include_children=include_children)
        return await qs.order_by("-id")

    for case in await fetch(Case):
        items.append(_asset_row("ui_case", case.id, case.name, case.username, case.create_time))
    for suite in await fetch(Suite):
        items.append(_asset_row("ui_suite", suite.id, suite.name, suite.username, suite.create_time))
    for task in await fetch(Task):
        items.append(_asset_row("ui_task", task.id, task.name, task.username, task.create_time))
    for case in await fetch(AppCase):
        items.append(_asset_row("app_case", case.id, case.name, case.username, case.create_time))
    for suite in await fetch(AppSuite):
        items.append(_asset_row("app_suite", suite.id, suite.name, suite.username, suite.create_time))
    for plan in await fetch(AppPlan):
        items.append(_asset_row("app_plan", plan.id, plan.name, plan.username, plan.create_time))
    for api in await fetch(ApiDefinition):
        items.append(_asset_row("api_def", api.id, api.name, api.create_by, api.create_time))
    for case in await fetch(ApiTestCase):
        items.append(_asset_row("api_case", case.id, case.name, case.create_by, case.create_time, api_id=case.api_id))
    for suite in await fetch(ApiTestSuite):
        items.append(_asset_row("api_suite", suite.id, suite.name, suite.create_by, suite.create_time))
    for plan in await fetch(ApiTestPlan):
        items.append(_asset_row("api_plan", plan.id, plan.name, plan.create_by, plan.create_time))
    for scene in await fetch(PerfScene):
        items.append(_asset_row("perf_scene", scene.id, scene.name, scene.create_by, scene.create_time))

    return items


async def _get_project_asset_totals(project_id: int) -> dict:
    """项目级资产总数（含未归属目录的资产）。"""
    web_case_n = await Case.filter(project_id=project_id, is_del=False).count()
    app_case_n = await AppCase.filter(project_id=project_id, is_del=False).count()
    web_suite_n = await Suite.filter(project_id=project_id, is_del=False).count()
    app_suite_n = await AppSuite.filter(project_id=project_id, is_del=False).count()
    api_suite_n = await ApiTestSuite.filter(project_id=project_id, is_del=False).count()
    web_task_n = await Task.filter(project_id=project_id, is_del=False).count()
    app_plan_n = await AppPlan.filter(project_id=project_id, is_del=False).count()
    api_n = await ApiDefinition.filter(project_id=project_id, is_del=False).count()
    api_case_n = await ApiTestCase.filter(project_id=project_id, is_del=False).count()
    api_plan_n = await ApiTestPlan.filter(project_id=project_id, is_del=False).count()
    perf_scene_n = await PerfScene.filter(project_id=project_id, is_del=False).count()
    catalog_n = await TestCatalog.filter(project_id=project_id, is_del=False).count()
    return {
        "catalog_count": catalog_n,
        "api_count": api_n,
        "case_count": api_case_n,
        "web_case_count": web_case_n,
        "app_case_count": app_case_n,
        "web_suite_count": web_suite_n,
        "app_suite_count": app_suite_n,
        "suite_count": web_suite_n + app_suite_n + api_suite_n,
        "web_task_count": web_task_n,
        "app_plan_count": app_plan_n,
        "api_plan_count": api_plan_n,
        "perf_scene_count": perf_scene_n,
    }


@router.post("", summary="创建目录", status_code=status.HTTP_201_CREATED, response_model=TestCatalogOut,
             dependencies=[Depends(require_permissions(MODULE_EDIT))])
async def create_catalog(item: TestCatalogCreate, username: str = Depends(get_current_username)):
    if not item.project_id or item.project_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请选择有效项目")
    project = await Project.get_or_none(id=item.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="传入的项目不存在或已被删除")
    if item.parent_id:
        await resolve_catalog(item.project_id, item.parent_id)
    catalog = await TestCatalog.create(
        name=item.name,
        project=project,
        parent_id=item.parent_id,
        sort=item.sort,
        description=item.description,
        username=username,
        is_del=False,
    )
    return catalog


@router.get("", summary="目录列表", status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(MODULE_VIEW))])
async def list_catalogs(
    project_id: int | None = None,
    tree: bool = Query(False, description="是否返回树形结构"),
    include_counts: bool = Query(False, description="是否附带各目录资产计数"),
    include_project_totals: bool = Query(False, description="是否附带项目级资产总数"),
):
    query = TestCatalog.filter(is_del=False).order_by("sort", "-id")
    if project_id:
        project = await Project.get_or_none(id=project_id, is_del=False)
        if not project:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="传入的项目不存在或已被删除")
        query = query.filter(project=project)

    catalogs = await query.all()
    flat = [_catalog_to_dict(c) for c in catalogs]
    await _attach_parent_names(flat)

    if include_counts:
        await _attach_counts_to_catalog_rows(flat, project_id)

    if include_project_totals and project_id and include_counts and not tree:
        return {
            "items": flat,
            "project_totals": await _get_project_asset_totals(project_id),
        }

    if not tree:
        return flat

    return build_catalog_tree(flat)


@router.get("/{catalog_id}/assets", summary="目录关联资产列表", status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(MODULE_VIEW))])
async def list_catalog_assets(
    catalog_id: int,
    project_id: int = Query(..., description="项目ID"),
    include_children: bool = Query(False, description="是否包含子目录资产"),
):
    catalog = await TestCatalog.get_or_none(id=catalog_id, project_id=project_id, is_del=False)
    if not catalog:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="目录不存在或已被删除")
    items = await _list_catalog_assets(catalog_id, project_id, include_children)
    return {"items": items, "total": len(items)}


@router.get("/{catalog_id}", summary="目录详情", status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(MODULE_VIEW))])
async def get_catalog_detail(catalog_id: int):
    catalog = await TestCatalog.get_or_none(id=catalog_id, is_del=False)
    if not catalog:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="目录不存在或已被删除")
    result = _catalog_to_dict(catalog)
    result.update(await _get_asset_counts(catalog_id))
    return result


@router.put("/{catalog_id}", summary="更新目录", response_model=TestCatalogOut, status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(MODULE_EDIT))])
async def update_catalog(catalog_id: int, item: TestCatalogUpdate):
    catalog = await TestCatalog.get_or_none(id=catalog_id, is_del=False)
    if not catalog:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="目录不存在或已被删除")

    updates = item.model_dump(exclude_unset=True)
    if "parent_id" in updates and updates["parent_id"] is not None:
        if updates["parent_id"] == catalog_id:
            raise HTTPException(status_code=422, detail="父目录不能是自身")
        await resolve_catalog(catalog.project_id, updates["parent_id"])

    await catalog.update_from_dict(updates)
    await catalog.save()
    return catalog


@router.delete("/{catalog_id}", summary="删除目录", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(MODULE_EDIT))])
async def delete_catalog(catalog_id: int):
    catalog = await TestCatalog.get_or_none(id=catalog_id, is_del=False)
    if not catalog:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="目录不存在或已被删除")

    parent_id = catalog.parent_id
    await TestCatalog.filter(parent_id=catalog_id, is_del=False).update(parent_id=parent_id)

    await Case.filter(catalog_id=catalog_id, is_del=False).update(catalog_id=None)
    await Suite.filter(catalog_id=catalog_id, is_del=False).update(catalog_id=None)
    await Task.filter(catalog_id=catalog_id, is_del=False).update(catalog_id=None)
    await AppCase.filter(catalog_id=catalog_id, is_del=False).update(catalog_id=None)
    await AppSuite.filter(catalog_id=catalog_id, is_del=False).update(catalog_id=None)
    await AppPlan.filter(catalog_id=catalog_id, is_del=False).update(catalog_id=None)
    await ApiDefinition.filter(catalog_id=catalog_id, is_del=False).update(catalog_id=None)
    await ApiTestCase.filter(catalog_id=catalog_id, is_del=False).update(catalog_id=None)
    await ApiTestSuite.filter(catalog_id=catalog_id, is_del=False).update(catalog_id=None)
    await ApiTestPlan.filter(catalog_id=catalog_id, is_del=False).update(catalog_id=None)
    await PerfScene.filter(catalog_id=catalog_id, is_del=False).update(catalog_id=None)

    catalog.is_del = True
    await catalog.save()
