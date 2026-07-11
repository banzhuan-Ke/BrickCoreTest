"""接口测试套件和执行相关 API"""
import json
import time
import asyncio
from typing import List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Depends, Query, status, BackgroundTasks
from tortoise import transactions

from app.models.http import (
    ApiTestSuite, ApiSuiteCase, ApiTestCase, ApiDefinition,
    ApiRunRecord, ApiSuiteRunRecord, ApiCronJob
)
from app.schemas.http import (
    ApiSuiteCreate, ApiSuiteUpdate, ApiSuiteOut, ApiSuiteListResponse,
    ApiBatchRunRequest, ApiSuiteRunRequest, ApiBatchRunResult,
    ApiRunResult, ApiAssertionResult,
    ApiSuiteRunRecordOut, ApiSuiteRunListResponse
)
from app.core.platform.auth import is_authenticated, require_permissions, get_current_username
from app.core.platform.permissions import API_SUITE_VIEW, API_SUITE_EDIT, API_CASE_EXECUTE
from app.models.sys import Environment, Project, TestCatalog
from app.core.platform.config import API_FILE_BUCKET
from app.core.shared.catalog_utils import apply_catalog_filter, resolve_catalog

router = APIRouter(tags=["接口测试套件"], dependencies=[Depends(is_authenticated), Depends(require_permissions(API_SUITE_VIEW))])


# ============ 测试套件管理 ============

@router.post("/suite", summary="创建测试套件", response_model=ApiSuiteOut,
             dependencies=[Depends(require_permissions(API_SUITE_EDIT))])
async def create_suite(item: ApiSuiteCreate, username: str = Depends(get_current_username)):
    """创建接口测试套件"""
    project = await Project.get_or_none(id=item.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=422, detail="项目不存在")
    
    async with transactions.in_transaction():
        suite = await ApiTestSuite.create(
            name=item.name,
            project_id=item.project_id,
            catalog_id=item.catalog_id,
            env_id=item.env_id,
            timeout=item.timeout,
            retry_count=item.retry_count,
            stop_on_failure=item.stop_on_failure,
            parallel=item.parallel,
            description=item.description,
            setup_sql_ids=item.setup_sql_ids or [],
            teardown_sql_ids=item.teardown_sql_ids or [],
            db_assertions=item.db_assertions or [],
            create_by=username,
            update_by=username,
        )
        
        # 添加用例关联
        for idx, case_id in enumerate(item.case_ids):
            case = await ApiTestCase.get_or_none(id=case_id, is_del=False)
            if case:
                await ApiSuiteCase.create(
                    suite_id=suite.id,
                    case_id=case_id,
                    sort=idx
                )
    
    return await get_suite_detail(suite.id)


@router.get("/suite", summary="测试套件列表", response_model=ApiSuiteListResponse)
async def get_suites(
    project_id: int = Query(..., description="项目ID"),
    keyword: Optional[str] = Query(None, description="关键字"),
    module_id: Optional[int] = Query(None, description="目录ID（兼容旧参数）"),
    catalog_id: Optional[int] = Query(None, description="目录ID"),
    include_children: bool = Query(True, description="目录筛选是否包含子目录"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=5000)
):
    """获取测试套件列表"""
    query = ApiTestSuite.filter(project_id=project_id, is_del=False)
    
    if keyword:
        query = query.filter(name__contains=keyword)
    
    filter_catalog = catalog_id if catalog_id is not None else module_id
    if filter_catalog:
        await resolve_catalog(project_id, filter_catalog)
        query = await apply_catalog_filter(query, project_id, filter_catalog, include_children=include_children)
    
    total = await query.count()
    suites = await query.order_by("-id").offset((page - 1) * size).limit(size).all()
    
    result = []
    for suite in suites:
        case_count = await ApiSuiteCase.filter(suite_id=suite.id).count()
        catalog_name = None
        if suite.catalog_id:
            catalog = await TestCatalog.get_or_none(id=suite.catalog_id)
            catalog_name = catalog.name if catalog else None
        result.append({
            "id": suite.id,
            "name": suite.name,
            "project_id": suite.project_id,
            "catalog_id": suite.catalog_id,
            "catalog_name": catalog_name,
            "module_id": suite.catalog_id,
            "module_name": catalog_name,
            "env_id": suite.env_id,
            "timeout": suite.timeout,
            "retry_count": suite.retry_count,
            "stop_on_failure": suite.stop_on_failure,
            "parallel": suite.parallel,
            "description": suite.description,
            "setup_sql_ids": getattr(suite, "setup_sql_ids", None) or [],
            "teardown_sql_ids": getattr(suite, "teardown_sql_ids", None) or [],
            "db_assertions": getattr(suite, "db_assertions", None) or [],
            "case_count": case_count,
            "cases": [],
            "create_by": suite.create_by,
            "update_by": suite.update_by,
            "create_time": suite.create_time,
            "update_time": suite.update_time
        })
    
    return ApiSuiteListResponse(data=result, total=total, page=page, size=size)


@router.get("/suite/{suite_id}", summary="套件详情", response_model=ApiSuiteOut)
async def get_suite_detail(suite_id: int):
    """获取测试套件详情"""
    suite = await ApiTestSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=404, detail="套件不存在")
    
    # 获取套件下的用例
    suite_cases = await ApiSuiteCase.filter(suite_id=suite_id).order_by("sort").all()
    cases = []
    for sc in suite_cases:
        case = await ApiTestCase.get_or_none(id=sc.case_id, is_del=False)
        if case:
            api = await case.api
            cases.append({
                "id": sc.id,
                "case_id": case.id,
                "case_name": case.name,
                "api_name": api.name if api else "未知",
                "api_method": api.method if api else "",
                "sort": sc.sort,
                "exec_order": sc.sort + 1,
            })
    
    catalog_name = None
    if suite.catalog_id:
        catalog = await TestCatalog.get_or_none(id=suite.catalog_id)
        catalog_name = catalog.name if catalog else None
    
    return {
        "id": suite.id,
        "name": suite.name,
        "project_id": suite.project_id,
        "catalog_id": suite.catalog_id,
        "catalog_name": catalog_name,
        "module_id": suite.catalog_id,
        "module_name": catalog_name,
        "env_id": suite.env_id,
        "timeout": suite.timeout,
        "retry_count": suite.retry_count,
        "stop_on_failure": suite.stop_on_failure,
        "parallel": suite.parallel,
        "description": suite.description,
        "setup_sql_ids": getattr(suite, "setup_sql_ids", None) or [],
        "teardown_sql_ids": getattr(suite, "teardown_sql_ids", None) or [],
        "db_assertions": getattr(suite, "db_assertions", None) or [],
        "case_count": len(cases),
        "cases": cases,
        "create_by": suite.create_by,
        "update_by": suite.update_by,
        "create_time": suite.create_time,
        "update_time": suite.update_time
    }


@router.put("/suite/{suite_id}", summary="更新测试套件", response_model=ApiSuiteOut,
            dependencies=[Depends(require_permissions(API_SUITE_EDIT))])
async def update_suite(suite_id: int, item: ApiSuiteUpdate, username: str = Depends(get_current_username)):
    """更新测试套件"""
    suite = await ApiTestSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=404, detail="套件不存在")
    
    async with transactions.in_transaction():
        suite.name = item.name
        suite.catalog_id = item.catalog_id
        suite.env_id = item.env_id
        suite.timeout = item.timeout
        suite.retry_count = item.retry_count
        suite.stop_on_failure = item.stop_on_failure
        suite.parallel = item.parallel
        suite.description = item.description
        suite.setup_sql_ids = item.setup_sql_ids or []
        suite.teardown_sql_ids = item.teardown_sql_ids or []
        suite.db_assertions = item.db_assertions or []
        suite.update_by = username
        await suite.save()
        
        # 更新用例关联
        if item.case_ids is not None:
            await ApiSuiteCase.filter(suite_id=suite_id).delete()
            for idx, case_id in enumerate(item.case_ids):
                case = await ApiTestCase.get_or_none(id=case_id, is_del=False)
                if case:
                    await ApiSuiteCase.create(
                        suite_id=suite_id,
                        case_id=case_id,
                        sort=idx
                    )
    
    return await get_suite_detail(suite_id)


@router.delete("/suite/{suite_id}", summary="删除测试套件", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(API_SUITE_EDIT))])
async def delete_suite(suite_id: int):
    """删除测试套件"""
    suite = await ApiTestSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=404, detail="套件不存在")
    
    suite.is_del = True
    await suite.save()


@router.post("/suite/batch-delete", summary="批量删除测试套件", status_code=status.HTTP_204_NO_CONTENT,
             dependencies=[Depends(require_permissions(API_SUITE_EDIT))])
async def batch_delete_suites(suite_ids: List[int]):
    """批量删除测试套件（逻辑删除）"""
    if not suite_ids:
        raise HTTPException(status_code=400, detail="请选择要删除的套件")
    deleted = 0
    for suite_id in suite_ids:
        suite = await ApiTestSuite.get_or_none(id=suite_id, is_del=False)
        if suite:
            suite.is_del = True
            await suite.save()
            deleted += 1
    return None


# ============ 套件用例管理 ============

@router.get("/suite/{suite_id}/cases", summary="获取套件用例列表")
async def get_suite_cases(suite_id: int):
    """获取套件下的用例列表"""
    suite = await ApiTestSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=404, detail="套件不存在")
    
    suite_cases = await ApiSuiteCase.filter(suite_id=suite_id).order_by("sort").all()
    cases = []
    for sc in suite_cases:
        case = await ApiTestCase.get_or_none(id=sc.case_id, is_del=False)
        if case:
            api = await case.api
            cases.append({
                "id": sc.id,
                "case_id": case.id,
                "case_name": case.name,
                "api_name": api.name if api else "未知",
                "api_method": api.method if api else "",
                "sort": sc.sort,
                "exec_order": sc.sort + 1,
            })
    return {"cases": cases}


@router.put("/suite/{suite_id}/cases", summary="更新套件用例",
            dependencies=[Depends(require_permissions(API_SUITE_EDIT))])
async def update_suite_cases(suite_id: int, data: dict):
    """更新套件下的用例列表"""
    suite = await ApiTestSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=404, detail="套件不存在")
    
    case_ids = data.get("case_ids", [])
    async with transactions.in_transaction():
        await ApiSuiteCase.filter(suite_id=suite_id).delete()
        for idx, case_id in enumerate(case_ids):
            case = await ApiTestCase.get_or_none(id=case_id, is_del=False)
            if case:
                await ApiSuiteCase.create(
                    suite_id=suite_id,
                    case_id=case_id,
                    sort=idx
                )
    
    return await get_suite_detail(suite_id)


# ============ 批量执行和套件执行 ============

from .utils import (
    evaluate_assertion,
    run_case_assertions,
    extract_variables,
    build_api_url,
    replace_variables_with_detail,
    resolve_body_fields,
    replace_body_fields_with_detail,
    build_form_data_multipart,
    prepare_httpx_headers,
)
from app.core.case.variable_resolver import VariableResolver
from app.modules.data_tools.errors import ToolExecutionError


async def run_single_case(
    case_id: int,
    env_id: int,
    suite_record_id: Optional[int] = None,
    username: str = "",
    variables: dict = None,
    auto_validate_schema: bool = False,
    data_run_index: Optional[int] = None,
    data_row_label: Optional[str] = None,
    project_global_vars: dict = None,
) -> ApiRunResult:
    """执行单个用例"""
    stage_timings = {}
    _stage_start = time.time()
    
    case = await ApiTestCase.get_or_none(id=case_id, is_del=False)
    if not case:
        return ApiRunResult(record_id=0, status="failed", error="用例不存在")
    
    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        return ApiRunResult(record_id=0, status="failed", error="环境不存在")
    
    api = await case.api
    if not api:
        return ApiRunResult(record_id=0, status="failed", error="关联接口不存在")
    
    stage_timings["load_case_ms"] = round((time.time() - _stage_start) * 1000, 2)
    _stage_start = time.time()

    # 项目全局变量（未传入时按用例所属项目自动加载）
    if project_global_vars is None:
        proj = await Project.get_or_none(id=case.project_id, is_del=False)
        proj_vars = (proj.global_vars or {}) if proj else {}
    else:
        proj = await Project.get_or_none(id=case.project_id, is_del=False)
        proj_vars = project_global_vars or {}

    # 获取环境变量；优先级：project_vars < env_vars < passed variables
    env_vars = env.global_vars or {}
    all_variables = {**proj_vars, **env_vars, **(variables or {})}

    from app.modules.data_tools.tag_service import merge_execution_variables

    all_variables = await merge_execution_variables(
        case.project_id, env_id, all_variables
    )
    
    stage_timings["merge_vars_ms"] = round((time.time() - _stage_start) * 1000, 2)
    _stage_start = time.time()

    # ===== API Token 授权注入 =====
    from app.modules.http.api_auth_service import inject_auth_variables
    auth_vars, auth_err = await inject_auth_variables(case.project_id, env_id, all_variables)
    if auth_err:
        return ApiRunResult(record_id=0, status="failed", error=f"授权刷新失败: {auth_err}")
    if auth_vars:
        all_variables.update(auth_vars)
    stage_timings["auth_inject_ms"] = round((time.time() - _stage_start) * 1000, 2)
    _stage_start = time.time()

    # ===== 前置脚本 =====
    script_logs = []
    if case.pre_script:
        from .script_runner import run_script
        pre_result = run_script(case.pre_script, all_variables)
        all_variables = pre_result["variables"]   # 脚本可修改变量
        script_logs.extend(pre_result["logs"])
        if pre_result["error"]:
            script_logs.append(f"[pre_script ERROR] {pre_result['error']}")
    
    stage_timings["pre_script_ms"] = round((time.time() - _stage_start) * 1000, 2)
    _stage_start = time.time()

    # 安全获取配置，确保是字典类型
    from app.core.shared.header_merge import merge_request_headers

    headers = merge_request_headers(
        api_headers=api.headers,
        case_headers=case.request_headers,
    )
    
    api_params = api.params or []
    if isinstance(api_params, dict):
        api_params = [{"name": k, "value": v} for k, v in api_params.items()]
    
    case_params = case.request_params or []
    if isinstance(case_params, dict):
        case_params = [{"name": k, "value": v} for k, v in case_params.items()]
    
    base_url = headers.pop("base_url", None) if isinstance(headers, dict) else None
    if not base_url and isinstance(case.request_headers, dict):
        base_url = case.request_headers.get("base_url")
    base_url = base_url or api.base_url or env.host
    api_protocol = getattr(api, "protocol", "http") or "http"
    try:
        url = build_api_url(base_url, api.path, protocol=api_protocol)
    except ValueError as e:
        return ApiRunResult(record_id=0, status="failed", error=str(e))
    
    # 请求头已在 merge_request_headers 中按 key 合并
    # 请求参数：用例级别的 params 完全覆盖接口定义的 params
    if case_params:
        params = {p.get("name", ""): p.get("value", "") for p in case_params if p.get("name")}
    else:
        params = {p.get("name", ""): p.get("value", "") for p in api_params if p.get("name")}
    
    body = case.request_body if case.request_body else (api.body or {})
    body_type = case.request_body_type or api.body_type or 'json'
    body_fields = resolve_body_fields(case.request_body_fields, api.body_fields)
    
    # 记录原始值
    original_url = url
    original_headers = dict(headers) if headers else {}
    original_params = dict(params) if params else {}
    original_body = body
    original_body_fields = list(body_fields)
    
    # 变量替换并获取详情（共享 resolver，保证 random_int / dt 工具等同用例内一致）
    var_resolver = VariableResolver(all_variables)
    try:
        url, url_details = replace_variables_with_detail(url, all_variables, "url", resolver=var_resolver)
        headers, headers_details = replace_variables_with_detail(headers, all_variables, "headers", resolver=var_resolver)
        params, params_details = replace_variables_with_detail(params, all_variables, "params", resolver=var_resolver)
        body, body_details = replace_variables_with_detail(body, all_variables, "body", resolver=var_resolver)
        body_fields, body_fields_details = replace_body_fields_with_detail(body_fields, all_variables, resolver=var_resolver)
    except ToolExecutionError as exc:
        return ApiRunResult(record_id=0, status="failed", error=str(exc))
    
    # 合并替换详情
    all_replacements = url_details + headers_details + params_details + body_details + body_fields_details
    
    # 构建请求详情
    request_detail = {
        "env_id": env_id,
        "env_name": env.name,
        "url": {"original": original_url, "final": url},
        "headers": {"original": original_headers, "final": headers if isinstance(headers, dict) else {}},
        "params": {"original": original_params, "final": params if isinstance(params, dict) else {}},
        "body": {"original": original_body, "final": body},
        "body_type": body_type,
        "body_fields": {"original": original_body_fields, "final": body_fields},
        "variables_used": var_resolver.get_resolved_snapshot(),
        "replacements": all_replacements,
        "script_logs": script_logs,   # 前置脚本日志（后置脚本日志将在执行后追加）
    }
    
    stage_timings["build_request_ms"] = round((time.time() - _stage_start) * 1000, 2)
    _stage_start = time.time()

    # 确定重试次数（用例级优先，未设置时继承套件级）
    retry_count = case.retry_count or 0
    if suite_record_id:
        suite_record = await ApiSuiteRunRecord.get_or_none(id=suite_record_id)
        if suite_record:
            suite = await suite_record.suite
            if suite and retry_count == 0:
                retry_count = suite.retry_count or 0

    # 内部函数：执行一次请求（含断言和变量提取）
    last_attempt_timings = {}
    is_ws = api_protocol == "websocket"
    is_graphql = api_protocol == "graphql"
    is_grpc = api_protocol == "grpc"
    
    async def _execute_once():
        if is_ws:
            from app.modules.http.ws_executor import execute_ws_case_attempt

            (
                response,
                response_body,
                assertions_result,
                all_passed,
                extracted_vars,
                extractor_results,
                db_assertion_results,
                attempt_timings,
                message_log,
            ) = await execute_ws_case_attempt(
                url=url,
                headers=headers if isinstance(headers, dict) else {},
                case=case,
                api=api,
                all_variables=all_variables,
                var_resolver=var_resolver,
                auto_validate_schema=auto_validate_schema,
                env_id=env_id,
                script_logs=script_logs,
            )
            last_attempt_timings.update(attempt_timings)
            request_detail["ws_messages"] = message_log
            return (
                response,
                response_body,
                assertions_result,
                all_passed,
                extracted_vars,
                extractor_results,
                db_assertion_results,
            )

        if is_graphql:
            from app.modules.http.graphql_executor import execute_graphql_case_attempt

            (
                response,
                response_body,
                assertions_result,
                all_passed,
                extracted_vars,
                extractor_results,
                db_assertion_results,
                attempt_timings,
                _,
            ) = await execute_graphql_case_attempt(
                url=url,
                headers=headers if isinstance(headers, dict) else {},
                case=case,
                api=api,
                all_variables=all_variables,
                var_resolver=var_resolver,
                auto_validate_schema=auto_validate_schema,
                env_id=env_id,
                script_logs=script_logs,
            )
            last_attempt_timings.update(attempt_timings)
            return (
                response,
                response_body,
                assertions_result,
                all_passed,
                extracted_vars,
                extractor_results,
                db_assertion_results,
            )

        if is_grpc:
            from app.modules.http.grpc_executor import execute_grpc_case_attempt

            (
                response,
                response_body,
                assertions_result,
                all_passed,
                extracted_vars,
                extractor_results,
                db_assertion_results,
                attempt_timings,
                _,
            ) = await execute_grpc_case_attempt(
                host=url,
                case=case,
                api=api,
                all_variables=all_variables,
                var_resolver=var_resolver,
                auto_validate_schema=auto_validate_schema,
                env_id=env_id,
                script_logs=script_logs,
            )
            last_attempt_timings.update(attempt_timings)
            return (
                response,
                response_body,
                assertions_result,
                all_passed,
                extracted_vars,
                extractor_results,
                db_assertion_results,
            )

        async with httpx.AsyncClient(timeout=case.timeout, follow_redirects=True) as client:
            method = api.method.upper()
            kwargs = {"headers": prepare_httpx_headers(headers), "params": params}

            if method in ["POST", "PUT", "PATCH"]:
                if body_type in ["json", "xml"] and isinstance(body, (dict, list)):
                    kwargs["json"] = body if body_type == "json" else body
                elif body_type == "form-data":
                    kwargs["files"] = build_form_data_multipart(
                        body_fields, API_FILE_BUCKET, use_bytes_io=True
                    )
                elif body is not None:
                    kwargs["data"] = body

            _t0 = time.time()
            response = await client.request(method, url, **kwargs)
            last_attempt_timings["request_ms"] = round((time.time() - _t0) * 1000, 2)

            try:
                response_body = response.json()
            except:
                response_body = response.text

            # 执行断言（支持条件分支 assertion_groups）
            _t0 = time.time()
            all_passed, assertion_rows, matched_group = run_case_assertions(response, response_body, case)
            assertions_result = []
            for row in assertion_rows:
                assertions_result.append(ApiAssertionResult(
                    type=row.get("type"),
                    target=row.get("target"),
                    operator=row.get("operator"),
                    expected=row.get("expected"),
                    actual=row.get("actual"),
                    passed=row.get("passed"),
                    group_name=row.get("group_name"),
                    description=row.get("description"),
                ))
            if matched_group:
                last_attempt_timings["assertion_group"] = matched_group
            last_attempt_timings["assertion_ms"] = round((time.time() - _t0) * 1000, 2)

            # 自动校验响应 Schema
            _t0 = time.time()
            if auto_validate_schema:
                schema_data = api.response_schema or {}
                schema_obj = schema_data.get('schema') if isinstance(schema_data, dict) else None
                if schema_obj:
                    from .utils import validate_response_schema
                    schema_assertions = validate_response_schema(response_body, schema_obj)
                    for sa in schema_assertions:
                        assertions_result.append(sa)
                        if not sa.get("passed"):
                            all_passed = False
            last_attempt_timings["schema_validate_ms"] = round((time.time() - _t0) * 1000, 2)
            
            # 提取变量
            _t0 = time.time()
            extracted_vars, extractor_results = extract_variables(
                response_body, case.extractors or [], headers=response.headers
            )
            last_attempt_timings["extract_vars_ms"] = round((time.time() - _t0) * 1000, 2)

            # ===== 后置脚本 =====
            _t0 = time.time()
            if case.post_script:
                from .script_runner import run_script
                resp_ctx = {
                    "status_code": response.status_code,
                    "body": response_body,
                    "headers": dict(response.headers),
                }
                script_vars = {**all_variables, **extracted_vars}
                post_result = run_script(case.post_script, script_vars, resp_ctx)
                for key, val in post_result["variables"].items():
                    if key not in all_variables or val != all_variables.get(key):
                        extracted_vars[key] = val
                        all_variables[key] = val
                script_logs.extend(post_result["logs"])
                if post_result["error"]:
                    script_logs.append(f"[post_script ERROR] {post_result['error']}")
            last_attempt_timings["post_script_ms"] = round((time.time() - _t0) * 1000, 2)

            # ===== 数据库断言 =====
            _t0 = time.time()
            db_assertion_results = []
            if getattr(case, "db_assertions", None):
                from app.core.db.db_factory_service import evaluate_db_assertions
                script_vars = {**all_variables, **extracted_vars}
                db_eval = await evaluate_db_assertions(
                    case.db_assertions or [],
                    script_vars,
                    env_id,
                    case.project_id,
                )
                for dr in db_eval.get("results", []):
                    db_assertion_results.append(ApiAssertionResult(
                        type="db",
                        target=dr.get("target"),
                        operator=dr.get("operator", "equals"),
                        expected=dr.get("expected"),
                        actual=dr.get("actual"),
                        passed=bool(dr.get("passed")),
                    ))
                    if not dr.get("passed"):
                        all_passed = False
            last_attempt_timings["db_assertion_ms"] = round((time.time() - _t0) * 1000, 2)

            return response, response_body, assertions_result, all_passed, extracted_vars, extractor_results, db_assertion_results

    # 重试循环
    last_error = None
    last_response = None
    last_response_body = None
    last_assertions_result = []
    last_all_passed = False
    last_extracted_vars = {}
    last_extractor_results = []
    last_db_assertion_results = []
    retry_history = []

    start_time = time.time()
    for attempt in range(retry_count + 1):
        attempt_start = time.time()
        try:
            response, response_body, assertions_result, all_passed, extracted_vars, extractor_results, db_assertion_results = await _execute_once()
            attempt_time = (time.time() - attempt_start) * 1000
            last_response = response
            last_response_body = response_body
            last_assertions_result = assertions_result + db_assertion_results
            last_all_passed = all_passed
            last_extracted_vars = extracted_vars
            last_extractor_results = extractor_results
            last_db_assertion_results = db_assertion_results

            retry_history.append({
                "attempt": attempt + 1,
                "status": "success" if all_passed else "failed",
                "response_status": response.status_code,
                "response_time": round(attempt_time, 2),
                "response_body": response_body if not isinstance(response_body, str) or len(response_body) <= 2000 else response_body[:2000] + "...(truncated)",
                "error": None,
                "assertion_passed": sum(1 for a in last_assertions_result if a.passed),
                "assertion_total": len(last_assertions_result),
                "assertions": [a.model_dump() if hasattr(a, 'model_dump') else a for a in last_assertions_result]
            })

            if all_passed:
                break

            if attempt < retry_count:
                await asyncio.sleep(1)
        except Exception as e:
            attempt_time = (time.time() - attempt_start) * 1000
            last_error = str(e)
            retry_history.append({
                "attempt": attempt + 1,
                "status": "error",
                "response_status": None,
                "response_time": round(attempt_time, 2),
                "response_body": None,
                "error": str(e),
                "assertion_passed": 0,
                "assertion_total": 0,
                "assertions": []
            })
            if attempt < retry_count:
                await asyncio.sleep(1)

    response_time = (time.time() - start_time) * 1000
    
    # 组装阶段耗时统计
    stage_timings["request_ms"] = last_attempt_timings.get("request_ms", 0)
    stage_timings["assertion_ms"] = last_attempt_timings.get("assertion_ms", 0)
    stage_timings["schema_validate_ms"] = last_attempt_timings.get("schema_validate_ms", 0)
    stage_timings["extract_vars_ms"] = last_attempt_timings.get("extract_vars_ms", 0)
    stage_timings["post_script_ms"] = last_attempt_timings.get("post_script_ms", 0)
    stage_timings["db_assertion_ms"] = last_attempt_timings.get("db_assertion_ms", 0)
    stage_timings["total_ms"] = round(response_time, 2)
    
    # 统一保存记录
    safe_headers = headers if 'headers' in locals() and isinstance(headers, dict) else {}

    if last_response is None:
        # 所有重试均异常
        request_detail_for_error = locals().get('request_detail', {
            "url": {"original": "", "final": url if 'url' in locals() else ""},
            "headers": {"original": {}, "final": safe_headers},
            "params": {"original": {}, "final": {}},
            "body": {"original": None, "final": body if 'body' in locals() else None},
            "variables_used": all_variables if 'all_variables' in locals() else {},
            "replacements": [],
            "stage_timings": stage_timings,
        })
        record_data = {
            "case_id": case_id,
            "project_id": case.project_id,
            "status": "failed",
            "request_url": url if 'url' in locals() else "",
            "request_method": "WS" if is_ws else (api.method if api else ""),
            "request_headers": safe_headers,
            "request_body": body if 'body' in locals() else None,
            "error_msg": last_error or "未知错误",
            "request_detail": request_detail_for_error,
            "run_by": username,
            "data_run_index": data_run_index,
            "data_row_label": data_row_label,
        }
        if suite_record_id:
            record_data["suite_run_record_id"] = suite_record_id
        record = await ApiRunRecord.create(**record_data)

        return ApiRunResult(
            record_id=record.id,
            status="failed",
            error=last_error or "未知错误",
            data_run_index=data_run_index,
            data_row_label=data_row_label,
        )
    else:
        # 先把 retry_info 和脚本日志写入 request_detail，确保持久化到数据库
        actual_retry_count = len(retry_history) - 1 if retry_history else 0
        request_detail["retry_info"] = {
            "retry_count": actual_retry_count,
            "total_attempts": len(retry_history),
            "attempts": retry_history
        }
        # 更新脚本日志（后置脚本执行后 script_logs 已追加）
        request_detail["script_logs"] = script_logs
        request_detail["stage_timings"] = stage_timings
        request_detail["extractor_results"] = last_extractor_results

        record_data = {
            "case_id": case_id,
            "project_id": case.project_id,
            "status": "success" if last_all_passed else "failed",
            "request_url": url,
            "request_method": "WS" if is_ws else (api.method.upper() if api else ""),
            "request_headers": safe_headers,
            "request_body": body,
            "response_status": last_response.status_code,
            "response_headers": dict(last_response.headers),
            "response_body": last_response_body,
            "response_time": response_time,
            "assertions_result": [a.model_dump() if hasattr(a, 'model_dump') else a for a in last_assertions_result],
            "extracted_vars": last_extracted_vars,
            "request_detail": request_detail,
            "run_by": username,
            "data_run_index": data_run_index,
            "data_row_label": data_row_label,
        }
        if suite_record_id:
            record_data["suite_run_record_id"] = suite_record_id
        record = await ApiRunRecord.create(**record_data)

        http_time = last_attempt_timings.get("request_ms", 0)
        response_detail = {
            "status_code": last_response.status_code,
            "headers": dict(last_response.headers),
            "body": last_response_body,
            "http_time": http_time,
            "total_time": round(response_time, 2),
            "time": http_time,
        }

        return ApiRunResult(
            record_id=record.id,
            status="success" if last_all_passed else "failed",
            response_status=last_response.status_code,
            response_time=response_time,
            http_response_time=http_time,
            assertions=last_assertions_result,
            extracted_vars=last_extracted_vars,
            extractor_results=last_extractor_results,
            request_detail=request_detail,
            response_detail=response_detail,
            case_id=case.id,
            case_name=case.name,
            retry_info=request_detail["retry_info"],
            data_run_index=data_run_index,
            data_row_label=data_row_label,
        )


async def run_data_driven_case(
    case_id: int,
    env_id: int,
    username: str = "",
    base_variables: dict = None,
    auto_validate_schema: bool = False,
    propagate_extracted: bool = True,
):
    """数据驱动执行：按 data_set 每行执行一次 run_single_case，返回 ApiDataDrivenRunResult"""
    from app.schemas.http import ApiDataDrivenRunResult

    case = await ApiTestCase.get_or_none(id=case_id, is_del=False)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")

    data_set = case.data_set or []

    if not data_set:
        # 无数据集时当做普通单次执行
        result = await run_single_case(case_id, env_id, None, username, base_variables, auto_validate_schema)
        return ApiDataDrivenRunResult(
            total_rows=1,
            results=[result],
            success=1 if result.status == "success" else 0,
            failed=0 if result.status == "success" else 1,
        )

    results = []
    success_count = 0
    failed_count = 0
    accumulated = dict(base_variables or {})

    for idx, row in enumerate(data_set):
        # 行数据优先级最高；可选：上一行提取的变量传递到下一行
        row_vars = {**accumulated, **row}
        row_label = ", ".join(f"{k}={v}" for k, v in row.items())[:100]

        result = await run_single_case(
            case_id,
            env_id,
            None,
            username,
            row_vars,
            auto_validate_schema,
            data_run_index=idx,
            data_row_label=row_label,
        )
        results.append(result)
        if propagate_extracted and result.extracted_vars:
            accumulated.update(result.extracted_vars)
        if result.status == "success":
            success_count += 1
        else:
            failed_count += 1

    return ApiDataDrivenRunResult(
        total_rows=len(data_set),
        results=results,
        success=success_count,
        failed=failed_count,
    )


@router.post("/batch-run", summary="批量执行用例", response_model=ApiBatchRunResult,
             dependencies=[Depends(require_permissions(API_CASE_EXECUTE))])
async def batch_run(request: ApiBatchRunRequest, background_tasks: BackgroundTasks, username: str = Depends(get_current_username)):
    """批量执行接口测试用例（委托 exec 模块，含数据工厂 hooks）"""
    from .exec import batch_run as exec_batch_run
    return await exec_batch_run(request, background_tasks, username)


@router.post("/suite/{suite_id}/run", summary="执行测试套件", response_model=ApiBatchRunResult)
async def run_suite(suite_id: int, request: ApiSuiteRunRequest, username: str = Depends(get_current_username)):
    """执行测试套件"""
    suite = await ApiTestSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=404, detail="套件不存在")
    
    # 获取套件下的用例
    suite_cases = await ApiSuiteCase.filter(suite_id=suite_id).order_by("sort").all()
    case_ids = [sc.case_id for sc in suite_cases]
    
    if not case_ids:
        raise HTTPException(status_code=422, detail="套件中没有用例")
    
    # 优先使用传入的环境ID，否则使用套件默认环境
    env_id = request.env_id
    if not env_id:
        env_id = suite.env_id
    
    if not env_id:
        raise HTTPException(status_code=422, detail="请指定执行环境")
    
    return await batch_run(
        ApiBatchRunRequest(case_ids=case_ids, env_id=env_id, suite_id=suite_id, auto_validate_schema=getattr(request, 'auto_validate_schema', False)),
        None,
        username
    )


# ============ 执行记录查询 ============

@router.get("/run-records", summary="执行记录列表", response_model=ApiSuiteRunListResponse)
async def get_run_records(
    project_id: int = Query(..., description="项目ID"),
    suite_id: Optional[int] = Query(None, description="套件ID"),
    status: Optional[str] = Query(None, description="状态"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=5000)
):
    """获取执行记录列表"""
    query = ApiSuiteRunRecord.filter(project_id=project_id)
    
    if suite_id:
        query = query.filter(suite_id=suite_id)
    
    if status:
        query = query.filter(status=status)
    
    total = await query.count()
    records = await query.order_by("-id").offset((page - 1) * size).limit(size).all()
    
    result = []
    for record in records:
        suite = await record.suite
        result.append({
            "id": record.id,
            "suite_id": record.suite_id,
            "suite_name": suite.name if suite else "未知套件",
            "project_id": record.project_id,
            "status": record.status,
            "trigger_type": record.trigger_type,
            "total_cases": record.total_cases,
            "success_cases": record.success_cases,
            "failed_cases": record.failed_cases,
            "skipped_cases": record.skipped_cases,
            "start_time": record.start_time,
            "end_time": record.end_time,
            "duration": record.duration,
            "env_id": record.env_id,
            "env_name": record.env_name,
            "run_by": record.run_by
        })
    
    return ApiSuiteRunListResponse(data=result, total=total, page=page, size=size)


@router.get("/run-records/{record_id}", summary="执行记录详情")
async def get_run_record_detail(record_id: int):
    """获取执行记录详情"""
    record = await ApiSuiteRunRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    
    suite = await record.suite
    
    # 获取关联的用例执行记录（通过 suite_run_record_id 关联）
    case_records = await ApiRunRecord.filter(
        suite_run_record_id=record_id
    ).order_by("id").all()
    
    case_results = []
    for cr in case_records:
        case = await cr.case
        req_detail = cr.request_detail or {}
        retry_info = req_detail.get("retry_info") if isinstance(req_detail, dict) else None
        stage_timings = req_detail.get("stage_timings") if isinstance(req_detail, dict) else {}
        http_response_time = (
            stage_timings.get("request_ms") if isinstance(stage_timings, dict) else None
        )
        case_results.append({
            "record_id": cr.id,
            "case_id": cr.case_id,
            "case_name": case.name if case else "未知",
            "status": cr.status,
            "response_status": cr.response_status,
            "response_time": cr.response_time,
            "http_response_time": http_response_time,
            "response_body": cr.response_body,
            "response_headers": cr.response_headers,
            "assertions": cr.assertions_result,
            "extracted_vars": cr.extracted_vars,
            "error_msg": cr.error_msg,
            "start_time": cr.start_time,
            "request_detail": req_detail,
            "retry_info": retry_info
        })
    
    return {
        "id": record.id,
        "suite_id": record.suite_id,
        "suite_name": suite.name if suite else "未知套件",
        "status": record.status,
        "trigger_type": record.trigger_type,
        "total_cases": record.total_cases,
        "success_cases": record.success_cases,
        "failed_cases": record.failed_cases,
        "skipped_cases": record.skipped_cases,
        "start_time": record.start_time,
        "end_time": record.end_time,
        "duration": record.duration,
        "env_name": record.env_name,
        "run_by": record.run_by,
        "case_results": case_results
    }
