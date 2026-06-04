"""Runner 客户端路由"""
from fastapi import APIRouter

from app.routers.runner.connect import router as connect_router
from app.routers.runner.results import router as results_router
from app.routers.runner.upload import router as upload_router
from app.routers.runner.device_log import router as device_log_router
from app.routers.runner.release import router as release_router

router = APIRouter()
router.include_router(connect_router)
router.include_router(release_router)
router.include_router(results_router)
router.include_router(upload_router)
router.include_router(device_log_router)

__all__ = ["router"]
