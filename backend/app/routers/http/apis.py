import json
import time
from datetime import datetime
from typing import List, Optional

import httpx
from tortoise.functions import Count
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Query, status
from uuid import uuid4
from pydantic import BaseModel, ValidationError

from app.models.http import ApiDefinition, ApiTestCase, ApiTestFile, ApiRunRecord
from app.schemas.http import (
    ApiDefinitionCreate, ApiDefinitionUpdate, ApiDefinitionOut,
    ApiLinkedCaseBrief,
    ApiListFilter, ApiListResponse, ApiDebugRequest, ApiDebugResponse,
    ApiImportResult, SwaggerDoc,
    ApiTestCaseCreate, ApiTestCaseUpdate, ApiTestCaseOut, ApiTestCaseListResponse,
    ApiRunRequest, ApiRunResult,
    CurlImportRequest, CurlImportResponse, CurlParseRequest, CurlParseResponse,
    ApiBodyFileUploadResponse
)
from app.core.shared.catalog_utils import apply_catalog_filter, resolve_catalog, load_active_catalog_names
from app.core.platform.auth import is_authenticated, require_permissions, get_current_username
from app.core.platform.permissions import API_MANAGE_VIEW, API_MANAGE_EDIT
from app.core.infra.minio_client import minio_client
from app.core.platform.config import API_FILE_BUCKET
from app.models.sys import Project, Environment

router = APIRouter(tags=["接口自动化"], dependencies=[Depends(is_authenticated), Depends(require_permissions(API_MANAGE_VIEW))])


def _normalize_api_protocol(protocol: Optional[str], method: Optional[str]) -> tuple[str, str]:
    p = (protocol or "http").lower()
    if p == "websocket":
        return p, "WS"
    if p == "graphql":
        return p, "POST"
    if p == "grpc":
        return p, "RPC"
    return p, (method or "GET").upper()


# ============ 接口管理 ============

@router.post("/definition", summary="创建接口", response_model=ApiDefinitionOut,
             dependencies=[Depends(require_permissions(API_MANAGE_EDIT))])
async def create_api(item: ApiDefinitionCreate, username: str = Depends(get_current_username)):
    """创建接口定义"""
    # 校验项目
    project = await Project.get_or_none(id=item.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=422, detail="项目不存在或已被删除")
    
    # 校验分类
    if item.catalog_id:
        await resolve_catalog(item.project_id, item.catalog_id)
    
    proto, method = _normalize_api_protocol(item.protocol, item.method)
    api = await ApiDefinition.create(
        name=item.name,
        project_id=item.project_id,
        catalog_id=item.catalog_id,
        protocol=proto,
        method=method,
        path=item.path,
        description=item.description,
        base_url=item.base_url,
        headers=item.headers if item.headers else [],
        global_header_policy=item.global_header_policy if item.global_header_policy else {"enabled_keys": []},
        params=item.params if item.params else [],
        body=item.body or {},
        body_type=item.body_type,
        body_fields=item.body_fields if hasattr(item, 'body_fields') else [],
        ws_config=item.ws_config if item.ws_config else {},
        grpc_config=item.grpc_config if getattr(item, "grpc_config", None) else {},
        response_schema=item.response_schema,
        create_by=username,
        update_by=username,
        version=1,
        version_history=[{"version": 1, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "desc": "创建接口"}]
    )
    return api


class CopyApiRequest(BaseModel):
    target_project_id: int
    target_catalog_id: Optional[int] = None
    new_name: Optional[str] = None


@router.post("/definition/{api_id}/copy", summary="复制接口到其他项目", response_model=ApiDefinitionOut,
             dependencies=[Depends(require_permissions(API_MANAGE_EDIT))])
async def copy_api_to_project(
    api_id: int,
    body: CopyApiRequest,
    user_info: dict = Depends(require_permissions(API_MANAGE_EDIT)),
):
    from app.core.shared.cross_project_copy import copy_api_definition_to_project, ensure_target_project, resolve_target_catalog
    from app.modules.ui.ui_project_guard import assert_user_project_member

    api = await ApiDefinition.get_or_none(id=api_id, is_del=False)
    if not api:
        raise HTTPException(status_code=404, detail="接口不存在")
    await assert_user_project_member(user_info, api.project_id)
    await assert_user_project_member(user_info, body.target_project_id)
    await ensure_target_project(body.target_project_id)
    target_catalog_id = await resolve_target_catalog(body.target_project_id, body.target_catalog_id)
    username = user_info.get("username") or "admin"
    new_api = await copy_api_definition_to_project(
        api, body.target_project_id, target_catalog_id, username, body.new_name
    )
    return new_api


@router.get("/definition", summary="接口列表", response_model=ApiListResponse)
async def get_apis(
    project_id: int = Query(..., description="项目ID"),
    catalog_id: Optional[int] = Query(None, description="目录ID"),
    include_children: bool = Query(True, description="目录筛选是否包含子目录"),
    keyword: Optional[str] = Query(None, description="关键字搜索"),
    method: Optional[str] = Query(None, description="请求方法"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=5000, description="每页数量")
):
    """获取接口列表"""
    query = ApiDefinition.filter(project_id=project_id, is_del=False)
    
    if catalog_id:
        await resolve_catalog(project_id, catalog_id)
        query = await apply_catalog_filter(query, project_id, catalog_id, include_children=include_children)
    
    if method:
        query = query.filter(method=method.upper())
    
    if keyword:
        # Tortoise ORM 不支持 | 操作符，使用 Q 对象
        from tortoise.expressions import Q
        query = query.filter(Q(name__contains=keyword) | Q(path__contains=keyword))
    
    total = await query.count()
    apis = await query.order_by("-id").offset((page - 1) * size).limit(size).all()
    api_ids = [a.id for a in apis]
    case_count_map: dict[int, int] = {}
    if api_ids:
        rows = (
            await ApiTestCase.filter(api_id__in=api_ids, is_del=False)
            .annotate(cnt=Count("id"))
            .group_by("api_id")
            .values("api_id", "cnt")
        )
        case_count_map = {int(row["api_id"]): int(row["cnt"]) for row in rows}

    # 补充分类名称（已软删目录不展示名称）
    catalog_name_map = await load_active_catalog_names(
        [a.catalog_id for a in apis if a.catalog_id]
    )
    result = []
    for api in apis:
        api_dict = {
            "id": api.id,
            "name": api.name,
            "project_id": api.project_id,
            "catalog_id": api.catalog_id,
            "catalog_name": catalog_name_map.get(api.catalog_id) if api.catalog_id else None,
            "case_count": case_count_map.get(api.id, 0),
            "protocol": getattr(api, "protocol", "http") or "http",
            "method": api.method,
            "path": api.path,
            "description": api.description,
            "base_url": api.base_url,
            "headers": api.headers,
            "params": api.params,
            "body": api.body,
            "body_type": api.body_type,
            "body_fields": api.body_fields or [],
            "ws_config": getattr(api, "ws_config", None) or {},
            "grpc_config": getattr(api, "grpc_config", None) or {},
            "response_schema": api.response_schema,
            "version": api.version,
            "source": api.source,
            "create_by": api.create_by,
            "update_by": api.update_by,
            "create_time": api.create_time,
            "update_time": api.update_time
        }
        result.append(api_dict)
    
    return ApiListResponse(data=result, total=total, page=page, size=size)


@router.get("/definition/{api_id}/linked-cases", summary="接口关联用例列表")
async def get_api_linked_cases(
    api_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    """获取某接口定义下的测试用例（简要信息）"""
    api = await ApiDefinition.get_or_none(id=api_id, is_del=False)
    if not api:
        raise HTTPException(status_code=404, detail="接口不存在")
    qs = ApiTestCase.filter(api_id=api_id, is_del=False)
    total = await qs.count()
    cases = await qs.order_by("-id").offset((page - 1) * size).limit(size).all()
    data = [
        ApiLinkedCaseBrief(
            id=c.id,
            name=c.name,
            priority=c.priority or "P2",
            create_by=c.create_by,
            update_time=c.update_time,
        )
        for c in cases
    ]
    return {"data": data, "total": total, "page": page, "size": size}


@router.get("/definition/{api_id}", summary="接口详情", response_model=ApiDefinitionOut)
async def get_api_detail(api_id: int):
    """获取接口详情"""
    api = await ApiDefinition.get_or_none(id=api_id, is_del=False)
    if not api:
        raise HTTPException(status_code=404, detail="接口不存在")
    
    # 构建返回数据
    result = {
        "id": api.id,
        "name": api.name,
        "project_id": api.project_id,
        "catalog_id": api.catalog_id,
        "catalog_name": None,
        "protocol": getattr(api, "protocol", "http") or "http",
        "method": api.method,
        "path": api.path,
        "description": api.description,
        "base_url": api.base_url,
        "headers": api.headers,
        "global_header_policy": api.global_header_policy or {},
        "params": api.params,
        "body": api.body,
        "body_type": api.body_type,
        "body_fields": api.body_fields,
        "ws_config": getattr(api, "ws_config", None) or {},
        "grpc_config": getattr(api, "grpc_config", None) or {},
        "response_schema": api.response_schema,
        "version": api.version,
        "source": api.source,
        "create_by": api.create_by,
        "update_by": api.update_by,
        "create_time": api.create_time,
        "update_time": api.update_time
    }

    if api.catalog_id:
        catalog_name_map = await load_active_catalog_names([api.catalog_id])
        result["catalog_name"] = catalog_name_map.get(api.catalog_id)

    return result


@router.put("/definition/{api_id}", summary="更新接口", response_model=ApiDefinitionOut,
            dependencies=[Depends(require_permissions(API_MANAGE_EDIT))])
async def update_api(api_id: int, item: ApiDefinitionUpdate, username: str = Depends(get_current_username)):
    """更新接口定义"""
    api = await ApiDefinition.get_or_none(id=api_id, is_del=False)
    if not api:
        raise HTTPException(status_code=404, detail="接口不存在")
    
    # 更新版本历史
    version_history = api.version_history or []
    version_history.append({
        "version": api.version + 1,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "desc": f"更新接口 - {username}"
    })
    
    # 更新字段
    proto, method = _normalize_api_protocol(item.protocol or getattr(api, "protocol", None), item.method)
    api.name = item.name
    api.protocol = proto
    api.method = method
    api.path = item.path
    api.description = item.description
    api.base_url = item.base_url
    # item.headers 和 item.params 已经是字典列表，不需要再调用 model_dump()
    api.headers = item.headers if item.headers else []
    api.global_header_policy = item.global_header_policy or {}
    api.params = item.params if item.params else []
    api.body = item.body or {}
    api.body_type = item.body_type
    api.body_fields = item.body_fields if hasattr(item, 'body_fields') else []
    api.ws_config = item.ws_config if item.ws_config else {}
    api.grpc_config = item.grpc_config if getattr(item, "grpc_config", None) else {}
    api.response_schema = item.response_schema
    if item.catalog_id:
        await resolve_catalog(api.project_id, item.catalog_id)
        api.catalog_id = item.catalog_id
    else:
        api.catalog_id = None
    api.version = api.version + 1
    api.version_history = version_history[-10:]  # 只保留最近10条
    api.update_by = username
    
    await api.save()
    return api


@router.get("/definition/{api_id}/sync-check", summary="检测接口关联用例同步状态",
            dependencies=[Depends(require_permissions(API_MANAGE_VIEW))])
async def sync_check_api(api_id: int):
    """检测接口定义修改后，关联用例是否存在差异"""
    api = await ApiDefinition.get_or_none(id=api_id, is_del=False)
    if not api:
        raise HTTPException(status_code=404, detail="接口不存在")
    
    cases = await ApiTestCase.filter(api_id=api_id, is_del=False)
    inconsistent_cases = []
    
    # 预计算接口定义的字段集合
    api_body_type = api.body_type or 'json'
    api_field_names = {f.get('name') for f in (api.body_fields or []) if f.get('name')}
    
    api_header_keys = set()
    if isinstance(api.headers, list):
        api_header_keys = {h.get('key') for h in api.headers if h.get('key')}
    elif isinstance(api.headers, dict):
        api_header_keys = set(api.headers.keys())
    
    api_param_names = set()
    if isinstance(api.params, list):
        api_param_names = {p.get('name') for p in api.params if p.get('name')}
    elif isinstance(api.params, dict):
        api_param_names = set(api.params.keys())
    
    for case in cases:
        diffs = []
        warnings = []
        
        # 1. body_type 不一致（GET/HEAD/OPTIONS 请求不检测，因为通常无 body）
        api_method = (api.method or 'GET').upper()
        case_body_type = case.request_body_type or api_body_type
        if case_body_type != api_body_type and api_method in ['POST', 'PUT', 'PATCH']:
            diffs.append(f"body_type: 用例为 {case_body_type}，接口为 {api_body_type}")
        
        # 用例覆盖的字段集合
        case_field_names = {f.get('name') for f in (case.request_body_fields or []) if f.get('name')}
        case_header_keys = set()
        if isinstance(case.request_headers, list):
            case_header_keys = {h.get('key') for h in case.request_headers if h.get('key')}
        elif isinstance(case.request_headers, dict):
            case_header_keys = set(case.request_headers.keys())
        case_param_names = set()
        if isinstance(case.request_params, list):
            case_param_names = {p.get('name') for p in case.request_params if p.get('name')}
        elif isinstance(case.request_params, dict):
            case_param_names = set(case.request_params.keys())
        
        # 2. body_fields 中字段在接口中不存在（用例超出接口定义）
        for fname in case_field_names:
            if fname not in api_field_names:
                diffs.append(f"body_field '{fname}' 在接口定义中不存在")
        
        # 3. headers 覆盖项在接口中不存在（用例超出接口定义）
        for key in case_header_keys:
            if key not in api_header_keys:
                diffs.append(f"header '{key}' 在接口定义中不存在")
        
        # 4. params 覆盖项在接口中不存在（用例超出接口定义）
        for key in case_param_names:
            if key not in api_param_names:
                diffs.append(f"param '{key}' 在接口定义中不存在")
        
        # 5. 接口有定义但用例覆盖不完整（信息性提示）
        if api_field_names and len(case_field_names) < len(api_field_names):
            warnings.append(f"body_fields 覆盖不完整（接口 {len(api_field_names)} 个，用例覆盖 {len(case_field_names)} 个）")
        if api_header_keys and len(case_header_keys) < len(api_header_keys):
            warnings.append(f"headers 覆盖不完整（接口 {len(api_header_keys)} 个，用例覆盖 {len(case_header_keys)} 个）")
        if api_param_names and len(case_param_names) < len(api_param_names):
            warnings.append(f"params 覆盖不完整（接口 {len(api_param_names)} 个，用例覆盖 {len(case_param_names)} 个）")
        
        if diffs or warnings:
            inconsistent_cases.append({
                "case_id": case.id,
                "case_name": case.name,
                "diffs": diffs,
                "warnings": warnings
            })
    
    return {
        "api_id": api_id,
        "api_name": api.name,
        "total_cases": len(cases),
        "diff_count": len([c for c in inconsistent_cases if c.get('diffs')]),
        "warning_count": len([c for c in inconsistent_cases if c.get('warnings')]),
        "inconsistent_cases": inconsistent_cases
    }


@router.delete("/definition/{api_id}", summary="删除接口", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(API_MANAGE_EDIT))])
async def delete_api(
    api_id: int,
    cascade: bool = Query(False, description="为 true 时连带删除关联用例，并清理套件/压测场景引用"),
):
    """删除接口（接口与用例为逻辑删除）。

    默认：若仍有关联用例则 409，需先删用例或传 cascade=true 连带删除。
    cascade=true：物理删除套件-用例关联、从压测场景引用中移除后，再软删用例与接口。
    """
    from tortoise.transactions import in_transaction

    from app.modules.http.api_delete import (
        list_active_cases_for_api,
        purge_case_references,
        soft_delete_cases,
        summarize_cases,
    )

    api = await ApiDefinition.get_or_none(id=api_id, is_del=False)
    if not api:
        raise HTTPException(status_code=404, detail="接口不存在")

    cases = await list_active_cases_for_api(api_id)
    if cases and not cascade:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"接口仍关联 {len(cases)} 个用例，无法直接删除。可先删除用例，或勾选连带删除。",
                "case_count": len(cases),
                "cases": summarize_cases(cases),
                "can_cascade": True,
            },
        )

    async with in_transaction() as conn:
        if cases:
            case_ids = [c.id for c in cases]
            await purge_case_references(project_id=api.project_id, case_ids=case_ids, using_db=conn)
            await soft_delete_cases(cases, using_db=conn)
        api.is_del = True
        await api.save(using_db=conn)


@router.post("/definition/batch-delete", summary="批量删除接口", status_code=status.HTTP_204_NO_CONTENT,
             dependencies=[Depends(require_permissions(API_MANAGE_EDIT))])
async def batch_delete_apis(
    api_ids: List[int],
    cascade: bool = Query(False, description="为 true 时连带删除各接口关联用例并清理引用"),
):
    """批量删除接口定义（逻辑删除）。有关联用例且未 cascade 时整批 409。"""
    from tortoise.transactions import in_transaction

    from app.modules.http.api_delete import (
        list_active_cases_for_api,
        purge_case_references,
        soft_delete_cases,
        summarize_cases,
    )

    if not api_ids:
        raise HTTPException(status_code=400, detail="请选择要删除的接口")

    unique_ids = list(dict.fromkeys(api_ids))
    blocked = []
    to_delete = []  # (api, cases)

    for api_id in unique_ids:
        api = await ApiDefinition.get_or_none(id=api_id, is_del=False)
        if not api:
            continue
        cases = await list_active_cases_for_api(api_id)
        if cases and not cascade:
            blocked.append({
                "api_id": api.id,
                "api_name": api.name,
                "case_count": len(cases),
                "cases": summarize_cases(cases, limit=5),
            })
        else:
            to_delete.append((api, cases))

    if blocked:
        total_cases = sum(b["case_count"] for b in blocked)
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"有 {len(blocked)} 个接口仍关联共 {total_cases} 个用例，已取消本次批量删除。"
                    "可先删除用例，或使用连带删除。"
                ),
                "blocked": blocked[:20],
                "can_cascade": True,
            },
        )

    async with in_transaction() as conn:
        for api, cases in to_delete:
            if cases:
                case_ids = [c.id for c in cases]
                await purge_case_references(project_id=api.project_id, case_ids=case_ids, using_db=conn)
                await soft_delete_cases(cases, using_db=conn)
            api.is_del = True
            await api.save(using_db=conn)
    return None


# ============ 导入导出 ============

@router.post("/import/swagger", summary="导入Swagger", response_model=ApiImportResult,
             dependencies=[Depends(require_permissions(API_MANAGE_EDIT))])
async def import_swagger(
    project_id: int = Form(..., description="项目ID"),
    catalog_id: Optional[int] = Form(None, description="目录ID"),
    file: UploadFile = File(...),
    username: str = Depends(get_current_username)
):
    """从Swagger文件导入接口"""
    try:
        content = await file.read()
        data = json.loads(content)
        swagger = SwaggerDoc(**data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Swagger文件解析失败: {str(e)}")
    
    # 校验项目
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=422, detail="项目不存在")
    
    def _resolve_ref(ref_path: str, components: dict) -> dict:
        """解析 OpenAPI $ref 引用，从 components/schemas 获取定义"""
        if not ref_path or not ref_path.startswith('#/components/schemas/'):
            return {}
        schema_name = ref_path.replace('#/components/schemas/', '')
        return components.get('schemas', {}).get(schema_name, {})

    def _extract_response_schema(responses: dict, components: dict) -> dict:
        """从 OpenAPI responses 中提取响应 schema 和示例"""
        if not responses:
            return {}

        # 优先取 200/201，其次取第一个成功的响应码，最后取 default
        response_obj = None
        status_code = None
        for code in ('200', '201', 'default'):
            if code in responses:
                response_obj = responses[code]
                status_code = int(code) if code.isdigit() else 200
                break
        if not response_obj:
            for code in sorted(responses.keys()):
                if str(code).startswith('2'):
                    response_obj = responses[code]
                    status_code = int(code) if str(code).isdigit() else 200
                    break
        if not response_obj:
            return {}

        # 解析 content
        content = response_obj.get('content', {})
        json_content = content.get('application/json', {})
        if not json_content:
            # 尝试其他 content type
            for ct, ct_data in content.items():
                if 'json' in ct:
                    json_content = ct_data
                    break

        schema = json_content.get('schema', {})
        # 解析 $ref
        if isinstance(schema, dict) and '$ref' in schema:
            schema = _resolve_ref(schema['$ref'], components)
            # 递归解析嵌套 $ref
            def _deep_resolve(obj):
                if isinstance(obj, dict):
                    if '$ref' in obj:
                        resolved = _resolve_ref(obj['$ref'], components)
                        obj = {**obj, **resolved}
                        del obj['$ref']
                    return {k: _deep_resolve(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [_deep_resolve(i) for i in obj]
                return obj
            schema = _deep_resolve(schema)

        # 提取示例
        example = json_content.get('example')
        if example is None:
            examples = json_content.get('examples', {})
            if examples:
                first_ex = list(examples.values())[0]
                example = first_ex.get('value') if isinstance(first_ex, dict) else None

        return {
            "status_code": status_code or 200,
            "content_type": "application/json",
            "description": response_obj.get('description', ''),
            "schema": schema,
            "example": example,
        }

    result = ApiImportResult(total=0, success=0, failed=0, errors=[], apis=[])
    components = swagger.components or {}

    # 解析路径
    for path, methods in swagger.paths.items():
        for method, detail in methods.items():
            if method in ['get', 'post', 'put', 'delete', 'patch']:
                result.total += 1
                try:
                    # 提取参数
                    params = []
                    headers = []
                    body = {}

                    if detail.parameters:
                        for param in detail.parameters:
                            if param.get('in') == 'query':
                                params.append({
                                    "name": param.get('name'),
                                    "type": param.get('schema', {}).get('type', 'string'),
                                    "required": param.get('required', False),
                                    "description": param.get('description', '')
                                })
                            elif param.get('in') == 'header':
                                headers.append({
                                    "key": param.get('name'),
                                    "value": "",
                                    "description": param.get('description', '')
                                })

                    # 提取请求体
                    if detail.requestBody:
                        req_content = detail.requestBody.get('content', {})
                        if 'application/json' in req_content:
                            schema = req_content['application/json'].get('schema', {})
                            body = schema.get('properties', {})

                    # 提取响应 schema
                    response_schema = _extract_response_schema(
                        detail.responses, components
                    )

                    # 创建接口
                    api = await ApiDefinition.create(
                        name=detail.summary or f"{method.upper()} {path}",
                        project_id=project_id,
                        catalog_id=catalog_id,
                        method=method.upper(),
                        path=path,
                        description=detail.description or detail.summary,
                        headers=headers,
                        params=params,
                        body=body,
                        body_type="json" if body else "none",
                        response_schema=response_schema,
                        source="swagger",
                        source_id=detail.operationId,
                        create_by=username,
                        update_by=username,
                        version=1
                    )

                    result.success += 1
                    result.apis.append(api)

                except Exception as e:
                    result.failed += 1
                    result.errors.append(f"{method.upper()} {path}: {str(e)}")

    return result


@router.post("/files/upload", summary="上传接口调试文件（兼容旧版，建议用 /files/upload?project_id=）",
             response_model=ApiBodyFileUploadResponse,
             dependencies=[Depends(require_permissions(API_MANAGE_EDIT))])
async def upload_api_body_file(
    file: UploadFile = File(...),
    project_id: Optional[int] = Query(None, description="项目ID（传入则登记到测试文件库）"),
    username: str = Depends(get_current_username),
):
    """上传接口测试文件到独立 bucket；传入 project_id 时写入 api_test_file 表便于复用。"""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="文件内容为空")

    safe_name = (file.filename or "upload.bin").replace("\\", "/").split("/")[-1].strip()
    mime_type = file.content_type or "application/octet-stream"
    if project_id:
        project = await Project.get_or_none(id=project_id, is_del=False)
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")
        object_name = f"{project_id}/{uuid4().hex}/{safe_name}"
    else:
        object_name = f"{uuid4().hex}/{safe_name}"

    success = minio_client.upload_bytes(
        object_name=object_name,
        data=content,
        content_type=mime_type,
        bucket_name=API_FILE_BUCKET,
    )
    if not success:
        raise HTTPException(status_code=500, detail="文件上传失败")

    if project_id:
        await ApiTestFile.create(
            project_id=project_id,
            file_name=safe_name,
            file_key=object_name,
            file_bucket=API_FILE_BUCKET,
            mime_type=mime_type,
            size=len(content),
            username=username,
        )

    return ApiBodyFileUploadResponse(
        success=True,
        file_bucket=API_FILE_BUCKET,
        file_key=object_name,
        file_name=safe_name,
        mime_type=mime_type,
        size=len(content),
    )


@router.post("/import/postman", summary="导入Postman", response_model=ApiImportResult,
             dependencies=[Depends(require_permissions(API_MANAGE_EDIT))])
async def import_postman(
    project_id: int = Form(..., description="项目ID"),
    catalog_id: Optional[int] = Form(None, description="目录ID"),
    file: UploadFile = File(...),
    username: str = Depends(get_current_username)
):
    """从Postman Collection导入接口"""
    try:
        content = await file.read()
        data = json.loads(content)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Postman文件解析失败: {str(e)}")
    
    # 校验项目
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=422, detail="项目不存在")
    
    result = ApiImportResult(total=0, success=0, failed=0, errors=[], apis=[])
    
    async def extract_items(items, folder_name=None):
        """递归提取接口"""
        for item in items:
            if 'item' in item:
                # 是文件夹
                await extract_items(item['item'], item.get('name', '未命名文件夹'))
            else:
                # 是接口
                result.total += 1
                try:
                    request = item.get('request', {})
                    url = request.get('url', {})
                    
                    if isinstance(url, dict):
                        path = url.get('path', [''])
                        path_str = '/' + '/'.join(path) if isinstance(path, list) else path
                        base_url = url.get('protocol', 'http') + '://' + url.get('host', [''])[0] if isinstance(url.get('host'), list) else ''
                    else:
                        path_str = url
                        base_url = None
                    
                    # 提取参数
                    params = []
                    if isinstance(url, dict) and 'query' in url:
                        for q in url['query']:
                            params.append({
                                "name": q.get('key', ''),
                                "value": q.get('value', ''),
                                "type": "string",
                                "required": True
                            })
                    
                    # 提取header
                    headers = []
                    for h in request.get('header', []):
                        headers.append({
                            "key": h.get('key', ''),
                            "value": h.get('value', ''),
                            "description": h.get('description', '')
                        })
                    
                    # 提取响应示例（取第一个 200 成功的响应）
                    response_example = None
                    responses = item.get('response', [])
                    for resp in responses:
                        code = resp.get('code')
                        if code and str(code).startswith('2'):
                            try:
                                body_str = resp.get('body', '')
                                if body_str:
                                    response_example = json.loads(body_str)
                            except Exception:
                                response_example = resp.get('body')
                            break

                    response_schema = {}
                    if response_example is not None:
                        response_schema = {
                            "status_code": 200,
                            "content_type": "application/json",
                            "description": "",
                            "example": response_example,
                        }

                    api = await ApiDefinition.create(
                        name=item.get('name', '未命名接口'),
                        project_id=project_id,
                        catalog_id=catalog_id,
                        method=request.get('method', 'GET').upper(),
                        path=path_str,
                        description=item.get('description', ''),
                        base_url=base_url,
                        headers=headers,
                        params=params,
                        body=request.get('body', {}).get('raw', {}),
                        body_type="json",
                        response_schema=response_schema,
                        source="postman",
                        create_by=username,
                        update_by=username,
                        version=1
                    )
                    
                    result.success += 1
                    result.apis.append(api)
                    
                except Exception as e:
                    result.failed += 1
                    result.errors.append(f"{item.get('name', '未知')}: {str(e)}")
    
    items = data.get('item', [])
    await extract_items(items)
    
    return result


from .curl_parser import parse_curl


@router.post("/import/curl/parse", summary="解析Curl命令", response_model=CurlParseResponse,
             dependencies=[Depends(require_permissions(API_MANAGE_EDIT))])
async def parse_curl_endpoint(item: CurlParseRequest):
    """解析 curl 命令，返回解析后的接口数据供预览和编辑"""
    try:
        # 解析 curl 命令
        parsed = parse_curl(item.curl_command)
        
        if not parsed:
            return CurlParseResponse(
                success=False,
                message="无法解析 curl 命令，请检查格式是否正确",
                api=None
            )
        
        # 组装返回数据
        # 将 headers 从 dict 转换为 list
        headers_list = []
        for key, value in parsed.get("headers", {}).items():
            headers_list.append({"key": key, "value": value, "description": ""})
        
        api_data = {
            "name": parsed.get("name", ""),
            "method": parsed.get("method", "GET"),
            "path": parsed.get("path", ""),
            "base_url": parsed.get("base_url"),
            "description": parsed.get("description", f"从 curl 命令导入: {parsed.get('method', 'GET')} {parsed.get('path', '')}"),
            "headers": headers_list,
            "params": parsed.get("params", []),
            "body": parsed.get("body") if parsed.get("body") else None,
            "body_type": parsed.get("body_type", "none"),
            "project_id": item.project_id,
            "catalog_id": item.catalog_id
        }
        
        return CurlParseResponse(
            success=True,
            message="解析成功",
            api=api_data
        )
        
    except Exception as e:
        return CurlParseResponse(
            success=False,
            message=f"解析失败: {str(e)}",
            api=None
        )


@router.post("/import/curl", summary="导入Curl命令", response_model=CurlImportResponse,
             dependencies=[Depends(require_permissions(API_MANAGE_EDIT))])
async def import_curl(
    item: ApiDefinitionCreate,
    username: str = Depends(get_current_username)
):
    """保存从 Curl 解析的接口"""
    try:
        # 校验项目
        project = await Project.get_or_none(id=item.project_id, is_del=False)
        if not project:
            raise HTTPException(status_code=422, detail="项目不存在或已被删除")
        
        # 检查是否已存在
        existing = await ApiDefinition.get_or_none(
            project_id=item.project_id,
            path=item.path,
            method=item.method,
            is_del=False
        )
        
        if existing:
            return CurlImportResponse(
                success=False,
                message=f"接口已存在: {item.method} {item.path}",
                api=None
            )
        
        # 处理 body，确保不为 null
        body = item.body if item.body is not None else {}
        
        # 创建接口
        api = await ApiDefinition.create(
            name=item.name,
            project_id=item.project_id,
            catalog_id=item.catalog_id,
            method=item.method,
            path=item.path,
            description=item.description,
            base_url=item.base_url,
            headers=item.headers if item.headers else [],
            params=item.params if item.params else [],
            body=body,
            body_type=item.body_type,
            source="curl",
            create_by=username,
            update_by=username,
            version=1
        )
        
        return CurlImportResponse(
            success=True,
            message=f"成功导入接口: {api.name}",
            api=api
        )
        
    except Exception as e:
        return CurlImportResponse(
            success=False,
            message=f"导入失败: {str(e)}",
            api=None
        )


# ============ 在线调试 ============

@router.post("/debug", summary="接口调试",
             dependencies=[Depends(require_permissions(API_MANAGE_EDIT))])
async def debug_api(item: ApiDebugRequest):
    """在线调试接口"""
    from .utils import (
        replace_variables_with_detail,
        replace_body_fields_with_detail,
        build_form_data_multipart,
        prepare_httpx_headers,
    )
    from app.core.case.variable_resolver import VariableResolver
    from app.core.shared.header_merge import merge_request_headers
    from app.models.sys import Environment
    
    try:
        # 获取变量：project < env < df < extra < Token 授权
        variables = dict(item.variables or {})
        env = None
        project_id = item.project_id

        original_url = (item.url or "").strip()
        if not original_url:
            raise HTTPException(status_code=400, detail="请输入请求 URL")
        if not item.env_id and not original_url.startswith(("http://", "https://")):
            if "${{" in original_url or "${" in original_url:
                raise HTTPException(
                    status_code=400,
                    detail="请求 URL 含有环境变量占位符，请先选择执行环境后再发送",
                )
            raise HTTPException(
                status_code=400,
                detail="未选择执行环境且 URL 非绝对地址，请选择环境或在 URL 中填写完整地址（含 http:// 或 https://）",
            )
        
        if item.env_id:
            env = await Environment.get_or_none(id=item.env_id, is_del=False)
            if env:
                project_id = project_id or env.project_id

        from app.modules.http.api_auth_service import prepare_api_runtime_variables
        from app.modules.http.http_utils import (
            collect_unresolved_placeholders,
            format_unresolved_variables_error,
        )
        if item.worker_id is not None:
            from app.modules.http.worker_http_proxy import require_api_proxy_worker_http
            await require_api_proxy_worker_http(int(project_id or 0), item.worker_id)
        variables, auth_err, auth_injected_keys = await prepare_api_runtime_variables(
            project_id, item.env_id, variables, inject_auth=True,
            worker_id=item.worker_id,
        )
        if auth_err:
            raise HTTPException(status_code=400, detail=f"授权刷新失败: {auth_err}")

        var_resolver = VariableResolver(variables)

        # 变量替换 URL
        url, url_details = replace_variables_with_detail(original_url, variables, "url", resolver=var_resolver)

        # 如果 URL 是相对路径，自动拼接环境的 base_url
        if env and not url.startswith(("http://", "https://")):
            base_url = env.host or ""
            base_url = base_url.rstrip("/")
            url = base_url + "/" + url.lstrip("/")

        # URL 校验：变量替换后仍不是绝对路径，说明缺少基础URL或环境
        if not url.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=400,
                detail="请求URL缺少协议（http:// 或 https://），请检查基础URL或选择执行环境"
            )

        # 处理参数
        original_params = {p.get('name', ''): p.get('value', '') for p in item.params if p.get('name')}
        params = {}
        params_details = []
        for p in item.params:
            if p.get('name'):
                val, details = replace_variables_with_detail(
                    p.get('value', ''), variables, f"params.{p.get('name')}", resolver=var_resolver
                )
                params[p['name']] = val
                params_details.extend(details)

        # 构建查询字符串
        if params:
            query_params = {k: v for k, v in params.items() if v}
            if query_params:
                query_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
                if "?" in url:
                    url += "&" + query_string
                else:
                    url += "?" + query_string

        # 构建headers：本接口 Header，再变量替换
        merged_headers = merge_request_headers(api_headers=item.headers)
        original_headers = dict(merged_headers)
        headers = {}
        headers_details = []
        for key, value in merged_headers.items():
            if not key or value is None:
                continue
            header_value, details = replace_variables_with_detail(
                value, variables, f"headers.{key}", resolver=var_resolver
            )
            headers[key] = header_value
            headers_details.extend(details)

        # 变量替换请求体
        original_body = item.body
        body, body_details = replace_variables_with_detail(original_body, variables, "body", resolver=var_resolver)
        original_body_fields = [
            field.model_dump() if hasattr(field, "model_dump") else dict(field)
            for field in (item.body_fields or [])
        ]
        body_fields, body_fields_details = replace_body_fields_with_detail(
            original_body_fields, variables, resolver=var_resolver
        )

        unresolved = []
        unresolved.extend(collect_unresolved_placeholders(url, "url"))
        unresolved.extend(collect_unresolved_placeholders(headers, "headers"))
        unresolved.extend(collect_unresolved_placeholders(params, "params"))
        unresolved.extend(collect_unresolved_placeholders(body, "body"))
        unresolved.extend(collect_unresolved_placeholders(body_fields, "body_fields"))
        if unresolved:
            raise HTTPException(
                status_code=400,
                detail=format_unresolved_variables_error(
                    unresolved,
                    env_name=(env.name if env else ""),
                    auth_injected_keys=auth_injected_keys,
                ),
            )
        
        # 合并所有替换详情
        all_replacements = url_details + headers_details + params_details + body_details + body_fields_details
        
        # 构建请求详情
        request_detail = {
            "url": {
                "original": original_url,
                "final": url
            },
            "headers": {
                "original": original_headers,
                "final": headers
            },
            "params": {
                "original": original_params,
                "final": params
            },
            "body": {
                "original": original_body,
                "final": body
            },
            "body_fields": {"original": original_body_fields, "final": body_fields},
            "variables_used": var_resolver.get_resolved_snapshot(),
            "replacements": all_replacements,
            "auth_injected_keys": auth_injected_keys,
        }

        resolved_request = {
            "method": item.method,
            "url": url,
            "headers": [{"key": k, "value": v} for k, v in headers.items()],
            "params": [{"name": k, "value": v} for k, v in params.items()],
            "body": body,
            "body_type": item.body_type,
            "body_fields": body_fields,
        }

        # -------- 经在线压测执行机代发 --------
        if item.worker_id is not None:
            from app.modules.http.worker_http_proxy import (
                WorkerProxyError,
                send_http_via_worker,
                to_http_exception,
            )

            try:
                proxied = await send_http_via_worker(
                    project_id=project_id,
                    worker_id=item.worker_id,
                    method=item.method.upper(),
                    url=url,
                    headers=headers,
                    body=body,
                    body_type=item.body_type or "json",
                    body_fields=body_fields,
                    timeout=int(item.timeout or 30),
                )
            except WorkerProxyError as exc:
                raise to_http_exception(exc) from exc

            response_detail = {
                "status_code": proxied.status_code,
                "headers": proxied.headers or {},
                "body": proxied._json if proxied._json is not None else proxied.text,
                "time": proxied.elapsed_ms,
                "size": proxied.size,
            }
            return {
                "status_code": proxied.status_code,
                "headers": proxied.headers or {},
                "body": proxied._json if proxied._json is not None else proxied.text,
                "time": proxied.elapsed_ms,
                "size": proxied.size,
                "request": resolved_request,
                "request_detail": request_detail,
                "response_detail": response_detail,
                "via_worker": True,
                "worker_id": proxied.worker_id,
            }

        # -------- 平台本机发送 --------
        request_headers = prepare_httpx_headers(headers)
        async with httpx.AsyncClient(timeout=item.timeout, follow_redirects=True) as client:
            method = item.method.upper()
            
            if method == "GET":
                response = await client.get(url, headers=request_headers)
            elif method in ("POST", "PUT", "PATCH"):
                if item.body_type == "json":
                    request_kwargs = {"json": body}
                elif item.body_type == "form-data":
                    try:
                        request_kwargs = {
                            "files": build_form_data_multipart(
                                body_fields, API_FILE_BUCKET, use_bytes_io=True
                            )
                        }
                    except ValueError as e:
                        raise HTTPException(status_code=400, detail=str(e))
                else:
                    request_kwargs = {"data": body}
                response = await client.request(method, url, headers=request_headers, **request_kwargs)
            elif method == "DELETE":
                response = await client.delete(url, headers=request_headers)
            else:
                raise HTTPException(status_code=400, detail=f"不支持的请求方法: {method}")
            
            # 解析响应体
            try:
                response_body = response.json()
            except:
                response_body = response.text
            
            # 构建响应详情
            response_detail = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response_body,
                "time": response.elapsed.total_seconds() * 1000,
                "size": len(response.content)
            }

            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response_body,
                "time": response.elapsed.total_seconds() * 1000,
                "size": len(response.content),
                "request": resolved_request,
                "request_detail": request_detail,
                "response_detail": response_detail
            }
            
    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="请求超时")
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"请求发送失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


# ============ JMeter (.jmx) 导入 ============

class JmeterCommitRequestBody(BaseModel):
    preview_token: str
    project_id: int
    catalog_id: Optional[int] = None
    conflict_strategy: str = "merge_case"
    create_suites: bool = True
    create_perf_scenes: bool = False
    selected_sampler_paths: Optional[List[str]] = None


_VALID_JMETER_CONFLICT = {"create_always", "skip_existing", "merge_case"}


@router.post(
    "/import/jmeter/preview",
    summary="预览 JMeter JMX 导入",
    dependencies=[Depends(require_permissions(API_MANAGE_EDIT))],
)
async def import_jmeter_preview(
    project_id: int = Form(..., description="项目ID"),
    catalog_id: Optional[int] = Form(None, description="目录ID"),
    file: UploadFile = File(...),
    username: str = Depends(get_current_username),
):
    """安全解析 .jmx，返回可导入预览与短期 preview_token（不落库）。"""
    from app.modules.jmeter.jmx_mapper import map_ir_to_preview
    from app.modules.jmeter.jmx_normalizer import normalize_jmx
    from app.modules.jmeter.jmx_parser import JmxParseError
    from app.modules.jmeter.models import JmeterPreviewResponse, JmeterPreviewCounts, JmeterUnsupportedNode
    from app.modules.jmeter.preview_store import save_preview

    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=422, detail="项目不存在")
    if catalog_id:
        await resolve_catalog(project_id, catalog_id)

    filename = (file.filename or "").lower()
    if not filename.endswith(".jmx"):
        raise HTTPException(status_code=422, detail="仅支持 .jmx 文件")

    content = await file.read()
    try:
        ir = normalize_jmx(content)
    except JmxParseError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"JMX 解析失败: {e}") from e

    preview = map_ir_to_preview(ir)
    token = await save_preview(
        project_id=project_id,
        username=username,
        catalog_id=catalog_id,
        ir=ir,
        preview=preview,
    )
    return JmeterPreviewResponse(
        preview_token=token,
        test_plan_name=preview.get("test_plan_name") or "JMeter Import",
        counts=JmeterPreviewCounts(**(preview.get("counts") or {})),
        apis=preview.get("apis") or [],
        cases=preview.get("cases") or [],
        suites=preview.get("suites") or [],
        perf_scenes=preview.get("perf_scenes") or [],
        unsupported_nodes=[
            JmeterUnsupportedNode(**u) for u in (preview.get("unsupported_nodes") or [])
        ],
        warnings=preview.get("warnings") or [],
        todos=preview.get("todos") or [],
    )


@router.post(
    "/import/jmeter/commit",
    summary="确认导入 JMeter JMX",
    dependencies=[Depends(require_permissions(API_MANAGE_EDIT))],
)
async def import_jmeter_commit(
    item: JmeterCommitRequestBody,
    username: str = Depends(get_current_username),
):
    """根据 preview_token 与冲突策略事务落库 API / 用例 / 套件。"""
    from app.modules.jmeter.jmx_importer import commit_jmeter_import
    from app.modules.jmeter.models import JmeterCommitRequest
    from app.modules.jmeter.preview_store import consume_preview

    project = await Project.get_or_none(id=item.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=422, detail="项目不存在")
    if item.conflict_strategy not in _VALID_JMETER_CONFLICT:
        raise HTTPException(
            status_code=422,
            detail=f"conflict_strategy 无效，可选: {', '.join(sorted(_VALID_JMETER_CONFLICT))}",
        )
    if item.catalog_id:
        await resolve_catalog(item.project_id, item.catalog_id)

    try:
        stored = await consume_preview(
            item.preview_token,
            project_id=item.project_id,
            username=username,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    catalog_id = item.catalog_id if item.catalog_id is not None else stored.get("catalog_id")
    if catalog_id:
        await resolve_catalog(item.project_id, catalog_id)
    req = JmeterCommitRequest(
        preview_token=item.preview_token,
        project_id=item.project_id,
        catalog_id=catalog_id,
        conflict_strategy=item.conflict_strategy,  # type: ignore[arg-type]
        create_suites=item.create_suites,
        create_perf_scenes=item.create_perf_scenes,
        selected_sampler_paths=item.selected_sampler_paths,
    )
    try:
        return await commit_jmeter_import(
            ir=stored.get("ir") or {},
            preview=stored.get("preview"),
            req=req,
            username=username,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {e}") from e
