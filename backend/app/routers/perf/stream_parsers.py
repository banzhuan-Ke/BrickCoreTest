"""流式阶段解析器 API"""
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.core.platform.auth import require_permissions
from app.core.platform.permissions import PERF_SCENE_VIEW, PERF_SCENE_EDIT
from app.modules.stream_phase.registry import list_parsers, get_parser_preset, parse_stream_lines
from app.modules.stream_phase.parsers.rule_based import DEFAULT_RULES

router = APIRouter(prefix="/stream-parsers", tags=["流式阶段解析器"])


class StreamParserTestRequest(BaseModel):
    parser_id: str = Field(..., description="解析器 ID")
    lines: List[str] = Field(..., description="SSE 原始行列表")
    parser_options: Optional[dict] = Field(default_factory=dict)
    success_rule: Optional[dict] = None
    status_code: int = 200


@router.get("", summary="解析器列表", dependencies=[Depends(require_permissions(PERF_SCENE_VIEW))])
async def get_stream_parsers():
    return {"data": list_parsers()}


@router.get("/{parser_id}/preset", summary="解析器预设配置", dependencies=[Depends(require_permissions(PERF_SCENE_VIEW))])
async def get_stream_parser_preset(parser_id: str):
    preset = get_parser_preset(parser_id)
    if not preset:
        raise HTTPException(status_code=404, detail="解析器不存在")
    if parser_id == "rule_based" and not preset.get("default_options", {}).get("rules"):
        preset["default_options"] = {"rules": DEFAULT_RULES}
    return preset


@router.post("/test", summary="测试解析器", dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))])
async def test_stream_parser(req: StreamParserTestRequest):
    import time
    try:
        result = parse_stream_lines(
            req.parser_id,
            req.lines,
            start_time=time.time(),
            status_code=req.status_code,
            options=req.parser_options,
            success_rule=req.success_rule,
        )
        return {"success": True, "result": result}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
