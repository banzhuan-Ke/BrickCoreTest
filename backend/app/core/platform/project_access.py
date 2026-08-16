"""
项目成员角色与访问控制
"""
from __future__ import annotations

from fastapi import HTTPException, status

PROJECT_ROLE_OWNER = "owner"
PROJECT_ROLE_MANAGER = "manager"
PROJECT_ROLE_MEMBER = "member"
PROJECT_ROLE_VIEWER = "viewer"

PROJECT_ROLE_LABELS = {
    PROJECT_ROLE_OWNER: "负责人",
    PROJECT_ROLE_MANAGER: "管理员",
    PROJECT_ROLE_MEMBER: "成员",
    PROJECT_ROLE_VIEWER: "观察者",
}

PROJECT_ROLE_RANK = {
    PROJECT_ROLE_VIEWER: 1,
    PROJECT_ROLE_MEMBER: 2,
    PROJECT_ROLE_MANAGER: 3,
    PROJECT_ROLE_OWNER: 4,
}

ALL_PROJECT_ROLES = list(PROJECT_ROLE_RANK.keys())


def rank_role(role: str | None) -> int:
    return PROJECT_ROLE_RANK.get(role or "", 0)


def role_at_least(role: str | None, min_role: str) -> bool:
    return rank_role(role) >= rank_role(min_role)


async def user_bypasses_project_membership(user_id: int, is_superuser: bool = False) -> bool:
    """超管或系统管理员角色可访问全部项目。"""
    if is_superuser:
        return True
    from app.core.platform.default_roles import SYSTEM_ADMIN_CODE
    from app.models.sys import Role

    # 不 prefetch User.roles：高并发下易 KeyError('_backward_relation_key')
    return await Role.filter(
        users__id=user_id, code=SYSTEM_ADMIN_CODE, is_del=False
    ).exists()


async def get_user_project_role(user_id: int, project_id: int) -> str | None:
    from app.models.sys import ProjectMember

    row = await ProjectMember.get_or_none(project_id=project_id, user_id=user_id, is_del=False)
    return row.role if row else None


async def get_accessible_project_ids(user_id: int, *, is_superuser: bool = False) -> list[int] | None:
    """
    返回用户可访问的项目 id 列表；None 表示不限制（超管/系统管理员）。
    """
    if await user_bypasses_project_membership(user_id, is_superuser):
        return None
    from app.models.sys import ProjectMember

    ids = await ProjectMember.filter(user_id=user_id, is_del=False).values_list("project_id", flat=True)
    return list(ids)


async def assert_project_access(
    user_info: dict,
    project_id: int,
    *,
    min_role: str = PROJECT_ROLE_VIEWER,
) -> str:
    """
    校验用户对项目的访问权限，返回用户在该项目中的角色。
    超管/系统管理员返回 owner 等价权限。
    """
    # MCP API Key 等无用户 ID 的超管身份（由 MCP 层显式标记）
    if user_info.get("is_api_key") and user_info.get("is_superuser"):
        return PROJECT_ROLE_OWNER

    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

    if await user_bypasses_project_membership(user_id, user_info.get("is_superuser", False)):
        return PROJECT_ROLE_OWNER

    from app.models.sys import Project

    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目不存在")

    role = await get_user_project_role(user_id, project_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="您不是该项目成员，无权访问")
    if not role_at_least(role, min_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"需要项目{PROJECT_ROLE_LABELS.get(min_role, min_role)}及以上权限",
        )
    return role


async def ensure_project_owner(project_id: int, user_id: int, *, invited_by_id: int | None = None) -> None:
    """确保用户为项目负责人（不存在成员记录时创建）。"""
    from app.models.sys import ProjectMember

    existing = await ProjectMember.get_or_none(project_id=project_id, user_id=user_id, is_del=False)
    if existing:
        if existing.role != PROJECT_ROLE_OWNER:
            existing.role = PROJECT_ROLE_OWNER
            await existing.save(update_fields=["role", "update_time"])
        return
    await ProjectMember.create(
        project_id=project_id,
        user_id=user_id,
        role=PROJECT_ROLE_OWNER,
        invited_by_id=invited_by_id or user_id,
        is_del=False,
    )


async def backfill_project_members() -> None:
    """为尚无成员记录的项目补全创建人为负责人。"""
    from app.models.sys import Project, ProjectMember

    projects = await Project.filter(is_del=False).all()
    for project in projects:
        has_any = await ProjectMember.filter(project_id=project.id, is_del=False).exists()
        if has_any:
            continue
        if project.user_id:
            await ProjectMember.create(
                project_id=project.id,
                user_id=project.user_id,
                role=PROJECT_ROLE_OWNER,
                invited_by_id=project.user_id,
                is_del=False,
            )
