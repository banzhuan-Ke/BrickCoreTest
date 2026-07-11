"""
AI 测试模块路由聚合
"""
from fastapi import APIRouter
from app.routers.ai.config import router as config_router
from app.routers.ai.embed_config import router as embed_config_router
from app.routers.ai.prompts import router as prompts_router
from app.routers.ai.generate import router as generate_router
from app.routers.ai.recorder import router as recorder_router
from app.routers.ai.requirements import router as requirements_router
from app.routers.ai.test_analysis import router as test_analysis_router
from app.routers.ai.workbench import router as workbench_router
from app.routers.ai.analyze import router as analyze_router
from app.routers.ai.functional_cases import router as functional_cases_router
from app.routers.ai.usage_logs import router as usage_logs_router
from app.routers.ai.browser_lab import router as browser_lab_router
ai_router = APIRouter(prefix="/ai", tags=["AI测试"])

# 注意：静态路由（如 /configs）必须在带路径参数的路由（如 /{id}）之前注册
ai_router.include_router(config_router)
ai_router.include_router(embed_config_router)
ai_router.include_router(prompts_router)
ai_router.include_router(generate_router)
ai_router.include_router(recorder_router)
ai_router.include_router(functional_cases_router)
ai_router.include_router(requirements_router)
ai_router.include_router(test_analysis_router)
ai_router.include_router(workbench_router)
ai_router.include_router(analyze_router)
ai_router.include_router(usage_logs_router)
ai_router.include_router(browser_lab_router)
