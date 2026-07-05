"""SSE 流式解析配置管理 API"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import get_current_username, is_authenticated, require_permissions
from app.core.permissions import AI_CONFIG_EDIT, AI_CONFIG_VIEW, AI_TEST_VIEW
from app.core.stream_parser_config_service import (
    create_stream_parser_config,
    delete_stream_parser_config,
    get_stream_parser_config,
    list_builtin_parsers,
    list_stream_parser_configs,
    test_stream_parser_config,
    update_stream_parser_config,
)
from app.schemas.ai import StandardResponse

router = APIRouter(prefix="/stream-parser-configs", tags=["SSE解析配置"])


class StreamParserConfigForm(BaseModel):
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    parser_id: str = Field(..., max_length=64)
    parser_options: dict = Field(default_factory=dict)
    success_rule: dict = Field(default_factory=dict)
    is_enabled: bool = True
    sort_order: int = 0


class StreamParserConfigTestRequest(BaseModel):
    parser_id: str
    lines: List[str] = Field(default_factory=list)
    parser_options: dict = Field(default_factory=dict)
    success_rule: dict = Field(default_factory=dict)


@router.get("/builtin-parsers", summary="内置解析器类型列表")
async def get_builtin_parsers(
    _user: dict = Depends(require_permissions(AI_TEST_VIEW)),
):
    return StandardResponse(data=list_builtin_parsers())


@router.get("", summary="解析配置列表")
async def get_stream_parser_configs(
    enabled_only: bool = Query(False, description="仅返回启用的配置"),
    _user: dict = Depends(require_permissions(AI_TEST_VIEW)),
):
    rows = await list_stream_parser_configs(enabled_only=enabled_only)
    return StandardResponse(data=rows)


@router.post("/test", summary="测试解析配置")
async def test_stream_parser_config_api(
    body: StreamParserConfigTestRequest,
    _user: dict = Depends(require_permissions(AI_CONFIG_VIEW)),
):
    try:
        data = await test_stream_parser_config(
            parser_id=body.parser_id,
            lines=body.lines,
            parser_options=body.parser_options,
            success_rule=body.success_rule,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return StandardResponse(data=data)


@router.get("/{config_id}", summary="解析配置详情")
async def get_stream_parser_config_detail(
    config_id: int,
    _user: dict = Depends(require_permissions(AI_TEST_VIEW)),
):
    row = await get_stream_parser_config(config_id)
    if not row:
        raise HTTPException(status_code=404, detail="配置不存在")
    return StandardResponse(data=row)


@router.post("", summary="新建解析配置")
async def create_stream_parser_config_api(
    body: StreamParserConfigForm,
    username: str = Depends(get_current_username),
    _auth=Depends(is_authenticated),
    _perm=Depends(require_permissions(AI_CONFIG_EDIT)),
):
    try:
        row = await create_stream_parser_config(body.model_dump(), username=username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StandardResponse(data=row, message="创建成功")


@router.put("/{config_id}", summary="更新解析配置")
async def update_stream_parser_config_api(
    config_id: int,
    body: StreamParserConfigForm,
    username: str = Depends(get_current_username),
    _auth=Depends(is_authenticated),
    _perm=Depends(require_permissions(AI_CONFIG_EDIT)),
):
    try:
        row = await update_stream_parser_config(config_id, body.model_dump(), username=username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StandardResponse(data=row, message="保存成功")


@router.delete("/{config_id}", summary="删除解析配置")
async def delete_stream_parser_config_api(
    config_id: int,
    username: str = Depends(get_current_username),
    _auth=Depends(is_authenticated),
    _perm=Depends(require_permissions(AI_CONFIG_EDIT)),
):
    try:
        await delete_stream_parser_config(config_id, username=username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StandardResponse(message="删除成功")
