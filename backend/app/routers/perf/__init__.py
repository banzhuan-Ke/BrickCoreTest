"""性能测试路由模块"""
from fastapi import APIRouter, Depends
from app.core.auth import is_authenticated, require_permissions
from app.core.permissions import PERF_SCENE_VIEW

from .scenes import router as scenes_router
from .exec import router as exec_router
from .records import router as records_router
from .cron import router as cron_router
from .workers import router as workers_router, public_router as workers_public_router
from .stream_parsers import router as stream_parsers_router

perf_router = APIRouter(
    prefix="/perf",
    tags=["性能测试"],
    dependencies=[Depends(is_authenticated), Depends(require_permissions(PERF_SCENE_VIEW))]
)

perf_router.include_router(scenes_router)
perf_router.include_router(exec_router)
perf_router.include_router(records_router)
perf_router.include_router(cron_router)
perf_router.include_router(workers_router)
perf_router.include_router(stream_parsers_router)
