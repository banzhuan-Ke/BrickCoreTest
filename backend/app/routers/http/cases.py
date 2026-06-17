"""接口测试用例相关 API"""
import json as _json
from datetime import datetime, timezone
from typing import Optional, List

from pydantic import BaseModel

from fastapi import APIRouter, HTTPException, Depends, Query, status, Form, UploadFile, File
from fastapi.responses import Response

from app.models.http import ApiDefinition, ApiTestCase
from app.models.sys import TestCatalog
from app.core.catalog_utils import apply_catalog_filter, resolve_catalog
from app.schemas.http import (
    ApiTestCaseCreate, ApiTestCaseUpdate, ApiTestCaseOut, ApiTestCaseListResponse,
    ApiRunRequest, ApiRunResult,
    ApiBodyFileUploadResponse,
    ApiCaseBatchExportRequest, ApiCaseImportResult, ApiCaseBatchUpdateCatalogRequest,
    VariablePreviewRequest,
)
from uuid import uuid4
from app.core.auth import is_authenticated, require_permissions, get_current_username
from app.core.permissions import API_CASE_VIEW, API_CASE_EDIT, API_CASE_EXECUTE

router = APIRouter(tags=["接口测试用例"], dependencies=[Depends(is_authenticated), Depends(require_permissions(API_CASE_VIEW))])


def _normalize_assertions(assertions):
    """兼容旧字段名"""
    result = []
    for a in assertions or []:
        if not isinstance(a, dict):
            continue
        assertion_type = a.get("type") or a.get("source", "status_code")
        target = a.get("target")
        if target is None:
            target = a.get("property")
        result.append({
            "type": assertion_type,
            "target": target,
            "operator": a.get("operator", "equals"),
            "expected": a.get("expected"),
            "description": a.get("description", ""),
        })
    return result


def _normalize_extractors(extractors):
    """兼容旧字段名，与 utils.normalize_extractor 对齐。"""
    from app.routers.http.utils import normalize_extractor

    result = []
    for e in extractors or []:
        if not isinstance(e, dict):
            continue
        ext = normalize_extractor(e)
        if ext.get("name") or ext.get("path"):
            result.append(ext)
    return result


def _build_case_response(case, api, catalog):
    """构建统一的用例响应字典"""
    return {
        "id": case.id,
        "name": case.name,
        "api_id": case.api_id,
        "api_name": api.name if api else "未知接口",
        "api_method": api.method if api else "",
        "api_path": api.path if api else "",
        "api_protocol": getattr(api, "protocol", "http") if api else "http",
        "project_id": case.project_id,
        "catalog_id": case.catalog_id,
        "catalog_name": catalog.name if catalog else None,
        "request_headers": (
            {h.get('key', ''): h.get('value', '') for h in case.request_headers if h.get('key')}
            if isinstance(case.request_headers, list) else
            (case.request_headers if isinstance(case.request_headers, dict) else {})
        ),
        "request_params": (
            [{"name": k, "value": str(v), "type": "string", "required": True, "description": ""}
             for k, v in case.request_params.items()] if isinstance(case.request_params, dict) and case.request_params else
            (case.request_params if isinstance(case.request_params, list) else [])
        ),
        "request_body": case.request_body,
        "request_body_type": case.request_body_type or "json",
        "request_body_fields": case.request_body_fields or [],
        "ws_steps": getattr(case, "ws_steps", None) or [],
        "assertions": _normalize_assertions(case.assertions),
        "assertion_groups": getattr(case, "assertion_groups", None) or [],
        "extractors": _normalize_extractors(case.extractors),
        "depends_on": case.depends_on,
        "timeout": case.timeout,
        "retry_count": case.retry_count,
        "tags": case.tags,
        "priority": case.priority,
        "api_version_snapshot": getattr(case, "api_version_snapshot", 1),
        "api_current_version": api.version if api else 1,
        "is_expired": (api.version > getattr(case, "api_version_snapshot", 1)) if api else False,
        "pre_script": getattr(case, "pre_script", None),
        "post_script": getattr(case, "post_script", None),
        "data_set": getattr(case, "data_set", None) or [],
        "db_assertions": getattr(case, "db_assertions", None) or [],
        "global_header_policy": getattr(case, "global_header_policy", None) or {},
        "create_by": case.create_by,
        "update_by": case.update_by,
        "create_time": case.create_time,
        "update_time": case.update_time
    }


@router.post("/case", summary="创建测试用例", response_model=ApiTestCaseOut,
             dependencies=[Depends(require_permissions(API_CASE_EDIT))])
async def create_test_case(item: ApiTestCaseCreate, username: str = Depends(get_current_username)):
    """创建接口测试用例"""
    api = await ApiDefinition.get_or_none(id=item.api_id, is_del=False)
    if not api:
        raise HTTPException(status_code=404, detail="接口不存在")
    
    catalog_id = item.catalog_id
    if catalog_id is None:
        catalog_id = api.catalog_id
    if catalog_id:
        await resolve_catalog(item.project_id, catalog_id)
    
    assertions_data = [a.model_dump() for a in (item.assertions or [])]
    extractors_data = [e.model_dump() for e in (item.extractors or [])]
    request_params_data = [p.model_dump() for p in (item.request_params or [])]
    
    case = await ApiTestCase.create(
        name=item.name,
        api_id=item.api_id,
        project_id=item.project_id,
        catalog_id=catalog_id,
        request_headers=item.request_headers or {},
        global_header_policy=item.global_header_policy or {},
        request_params=request_params_data,
        request_body=item.request_body or {},
        request_body_type=item.request_body_type or "json",
        request_body_fields=item.request_body_fields or [],
        ws_steps=item.ws_steps or [],
        assertions=assertions_data,
        assertion_groups=item.assertion_groups or [],
        extractors=extractors_data,
        depends_on=item.depends_on or [],
        timeout=item.timeout or 30,
        retry_count=item.retry_count or 0,
        tags=item.tags or [],
        priority=item.priority or "P2",
        pre_script=item.pre_script,
        post_script=item.post_script,
        data_set=item.data_set or [],
        db_assertions=item.db_assertions or [],
        api_version_snapshot=api.version,
        create_by=username,
        update_by=username,
    )
    api = await case.api
    catalog = await case.catalog
    return _build_case_response(case, api, catalog)


@router.get("/case", summary="测试用例列表", response_model=ApiTestCaseListResponse)
async def get_test_cases(
    project_id: int = Query(..., description="项目ID"),
    api_id: Optional[int] = Query(None, description="接口ID"),
    catalog_id: Optional[int] = Query(None, description="目录ID"),
    include_children: bool = Query(True, description="目录筛选是否包含子目录"),
    priority: Optional[str] = Query(None, description="优先级 P0/P1/P2/P3"),
    keyword: Optional[str] = Query(None, description="关键字"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=5000)
):
    """获取测试用例列表"""
    query = ApiTestCase.filter(project_id=project_id, is_del=False)
    
    if api_id:
        query = query.filter(api_id=api_id)
    
    if catalog_id:
        await resolve_catalog(project_id, catalog_id)
        query = await apply_catalog_filter(query, project_id, catalog_id, include_children=include_children)
    
    if priority:
        query = query.filter(priority=priority)
    
    if keyword:
        query = query.filter(name__contains=keyword)
    
    total = await query.count()
    cases = await query.order_by("-id").offset((page - 1) * size).limit(size).all()
    
    result = []
    for case in cases:
        api = await case.api
        catalog = await case.catalog
        result.append(_build_case_response(case, api, catalog))
    
    return ApiTestCaseListResponse(data=result, total=total, page=page, size=size)




@router.get("/case/{case_id}", summary="用例详情", response_model=ApiTestCaseOut)
async def get_test_case(case_id: int):
    """获取测试用例详情"""
    case = await ApiTestCase.get_or_none(id=case_id, is_del=False)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    
    api = await case.api
    catalog = await case.catalog
    return _build_case_response(case, api, catalog)


@router.put("/case/{case_id}", summary="更新测试用例", response_model=ApiTestCaseOut,
            dependencies=[Depends(require_permissions(API_CASE_EDIT))])
async def update_test_case(case_id: int, item: ApiTestCaseUpdate, username: str = Depends(get_current_username)):
    """更新测试用例"""
    case = await ApiTestCase.get_or_none(id=case_id, is_del=False)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    
    if item.catalog_id:
        await resolve_catalog(case.project_id, item.catalog_id)
        case.catalog_id = item.catalog_id
    else:
        case.catalog_id = None
    
    case.name = item.name
    case.request_headers = item.request_headers or {}
    case.global_header_policy = item.global_header_policy or {}
    case.request_params = [p.model_dump() for p in (item.request_params or [])]
    case.request_body = item.request_body or {}
    case.request_body_type = item.request_body_type or "json"
    case.request_body_fields = item.request_body_fields or []
    case.ws_steps = item.ws_steps or []
    case.assertions = [a.model_dump() for a in (item.assertions or [])]
    case.assertion_groups = item.assertion_groups or []
    case.extractors = [e.model_dump() for e in (item.extractors or [])]
    case.depends_on = item.depends_on or []
    case.timeout = item.timeout or 30
    case.retry_count = item.retry_count or 0
    case.tags = item.tags or []
    case.priority = item.priority or "P2"
    case.pre_script = item.pre_script
    case.post_script = item.post_script
    case.data_set = item.data_set or []
    case.db_assertions = item.db_assertions or []
    case.update_by = username
    # 保存时同步更新版本快照（消除过期状态）
    api = await case.api
    if api:
        case.api_version_snapshot = api.version
    await case.save()
    
    catalog = await case.catalog
    return _build_case_response(case, api, catalog)


@router.delete("/case/{case_id}", summary="删除测试用例", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(API_CASE_EDIT))])
async def delete_test_case(case_id: int):
    """删除测试用例"""
    case = await ApiTestCase.get_or_none(id=case_id, is_del=False)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    
    case.is_del = True
    await case.save()


@router.post("/case/batch-delete", summary="批量删除测试用例", status_code=status.HTTP_204_NO_CONTENT,
             dependencies=[Depends(require_permissions(API_CASE_EDIT))])
async def batch_delete_test_cases(case_ids: List[int]):
    """批量删除测试用例（逻辑删除）"""
    if not case_ids:
        raise HTTPException(status_code=400, detail="请选择要删除的用例")
    deleted = 0
    for case_id in case_ids:
        case = await ApiTestCase.get_or_none(id=case_id, is_del=False)
        if case:
            case.is_del = True
            await case.save()
            deleted += 1
    return None


@router.post("/case/batch-update-catalog", summary="批量修改用例目录",
             dependencies=[Depends(require_permissions(API_CASE_EDIT))])
async def batch_update_test_case_catalog(item: ApiCaseBatchUpdateCatalogRequest):
    """批量修改接口测试用例所属目录"""
    if not item.case_ids:
        raise HTTPException(status_code=400, detail="请选择要修改的用例")
    updated = 0
    for case_id in item.case_ids:
        case = await ApiTestCase.get_or_none(id=case_id, is_del=False)
        if not case:
            continue
        if item.catalog_id is not None:
            await resolve_catalog(case.project_id, item.catalog_id)
        case.catalog_id = item.catalog_id
        await case.save()
        updated += 1
    return {"updated": updated}


@router.post("/case/export", summary="批量导出测试用例",
             dependencies=[Depends(require_permissions(API_CASE_VIEW))])
async def export_test_cases(item: ApiCaseBatchExportRequest):
    """批量导出 API 测试用例为 JSON 文件"""
    if not item.case_ids:
        raise HTTPException(status_code=400, detail="请选择要导出的用例")
    if len(item.case_ids) > 500:
        raise HTTPException(status_code=400, detail="单次最多导出 500 条")
    cases = await ApiTestCase.filter(id__in=item.case_ids, is_del=False).all()
    cases_data = []
    for case in cases:
        api = await case.api
        cases_data.append({
            "name": case.name,
            "api_method": api.method if api else "",
            "api_path": api.path if api else "",
            "api_name": api.name if api else "",
            "request_headers": case.request_headers or {},
            "request_params": case.request_params or [],
            "request_body": case.request_body or {},
            "request_body_type": case.request_body_type or "json",
            "request_body_fields": case.request_body_fields or [],
            "assertions": case.assertions or [],
            "extractors": case.extractors or [],
            "depends_on": [],
            "timeout": case.timeout,
            "retry_count": case.retry_count,
            "tags": case.tags or [],
            "priority": case.priority or "P2",
            "pre_script": case.pre_script if hasattr(case, "pre_script") else None,
            "post_script": case.post_script if hasattr(case, "post_script") else None,
            "data_set": case.data_set if hasattr(case, "data_set") and case.data_set else [],
        })
    payload = {
        "meta": {
            "version": "1.0",
            "type": "api_cases",
            "export_time": datetime.now(timezone.utc).isoformat(),
            "count": len(cases_data),
        },
        "cases": cases_data,
    }
    json_str = _json.dumps(payload, ensure_ascii=False, indent=2)
    return Response(
        content=json_str,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=api_cases_export.json"},
    )


@router.post("/case/import", summary="批量导入测试用例",
             response_model=ApiCaseImportResult,
             dependencies=[Depends(require_permissions(API_CASE_EDIT))])
async def import_test_cases(
    file: UploadFile = File(...),
    project_id: int = Form(...),
    catalog_id: Optional[int] = Form(None),
    username: str = Depends(get_current_username),
):
    """从 JSON 文件批量导入 API 测试用例"""
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大，最大支持 10MB")
    try:
        text = content.decode("utf-8")
        data = _json.loads(text)
    except (UnicodeDecodeError, _json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="文件格式错误，请上传有效的 JSON 文件")

    meta = data.get("meta", {})
    if meta.get("type") != "api_cases":
        raise HTTPException(
            status_code=400,
            detail=f"文件类型不匹配，期望 api_cases，实际为 {meta.get('type')}"
        )

    cases_raw = data.get("cases", [])
    # 预加载接口定义：(METHOD, path) -> ApiDefinition
    all_apis = await ApiDefinition.filter(project_id=project_id, is_del=False).all()
    api_map = {(a.method.upper(), a.path): a for a in all_apis}
    # 预加载现有用例名称集合（用于同名去重）
    existing_raw = await ApiTestCase.filter(project_id=project_id, is_del=False).values_list("name", flat=True)
    existing_names = set(existing_raw)

    def resolve_name(base: str) -> str:
        candidate = base + "_导入"
        if candidate not in existing_names:
            existing_names.add(candidate)
            return candidate
        i = 2
        while True:
            candidate = f"{base}_导入{i}"
            if candidate not in existing_names:
                existing_names.add(candidate)
                return candidate
            i += 1

    success, failed = 0, 0
    warnings_list, errors_list, created_names = [], [], []

    for idx, c in enumerate(cases_raw):
        try:
            method = (c.get("api_method") or "").upper()
            path = c.get("api_path") or ""
            api_obj = api_map.get((method, path))
            if not api_obj:
                warnings_list.append(
                    f"用例「{c.get('name', f'第{idx+1}条')}」：找不到匹配接口 {method} {path}，已跳过"
                )
                failed += 1
                continue
            new_name = resolve_name(c.get("name", f"导入用例{idx + 1}"))
            create_kwargs = dict(
                name=new_name,
                api_id=api_obj.id,
                project_id=project_id,
                catalog_id=catalog_id,
                request_headers=c.get("request_headers") or {},
                request_params=c.get("request_params") or [],
                request_body=c.get("request_body") or {},
                request_body_type=c.get("request_body_type") or "json",
                request_body_fields=c.get("request_body_fields") or [],
                assertions=c.get("assertions") or [],
                extractors=c.get("extractors") or [],
                depends_on=[],
                timeout=c.get("timeout") or 30,
                retry_count=c.get("retry_count") or 0,
                tags=c.get("tags") or [],
                priority=c.get("priority") or "P2",
                create_by=username,
                update_by=username,
            )
            # pre/post_script 和 data_set 是 Phase 4.4 新增字段，兼容处理
            from app.models.http import ApiTestCase as _ApiTestCase
            if hasattr(_ApiTestCase, "pre_script"):
                create_kwargs["pre_script"] = c.get("pre_script")
                create_kwargs["post_script"] = c.get("post_script")
            if hasattr(_ApiTestCase, "data_set"):
                create_kwargs["data_set"] = c.get("data_set") or []
            await ApiTestCase.create(**create_kwargs)
            created_names.append(new_name)
            success += 1
        except Exception as e:
            errors_list.append(f"第 {idx + 1} 条用例处理失败：{str(e)}")
            failed += 1

    return ApiCaseImportResult(
        success=success,
        failed=failed,
        warnings=warnings_list,
        errors=errors_list,
        created_names=created_names,
    )


class CopyApiCaseRequest(BaseModel):
    target_project_id: Optional[int] = None
    target_catalog_id: Optional[int] = None
    new_name: Optional[str] = None


@router.post("/case/{case_id}/copy", summary="复制测试用例", response_model=ApiTestCaseOut,
             dependencies=[Depends(require_permissions(API_CASE_EDIT))])
async def copy_test_case(
    case_id: int,
    body: CopyApiCaseRequest | None = None,
    user_info: dict = Depends(require_permissions(API_CASE_EDIT)),
):
    """复制接口测试用例；可跨项目复制（自动匹配或复制关联接口）。"""
    from app.core.cross_project_copy import copy_api_case_to_project, ensure_target_project, resolve_target_catalog
    from app.core.ui_project_guard import assert_user_project_member

    case = await ApiTestCase.get_or_none(id=case_id, is_del=False)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    await assert_user_project_member(user_info, case.project_id)

    req = body or CopyApiCaseRequest()
    target_project_id = req.target_project_id or case.project_id
    if target_project_id != case.project_id:
        await assert_user_project_member(user_info, target_project_id)
        await ensure_target_project(target_project_id)
    target_catalog_id = await resolve_target_catalog(
        target_project_id,
        req.target_catalog_id if target_project_id != case.project_id else (req.target_catalog_id or case.catalog_id),
    )

    username = user_info.get("username") or "admin"
    new_case = await copy_api_case_to_project(
        case,
        target_project_id,
        target_catalog_id,
        username,
        req.new_name,
    )
    return await get_test_case(new_case.id)


@router.post("/variables/preview", summary="预览合并变量与替换结果",
             dependencies=[Depends(require_permissions(API_CASE_VIEW))])
async def preview_variables(body: VariablePreviewRequest):
    """合并项目/环境/额外变量，返回快照及示例字符串替换结果（执行前预览）。"""
    from app.core.variable_resolver import VariableResolver
    from app.core.data_tools.tag_service import merge_execution_variables
    from app.models.sys import Environment

    project_id = body.project_id
    if body.env_id:
        env = await Environment.get_or_none(id=body.env_id, is_del=False)
        if env:
            project_id = project_id or env.project_id

    merged = await merge_execution_variables(
        project_id,
        body.env_id,
        body.extra_variables or {},
    )
    resolver = VariableResolver(merged)

    def _var_expr(key: str) -> str:
        return "${{" + key + "}}"

    samples_in = list(body.samples or [])
    if not samples_in and merged:
        for key in list(merged.keys())[:2]:
            samples_in.append(_var_expr(key))
            samples_in.append(f"Bearer {_var_expr(key)}")

    samples_out = []
    for raw in samples_in:
        if not isinstance(raw, str):
            continue
        replaced = resolver.replace_in_string(raw)
        samples_out.append({
            "original": raw,
            "replaced": replaced,
            "unchanged": raw == replaced,
        })

    return {
        "variables": resolver.get_resolved_snapshot(),
        "priority": "project_global_vars < env_global_vars < df_tags < extra_variables",
        "samples": samples_out,
    }


@router.post("/case/{case_id}/run", summary="执行单条用例", response_model=ApiRunResult,
             dependencies=[Depends(require_permissions(API_CASE_EXECUTE))])
async def run_test_case(case_id: int, request: ApiRunRequest, username: str = Depends(get_current_username)):
    """执行单个接口测试用例（含前置/后置脚本、变量提取、重试）"""
    from .suites import run_single_case, run_data_driven_case
    from app.schemas.http import ApiDataDrivenRunResult

    case = await ApiTestCase.get_or_none(id=case_id, is_del=False)
    if case and case.data_set:
        return await run_data_driven_case(
            case_id,
            request.env_id,
            username,
            request.variables or {},
            request.auto_validate_schema,
            request.propagate_extracted,
        )

    return await run_single_case(
        case_id=case_id,
        env_id=request.env_id,
        suite_record_id=None,
        username=username,
        variables=request.variables or {},
        auto_validate_schema=request.auto_validate_schema,
    )
