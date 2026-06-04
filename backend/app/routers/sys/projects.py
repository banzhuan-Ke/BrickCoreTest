from fastapi import APIRouter, HTTPException, Depends, status
from app.schemas.sys import AddProjectForm, UpdateProjectForm, ProjectSchemas, ProjectListSchemas
from app.models.sys import Project
from app.models.sys import User
from app.core.auth import is_authenticated, require_permissions
from app.core.permissions import PROJECT_VIEW, PROJECT_EDIT

# 创建路由对象，添加用户鉴权
router = APIRouter(prefix="/projects", tags=["项目管理"], dependencies=[Depends(is_authenticated)])


def _project_dict(project: Project, *, is_user_default: bool = False) -> dict:
    d = project.__dict__.copy()
    d["global_vars"] = d.get("global_vars") or {}
    d["default_headers"] = d.get("default_headers") or []
    d["is_user_default"] = is_user_default
    return d


# 创建项目
@router.post("", summary="创建项目", status_code=status.HTTP_201_CREATED, response_model=ProjectSchemas,
             dependencies=[Depends(require_permissions(PROJECT_EDIT))])
async def create_project(item: AddProjectForm):
    # 根据用户ID查询用户
    user = await User.get_or_none(id=item.user)
    if not user:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户不存在")
    # 创建项目，关联用户并设置is_del=False
    project = await Project.create(name=item.name, user=user, username=user.username, is_del=False)
    return ProjectSchemas(**_project_dict(project))


# 获取项目列表
@router.get("", summary="项目列表", response_model=ProjectListSchemas, status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(PROJECT_VIEW))])
async def get_projects(
    page: int = 1,
    size: int = 10,
    user_info: dict = Depends(is_authenticated),
):
    page = max(page, 1)
    size = max(size, 1)
    query = Project.filter(is_del=False).order_by("-id")
    total = await query.count()
    projects = await query.offset((page - 1) * size).limit(size)
    user = await User.get_or_none(id=user_info.get("id"), is_del=False)
    default_pid = user.default_project_id if user else None
    result = []
    for project in projects:
        result.append(ProjectSchemas(**_project_dict(
            project,
            is_user_default=bool(default_pid and project.id == default_pid),
        )))
    return {"total": total, "data": result}


# 获取单个项详情
@router.get("/{project_id}", summary="项目详情", response_model=ProjectSchemas, status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(PROJECT_VIEW))])
async def get_project(project_id: int, user_info: dict = Depends(is_authenticated)):
    # 获取未删除的项目详情
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目不存在")
    user = await User.get_or_none(id=user_info.get("id"), is_del=False)
    default_pid = user.default_project_id if user else None
    return ProjectSchemas(**_project_dict(
        project,
        is_user_default=bool(default_pid and project.id == default_pid),
    ))


# 删除项目（逻辑删除）
@router.delete("/{project_id}", summary="删除项目", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(PROJECT_EDIT))])
async def delete_project(project_id: int):
    # 获取未删除的项目
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目不存在")
    # 逻辑删除：设置is_del=True
    project.is_del = True
    await project.save()
    await User.filter(default_project_id=project_id).update(default_project_id=None)


@router.put("/{project_id}/default", summary="设为当前用户默认项目", status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(PROJECT_VIEW))])
async def set_default_project(
    project_id: int,
    user_info: dict = Depends(is_authenticated),
):
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目不存在")
    user = await User.get_or_none(id=user_info.get("id"), is_del=False)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    user.default_project_id = project_id
    await user.save(update_fields=["default_project_id"])
    return {"id": project.id, "name": project.name, "default_project_id": project_id}


@router.delete("/default", summary="清除默认项目", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(PROJECT_VIEW))])
async def clear_default_project(user_info: dict = Depends(is_authenticated)):
    user = await User.get_or_none(id=user_info.get("id"), is_del=False)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    user.default_project_id = None
    await user.save(update_fields=["default_project_id"])
    return None


@router.put("/{project_id}", summary="修改项目", response_model=ProjectSchemas, status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(PROJECT_EDIT))])
async def update_project(project_id: int, item: UpdateProjectForm):
    # 获取未删除的项目
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目不存在")
    # 更新项目名称
    project.name = item.name
    # 更新全局变量（仅当传入时）
    if item.global_vars is not None:
        project.global_vars = item.global_vars
    if item.default_headers is not None:
        from app.core.default_headers_validate import normalize_default_headers
        try:
            project.default_headers = normalize_default_headers(item.default_headers)
        except ValueError as e:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail=str(e))
    await project.save()
    return ProjectSchemas(**_project_dict(project))