"""
项目级 access 校验依赖（从 query/path 提取 project_id）
"""
from fastapi import Depends, Header, HTTPException, Request

from app.core.auth import _authenticate_user_from_token, oauth2_scheme_optional
from app.core.config import INTERNAL_API_KEY
from app.core.project_access import PROJECT_ROLE_MEMBER, PROJECT_ROLE_VIEWER, assert_project_access


async def optional_project_access_check(
    request: Request,
    token: str | None = Depends(oauth2_scheme_optional),
    x_runner_token: str | None = Header(None, alias="X-Runner-Token"),
    x_internal_token: str | None = Header(None, alias="X-Internal-Token"),
) -> None:
    """对带 project_id 的请求校验项目成员权限（GET 需 viewer，写操作需 member）。"""
    path = request.url.path.rstrip("/")

    # 项目列表/创建不走成员校验
    if path.endswith("/projects") and request.method in ("GET", "POST"):
        return

    project_id = request.path_params.get("project_id") or request.query_params.get("project_id")

    # Runner / 内部回调（如 /ai/record/{id}/callback）无用户 JWT，由路由内 verify_runner_or_internal 校验
    if not project_id and (
        x_runner_token
        or (x_internal_token and x_internal_token == INTERNAL_API_KEY)
    ):
        return

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_info = await _authenticate_user_from_token(token)

    if not project_id:
        return

    try:
        pid = int(project_id)
    except (TypeError, ValueError):
        return

    # 成员管理接口在专用路由内校验更高权限
    if "/members" in path:
        return

    min_role = PROJECT_ROLE_VIEWER if request.method in ("GET", "HEAD", "OPTIONS") else PROJECT_ROLE_MEMBER
    await assert_project_access(user_info, pid, min_role=min_role)
