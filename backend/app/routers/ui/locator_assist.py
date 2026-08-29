"""Web 定位助手 API。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.platform.auth import require_permissions
from app.core.platform.permissions import UI_CASE_EXECUTE
from app.modules.ui.locator_assist.service import suggest_locators
from app.modules.ui.locator_assist.validate import MAX_CANDIDATES
from app.modules.ui.ui_project_guard import assert_user_project_member

router = APIRouter(prefix="/locator-assist", tags=["UI Locator Assist"])

_MAX_RAW = 20_000


class LocatorAssistSuggestForm(BaseModel):
    project_id: int = Field(..., description="项目 ID")
    raw_element: str = Field(..., min_length=1, max_length=_MAX_RAW, description="元素 outerHTML / 属性 / JSON")
    intent: str = Field("", max_length=500, description="意图，如取第几个、要哪个字段")
    ai_enabled: bool = Field(True, description="是否尝试 AI 增强")
    ai_config_id: Optional[int] = Field(None, description="指定 AI 配置")
    step_method: str = Field("", max_length=64)
    max_candidates: int = Field(MAX_CANDIDATES, ge=1, le=12)


@router.post("/suggest", summary="根据元素信息生成定位候选")
async def suggest_locator_candidates(
    body: LocatorAssistSuggestForm,
    user_info: dict = Depends(require_permissions(UI_CASE_EXECUTE)),
):
    await assert_user_project_member(user_info, body.project_id)
    raw = (body.raw_element or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="请粘贴元素信息")
    if len(raw) > _MAX_RAW:
        raise HTTPException(status_code=422, detail="元素信息过长")

    data = await suggest_locators(
        raw_element=raw,
        intent=body.intent or "",
        ai_enabled=bool(body.ai_enabled),
        ai_config_id=body.ai_config_id,
        step_method=body.step_method or "",
        max_candidates=body.max_candidates,
        project_id=body.project_id,
        username=str(user_info.get("username") or ""),
    )
    return {"data": data}
