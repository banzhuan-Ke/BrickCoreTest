from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends, status, Query
from tortoise.functions import Count

from app.schemas.sys import TestCatalogOut, TestCatalogCreate, TestCatalogUpdate, TestCatalogTreeNode
from app.models.sys import TestCatalog, Project
from app.models.ui import Case, Suite, Task
from app.models.http import ApiDefinition, ApiTestCase, ApiTestSuite, ApiTestPlan
from app.core.auth import is_authenticated, require_permissions, get_current_username
from app.core.permissions import MODULE_VIEW, MODULE_EDIT
from app.core.catalog_utils import build_catalog_tree, resolve_catalog

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
    ui_suite_counts: Dict[int, int],
    api_suite_counts: Dict[int, int],
) -> dict:
    api_n = api_counts.get(catalog_id, 0)
    case_n = case_counts.get(catalog_id, 0)
    ui_case_n = ui_case_counts.get(catalog_id, 0)
    suite_n = ui_suite_counts.get(catalog_id, 0) + api_suite_counts.get(catalog_id, 0)
    return {
        "api_count": api_n,
        "case_count": case_n,
        "ui_case_count": ui_case_n,
        "suite_count": suite_n,
        "api_defs": api_n,
        "api_cases": case_n,
        "ui_cases": ui_case_n,
        "ui_suites": ui_suite_counts.get(catalog_id, 0),
        "api_suites": api_suite_counts.get(catalog_id, 0),
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
    ui_suite_counts = await _count_by_catalog(Suite, catalog_ids, project_id)
    api_suite_counts = await _count_by_catalog(ApiTestSuite, catalog_ids, project_id)
    for item in flat:
        item.update(_counts_to_row_fields(
            item["id"], api_counts, case_counts, ui_case_counts, ui_suite_counts, api_suite_counts,
        ))


async def _get_asset_counts(catalog_id: int) -> dict:
    api_n = await ApiDefinition.filter(catalog_id=catalog_id, is_del=False).count()
    case_n = await ApiTestCase.filter(catalog_id=catalog_id, is_del=False).count()
    ui_case_n = await Case.filter(catalog_id=catalog_id, is_del=False).count()
    ui_suite_n = await Suite.filter(catalog_id=catalog_id, is_del=False).count()
    api_suite_n = await ApiTestSuite.filter(catalog_id=catalog_id, is_del=False).count()
    return {
        "api_count": api_n,
        "case_count": case_n,
        "ui_case_count": ui_case_n,
        "suite_count": ui_suite_n + api_suite_n,
        "ui_cases": ui_case_n,
        "ui_suites": ui_suite_n,
        "api_defs": api_n,
        "api_cases": case_n,
        "api_suites": api_suite_n,
        "ui_tasks": await Task.filter(catalog_id=catalog_id, is_del=False).count(),
        "api_plans": await ApiTestPlan.filter(catalog_id=catalog_id, is_del=False).count(),
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

    if not tree:
        return flat

    return build_catalog_tree(flat)


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
    await ApiDefinition.filter(catalog_id=catalog_id, is_del=False).update(catalog_id=None)
    await ApiTestCase.filter(catalog_id=catalog_id, is_del=False).update(catalog_id=None)
    await ApiTestSuite.filter(catalog_id=catalog_id, is_del=False).update(catalog_id=None)
    await ApiTestPlan.filter(catalog_id=catalog_id, is_del=False).update(catalog_id=None)

    catalog.is_del = True
    await catalog.save()
