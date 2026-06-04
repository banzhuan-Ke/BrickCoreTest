"""
路由模块统一入口
"""
from fastapi import FastAPI

# 系统管理路由
from .sys.users import router as users_router
from .sys.roles import router as roles_router
from .sys.projects import router as projects_router
from .sys.envs import router as envs_router
from .sys.devices import router as devices_router
from .sys.catalogs import router as catalogs_router
from .sys.files import router as files_router
from .sys.dashboard import router as dashboard_router

# Web自动化路由
from .ui.cases import router as ui_cases_router
from .ui.suites import router as ui_suites_router
from .ui.tasks import router as ui_tasks_router
from .ui.exec import router as ui_exec_router
from .ui.records import router as ui_records_router

# API自动化路由
from .http.apis import router as http_apis_router
from .http.cases import router as http_cases_router
from .http.suites import router as http_suites_router
from .http.exec import router as http_exec_router
from .http.records import router as http_records_router
from .http.cron import router as http_cron_router

# 定时任务路由
from .schedule.jobs import router as schedule_jobs_router

__all__ = [
    "register_routers",
]


def register_routers(app: FastAPI):
    """注册所有路由到FastAPI应用"""
    
    # 系统管理 (/sys/*)
    app.include_router(users_router, prefix="/sys")
    app.include_router(roles_router, prefix="/sys")
    app.include_router(projects_router, prefix="/sys")
    app.include_router(envs_router, prefix="/sys")
    app.include_router(devices_router, prefix="/sys")
    app.include_router(catalogs_router, prefix="/sys")
    app.include_router(files_router, prefix="/sys")
    app.include_router(dashboard_router, prefix="/sys")
    
    # Web自动化(/ui/*)
    app.include_router(ui_cases_router, prefix="/ui")
    app.include_router(ui_suites_router, prefix="/ui")
    app.include_router(ui_tasks_router, prefix="/ui")
    app.include_router(ui_exec_router, prefix="/ui")
    app.include_router(ui_records_router, prefix="/ui")
    
    # API自动化(/http/*)
    app.include_router(http_apis_router, prefix="/http")
    app.include_router(http_cases_router, prefix="/http")
    app.include_router(http_suites_router, prefix="/http")
    app.include_router(http_exec_router, prefix="/http")
    app.include_router(http_records_router, prefix="/http")
    app.include_router(http_cron_router, prefix="/http")
    
    # 定时任务 (/schedule/*)
    app.include_router(schedule_jobs_router, prefix="/schedule")
