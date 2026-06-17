"""项目成员访问控制单元测试"""
from app.core.project_access import (
    PROJECT_ROLE_MANAGER,
    PROJECT_ROLE_MEMBER,
    PROJECT_ROLE_OWNER,
    PROJECT_ROLE_VIEWER,
    role_at_least,
)


def test_role_rank_order():
    assert role_at_least(PROJECT_ROLE_OWNER, PROJECT_ROLE_VIEWER)
    assert role_at_least(PROJECT_ROLE_MANAGER, PROJECT_ROLE_MEMBER)
    assert not role_at_least(PROJECT_ROLE_VIEWER, PROJECT_ROLE_MEMBER)
    assert not role_at_least(PROJECT_ROLE_MEMBER, PROJECT_ROLE_MANAGER)


def test_role_at_least_same_level():
    assert role_at_least(PROJECT_ROLE_MEMBER, PROJECT_ROLE_MEMBER)
