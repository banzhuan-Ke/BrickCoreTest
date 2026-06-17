"""接口测试执行记录查询 API"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query, status
from fastapi.responses import HTMLResponse

from app.models.http import ApiSuiteRunRecord, ApiRunRecord, ApiPlanRunRecord
from app.core.auth import is_authenticated, require_permissions
from app.core.permissions import API_RECORD_VIEW
from app.core.api_report_export import (
    generate_api_html_report,
    sum_http_response_time_ms,
    sum_plan_item_results_http_ms,
    resolve_http_response_time,
)
from app.core.notification import NotificationService

# 导入 schemas
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any


class ApiSuiteRunRecordOut(BaseModel):
    """套件执行记录输出"""
    id: int
    suite_id: int
    suite_name: str
    project_id: int
    status: str
    trigger_type: str
    total_cases: int
    success_cases: int
    failed_cases: int
    skipped_cases: int
    start_time: datetime
    end_time: Optional[datetime]
    duration: float
    env_id: Optional[int]
    env_name: Optional[str]
    run_by: str
    
    class Config:
        from_attributes = True


class ApiSuiteRunListResponse(BaseModel):
    """套件执行记录列表响应"""
    data: List[ApiSuiteRunRecordOut]
    total: int
    page: int
    size: int


class ApiRunRecordUnifiedOut(BaseModel):
    """统一执行记录输出（套件+计划）"""
    id: int
    record_type: str          # suite / plan
    name: str                 # 套件名/计划名
    suite_id: Optional[int] = None
    plan_id: Optional[int] = None
    project_id: int
    status: str
    trigger_type: str
    total_cases: int
    success_cases: int
    failed_cases: int
    skipped_cases: Optional[int] = None   # 套件有，计划无
    start_time: datetime
    end_time: Optional[datetime]
    duration: Optional[float] = None
    http_duration: Optional[float] = Field(None, description="接口总耗时(ms)，各用例纯HTTP之和")
    env_id: Optional[int]
    env_name: Optional[str]
    run_by: str


class ApiRunRecordUnifiedListResponse(BaseModel):
    """统一执行记录列表响应"""
    data: List[ApiRunRecordUnifiedOut]
    total: int
    page: int
    size: int


class ApiCaseRunResultOut(BaseModel):
    """用例执行记录输出"""
    record_id: int
    case_id: int
    case_name: str
    status: str
    response_status: Optional[int]
    response_time: Optional[float]
    response_body: Optional[Any]
    response_headers: Optional[Dict]
    assertions: List[Dict]
    extracted_vars: Dict[str, Any]
    error_msg: Optional[str]
    start_time: datetime
    request_detail: Dict[str, Any]


router = APIRouter(prefix="/records", tags=["接口执行记录"], dependencies=[Depends(is_authenticated), Depends(require_permissions(API_RECORD_VIEW))])


# ============ 套件执行记录查询 ============

@router.get("/suites", summary="执行记录列表", response_model=ApiSuiteRunListResponse, status_code=status.HTTP_200_OK)
async def get_run_records(
    project_id: int = Query(..., description="项目ID"),
    suite_id: Optional[int] = Query(None, description="套件ID"),
    status: Optional[str] = Query(None, description="状态"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=5000)
):
    """获取执行记录列表（套件）"""
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


@router.get("/all", summary="统一执行记录列表(套件+计划)", response_model=ApiRunRecordUnifiedListResponse, status_code=status.HTTP_200_OK)
async def get_all_run_records(
    project_id: int = Query(..., description="项目ID"),
    record_type: Optional[str] = Query(None, description="记录类型: suite/plan"),
    status: Optional[str] = Query(None, description="状态"),
    keyword: Optional[str] = Query(None, description="关键词搜索(套件名/计划名)"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=5000)
):
    """获取统一执行记录列表（套件+计划合并）"""
    from collections import defaultdict

    suite_records = []
    plan_records = []

    # 查询套件记录（用 -id 排序避免 MySQL sort buffer 不足）
    # 过滤掉 trigger_type='plan' 的套件记录（计划执行产生的子套件记录不单独展示）
    if not record_type or record_type == "suite":
        suite_query = ApiSuiteRunRecord.filter(project_id=project_id).exclude(trigger_type="plan")
        if status:
            suite_query = suite_query.filter(status=status)
        suite_records = await suite_query.order_by("-id").all()

    # 查询计划记录
    if not record_type or record_type == "plan":
        plan_query = ApiPlanRunRecord.filter(project_id=project_id)
        if status:
            plan_query = plan_query.filter(status=status)
        plan_records = await plan_query.order_by("-id").all()

    suite_http_map: dict = defaultdict(float)
    suite_ids = [r.id for r in suite_records]
    if suite_ids:
        suite_case_rows = await ApiRunRecord.filter(suite_run_record_id__in=suite_ids).all()
        for cr in suite_case_rows:
            t = resolve_http_response_time({
                "request_detail": cr.request_detail or {},
            })
            if t is not None:
                suite_http_map[cr.suite_run_record_id] += float(t)

    # 组装统一数据
    unified = []
    for record in suite_records:
        suite = await record.suite
        name = suite.name if suite else "未知套件"
        if keyword and keyword.lower() not in name.lower():
            continue
        unified.append(ApiRunRecordUnifiedOut(
            id=record.id,
            record_type="suite",
            name=name,
            suite_id=record.suite_id,
            plan_id=None,
            project_id=record.project_id,
            status=record.status,
            trigger_type=record.trigger_type,
            total_cases=record.total_cases,
            success_cases=record.success_cases,
            failed_cases=record.failed_cases,
            skipped_cases=record.skipped_cases,
            start_time=record.start_time,
            end_time=record.end_time,
            duration=record.duration,
            http_duration=(
                round(suite_http_map[record.id], 2)
                if record.id in suite_http_map
                else None
            ),
            env_id=record.env_id,
            env_name=record.env_name,
            run_by=record.run_by,
        ))

    for record in plan_records:
        plan = await record.plan
        name = plan.name if plan else "未知计划"
        if keyword and keyword.lower() not in name.lower():
            continue
        unified.append(ApiRunRecordUnifiedOut(
            id=record.id,
            record_type="plan",
            name=name,
            suite_id=None,
            plan_id=record.plan_id,
            project_id=record.project_id,
            status=record.status,
            trigger_type=record.trigger_type,
            total_cases=record.total_cases,
            success_cases=record.success_cases,
            failed_cases=record.failed_cases,
            skipped_cases=None,
            start_time=record.start_time,
            end_time=record.end_time,
            duration=record.duration,
            http_duration=(
                sum_plan_item_results_http_ms(record.item_results) or None
            ),
            env_id=record.env_id,
            env_name=record.env_name,
            run_by=record.run_by,
        ))

    # 按 start_time 倒序排列
    unified.sort(key=lambda x: x.start_time or datetime.min, reverse=True)

    total = len(unified)
    start = (page - 1) * size
    end = start + size
    paginated = unified[start:end]

    return ApiRunRecordUnifiedListResponse(data=paginated, total=total, page=page, size=size)


@router.get("/suites/{record_id}", summary="执行记录详情", status_code=status.HTTP_200_OK)
async def get_run_record_detail(record_id: int):
    """获取执行记录详情"""
    record = await ApiSuiteRunRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    
    suite = await record.suite
    
    case_records = await ApiRunRecord.filter(
        suite_run_record_id=record_id
    ).order_by("id").all()
    
    # 第一遍：构建变量来源映射（变量名 → 哪个用例提取的）
    var_source_map = {}
    case_info_map = {}
    for cr in case_records:
        case = await cr.case
        case_info_map[cr.case_id] = case.name if case else "未知"
        for var_name in (cr.extracted_vars or {}).keys():
            if var_name not in var_source_map:
                var_source_map[var_name] = {
                    "case_id": cr.case_id,
                    "case_name": case.name if case else "未知"
                }
    
    # 第二遍：构建变量引用映射，并组装 case_results
    var_usage_map = {}  # 变量名 → 引用它的用例列表
    case_results = []
    for cr in case_records:
        case = await cr.case
        request_detail = cr.request_detail or {}
        replacements = request_detail.get("replacements", []) or []
        
        # 为每个替换记录标注变量来源用例
        enriched_replacements = []
        for rep in replacements:
            var_name = rep.get("key", "")
            source = var_source_map.get(var_name)
            enriched_rep = dict(rep)
            if source:
                enriched_rep["source_case_name"] = source["case_name"]
                enriched_rep["source_case_id"] = source["case_id"]
                # 记录该变量被当前用例引用
                if var_name not in var_usage_map:
                    var_usage_map[var_name] = []
                var_usage_map[var_name].append({
                    "case_id": cr.case_id,
                    "case_name": case.name if case else "未知"
                })
            else:
                enriched_rep["source_case_name"] = None
                enriched_rep["source_case_id"] = None
            enriched_replacements.append(enriched_rep)
        
        # 为提取的变量标注被哪些用例引用
        extracted_meta = {}
        for var_name, var_value in (cr.extracted_vars or {}).items():
            extracted_meta[var_name] = {
                "value": var_value,
                "used_by": var_usage_map.get(var_name, [])
            }
        
        retry_info = request_detail.get("retry_info") if isinstance(request_detail, dict) else None
        stage_timings = request_detail.get("stage_timings") if isinstance(request_detail, dict) else {}
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
            "extracted_meta": extracted_meta,
            "extractor_results": request_detail.get("extractor_results") or [],
            "error_msg": cr.error_msg,
            "start_time": cr.start_time,
            "retry_info": retry_info,
            "request_detail": {
                **request_detail,
                "replacements": enriched_replacements
            }
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
        "http_duration": sum_http_response_time_ms(case_results) or None,
        "env_name": record.env_name,
        "run_by": record.run_by,
        "case_results": case_results
    }


# ============ 单个用例执行记录查询 ============

@router.post("/suites/{record_id}/send-report", summary="发送 API 测试报告邮件", status_code=status.HTTP_200_OK)
async def send_suite_report(record_id: int):
    """手动发送 API 测试报告邮件"""
    record = await ApiSuiteRunRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    try:
        await NotificationService.send_api_report(
            project_id=record.project_id,
            record_id=record_id
        )
        return {"detail": "报告邮件已发送"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发送失败: {e}")


@router.get("/suites/{record_id}/report", summary="导出套件执行报告(HTML)", status_code=status.HTTP_200_OK)
async def export_suite_report(record_id: int):
    """导出 API 套件执行记录为 HTML 报告"""
    record = await ApiSuiteRunRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    
    suite = await record.suite
    case_records = await ApiRunRecord.filter(
        suite_run_record_id=record_id
    ).order_by("id").all()
    
    # 第一遍：构建变量来源映射
    var_source_map = {}
    case_info_map = {}
    for cr in case_records:
        case = await cr.case
        case_info_map[cr.case_id] = case.name if case else "未知"
        for var_name in (cr.extracted_vars or {}).keys():
            if var_name not in var_source_map:
                var_source_map[var_name] = {
                    "case_id": cr.case_id,
                    "case_name": case.name if case else "未知"
                }
    
    # 第二遍：构建变量引用映射，并组装 case_results
    var_usage_map = {}
    case_results = []
    for cr in case_records:
        case = await cr.case
        request_detail = cr.request_detail or {}
        replacements = request_detail.get("replacements", []) or []
        
        # 为每个替换记录标注变量来源用例
        enriched_replacements = []
        for rep in replacements:
            var_name = rep.get("key", "")
            source = var_source_map.get(var_name)
            enriched_rep = dict(rep)
            if source:
                enriched_rep["source_case_name"] = source["case_name"]
                enriched_rep["source_case_id"] = source["case_id"]
                if var_name not in var_usage_map:
                    var_usage_map[var_name] = []
                var_usage_map[var_name].append({
                    "case_id": cr.case_id,
                    "case_name": case.name if case else "未知"
                })
            else:
                enriched_rep["source_case_name"] = None
                enriched_rep["source_case_id"] = None
            enriched_replacements.append(enriched_rep)
        
        # 为提取的变量标注被哪些用例引用
        extracted_meta = {}
        for var_name, var_value in (cr.extracted_vars or {}).items():
            extracted_meta[var_name] = {
                "value": var_value,
                "used_by": var_usage_map.get(var_name, [])
            }
        
        retry_info = request_detail.get("retry_info") if isinstance(request_detail, dict) else None
        stage_timings = request_detail.get("stage_timings") if isinstance(request_detail, dict) else {}
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
            "assertions_result": cr.assertions_result,
            "extracted_vars": cr.extracted_vars,
            "extracted_meta": extracted_meta,
            "extractor_results": request_detail.get("extractor_results") or [],
            "error_msg": cr.error_msg,
            "start_time": cr.start_time,
            "retry_info": retry_info,
            "request_detail": {
                **request_detail,
                "replacements": enriched_replacements
            },
            "request_url": cr.request_url,
            "request_headers": cr.request_headers,
            "request_body": cr.request_body,
        })
    
    suite_record = {
        "id": record.id,
        "suite_name": suite.name if suite else "未知套件",
        "status": record.status,
        "trigger_type": record.trigger_type,
        "total_cases": record.total_cases,
        "success_cases": record.success_cases,
        "failed_cases": record.failed_cases,
        "skipped_cases": record.skipped_cases,
        "error_cases": 0,
        "start_time": record.start_time,
        "end_time": record.end_time,
        "duration": record.duration,
        "http_duration": sum_http_response_time_ms(case_results) or None,
        "env_name": record.env_name,
        "run_by": record.run_by,
        "hooks_result": record.hooks_result or {},
    }
    
    html_content = generate_api_html_report(suite_record, case_results)
    filename = f"api_report_{record_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    
    return HTMLResponse(
        content=html_content,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/cases", summary="用例执行记录列表", status_code=status.HTTP_200_OK)
async def get_case_run_records(
    project_id: int = Query(..., description="项目ID"),
    case_id: Optional[int] = Query(None, description="用例ID"),
    status: Optional[str] = Query(None, description="状态"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=5000)
):
    """获取单个用例的执行记录列表"""
    query = ApiRunRecord.filter(project_id=project_id)
    
    if case_id:
        query = query.filter(case_id=case_id)
    
    if status:
        query = query.filter(status=status)
    
    total = await query.count()
    records = await query.order_by("-id").offset((page - 1) * size).limit(size).all()
    
    result = []
    for record in records:
        case = await record.case
        result.append({
            "id": record.id,
            "case_id": record.case_id,
            "case_name": case.name if case else "未知用例",
            "project_id": record.project_id,
            "status": record.status,
            "request_url": record.request_url,
            "request_method": record.request_method,
            "response_status": record.response_status,
            "response_time": record.response_time,
            "assertions_result": record.assertions_result,
            "error_msg": record.error_msg,
            "start_time": record.start_time,
            "run_by": record.run_by
        })
    
    return {"data": result, "total": total, "page": page, "size": size}


@router.post("/suites/batch-delete", summary="批量删除套件执行记录", status_code=status.HTTP_204_NO_CONTENT)
async def batch_delete_suite_records(record_ids: List[int]):
    """批量删除套件执行记录"""
    if not record_ids:
        raise HTTPException(status_code=400, detail="请选择要删除的记录")
    
    deleted = 0
    for rid in record_ids:
        record = await ApiSuiteRunRecord.get_or_none(id=rid)
        if record:
            await record.delete()
            deleted += 1
    
    return None


@router.get("/cases/{record_id}", summary="用例执行记录详情", status_code=status.HTTP_200_OK)
async def get_case_run_record_detail(record_id: int):
    """获取单个用例执行记录详情"""
    record = await ApiRunRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    
    case = await record.case
    request_detail = record.request_detail or {}
    stage_timings = request_detail.get("stage_timings") if isinstance(request_detail, dict) else {}
    http_response_time = (
        stage_timings.get("request_ms") if isinstance(stage_timings, dict) else None
    )

    env_name = None
    env_id = None
    if record.suite_run_record_id:
        suite_record = await ApiSuiteRunRecord.get_or_none(id=record.suite_run_record_id)
        if suite_record:
            env_name = suite_record.env_name
            env_id = suite_record.env_id
    if not env_name and isinstance(request_detail, dict):
        env_name = request_detail.get("env_name")
        env_id = request_detail.get("env_id")

    return {
        "id": record.id,
        "case_id": record.case_id,
        "case_name": case.name if case else "未知用例",
        "project_id": record.project_id,
        "status": record.status,
        "env_id": env_id,
        "env_name": env_name,
        "request_url": record.request_url,
        "request_method": record.request_method,
        "request_headers": record.request_headers,
        "request_body": record.request_body,
        "response_status": record.response_status,
        "response_headers": record.response_headers,
        "response_body": record.response_body,
        "response_time": record.response_time,
        "http_response_time": http_response_time,
        "assertions_result": record.assertions_result,
        "extracted_vars": record.extracted_vars,
        "error_msg": record.error_msg,
        "request_detail": record.request_detail,
        "start_time": record.start_time,
        "run_by": record.run_by
    }
