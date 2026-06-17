"""权限与邀请码注册相关测试"""
import pytest

from app.core.default_roles import (
    DEFAULT_ROLES,
    MEMBER_CODE,
    SYSTEM_ADMIN_CODE,
    SYSTEM_ADMIN_PERMISSIONS,
)
from app.core.permissions import (
    DOCS_VIEW,
    PROJECT_VIEW,
    ROLE_EDIT,
    ROLE_VIEW,
    USER_EDIT,
    USER_VIEW,
    get_user_permissions,
    UI_CASE_VIEW,
)
from app.models.sys import Role, User


@pytest.mark.asyncio
async def test_no_roles_returns_empty_permissions():
    user = User(id=1, username="u1", nickname="u1", is_superuser=False)
    user.roles.all = lambda: _async_empty()
    perms = await get_user_permissions(user)
    assert perms == []


@pytest.mark.asyncio
async def test_system_admin_role_view_only_user_role():
    role = Role(
        id=1,
        code=SYSTEM_ADMIN_CODE,
        name="系统管理员",
        permissions=SYSTEM_ADMIN_PERMISSIONS,
    )
    user = User(id=1, username="u1", nickname="u1", is_superuser=False)
    user.roles.all = lambda: _async_list([role])
    perms = await get_user_permissions(user)
    assert set(perms) == set(SYSTEM_ADMIN_PERMISSIONS)
    assert USER_VIEW in perms
    assert ROLE_VIEW in perms
    assert USER_EDIT not in perms
    assert ROLE_EDIT not in perms


@pytest.mark.asyncio
async def test_member_role_has_module_view_permissions():
    member = next(r for r in DEFAULT_ROLES if r["code"] == MEMBER_CODE)
    role = Role(id=2, code=MEMBER_CODE, name="普通成员", permissions=member["permissions"])
    user = User(id=1, username="u1", nickname="u1", is_superuser=False)
    user.roles.all = lambda: _async_list([role])
    perms = await get_user_permissions(user)
    assert UI_CASE_VIEW in perms
    assert PROJECT_VIEW in perms
    assert USER_EDIT not in perms


@pytest.mark.asyncio
async def test_member_role_not_edit_permissions():
    member = next(r for r in DEFAULT_ROLES if r["code"] == MEMBER_CODE)
    role = Role(id=2, code=MEMBER_CODE, name="普通成员", permissions=member["permissions"])
    user = User(id=1, username="u1", nickname="u1", is_superuser=False)
    user.roles.all = lambda: _async_list([role])
    perms = await get_user_permissions(user)
    assert PROJECT_VIEW in perms
    assert DOCS_VIEW in perms
    from app.core.permissions import UI_CASE_EDIT
    assert UI_CASE_EDIT not in perms


@pytest.mark.asyncio
async def test_project_manager_name_does_not_grant_all():
    """角色名含「管理」不再自动获得全部权限。"""
    role = Role(id=3, code="project_manager", name="项目管理员", permissions=[PROJECT_VIEW])
    user = User(id=1, username="u1", nickname="u1", is_superuser=False)
    user.roles.all = lambda: _async_list([role])
    perms = await get_user_permissions(user)
    assert perms == [PROJECT_VIEW]


def test_default_roles_spec_complete():
    codes = {r["code"] for r in DEFAULT_ROLES}
    assert codes >= {
        "system_admin", "member", "project_manager",
        "web_tester", "api_tester", "perf_tester", "ai_tester", "viewer",
    }
    member = next(r for r in DEFAULT_ROLES if r["code"] == MEMBER_CODE)
    assert "user:view" not in member["permissions"]
    assert "role:view" not in member["permissions"]
    assert UI_CASE_VIEW in member["permissions"]
    sys_admin = next(r for r in DEFAULT_ROLES if r["code"] == SYSTEM_ADMIN_CODE)
    assert "user:view" in sys_admin["permissions"]
    assert "role:view" in sys_admin["permissions"]
    assert "user:edit" not in sys_admin["permissions"]
    assert "role:edit" not in sys_admin["permissions"]


async def _async_empty():
    return []


async def _async_list(items):
    return items
