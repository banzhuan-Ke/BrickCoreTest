"""版本智能化 API"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.platform.auth import is_authenticated, require_permissions
from app.core.platform.permissions import AI_TEST_EXECUTE, TEST_QUALITY_VIEW
from app.modules.test_management import service as release_svc
from app.modules.test_management import release_intelligence_service as intel_svc
from app.modules.test_management.premium_gateway import require_tm_premium
from app.schemas.test_management import StandardResponse

router = APIRouter(
    prefix="/releases",
    tags=["测试管理-智能化"],
    dependencies=[Depends(require_tm_premium)],
)


class AiSummaryGenerateBody(BaseModel):
    ai_config_id: Optional[int] = Field(None, description="可选 AI 配置 ID")


def _username(user_info: dict) -> str:
    return user_info.get("username") or user_info.get("sub") or "system"


@router.get(
    "/{release_id}/intelligence",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_QUALITY_VIEW))],
)
async def get_release_intelligence(
    release_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    release = await release_svc.get_release_or_404(release_id, project_id)
    data = await intel_svc.build_release_intelligence(release)
    return StandardResponse(data=data)


@router.get(
    "/{release_id}/intelligence/ai-summary",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(TEST_QUALITY_VIEW))],
)
async def get_ai_release_summary(
    release_id: int,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    await release_svc.get_release_or_404(release_id, project_id)
    data = await intel_svc.get_cached_ai_summary(release_id, project_id)
    return StandardResponse(data=data)


@router.post(
    "/{release_id}/intelligence/ai-summary",
    response_model=StandardResponse,
    dependencies=[Depends(require_permissions(AI_TEST_EXECUTE))],
)
async def generate_ai_release_summary(
    release_id: int,
    body: AiSummaryGenerateBody,
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    release = await release_svc.get_release_or_404(release_id, project_id)
    data = await intel_svc.generate_ai_release_summary(
        release,
        username=_username(user_info),
        ai_config_id=body.ai_config_id,
    )
    ok = (data or {}).get("status") == "done"
    return StandardResponse(
        data=data,
        message="AI 版本总结已生成" if ok else ((data or {}).get("error") or "AI 版本总结生成失败"),
    )
