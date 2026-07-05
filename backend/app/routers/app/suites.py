"""App 套件 CRUD"""
from fastapi import APIRouter, Depends, HTTPException, status
from tortoise import transactions

from app.core.auth import get_current_username, is_authenticated, require_permissions
from app.core.catalog_utils import resolve_catalog
from app.core.permissions import APP_SUITE_EDIT, APP_SUITE_VIEW
from app.core.ui_project_guard import assert_user_project_member, assert_user_project_viewer
from app.models.app import AppCase, AppSuite, AppSuiteExecution, AppSuiteStep
from app.models.sys import Project
from app.schemas.app import (
    AddAppSuiteForm,
    AddAppSuiteStepForm,
    AppSuiteSchemas,
    UpdateAppSuiteForm,
)

router = APIRouter(prefix="/suites", dependencies=[Depends(is_authenticated)], tags=["App套件"])


@router.post("", response_model=AppSuiteSchemas, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permissions(APP_SUITE_EDIT))])
async def create_suite(
    item: AddAppSuiteForm,
    user_info: dict = Depends(require_permissions(APP_SUITE_EDIT)),
    username: str = Depends(get_current_username),
):
    await assert_user_project_member(user_info, item.project_id)
    if not await Project.get_or_none(id=item.project_id, is_del=False):
        raise HTTPException(status_code=422, detail="项目不存在")
    if item.catalog_id is not None:
        await resolve_catalog(item.project_id, item.catalog_id)
    payload = item.model_dump()
    payload["username"] = username
    return await AppSuite.create(**payload, is_del=False, update_by=username)


@router.get("", dependencies=[Depends(require_permissions(APP_SUITE_VIEW))])
async def list_suites(
    project_id: int,
    page: int = 1,
    size: int = 10,
    name: str | None = None,
    user_info: dict = Depends(require_permissions(APP_SUITE_VIEW)),
):
    await assert_user_project_viewer(user_info, project_id)
    query = AppSuite.filter(project_id=project_id, is_del=False).order_by("-id")
    if name:
        query = query.filter(name__icontains=name)
    total = await query.count()
    data = []
    for suite in await query.offset((page - 1) * size).limit(size):
        steps = await AppSuiteStep.filter(suite_id=suite.id, is_del=False).count()
        last = await AppSuiteExecution.filter(suite_id=suite.id, is_del=False).order_by("-id").first()
        data.append({
            "id": suite.id,
            "name": suite.name,
            "username": suite.username,
            "case_count": steps,
            "status": last.status if last else "等待执行",
            "create_time": suite.create_time,
            "update_time": suite.update_time,
        })
    return {"data": data, "total": total}


@router.get("/{suite_id}", response_model=AppSuiteSchemas, dependencies=[Depends(require_permissions(APP_SUITE_VIEW))])
async def get_suite(suite_id: int, user_info: dict = Depends(require_permissions(APP_SUITE_VIEW))):
    suite = await AppSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=422, detail="套件不存在")
    await assert_user_project_viewer(user_info, suite.project_id)
    return suite


@router.put("/{suite_id}", response_model=AppSuiteSchemas, dependencies=[Depends(require_permissions(APP_SUITE_EDIT))])
async def update_suite(
    suite_id: int,
    item: UpdateAppSuiteForm,
    user_info: dict = Depends(require_permissions(APP_SUITE_EDIT)),
    username: str = Depends(get_current_username),
):
    suite = await AppSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=422, detail="套件不存在")
    await assert_user_project_member(user_info, suite.project_id)
    if item.catalog_id is not None:
        await resolve_catalog(suite.project_id, item.catalog_id)
    await suite.update_from_dict(item.model_dump(exclude_unset=True))
    suite.update_by = username
    await suite.save()
    return suite


@router.delete("/{suite_id}", status_code=204, dependencies=[Depends(require_permissions(APP_SUITE_EDIT))])
async def delete_suite(suite_id: int, user_info: dict = Depends(require_permissions(APP_SUITE_EDIT))):
    suite = await AppSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=422, detail="套件不存在")
    await assert_user_project_member(user_info, suite.project_id)
    suite.is_del = True
    await suite.save()


@router.post("/{suite_id}/cases", status_code=201, dependencies=[Depends(require_permissions(APP_SUITE_EDIT))])
async def add_case_to_suite(
    suite_id: int,
    item: AddAppSuiteStepForm,
    user_info: dict = Depends(require_permissions(APP_SUITE_EDIT)),
):
    suite = await AppSuite.get_or_none(id=suite_id, is_del=False)
    case = await AppCase.get_or_none(id=item.case_id, is_del=False)
    if not suite or not case:
        raise HTTPException(status_code=422, detail="套件或用例不存在")
    await assert_user_project_member(user_info, suite.project_id)
    if case.project_id != suite.project_id:
        raise HTTPException(status_code=422, detail="用例与套件不属于同一项目")
    exists = await AppSuiteStep.get_or_none(suite_id=suite_id, case_id=item.case_id, is_del=False)
    if exists:
        raise HTTPException(status_code=422, detail="用例已在套件中")
    return await AppSuiteStep.create(suite=suite, case=case, sort=item.sort, skip=item.skip, is_del=False)


@router.get("/{suite_id}/cases", dependencies=[Depends(require_permissions(APP_SUITE_VIEW))])
async def list_suite_cases(suite_id: int, user_info: dict = Depends(require_permissions(APP_SUITE_VIEW))):
    suite = await AppSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=422, detail="套件不存在")
    await assert_user_project_viewer(user_info, suite.project_id)
    steps = await AppSuiteStep.filter(suite_id=suite_id, is_del=False).order_by("sort").prefetch_related("case")
    out = []
    for step in steps:
        case = await step.case
        if case and not case.is_del:
            out.append({
                "step_id": step.id,
                "case_id": case.id,
                "name": case.name,
                "sort": step.sort,
                "skip": step.skip,
                "level": case.level,
            })
    return out


@router.put("/{suite_id}/cases", dependencies=[Depends(require_permissions(APP_SUITE_EDIT))])
async def replace_suite_cases(
    suite_id: int,
    items: list[AddAppSuiteStepForm],
    user_info: dict = Depends(require_permissions(APP_SUITE_EDIT)),
):
    suite = await AppSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=422, detail="套件不存在")
    await assert_user_project_member(user_info, suite.project_id)

    validated: list[AddAppSuiteStepForm] = []
    skipped: list[int] = []
    for item in items:
        case = await AppCase.get_or_none(id=item.case_id, is_del=False)
        if not case or case.project_id != suite.project_id:
            skipped.append(item.case_id)
            continue
        validated.append(item)
    if skipped:
        raise HTTPException(status_code=422, detail=f"以下用例不存在或不属于当前项目: {skipped}")

    async with transactions.in_transaction():
        await AppSuiteStep.filter(suite_id=suite_id).update(is_del=True)
        created = []
        for item in validated:
            created.append(
                await AppSuiteStep.create(
                    suite=suite,
                    case_id=item.case_id,
                    sort=item.sort,
                    skip=item.skip,
                    is_del=False,
                )
            )
    return {"count": len(created)}
