"""
项目级 access 校验依赖（从 query/path/body 提取 project_id）
"""
import json

from fastapi import Depends, Header, HTTPException, Request

from app.core.platform.auth import _authenticate_user_from_token, oauth2_scheme_optional
from app.core.platform.config import INTERNAL_API_KEY
from app.core.platform.project_access import PROJECT_ROLE_MEMBER, PROJECT_ROLE_VIEWER, assert_project_access


async def _project_id_from_json_body(request: Request) -> str | None:
    """从 JSON body 读取 project_id，并回放 body 供后续路由使用。"""
    ct = (request.headers.get("content-type") or "").lower()
    if "application/json" not in ct:
        return None
    body = await request.body()
    if not body:
        return None

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive  # noqa: SLF001 — Starlette 标准回放方式
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(data, dict) and data.get("project_id") is not None:
        return str(data["project_id"])
    return None


def is_mock_call_path(path: str) -> bool:
    """Mock 调用作假 SUT：仅 /api-module/mock-call（及子路径），不含 CRUD /mock。"""
    normalized = (path or "").rstrip("/")
    return normalized == "/api-module/mock-call" or normalized.startswith(
        "/api-module/mock-call/"
    )


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

    # Mock 调用免平台 JWT（管理 CRUD /api-module/mock 仍鉴权）
    if is_mock_call_path(path):
        return

    project_id = request.path_params.get("project_id") or request.query_params.get("project_id")
    if not project_id and request.method in ("POST", "PUT", "PATCH", "DELETE"):
        project_id = await _project_id_from_json_body(request)

    has_runner_auth = bool(
        x_runner_token
        or (x_internal_token and x_internal_token == INTERNAL_API_KEY)
    )

    # App Inspector Runner 回调/状态（无 project_id、无用户 JWT，由路由内 verify_runner_or_internal 校验）
    if "/inspector/sessions/" in path and (
        path.endswith("/callback")
        or path.endswith("/webview-callback")
        or path.endswith("/runner-status")
    ):
        return

    # UI 交互调试 Runner 回调/轮询（无 project_id、无用户 JWT）
    if "/debug/sessions/" in path and (
        path.endswith("/runner-status")
        or path.endswith("/runner-command")
        or path.endswith("/runner-callback")
    ):
        return

    # 智能浏览器 Runner 回调 / LLM 代理（无 project_id、无用户 JWT）
    if "/browser-lab/tasks/" in path and (
        path.endswith("/runner-callback")
        or path.endswith("/chat/completions")
    ):
        return

    if "/ui-agent-jobs/" in path and (
        path.endswith("/runner-callback")
        or path.endswith("/runner-plan")
        or path.endswith("/chat/completions")
    ):
        return

    # 单页 DOM 抓取 Runner 回调（browser_job 内部 token，非用户 JWT）
    if "/page-fetch/" in path and path.endswith("/runner-callback"):
        return

    # Runner / 内部回调（如 /ai/record/{id}/callback）无用户 JWT，由路由内 verify_runner_or_internal 校验
    if has_runner_auth and not project_id:
        return

    # Runner 定位器自愈等 internal 接口可在 body/query 带 project_id（记用量），仍用 Runner Token 鉴权
    if has_runner_auth and (
        path.endswith("/locator-heal/internal")
        or path.endswith("/app-locator-heal/internal")
    ):
        return

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_info = await _authenticate_user_from_token(token)

    if not project_id and request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if "/test-management" in path:
            raise HTTPException(status_code=403, detail="缺少 project_id，拒绝访问")
        return

    try:
        pid = int(project_id)
    except (TypeError, ValueError):
        if "/test-management" in path and request.method in ("POST", "PUT", "PATCH", "DELETE"):
            raise HTTPException(status_code=403, detail="project_id 无效")
        return

    # 成员管理接口在专用路由内校验更高权限
    if "/members" in path:
        return

    min_role = PROJECT_ROLE_VIEWER if request.method in ("GET", "HEAD", "OPTIONS") else PROJECT_ROLE_MEMBER
    await assert_project_access(user_info, pid, min_role=min_role)
