"""接口测试执行相关 API"""
import json
import time
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query, status, BackgroundTasks
from tortoise import transactions

from app.models.http import (
    ApiTestSuite, ApiSuiteCase, ApiTestCase, ApiDefinition,
    ApiRunRecord, ApiSuiteRunRecord
)
from app.core.platform.auth import is_authenticated, require_permissions, get_current_username
from app.core.platform.permissions import API_CASE_EXECUTE
from app.core.ops.notification import NotificationService
from app.modules.data_tools.inline_tools import ensure_dt_cache
from app.models.sys import Environment, NotificationConfig, Project

# 导入 schemas
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any


class ApiAssertionResult(BaseModel):
    """断言结果"""
    type: str
    target: Optional[str]
    operator: str
    expected: Any
    actual: Any
    passed: bool


class ApiRunResult(BaseModel):
    """执行结果"""
    record_id: int
    status: str = Field(..., description="success/failed")
    response_status: Optional[int] = None
    response_time: Optional[float] = Field(
        default=None,
        description="用例执行总耗时(ms)：含重试等待、断言、变量提取、脚本等",
    )
    http_response_time: Optional[float] = Field(
        default=None,
        description="纯 HTTP 请求耗时(ms)：httpx 发起到收到响应",
    )
    assertions: List[ApiAssertionResult] = Field(default=[])
    extracted_vars: Dict[str, Any] = Field(default={})
    error: Optional[str] = None
    request_detail: Optional[Dict[str, Any]] = Field(default=None, description="请求详情")
    response_detail: Optional[Dict[str, Any]] = Field(default=None, description="响应详情")
    case_id: Optional[int] = Field(default=None, description="用例ID")
    case_name: Optional[str] = Field(default=None, description="用例名称")
    retry_info: Optional[Dict[str, Any]] = Field(default=None, description="重试信息")


class ApiBatchRunRequest(BaseModel):
    """批量执行请求"""
    case_ids: List[int] = Field(..., description="用例ID列表")
    env_id: int = Field(..., description="环境ID")
    suite_id: Optional[int] = Field(None, description="所属套件ID")
    auto_validate_schema: bool = Field(default=False, description="是否自动校验响应 Schema")


class ApiSuiteRunRequest(BaseModel):
    """套件执行请求"""
    env_id: Optional[int] = Field(None, description="环境ID，不传则使用套件默认环境")
    auto_validate_schema: bool = Field(default=False, description="是否自动校验响应 Schema")
    trigger_type: str = Field(default="manual", description="触发方式: manual/cron/assistant 等")


class ApiBatchRunResult(BaseModel):
    """批量执行结果"""
    record_id: Optional[int] = None
    total: int
    success: int
    failed: int
    total_time: Optional[float] = None
    results: List[ApiRunResult]


router = APIRouter(prefix="/exec", tags=["接口测试执行"], dependencies=[Depends(is_authenticated), Depends(require_permissions(API_CASE_EXECUTE))])


# ============ 执行单个用例的核心函数（复用 suites 实现） ============

from .suites import run_single_case  # noqa: E402


from app.modules.http.api_suite_runner import execute_api_suite_cases as _execute_api_suite_cases


# ============ 批量执行和套件执行 ============

async def batch_run(request: ApiBatchRunRequest, background_tasks: BackgroundTasks = None, username: str = Depends(get_current_username)):
    """批量执行接口测试用例"""
    if not request.case_ids:
        raise HTTPException(status_code=422, detail="请选择要执行的用例")
    
    env = await Environment.get_or_none(id=request.env_id, is_del=False)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")

    suite = await ApiTestSuite.get_or_none(id=request.suite_id, is_del=False) if request.suite_id else None
    proj = await Project.get_or_none(id=env.project_id, is_del=False)
    project_global_vars = (proj.global_vars or {}) if proj else {}
    
    suite_record = None
    start_time = time.time()  # 记录开始时间
    if request.suite_id:
        suite_record = await ApiSuiteRunRecord.create(
            suite_id=request.suite_id,
            project_id=(await ApiTestSuite.get(id=request.suite_id)).project_id,
            status="running",
            trigger_type="manual",
            total_cases=len(request.case_ids),
            env_id=request.env_id,
            env_name=env.name,
            run_by=username
        )
    
    batch_start_time = time.time()

    if suite:
        run_result = await _execute_api_suite_cases(
            suite=suite,
            env=env,
            case_ids=request.case_ids,
            suite_record=suite_record,
            username=username,
            auto_validate_schema=getattr(request, "auto_validate_schema", False),
            project_global_vars=project_global_vars,
        )
        results = run_result["case_results"]
        success_count = run_result["success_count"]
        failed_count = run_result["failed_count"]
        hooks_result = run_result["hooks_result"]
    else:
        results = []
        success_count = 0
        failed_count = 0
        accumulated_vars = ensure_dt_cache({})
        hooks_result: dict = {"setup": [], "teardown": [], "db_assertions": [], "success": True}

        try:
            for case_id in request.case_ids:
                result = await run_single_case(
                    case_id, request.env_id, None, username,
                    accumulated_vars, getattr(request, "auto_validate_schema", False),
                    project_global_vars=project_global_vars,
                )
                results.append(result)
                accumulated_vars.update(result.extracted_vars)

                if result.status == "success":
                    success_count += 1
                else:
                    failed_count += 1
        except Exception:
            raise
    
    if suite_record:
        end_time = time.time()
        suite_record.status = "success" if failed_count == 0 and hooks_result.get("success", True) else "failed"
        suite_record.success_cases = success_count
        suite_record.failed_cases = failed_count
        suite_record.end_time = time.strftime("%Y-%m-%d %H:%M:%S")
        suite_record.duration = round((end_time - start_time) * 1000, 2)  # 统一为毫秒
        suite_record.hooks_result = hooks_result
        await suite_record.save()

        # 触发失败告警
        if failed_count > 0 or not hooks_result.get("success", True):
            suite_obj = await ApiTestSuite.get_or_none(id=suite_record.suite_id, is_del=False)
            await NotificationService.send_alert(
                project_id=suite_record.project_id,
                title=f"API套件执行失败：{suite_obj.name if suite_obj else '未知套件'}",
                content={
                    "execution_type": "API套件",
                    "name": suite_obj.name if suite_obj else "未知套件",
                    "status": "failed",
                    "total": suite_record.total_cases,
                    "success": success_count,
                    "failed": failed_count,
                    "pass_rate": round(success_count / suite_record.total_cases * 100, 2) if suite_record.total_cases > 0 else 0,
                    "duration": round(suite_record.duration / 1000, 2),  # 告警通知中转为秒展示
                    "run_by": suite_record.run_by,
                    "link": ""
                },
                related_id=suite_record.id,
                related_type="api_suite_run_record"
            )

        # 自动推送报告（执行完成后无论成功/失败都推送，便于查看详细结果）
        email_cfg = await NotificationConfig.filter(
            project_id=suite_record.project_id,
            channel_type="email",
            enabled=True,
            api_auto_push_report=True
        ).first()
        if email_cfg:
            try:
                await NotificationService.send_api_report(
                    project_id=suite_record.project_id,
                    record_id=suite_record.id
                )
            except Exception as e:
                print(f"[AutoReport] API 报告自动推送失败: {e}")

    batch_end_time = time.time()
    return ApiBatchRunResult(
        record_id=suite_record.id if suite_record else None,
        total=len(results),
        success=success_count,
        failed=failed_count,
        total_time=round(batch_end_time - batch_start_time, 3),
        results=results
    )


@router.post("/batch-run", summary="批量执行用例", response_model=ApiBatchRunResult, status_code=status.HTTP_201_CREATED)
async def batch_run_endpoint(request: ApiBatchRunRequest, background_tasks: BackgroundTasks, username: str = Depends(get_current_username)):
    """批量执行接口测试用例"""
    return await batch_run(request, background_tasks, username)


@router.post("/suites/{suite_id}", summary="执行测试套件", response_model=ApiBatchRunResult, status_code=status.HTTP_201_CREATED)
async def run_suite(suite_id: int, request: ApiSuiteRunRequest, username: str = Depends(get_current_username)):
    """执行测试套件"""
    suite = await ApiTestSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=404, detail="套件不存在")
    
    suite_cases = await ApiSuiteCase.filter(suite_id=suite_id).order_by("sort").all()
    case_ids = [sc.case_id for sc in suite_cases]
    
    if not case_ids:
        raise HTTPException(status_code=422, detail="套件中没有用例")
    
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


class AsyncRunResponse(BaseModel):
    """异步执行响应"""
    record_id: int
    message: str = "套件已开始后台执行"


@router.post("/suites/{suite_id}/async-run", summary="异步执行测试套件（后台执行）", response_model=AsyncRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_suite_async(suite_id: int, request: ApiSuiteRunRequest, background_tasks: BackgroundTasks, username: str = Depends(get_current_username)):
    """立即返回 record_id，后台执行套件，避免请求超时"""
    suite = await ApiTestSuite.get_or_none(id=suite_id, is_del=False)
    if not suite:
        raise HTTPException(status_code=404, detail="套件不存在")

    suite_cases = await ApiSuiteCase.filter(suite_id=suite_id).order_by("sort").all()
    case_ids = [sc.case_id for sc in suite_cases]

    if not case_ids:
        raise HTTPException(status_code=422, detail="套件中没有用例")

    env_id = request.env_id or suite.env_id
    if not env_id:
        raise HTTPException(status_code=422, detail="请指定执行环境")

    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")

    # 立即创建执行记录（状态为 running），并返回 record_id
    suite_record = await ApiSuiteRunRecord.create(
        suite_id=suite_id,
        project_id=suite.project_id,
        status="running",
        trigger_type=(request.trigger_type or "manual"),
        total_cases=len(case_ids),
        env_id=env_id,
        env_name=env.name,
        run_by=username
    )

    batch_request = ApiBatchRunRequest(
        case_ids=case_ids,
        env_id=env_id,
        suite_id=suite_id,
        auto_validate_schema=getattr(request, 'auto_validate_schema', False)
    )

    async def _run_in_background():
        """后台执行套件（重用 execute_api_suite_cases，跳过重复建记录）"""
        start_time = time.time()
        proj = await Project.get_or_none(id=suite.project_id, is_del=False)
        project_global_vars = (proj.global_vars or {}) if proj else {}

        try:
            run_result = await _execute_api_suite_cases(
                suite=suite,
                env=env,
                case_ids=case_ids,
                suite_record=suite_record,
                username=username,
                auto_validate_schema=getattr(batch_request, "auto_validate_schema", False),
                project_global_vars=project_global_vars,
            )
        except Exception as e:
            print(f"[AsyncSuiteRun] 执行异常: {e}")
            import traceback
            traceback.print_exc()
            suite_record.status = "failed"
            suite_record.end_time = time.strftime("%Y-%m-%d %H:%M:%S")
            suite_record.duration = round((time.time() - start_time) * 1000, 2)
            await suite_record.save()
            return

        success_count = run_result["success_count"]
        failed_count = run_result["failed_count"]
        hooks_result = run_result["hooks_result"]

        end_time = time.time()
        suite_record.status = "success" if failed_count == 0 and hooks_result.get("success", True) else "failed"
        suite_record.success_cases = success_count
        suite_record.failed_cases = failed_count
        suite_record.end_time = time.strftime("%Y-%m-%d %H:%M:%S")
        suite_record.duration = round((end_time - start_time) * 1000, 2)  # 统一为毫秒
        suite_record.hooks_result = hooks_result
        await suite_record.save()

        # 触发失败告警
        if failed_count > 0 or not hooks_result.get("success", True):
            suite_obj = await ApiTestSuite.get_or_none(id=suite_id, is_del=False)
            await NotificationService.send_alert(
                project_id=suite_record.project_id,
                title=f"API套件执行失败：{suite_obj.name if suite_obj else '未知套件'}",
                content={
                    "execution_type": "API套件",
                    "name": suite_obj.name if suite_obj else "未知套件",
                    "status": "failed",
                    "total": suite_record.total_cases,
                    "success": success_count,
                    "failed": failed_count,
                    "pass_rate": round(success_count / suite_record.total_cases * 100, 2) if suite_record.total_cases > 0 else 0,
                    "duration": round(suite_record.duration / 1000, 2),  # 告警通知中转为秒展示
                    "run_by": suite_record.run_by,
                    "link": ""
                },
                related_id=suite_record.id,
                related_type="api_suite_run_record"
            )

        # 自动推送报告
        from app.models.sys import NotificationConfig
        email_cfg = await NotificationConfig.filter(
            project_id=suite_record.project_id,
            channel_type="email",
            enabled=True,
            api_auto_push_report=True
        ).first()
        if email_cfg:
            try:
                await NotificationService.send_api_report(
                    project_id=suite_record.project_id,
                    record_id=suite_record.id
                )
            except Exception as e:
                print(f"[AutoReport] API 报告自动推送失败: {e}")

    background_tasks.add_task(_run_in_background)
    return AsyncRunResponse(record_id=suite_record.id)


class ApiRunCaseRequest(BaseModel):
    """单条用例执行请求"""
    env_id: int = Field(..., description="环境ID")
    variables: Optional[Dict[str, Any]] = Field(default={}, description="变量")
    auto_validate_schema: bool = Field(default=False, description="是否自动校验响应 Schema")
    propagate_extracted: bool = Field(default=True, description="数据驱动时行间传递提取变量")


@router.post("/cases/{case_id}", summary="执行单条用例", status_code=status.HTTP_201_CREATED)
async def run_single_case_endpoint(case_id: int, request: ApiRunCaseRequest, username: str = Depends(get_current_username)):
    """执行单个接口测试用例；如果用例配置了数据集，则执行数据驱动（返回 ApiDataDrivenRunResult）"""
    from app.schemas.http import ApiDataDrivenRunResult
    from .suites import run_single_case as _run_single_case, run_data_driven_case

    case = await ApiTestCase.get_or_none(id=case_id, is_del=False)
    if case and case.data_set:
        return await run_data_driven_case(
            case_id,
            request.env_id,
            username,
            request.variables,
            request.auto_validate_schema,
            request.propagate_extracted,
        )
    return await _run_single_case(
        case_id,
        request.env_id,
        None,
        username,
        request.variables,
        request.auto_validate_schema,
    )
