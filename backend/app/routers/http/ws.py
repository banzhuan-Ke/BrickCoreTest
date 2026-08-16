"""WebSocket 接口调试路由"""
from fastapi import APIRouter, Depends, HTTPException

from app.core.platform.auth import is_authenticated, require_permissions, get_current_username
from app.core.platform.permissions import API_MANAGE_EDIT
from app.core.case.variable_resolver import VariableResolver
from app.models.sys import Environment
from app.schemas.http import WsDebugRequest, WsDebugResponse
from app.modules.http.ws_executor import (
    build_ws_response_body,
    ensure_ws_url,
    execute_ws_steps,
    normalize_ws_headers,
    run_ws_assertions,
)
from .utils import replace_variables_with_detail

router = APIRouter(tags=["接口自动化"], dependencies=[Depends(is_authenticated)])


@router.post(
    "/ws/debug",
    summary="WebSocket 接口调试",
    response_model=WsDebugResponse,
    dependencies=[Depends(require_permissions(API_MANAGE_EDIT))],
)
async def debug_ws(item: WsDebugRequest, username: str = Depends(get_current_username)):
    """在线调试 WebSocket：连接 → 发送/接收 → 断言"""
    from app.core.shared.header_merge import merge_request_headers
    from app.modules.http.api_auth_service import prepare_api_runtime_variables

    variables = dict(item.variables or {})
    project_id = item.project_id
    env = None

    original_url = (item.url or "").strip()
    if not original_url:
        raise HTTPException(status_code=400, detail="请输入 WebSocket URL")

    if item.env_id:
        env = await Environment.get_or_none(id=item.env_id, is_del=False)
        if env:
            project_id = project_id or env.project_id

    variables, auth_err, auth_injected_keys = await prepare_api_runtime_variables(
        project_id, item.env_id, variables, inject_auth=True
    )
    if auth_err:
        raise HTTPException(status_code=400, detail=f"授权刷新失败: {auth_err}")

    var_resolver = VariableResolver(variables)
    url, _ = replace_variables_with_detail(original_url, variables, "url", resolver=var_resolver)

    if env and not url.startswith(("ws://", "wss://", "http://", "https://")):
        base_url = (env.host or "").rstrip("/")
        url = base_url + "/" + url.lstrip("/")

    url = ensure_ws_url(url)
    if not url.startswith(("ws://", "wss://")):
        raise HTTPException(
            status_code=400,
            detail="WebSocket URL 需为 ws:// 或 wss://，请检查环境 Base_url 或填写完整地址",
        )

    merged_headers = merge_request_headers(api_headers=item.headers)
    headers = normalize_ws_headers(merged_headers)
    resolved_headers = {}
    for key, value in headers.items():
        val, _ = replace_variables_with_detail(value, variables, f"headers.{key}", resolver=var_resolver)
        resolved_headers[key] = val

    from app.modules.http.http_utils import (
        collect_unresolved_placeholders,
        format_unresolved_variables_error,
    )
    unresolved = []
    unresolved.extend(collect_unresolved_placeholders(url, "url"))
    unresolved.extend(collect_unresolved_placeholders(resolved_headers, "headers"))
    if unresolved:
        raise HTTPException(
            status_code=400,
            detail=format_unresolved_variables_error(
                unresolved,
                env_name=(env.name if env else ""),
                auth_injected_keys=auth_injected_keys,
            ),
        )

    message_log, error, elapsed_ms = await execute_ws_steps(
        url=url,
        headers=resolved_headers,
        steps=item.steps or [],
        timeout=item.timeout or 30,
        variables=variables,
        var_resolver=var_resolver,
    )

    response_body = build_ws_response_body(message_log)
    assertion_results = []
    all_passed = True

    if item.assertions:
        class _TmpCase:
            assertions = item.assertions

        all_passed, assertion_results, _ = run_ws_assertions(response_body, _TmpCase())

    return WsDebugResponse(
        success=error is None and all_passed,
        messages=message_log,
        assertions=assertion_results,
        response_body=response_body,
        elapsed_ms=round(elapsed_ms, 2),
        error=error,
    )
