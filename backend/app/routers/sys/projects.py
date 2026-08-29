from fastapi import APIRouter, Depends, HTTPException, status

from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import ENVIRONMENT_VIEW
from app.core.platform.project_access import (
    PROJECT_ROLE_MANAGER,
    PROJECT_ROLE_MEMBER,
    PROJECT_ROLE_OWNER,
    PROJECT_ROLE_VIEWER,
    assert_project_access,
    ensure_project_owner,
    get_accessible_project_ids,
    get_user_project_role,
    role_at_least,
    user_bypasses_project_membership,
)
from app.models.sys import Project, User
from app.schemas.sys import AddProjectForm, ProjectListSchemas, ProjectSchemas, UpdateProjectForm

router = APIRouter(prefix="/projects", tags=["项目管理"], dependencies=[Depends(is_authenticated)])


def _project_dict(
    project: Project,
    *,
    is_user_default: bool = False,
    my_role: str | None = None,
) -> dict:
    d = project.__dict__.copy()
    d.pop("_partial", None)
    d.pop("_saved_in_db", None)
    d.pop("_custom_generated_pk", None)
    d["global_vars"] = d.get("global_vars") or {}
    d["default_headers"] = d.get("default_headers") or []
    d["is_user_default"] = is_user_default
    d["my_role"] = my_role
    d["can_manage_members"] = role_at_least(my_role, PROJECT_ROLE_MANAGER) if my_role else False
    d["can_edit_project"] = role_at_least(my_role, PROJECT_ROLE_MANAGER) if my_role else False
    d["can_delete_project"] = my_role == PROJECT_ROLE_OWNER if my_role else False
    return d


async def _resolve_my_role(user_info: dict, project_id: int) -> str | None:
    if await user_bypasses_project_membership(user_info.get("id"), user_info.get("is_superuser", False)):
        return PROJECT_ROLE_OWNER
    return await get_user_project_role(user_info.get("id"), project_id)


@router.post(
    "",
    summary="创建项目",
    status_code=status.HTTP_201_CREATED,
    response_model=ProjectSchemas,
    dependencies=[Depends(require_permissions("project:edit"))],
)
async def create_project(item: AddProjectForm, user_info: dict = Depends(is_authenticated)):
    user = await User.get_or_none(id=item.user, is_del=False)
    if not user:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户不存在")
    project = await Project.create(name=item.name, user=user, username=user.username, is_del=False)
    await ensure_project_owner(project.id, user.id, invited_by_id=user_info.get("id"))
    my_role = await _resolve_my_role(user_info, project.id)
    return ProjectSchemas(**_project_dict(project, my_role=my_role))


@router.get(
    "",
    summary="项目列表",
    response_model=ProjectListSchemas,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permissions("project:view"))],
)
async def get_projects(
    page: int = 1,
    size: int = 10,
    user_info: dict = Depends(is_authenticated),
):
    page = max(page, 1)
    size = max(size, 1)
    accessible = await get_accessible_project_ids(
        user_info.get("id"), is_superuser=user_info.get("is_superuser", False)
    )
    query = Project.filter(is_del=False).order_by("-id")
    if accessible is not None:
        if not accessible:
            return {"total": 0, "data": []}
        query = query.filter(id__in=accessible)
    total = await query.count()
    projects = await query.offset((page - 1) * size).limit(size)
    user = await User.get_or_none(id=user_info.get("id"), is_del=False)
    default_pid = user.default_project_id if user else None
    result = []
    for project in projects:
        my_role = await _resolve_my_role(user_info, project.id)
        result.append(
            ProjectSchemas(
                **_project_dict(
                    project,
                    is_user_default=bool(default_pid and project.id == default_pid),
                    my_role=my_role,
                )
            )
        )
    return {"total": total, "data": result}


@router.get(
    "/{project_id}",
    summary="项目详情",
    response_model=ProjectSchemas,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permissions("project:view"))],
)
async def get_project(project_id: int, user_info: dict = Depends(is_authenticated)):
    my_role = await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_VIEWER)
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目不存在")
    user = await User.get_or_none(id=user_info.get("id"), is_del=False)
    default_pid = user.default_project_id if user else None
    return ProjectSchemas(
        **_project_dict(
            project,
            is_user_default=bool(default_pid and project.id == default_pid),
            my_role=my_role,
        )
    )


@router.delete(
    "/{project_id}",
    summary="删除项目",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("project:edit"))],
)
async def delete_project(project_id: int, user_info: dict = Depends(is_authenticated)):
    await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_OWNER)
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目不存在")
    project.is_del = True
    await project.save()
    await User.filter(default_project_id=project_id).update(default_project_id=None)


@router.put(
    "/{project_id}/default",
    summary="设为当前用户默认项目",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permissions("project:view"))],
)
async def set_default_project(project_id: int, user_info: dict = Depends(is_authenticated)):
    await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_VIEWER)
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目不存在")
    user = await User.get_or_none(id=user_info.get("id"), is_del=False)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    user.default_project_id = project_id
    await user.save(update_fields=["default_project_id"])
    return {"id": project.id, "name": project.name, "default_project_id": project_id}


@router.delete(
    "/default",
    summary="清除默认项目",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("project:view"))],
)
async def clear_default_project(user_info: dict = Depends(is_authenticated)):
    user = await User.get_or_none(id=user_info.get("id"), is_del=False)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    user.default_project_id = None
    await user.save(update_fields=["default_project_id"])
    return None


@router.put(
    "/{project_id}",
    summary="修改项目",
    response_model=ProjectSchemas,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permissions("project:edit"))],
)
async def update_project(
    project_id: int,
    item: UpdateProjectForm,
    user_info: dict = Depends(is_authenticated),
):
    my_role = await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_MANAGER)
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目不存在")
    if item.name is not None:
        project.name = item.name
    if item.global_vars is not None:
        project.global_vars = item.global_vars
    if item.default_headers is not None:
        from app.core.shared.default_headers_validate import normalize_default_headers

        try:
            project.default_headers = normalize_default_headers(item.default_headers)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    await project.save()
    return ProjectSchemas(**_project_dict(project, my_role=my_role))


@router.get(
    "/{project_id}/variable-usages",
    summary="查询变量在用例/套件/计划等处的引用",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permissions(ENVIRONMENT_VIEW))],
)
async def get_variable_usages(
    project_id: int,
    name: str,
    user_info: dict = Depends(is_authenticated),
):
    await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_VIEWER)
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=422, detail="项目不存在")
    from app.modules.sys.variable_usages import collect_variable_usages

    try:
        return await collect_variable_usages(project_id, name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
