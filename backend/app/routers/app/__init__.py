from app.routers.app.cases import router as app_case_router
from app.routers.app.suites import router as app_suite_router
from app.routers.app.plans import router as app_plan_router
from app.routers.app.exec import router as app_exec_router
from app.routers.app.records import router as app_record_router
from app.routers.app.elements import router as app_element_router
from app.routers.app.inspector import router as app_inspector_router
from app.routers.app.fragments import router as app_fragment_router
from app.routers.app.cron import router as app_cron_router

__all__ = [
    "app_case_router",
    "app_suite_router",
    "app_plan_router",
    "app_exec_router",
    "app_record_router",
    "app_element_router",
    "app_inspector_router",
    "app_fragment_router",
    "app_cron_router",
]
