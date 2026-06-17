from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import is_authenticated
from app.core.project_access import (
    ALL_PROJECT_ROLES,
    PROJECT_ROLE_LABELS,
    PROJECT_ROLE_MANAGER,
    PROJECT_ROLE_OWNER,
    PROJECT_ROLE_VIEWER,
    assert_project_access,
)
from app.models.sys import ProjectMember, User
from app.schemas.sys import (
    AddProjectMemberForm,
    ProjectMemberListSchemas,
    ProjectMemberSchemas,
    TransferProjectOwnerForm,
    UpdateProjectMemberForm,
)

router = APIRouter(prefix="/projects/{project_id}/members", tags=["项目成员"])


def _member_dict(row: ProjectMember, user: User, invited_by: User | None = None) -> dict:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "user_id": row.user_id,
        "role": row.role,
        "username": user.username if user else "",
        "nickname": user.nickname if user else "",
        "invited_by_username": invited_by.username if invited_by else "",
        "create_time": row.create_time,
        "update_time": row.update_time,
    }


@router.get("", summary="项目成员列表", response_model=ProjectMemberListSchemas)
async def list_members(project_id: int, user_info: dict = Depends(is_authenticated)):
    await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_VIEWER)
    query = ProjectMember.filter(project_id=project_id, is_del=False).order_by("-id")
    total = await query.count()
    rows = await query.prefetch_related("user", "invited_by")
    data = []
    for row in rows:
        data.append(ProjectMemberSchemas(**_member_dict(row, row.user, row.invited_by)))
    return {"total": total, "data": data}


@router.post("", summary="添加项目成员", response_model=ProjectMemberSchemas, status_code=status.HTTP_201_CREATED)
async def add_member(
    project_id: int,
    item: AddProjectMemberForm,
    user_info: dict = Depends(is_authenticated),
):
    my_role = await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_MANAGER)
    if item.role not in ALL_PROJECT_ROLES:
        raise HTTPException(status_code=422, detail="无效的项目角色")
    if item.role == PROJECT_ROLE_OWNER:
        raise HTTPException(status_code=422, detail="请使用「转让负责人」变更负责人")
    if my_role != PROJECT_ROLE_OWNER and item.role == PROJECT_ROLE_MANAGER:
        raise HTTPException(status_code=403, detail="仅项目负责人可添加项目管理员")

    target = await User.get_or_none(id=item.user_id, is_del=False)
    if not target:
        raise HTTPException(status_code=422, detail="用户不存在")

    existing = await ProjectMember.get_or_none(project_id=project_id, user_id=item.user_id, is_del=False)
    if existing:
        raise HTTPException(status_code=422, detail="该用户已是项目成员")

    row = await ProjectMember.create(
        project_id=project_id,
        user_id=item.user_id,
        role=item.role,
        invited_by_id=user_info.get("id"),
        is_del=False,
    )
    await row.fetch_related("user", "invited_by")
    return ProjectMemberSchemas(**_member_dict(row, row.user, row.invited_by))


@router.get("/roles", summary="可选项目角色")
async def list_project_roles():
    return [{"value": k, "label": v} for k, v in PROJECT_ROLE_LABELS.items() if k != PROJECT_ROLE_OWNER]


@router.post("/transfer-owner", summary="转让项目负责人", status_code=status.HTTP_200_OK)
async def transfer_owner(
    project_id: int,
    item: TransferProjectOwnerForm,
    user_info: dict = Depends(is_authenticated),
):
    await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_OWNER)
    target = await ProjectMember.get_or_none(project_id=project_id, user_id=item.user_id, is_del=False)
    if not target:
        raise HTTPException(status_code=422, detail="目标用户不是项目成员，请先添加为成员")

    current_owner = await ProjectMember.get_or_none(
        project_id=project_id, user_id=user_info.get("id"), is_del=False
    )
    if current_owner:
        current_owner.role = PROJECT_ROLE_MANAGER
        await current_owner.save(update_fields=["role", "update_time"])

    target.role = PROJECT_ROLE_OWNER
    await target.save(update_fields=["role", "update_time"])
    return {"detail": "负责人已转让", "new_owner_id": item.user_id}


@router.put("/{member_id}", summary="修改成员角色", response_model=ProjectMemberSchemas)
async def update_member(
    project_id: int,
    member_id: int,
    item: UpdateProjectMemberForm,
    user_info: dict = Depends(is_authenticated),
):
    my_role = await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_MANAGER)
    if item.role not in ALL_PROJECT_ROLES:
        raise HTTPException(status_code=422, detail="无效的项目角色")
    if item.role == PROJECT_ROLE_OWNER:
        raise HTTPException(status_code=422, detail="请使用「转让负责人」变更负责人")

    row = await ProjectMember.get_or_none(id=member_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=422, detail="成员不存在")
    if row.role == PROJECT_ROLE_OWNER:
        raise HTTPException(status_code=403, detail="不可直接修改负责人角色")
    if item.role == PROJECT_ROLE_MANAGER and my_role != PROJECT_ROLE_OWNER:
        raise HTTPException(status_code=403, detail="仅项目负责人可设置项目管理员")

    row.role = item.role
    await row.save()
    await row.fetch_related("user", "invited_by")
    return ProjectMemberSchemas(**_member_dict(row, row.user, row.invited_by))


@router.delete("/{member_id}", summary="移除项目成员", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    project_id: int,
    member_id: int,
    user_info: dict = Depends(is_authenticated),
):
    my_role = await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_MANAGER)
    row = await ProjectMember.get_or_none(id=member_id, project_id=project_id, is_del=False)
    if not row:
        raise HTTPException(status_code=422, detail="成员不存在")
    if row.role == PROJECT_ROLE_OWNER:
        raise HTTPException(status_code=403, detail="不可移除项目负责人")
    if row.role == PROJECT_ROLE_MANAGER and my_role != PROJECT_ROLE_OWNER:
        raise HTTPException(status_code=403, detail="仅项目负责人可移除项目管理员")
    if row.user_id == user_info.get("id"):
        raise HTTPException(status_code=422, detail="不能移除自己，请联系其他管理员")

    owner_count = await ProjectMember.filter(
        project_id=project_id, role=PROJECT_ROLE_OWNER, is_del=False
    ).count()
    if row.role == PROJECT_ROLE_OWNER and owner_count <= 1:
        raise HTTPException(status_code=422, detail="项目至少保留一名负责人")

    row.is_del = True
    await row.save()
    await User.filter(default_project_id=project_id, id=row.user_id).update(default_project_id=None)
