"""App 用例 CRUD"""
import copy

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.platform.auth import get_current_username, is_authenticated, require_permissions
from app.core.shared.catalog_utils import apply_catalog_filter, resolve_catalog
from app.core.platform.permissions import APP_CASE_EDIT, APP_CASE_VIEW
from app.modules.ui.ui_project_guard import assert_user_project_member, assert_user_project_viewer
from app.core.case.case_execution_hints import build_execution_hints_response, resolve_latest_execution_record
from app.modules.app.app_locator_validate import validate_case_steps_driver_mode_for_project
from app.models.app import AppCase, AppCaseExecution
from app.models.sys import Project
from app.schemas.app import AddAppCaseForm, AppCaseSchemas, UpdateAppCaseForm

router = APIRouter(prefix="/cases", dependencies=[Depends(is_authenticated)], tags=["App用例"])


class CopyAppCaseRequest(BaseModel):
    new_name: str | None = None
    target_catalog_id: int | None = None


@router.post("", summary="创建 App 用例", status_code=status.HTTP_201_CREATED, response_model=AppCaseSchemas,
             dependencies=[Depends(require_permissions(APP_CASE_EDIT))])
async def create_case(
    item: AddAppCaseForm,
    user_info: dict = Depends(require_permissions(APP_CASE_EDIT)),
    username: str = Depends(get_current_username),
):
    await assert_user_project_member(user_info, item.project_id)
    project = await Project.get_or_none(id=item.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=422, detail="项目不存在")
    if item.catalog_id is not None:
        await resolve_catalog(item.project_id, item.catalog_id)
    driver_mode = await validate_case_steps_driver_mode_for_project(item.driver_mode, item.steps, item.project_id)
    payload = item.model_dump()
    payload["driver_mode"] = driver_mode
    payload["username"] = username
    return await AppCase.create(**payload, is_del=False, update_by=username)


@router.get("", summary="App 用例列表")
async def list_cases(
    project_id: int,
    page: int = 1,
    size: int = 10,
    name: str | None = None,
    catalog_id: int | None = None,
    include_children: bool = True,
    user_info: dict = Depends(require_permissions(APP_CASE_VIEW)),
):
    await assert_user_project_viewer(user_info, project_id)
    query = AppCase.filter(project_id=project_id, is_del=False).order_by("-id")
    if name:
        query = query.filter(name__icontains=name)
    if catalog_id is not None:
        await resolve_catalog(project_id, catalog_id)
        query = await apply_catalog_filter(query, project_id, catalog_id, include_children=include_children)
    total = await query.count()
    rows = await query.offset((page - 1) * size).limit(size)
    return {"data": [AppCaseSchemas.model_validate(r) for r in rows], "total": total}


@router.get("/{case_id}", response_model=AppCaseSchemas, dependencies=[Depends(require_permissions(APP_CASE_VIEW))])
async def get_case(case_id: int, user_info: dict = Depends(require_permissions(APP_CASE_VIEW))):
    case = await AppCase.get_or_none(id=case_id, is_del=False)
    if not case:
        raise HTTPException(status_code=422, detail="用例不存在")
    await assert_user_project_viewer(user_info, case.project_id)
    return case


@router.get(
    "/{case_id}/execution-hints",
    summary="App 用例最近失败执行提示",
    dependencies=[Depends(require_permissions(APP_CASE_VIEW))],
)
async def get_case_execution_hints(
    case_id: int,
    execution_id: int | None = None,
    user_info: dict = Depends(require_permissions(APP_CASE_VIEW)),
):
    case = await AppCase.get_or_none(id=case_id, is_del=False)
    if not case:
        raise HTTPException(status_code=422, detail="用例不存在")
    await assert_user_project_viewer(user_info, case.project_id)

    if execution_id:
        record = await AppCaseExecution.get_or_none(id=execution_id, is_del=False)
        if not record or record.case_id != case_id:
            raise HTTPException(status_code=422, detail="执行记录不存在")
    else:
        record = await resolve_latest_execution_record(AppCaseExecution, case_id)

    if not record:
        return build_execution_hints_response(None)

    return build_execution_hints_response(record, case_steps=case.steps or [])


@router.put("/{case_id}", response_model=AppCaseSchemas, dependencies=[Depends(require_permissions(APP_CASE_EDIT))])
async def update_case(
    case_id: int,
    item: UpdateAppCaseForm,
    user_info: dict = Depends(require_permissions(APP_CASE_EDIT)),
    username: str = Depends(get_current_username),
):
    case = await AppCase.get_or_none(id=case_id, is_del=False)
    if not case:
        raise HTTPException(status_code=422, detail="用例不存在")
    await assert_user_project_member(user_info, case.project_id)
    if item.catalog_id is not None:
        await resolve_catalog(case.project_id, item.catalog_id)
    data = item.model_dump(exclude_unset=True)
    driver_mode = data.get("driver_mode", case.driver_mode)
    steps = data.get("steps", case.steps)
    if "driver_mode" in data or "steps" in data:
        data["driver_mode"] = await validate_case_steps_driver_mode_for_project(
            driver_mode, steps, case.project_id
        )
    await case.update_from_dict(data)
    case.update_by = username
    await case.save()
    return case


@router.post(
    "/{case_id}/copy",
    summary="复制 App 用例",
    response_model=AppCaseSchemas,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(APP_CASE_EDIT))],
)
async def copy_app_case(
    case_id: int,
    body: CopyAppCaseRequest | None = None,
    user_info: dict = Depends(require_permissions(APP_CASE_EDIT)),
    username: str = Depends(get_current_username),
):
    case = await AppCase.get_or_none(id=case_id, is_del=False)
    if not case:
        raise HTTPException(status_code=422, detail="用例不存在")
    await assert_user_project_member(user_info, case.project_id)
    req = body or CopyAppCaseRequest()
    new_name = (req.new_name or f"{case.name}_副本").strip()
    if not new_name:
        raise HTTPException(status_code=422, detail="用例名称不能为空")
    catalog_id = case.catalog_id if req.target_catalog_id is None else req.target_catalog_id
    if catalog_id is not None:
        await resolve_catalog(case.project_id, catalog_id)
    driver_mode = await validate_case_steps_driver_mode_for_project(
        case.driver_mode, case.steps, case.project_id
    )
    return await AppCase.create(
        name=new_name,
        project_id=case.project_id,
        catalog_id=catalog_id,
        level=case.level,
        platform_scope=case.platform_scope,
        driver_mode=driver_mode,
        description=case.description or "",
        steps=copy.deepcopy(case.steps or []),
        username=username,
        is_del=False,
        update_by=username,
    )


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(APP_CASE_EDIT))])
async def delete_case(case_id: int, user_info: dict = Depends(require_permissions(APP_CASE_EDIT))):
    case = await AppCase.get_or_none(id=case_id, is_del=False)
    if not case:
        raise HTTPException(status_code=422, detail="用例不存在")
    await assert_user_project_member(user_info, case.project_id)
    case.is_del = True
    await case.save()
