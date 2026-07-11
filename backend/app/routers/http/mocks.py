import asyncio
import json
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query, Request, status
from pydantic import BaseModel, Field
from starlette.responses import Response
from app.models.http import MockApi
from app.schemas.http import MockApiCreate, MockApiUpdate, MockApiOut, MockApiListResponse
from app.core.platform.auth import require_permissions, is_authenticated
from app.core.platform.permissions import API_MOCK_VIEW, API_MOCK_EDIT, AI_TEST_EXECUTE
from app.core.llm.mock_ai_service import generate_mock_response_body

router = APIRouter()

MOCK_VIEW = API_MOCK_VIEW
MOCK_EDIT = API_MOCK_EDIT


class MockAiGenerateRequest(BaseModel):
    method: str = Field(default="GET", description="HTTP 方法")
    path: str = Field(..., description="Mock 路径")
    name: str = Field(default="", description="Mock 名称")
    description: str = Field(default="", description="响应业务描述")
    response_status: int = Field(default=200, ge=100, le=599)
    ai_config_id: Optional[int] = Field(default=None, description="可选 AI 配置 ID")
    project_id: Optional[int] = Field(default=None, description="项目 ID（用于 usage 日志）")


class MockAiGenerateResponse(BaseModel):
    response_body: dict | list | str | int | float | bool | None = Field(default_factory=dict)
    response_status: int = 200


def _build_mock_out(mock: MockApi) -> dict:
    return {
        "id": mock.id,
        "name": mock.name,
        "project_id": mock.project_id,
        "method": mock.method,
        "path": mock.path,
        "match_rules": mock.match_rules or {},
        "response_status": mock.response_status,
        "response_headers": mock.response_headers or {},
        "response_body": mock.response_body,
        "response_delay": mock.response_delay,
        "is_enabled": mock.is_enabled,
        "call_count": mock.call_count,
        "last_call_time": mock.last_call_time,
        "create_time": mock.create_time,
        "update_time": mock.update_time,
    }


@router.post("/mock/ai-generate", summary="AI 生成 Mock 响应体", response_model=MockAiGenerateResponse,
             dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))])
async def ai_generate_mock_body(
    body: MockAiGenerateRequest,
    user_info: dict = Depends(is_authenticated),
):
    """根据接口路径与业务描述，AI 生成 Mock 响应 JSON。"""
    if not body.path.strip():
        raise HTTPException(status_code=400, detail="path 不能为空")
    project_id = body.project_id or user_info.get("project_id") or user_info.get("current_project_id")
    result = await generate_mock_response_body(
        method=body.method.upper(),
        path=body.path.strip(),
        name=body.name.strip(),
        description=body.description.strip(),
        response_status=body.response_status,
        ai_config_id=body.ai_config_id,
        user_info=user_info,
        project_id=project_id,
    )
    return MockAiGenerateResponse(
        response_body=result["response_body"],
        response_status=result["response_status"],
    )


@router.get("/mock", summary="Mock 接口列表", response_model=MockApiListResponse,
            dependencies=[Depends(require_permissions(MOCK_VIEW))])
async def get_mock_list(
    project_id: int = Query(..., description="项目ID"),
    keyword: Optional[str] = Query(None, description="关键字（名称/路径）"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200)
):
    """获取 Mock 接口列表"""
    query = MockApi.filter(project_id=project_id, is_del=False)
    if keyword:
        query = query.filter(name__contains=keyword) | MockApi.filter(project_id=project_id, is_del=False, path__contains=keyword)
        query = MockApi.filter(project_id=project_id, is_del=False).filter(
            name__contains=keyword
        )
    total = await query.count()
    mocks = await query.order_by("-id").offset((page - 1) * size).limit(size).all()
    return MockApiListResponse(
        data=[_build_mock_out(m) for m in mocks],
        total=total, page=page, size=size
    )


@router.post("/mock", summary="创建 Mock 接口", response_model=MockApiOut,
             dependencies=[Depends(require_permissions(MOCK_EDIT))])
async def create_mock(item: MockApiCreate):
    """创建 Mock 接口"""
    mock = await MockApi.create(
        name=item.name,
        project_id=item.project_id,
        method=item.method.upper(),
        path=item.path,
        match_rules=item.match_rules or {},
        response_status=item.response_status,
        response_headers=item.response_headers or {},
        response_body=item.response_body if item.response_body is not None else {},
        response_delay=item.response_delay,
        is_enabled=item.is_enabled,
    )
    return _build_mock_out(mock)


@router.get("/mock/{mock_id}", summary="Mock 接口详情", response_model=MockApiOut,
            dependencies=[Depends(require_permissions(MOCK_VIEW))])
async def get_mock(mock_id: int):
    """获取 Mock 接口详情"""
    mock = await MockApi.get_or_none(id=mock_id, is_del=False)
    if not mock:
        raise HTTPException(status_code=404, detail="Mock 接口不存在")
    return _build_mock_out(mock)


@router.put("/mock/{mock_id}", summary="更新 Mock 接口", response_model=MockApiOut,
            dependencies=[Depends(require_permissions(MOCK_EDIT))])
async def update_mock(mock_id: int, item: MockApiUpdate):
    """更新 Mock 接口"""
    mock = await MockApi.get_or_none(id=mock_id, is_del=False)
    if not mock:
        raise HTTPException(status_code=404, detail="Mock 接口不存在")
    mock.name = item.name
    mock.method = item.method.upper()
    mock.path = item.path
    mock.match_rules = item.match_rules or {}
    mock.response_status = item.response_status
    mock.response_headers = item.response_headers or {}
    mock.response_body = item.response_body if item.response_body is not None else {}
    mock.response_delay = item.response_delay
    mock.is_enabled = item.is_enabled
    await mock.save()
    return _build_mock_out(mock)


@router.delete("/mock/{mock_id}", summary="删除 Mock 接口",
               status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(MOCK_EDIT))])
async def delete_mock(mock_id: int):
    """删除 Mock 接口（逻辑删除）"""
    mock = await MockApi.get_or_none(id=mock_id, is_del=False)
    if not mock:
        raise HTTPException(status_code=404, detail="Mock 接口不存在")
    mock.is_del = True
    await mock.save()


@router.post("/mock/{mock_id}/toggle", summary="切换 Mock 启用状态",
             dependencies=[Depends(require_permissions(MOCK_EDIT))])
async def toggle_mock(mock_id: int):
    """启用/禁用 Mock 接口"""
    mock = await MockApi.get_or_none(id=mock_id, is_del=False)
    if not mock:
        raise HTTPException(status_code=404, detail="Mock 接口不存在")
    mock.is_enabled = not mock.is_enabled
    await mock.save()
    return {"is_enabled": mock.is_enabled}


# ---------------------------------------------------------------------------
# Mock 调用端点：接收真实请求，按 method + path + match_rules 匹配后返回响应
# ---------------------------------------------------------------------------

@router.api_route(
    "/mock-call/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
    summary="Mock 接口调用",
    include_in_schema=False,
)
async def mock_call(request: Request, path: str):
    """
    根据已配置的 Mock 规则返回预设响应。
    
    匹配逻辑：
    1. 按 request.method + path 精确匹配
    2. 校验 match_rules（header / query / body）
    3. 如有 response_delay 则延迟响应
    4. 更新 call_count + last_call_time
    5. 返回配置的 response_status + response_headers + response_body
    
    调用示例：
        GET  /api-module/mock-call/api/users
        POST /api-module/mock-call/api/login
    """
    request_path = path if path.startswith("/") else "/" + path
    method = request.method.upper()

    # 支持通过 query param 传入 project_id 缩小匹配范围
    query_params = dict(request.query_params)
    project_id = query_params.pop("_project_id", None)

    # 构建查询条件
    filters = {"method": method, "is_enabled": True, "is_del": False}
    if project_id:
        try:
            filters["project_id"] = int(project_id)
        except ValueError:
            pass

    mocks = await MockApi.filter(**filters).all()

    # 精确匹配 path（兼容用户配置时带或不带前导 /）
    matched_mock = None
    for mock in mocks:
        mock_path = mock.path if mock.path.startswith("/") else "/" + mock.path
        if mock_path == request_path:
            matched_mock = mock
            break

    if not matched_mock:
        raise HTTPException(status_code=404, detail="Mock 接口未找到或未启用")

    # ---------- 高级匹配规则校验 ----------
    match_rules = matched_mock.match_rules or {}

    # 1. Header 匹配
    if "header" in match_rules:
        for key, expected_val in match_rules["header"].items():
            actual_val = request.headers.get(key)
            if actual_val != expected_val:
                raise HTTPException(
                    status_code=404,
                    detail=f"Mock header 匹配失败: {key}={actual_val} (期望 {expected_val})"
                )

    # 2. Query 参数匹配（排除内部参数 _project_id）
    if "query" in match_rules:
        for key, expected_val in match_rules["query"].items():
            actual_val = query_params.get(key)
            if actual_val != str(expected_val):
                raise HTTPException(
                    status_code=404,
                    detail=f"Mock query 匹配失败: {key}={actual_val} (期望 {expected_val})"
                )

    # 3. Body 匹配（仅对非 GET/HEAD/OPTIONS 请求做简单 JSON 顶层字段匹配）
    if "body" in match_rules and method not in ("GET", "HEAD", "OPTIONS"):
        try:
            body_bytes = await request.body()
            if body_bytes:
                body_json = json.loads(body_bytes)
            else:
                body_json = {}
        except Exception:
            body_json = {}

        for key, expected_val in match_rules["body"].items():
            actual_val = body_json.get(key)
            if actual_val != expected_val:
                raise HTTPException(
                    status_code=404,
                    detail=f"Mock body 匹配失败: {key}={actual_val} (期望 {expected_val})"
                )

    # ---------- 延迟响应 ----------
    if matched_mock.response_delay and matched_mock.response_delay > 0:
        await asyncio.sleep(matched_mock.response_delay / 1000)

    # ---------- 更新统计 ----------
    matched_mock.call_count = matched_mock.call_count + 1
    matched_mock.last_call_time = datetime.now()
    await matched_mock.save(update_fields=["call_count", "last_call_time"])

    # ---------- 构造响应 ----------
    response_body = matched_mock.response_body
    if isinstance(response_body, (dict, list)):
        content = json.dumps(response_body, ensure_ascii=False)
        default_headers = {"Content-Type": "application/json; charset=utf-8"}
    else:
        content = str(response_body)
        default_headers = {}

    # 合并用户配置的响应头
    mock_headers = matched_mock.response_headers or {}
    response_headers = {**default_headers, **mock_headers}

    return Response(
        status_code=matched_mock.response_status,
        headers=response_headers,
        content=content,
    )
