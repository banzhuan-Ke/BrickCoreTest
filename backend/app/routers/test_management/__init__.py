"""测试管理路由聚合"""
from fastapi import APIRouter

from app.routers.test_management.assets import router as assets_router
from app.routers.test_management.defects import router as defects_router
from app.routers.test_management.intelligence import router as intelligence_router
from app.routers.test_management.plans import router as plans_router
from app.routers.test_management.quality import router as quality_router
from app.routers.test_management.releases import router as releases_router
from app.routers.test_management.requirement_reviews import router as requirement_reviews_router
from app.routers.test_management.reviews import router as reviews_router
from app.routers.test_management.traceability import router as traceability_router

test_management_router = APIRouter(prefix="/test-management", tags=["测试管理"])


@test_management_router.get("/premium-status", tags=["测试管理"])
async def tm_premium_status():
    """测试管理扩展包安装/兼容状态（无需项目权限，供前端引导）。"""
    from app.modules.test_management.premium_gateway import get_tm_premium_info
    from app.schemas.test_management import StandardResponse

    return StandardResponse(data=get_tm_premium_info())


test_management_router.include_router(releases_router)
test_management_router.include_router(quality_router)
test_management_router.include_router(intelligence_router)
test_management_router.include_router(assets_router)
test_management_router.include_router(reviews_router)
test_management_router.include_router(requirement_reviews_router)
test_management_router.include_router(traceability_router)
test_management_router.include_router(plans_router)
test_management_router.include_router(defects_router)
