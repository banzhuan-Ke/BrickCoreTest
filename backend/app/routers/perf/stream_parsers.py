"""流式阶段解析器 API"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.core.platform.auth import require_permissions
from app.core.platform.permissions import PERF_SCENE_VIEW, PERF_SCENE_EDIT
from app.modules.stream_phase.registry import list_parsers, get_parser_preset, parse_stream_lines
from app.modules.stream_phase.parsers.rule_based import DEFAULT_RULES
from app.modules.stream_phase.parsers.custom_sse import DEFAULT_RULES as CUSTOM_SSE_DEFAULT_RULES
from app.modules.stream_phase.data_preprocess import list_example_rule_templates

router = APIRouter(prefix="/stream-parsers", tags=["流式阶段解析器"])


class StreamParserTestRequest(BaseModel):
    parser_id: str = Field(..., description="解析器 ID")
    lines: List[str] = Field(..., description="SSE 原始行列表")
    parser_options: Optional[dict] = Field(default_factory=dict)
    success_rule: Optional[dict] = None
    status_code: int = 200
    debug_match_views: bool = Field(True, description="返回整形后的 match_view 样本，便于排错")


@router.get("", summary="解析器列表", dependencies=[Depends(require_permissions(PERF_SCENE_VIEW))])
async def get_stream_parsers():
    return {"data": list_parsers()}


@router.get(
    "/example-templates",
    summary="匿名规则示例模板",
    dependencies=[Depends(require_permissions(PERF_SCENE_VIEW))],
)
async def get_example_rule_templates():
    """通用示例（嵌套 JSON / Patch 流），套用后可按公司协议随意改，不绑定厂商。"""
    return {"data": list_example_rule_templates()}


@router.get("/{parser_id}/preset", summary="解析器预设配置", dependencies=[Depends(require_permissions(PERF_SCENE_VIEW))])
async def get_stream_parser_preset(parser_id: str):
    preset = get_parser_preset(parser_id)
    if not preset:
        raise HTTPException(status_code=404, detail="解析器不存在")
    if parser_id == "rule_based" and not preset.get("default_options", {}).get("rules"):
        preset["default_options"] = {"rules": DEFAULT_RULES}
    if parser_id == "custom_sse" and not preset.get("default_options", {}).get("rules"):
        preset["default_options"] = {"rules": CUSTOM_SSE_DEFAULT_RULES}
    return preset


@router.post("/test", summary="测试解析器", dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))])
async def test_stream_parser(req: StreamParserTestRequest):
    import time
    try:
        options = dict(req.parser_options or {})
        if req.debug_match_views:
            options["debug_match_views"] = True
        result = parse_stream_lines(
            req.parser_id,
            req.lines,
            start_time=time.time(),
            status_code=req.status_code,
            options=options,
            success_rule=req.success_rule,
        )
        return {"success": True, "result": result}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
