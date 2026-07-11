"""UI 资源项目归属与访问校验"""
from __future__ import annotations

from fastapi import HTTPException, status

from app.core.platform.project_access import PROJECT_ROLE_MEMBER, PROJECT_ROLE_VIEWER, assert_project_access
from app.models.sys import Environment


async def assert_user_project_member(user_info: dict, project_id: int) -> None:
    await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_MEMBER)


async def assert_user_project_viewer(user_info: dict, project_id: int) -> None:
    await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_VIEWER)


def assert_environment_for_project(env: Environment | None, project_id: int) -> Environment:
    if not env:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="所选运行环境不存在或已被移除",
        )
    if env.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="运行环境与当前项目不匹配，请选择本项目下的环境",
        )
    return env
