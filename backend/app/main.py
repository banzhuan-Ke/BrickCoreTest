import asyncio
import logging
import logging.handlers
import click
from fastapi import FastAPI, Request, status, Depends, HTTPException
import uvicorn
from starlette.responses import JSONResponse, Response
from tortoise.contrib.fastapi import register_tortoise
from app.core.platform import config as settings
from app.core.platform.config import MCP_ENABLED, MCP_HTTP_PATH
from app.routers.sys.users import router as user_router
from app.routers.sys.roles import router as role_router
from app.routers.sys.projects import router as project_router
from app.routers.sys.envs import router as environment_router
from app.routers.sys.catalogs import router as catalog_router
from app.routers.sys.files import router as files_router
from app.routers.sys.dashboard import router as dashboard_router
from app.routers.sys.asset_favorites import router as asset_favorites_router
from app.routers.sys.search import router as search_router
from app.routers.sys.operation_logs import router as operation_log_router
from app.routers.sys.notifications import router as notification_router, internal_router as notification_internal_router
from app.routers.sys.docs import router as docs_router
from app.routers.sys.mcp_info import router as mcp_info_router
from app.routers.sys.runner_release_config import router as runner_release_config_router
from app.routers.sys.login_page_config import router as login_page_config_router
from app.routers.sys.platform_settings import router as platform_settings_router
from app.routers.sys.stream_parser_config import router as stream_parser_config_router
from app.routers.sys.invite_codes import router as invite_code_router
from app.routers.sys.project_members import router as project_member_router
from app.routers.sys.project_settings import router as project_settings_router
from app.core.platform.project_access_deps import optional_project_access_check
from app.routers.ui.cases import router as case_router
from app.routers.ui.fragments import router as ui_fragment_router
from app.routers.ui.suites import router as suite_router
from app.routers.ui.tasks import router as task_router
from app.routers.ui.records import router as runner_router
from app.routers.ui.exec import router as ui_exec_router
from app.routers.ui.files import router as ui_files_router
from app.routers.ui.folders import router as ui_folders_router
from app.routers.ui.debug import router as ui_debug_router
from app.routers.app import (
    app_case_router,
    app_suite_router,
    app_plan_router,
    app_exec_router,
    app_record_router,
    app_element_router,
    app_inspector_router,
    app_fragment_router,
    app_cron_router,
)
from app.routers.sys.devices import router as device_router
from app.routers.runner import router as runner_client_router
from app.routers.schedule.jobs import router as cronjob_router
from app.routers.http.apis import router as api_definition_router
from app.routers.http.api_files import router as api_files_router
from app.routers.http.cases import router as api_case_router
from app.routers.http.suites import router as api_suite_router
from app.routers.http.records import router as api_records_router
from app.routers.http.cron import router as api_cron_router, scheduler as api_cron_scheduler
from app.routers.app.cron import scheduler as app_cron_scheduler
from app.routers.http.exec import router as api_exec_router
from app.routers.http.mocks import router as api_mock_router
from app.routers.http.plan import router as api_plan_router
from app.routers.http.auth_config import router as api_auth_config_router
from app.routers.http.data_factory import router as api_data_factory_router
from app.routers.http.header_templates import router as api_header_templates_router
from app.routers.perf import perf_router, workers_public_router
from app.routers.perf.cron import scheduler as perf_scheduler
from app.routers.ai import ai_router
from app.routers.ai.assistant import router as ai_assistant_router
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager, AsyncExitStack
from app.routers.schedule.jobs import scheduler
from app.core.ops.operation_log import OperationLogMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
import base64
import os

# CORS：本地默认 + Pro 正式机；额外来源可用 CORS_ALLOWED_ORIGINS 追加（逗号分隔）
def _cors_allowed_origins() -> list[str]:
    defaults = [
        "http://localhost:8080",
        "http://localhost:8000",
        "http://localhost",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:8000",
        "http://47.111.226.241",
        "http://47.111.226.241:8000",
        "http://47.111.226.241:81",
        "http://47.111.226.241:80",
    ]
    raw = (os.getenv("CORS_ALLOWED_ORIGINS") or "").strip()
    extras = [x.strip() for x in raw.split(",") if x.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for origin in defaults + extras:
        if origin not in seen:
            seen.add(origin)
            out.append(origin)
    return out


ALLOWED_ORIGINS = _cors_allowed_origins()

# 高频探活/心跳不写 access 日志，避免执行器客户端长期在线时日志膨胀
_ACCESS_LOG_QUIET_PATHS = (
    "/runner/health",
    "/runner/heartbeat",
    "/runner/version",
    "/runner/active-recording",
)


class _AccessLogQuietFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(path in msg for path in _ACCESS_LOG_QUIET_PATHS)


def _install_access_log_quiet_filter() -> None:
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _AccessLogQuietFilter) for f in access_logger.filters):
        access_logger.addFilter(_AccessLogQuietFilter())


_install_access_log_quiet_filter()

banner = """
██████╗ ██╗   ██╗███╗   ██╗███╗   ██╗███████╗██████╗
██╔══██╗██║   ██║████╗  ██║████╗  ██║██╔════╝██╔══██╗
██████╔╝██║   ██║██╔██╗ ██║██╔██╗ ██║█████╗  ██████╔╝
██╔══██╗██║   ██║██║╚██╗██║██║╚██╗██║██╔══╝  ██╔══██╗
██║  ██║╚██████╔╝██║ ╚████║██║ ╚████║███████╗██║  ██║
╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝
"""

# 安全配置
security = HTTPBasic()


def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    """验证用户名和密码"""
    # 从配置文件获取用户名和密码
    correct_username = secrets.compare_digest(credentials.username, settings.DOC_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, settings.DOC_PASSWORD)

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def check_auth(request: Request):
    """检查请求是否已认证"""
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        return False

    encoded_credentials = auth_header.split(" ")[1]
    decoded = base64.b64decode(encoded_credentials).decode("ascii")
    username, password = decoded.split(":")

    # 从配置文件获取用户名和密码
    return (username == settings.DOC_USERNAME and
            password == settings.DOC_PASSWORD)


@asynccontextmanager
async def _core_lifespan(app: FastAPI):
    """BrickCore 主应用生命周期（调度器、日志等）"""
    click.echo(banner)
    scheduler.start()
    from app.modules.ui.ui_execution_stale import register_stale_cleanup_job
    register_stale_cleanup_job(scheduler)
    from app.modules.ui.ui_debug_session_lifecycle import register_debug_session_cleanup_job
    register_debug_session_cleanup_job(scheduler)
    from app.modules.app.app_execution_stale import register_stale_cleanup_job as register_app_stale_cleanup_job
    register_app_stale_cleanup_job(scheduler)
    from app.modules.runner.runner_offline_cleanup import register_runner_heartbeat_stale_job
    register_runner_heartbeat_stale_job(scheduler)
    api_cron_scheduler.start()
    app_cron_scheduler.start()
    perf_scheduler.start()
    _install_access_log_quiet_filter()
    logger = logging.getLogger("uvicorn.access")
    handler = logging.handlers.RotatingFileHandler("logs/py.log", mode="a", maxBytes=100 * 1024)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
    try:
        from app.core.infra.minio_client import init_minio_buckets

        try:
            await asyncio.to_thread(init_minio_buckets)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "MinIO bucket 自动初始化失败（MinIO 未就绪时可忽略，首次上传会重试）: %s", exc
            )
        from app.core.platform.role_seed import ensure_default_roles
        from app.core.platform.project_access import backfill_project_members

        try:
            await ensure_default_roles()
        except Exception as exc:
            logging.getLogger(__name__).warning("系统角色种子初始化失败: %s", exc)
        try:
            await backfill_project_members()
        except Exception as exc:
            logging.getLogger(__name__).warning("项目成员回填失败: %s", exc)
        try:
            from app.core.integration.stream_parser_config_service import ensure_builtin_stream_parser_configs

            await ensure_builtin_stream_parser_configs()
        except Exception as exc:
            logging.getLogger(__name__).warning("SSE 解析配置种子初始化失败: %s", exc)
        # ORM 已可用后再校准，避免启动早期查库失败
        try:
            from app.routers.schedule.jobs import reconcile_ui_cron_jobs

            await reconcile_ui_cron_jobs()
        except Exception as exc:
            logging.getLogger(__name__).warning("Web 定时任务启动校准失败: %s", exc)
        yield
    finally:
        scheduler.shutdown()
        api_cron_scheduler.shutdown()
        app_cron_scheduler.shutdown()
        perf_scheduler.shutdown()
        for log_handler in logger.handlers:
            logger.removeHandler(log_handler)
            log_handler.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """合并主应用与 MCP（Streamable HTTP 需初始化 task group）"""
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(_core_lifespan(app))
        if MCP_ENABLED:
            from app.mcp.server import get_mcp_asgi_app

            mcp_app = get_mcp_asgi_app()
            await stack.enter_async_context(mcp_app.router.lifespan_context(mcp_app))
        yield


# 线上部署屏蔽接口文档，可以增加参数openapi_url=None
app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, title="BrickCore 接口文档",
              description="v0.1.0版接口文档", version="0.1.0", summary="BrickCore 接口文档")


# 接口文档
@app.get("/swagger", include_in_schema=False)
async def custom_swagger_ui_html(request: Request):
    """需要认证才能访问的swagger接口文档"""
    if not check_auth(request):
        return Response(
            content="请登录后访问",
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Basic"}
        )

    return get_swagger_ui_html(openapi_url=app.openapi_url, title=app.title + " - Swagger UI",
                               oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
                               swagger_js_url="/static/swagger-ui-bundle.js",
                               swagger_css_url="/static/swagger-ui.css")


@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect(request: Request):
    """需要认证才能访问的swagger认证重定向"""
    if not check_auth(request):
        return Response(
            content="请登录后访问",
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Basic"}
        )

    return get_swagger_ui_oauth2_redirect_html()


@app.get("/redoc", include_in_schema=False)
async def redoc_html(request: Request):
    """需要认证才能访问的redoc接口文档"""
    if not check_auth(request):
        return Response(
            content="请登录后访问",
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Basic"}
        )

    return get_redoc_html(openapi_url=app.openapi_url, title=app.title + " - ReDoc",
                          redoc_js_url="/static/redoc.standalone.js")


# 接口文档的静态文件路径（统一从 config 读取，避免工作目录问题）
# 增量 .bcpack 仅允许经鉴权接口下载，禁止走公开 /static
@app.middleware("http")
async def block_public_runner_patches(request: Request, call_next):
    path = (request.url.path or "").replace("\\", "/").lower()
    if path.startswith("/static/runner/patches/") or path.endswith(".bcpack"):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "请登录后通过 /runner/client-patch/{channel} 下载增量包"},
        )
    return await call_next(request)


app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")


@app.exception_handler(StarletteHTTPException)
async def global_exception_handler(request: Request, exc: StarletteHTTPException):
    """全局http响应异常处理"""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def global_validation_handler(request: Request, exc: RequestValidationError):
    """全局参数校验异常处理"""
    import logging
    errors = exc.errors()
    # 将 errors 中的 bytes 转为可序列化的 str，避免 JSONResponse 500
    def _convert(obj):
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        if isinstance(obj, dict):
            return {k: _convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_convert(i) for i in obj]
        return obj
    serializable_errors = _convert(errors)
    logging.error(f"Validation error for {request.url}: {serializable_errors}")
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": "请求参数错误！", "errors": serializable_errors})


# CORS跨域问题
# app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"],
#                    allow_headers=["*"])
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True, allow_methods=["*"],
                   allow_headers=["*"])

# 注册操作日志中间件
app.add_middleware(OperationLogMiddleware)

# 注册ORM模型
register_tortoise(app, config=settings.TORTOISE_ORM, modules={"models": ["models"]}, add_exception_handlers=True,
                  generate_schemas=False)

# 注册路由
_project_access_dep = [Depends(optional_project_access_check)]

app.include_router(user_router, prefix="/sys")
app.include_router(role_router, prefix="/sys")
app.include_router(project_router, prefix="/sys")
app.include_router(project_member_router, prefix="/sys")
app.include_router(project_settings_router, prefix="/sys", dependencies=_project_access_dep)
app.include_router(environment_router, prefix="/sys", dependencies=_project_access_dep)
app.include_router(catalog_router, prefix="/sys", dependencies=_project_access_dep)
app.include_router(files_router, prefix="/sys")
app.include_router(device_router, prefix="/sys")
app.include_router(runner_client_router)
app.include_router(dashboard_router, prefix="/sys")
app.include_router(asset_favorites_router, prefix="/sys")
app.include_router(search_router, prefix="/sys")
app.include_router(operation_log_router, prefix="/sys")
app.include_router(notification_router, prefix="/sys", dependencies=_project_access_dep)
app.include_router(notification_internal_router, prefix="/sys")
app.include_router(docs_router, prefix="/sys")
app.include_router(mcp_info_router, prefix="/sys")
app.include_router(runner_release_config_router, prefix="/sys")
app.include_router(login_page_config_router, prefix="/sys")
app.include_router(platform_settings_router, prefix="/sys")
app.include_router(stream_parser_config_router, prefix="/sys")
app.include_router(invite_code_router, prefix="/sys")

if MCP_ENABLED:
    from app.mcp.server import get_mcp_asgi_app

    _mcp_asgi_app = get_mcp_asgi_app()
    app.mount(MCP_HTTP_PATH, _mcp_asgi_app)

app.include_router(case_router, prefix="/ui", dependencies=_project_access_dep)
app.include_router(ui_fragment_router, prefix="/ui", dependencies=_project_access_dep)
app.include_router(suite_router, prefix="/ui", dependencies=_project_access_dep)
app.include_router(task_router, prefix="/ui", dependencies=_project_access_dep)
app.include_router(runner_router, prefix="/ui", dependencies=_project_access_dep)
app.include_router(ui_exec_router, prefix="/ui", dependencies=_project_access_dep)
app.include_router(ui_files_router, prefix="/ui", dependencies=_project_access_dep)
app.include_router(ui_folders_router, prefix="/ui", dependencies=_project_access_dep)
app.include_router(ui_debug_router, prefix="/ui", dependencies=_project_access_dep)

app.include_router(app_case_router, prefix="/app-module", dependencies=_project_access_dep)
app.include_router(app_suite_router, prefix="/app-module", dependencies=_project_access_dep)
app.include_router(app_plan_router, prefix="/app-module", dependencies=_project_access_dep)
app.include_router(app_exec_router, prefix="/app-module", dependencies=_project_access_dep)
app.include_router(app_record_router, prefix="/app-module", dependencies=_project_access_dep)
app.include_router(app_element_router, prefix="/app-module", dependencies=_project_access_dep)
app.include_router(app_inspector_router, prefix="/app-module", dependencies=_project_access_dep)
app.include_router(app_fragment_router, prefix="/app-module", dependencies=_project_access_dep)
app.include_router(app_cron_router, prefix="/app-module", dependencies=_project_access_dep)

app.include_router(cronjob_router, prefix="/schedule", dependencies=_project_access_dep)

app.include_router(api_definition_router, prefix="/api-module", dependencies=_project_access_dep)
app.include_router(api_files_router, prefix="/api-module", dependencies=_project_access_dep)
app.include_router(api_case_router, prefix="/api-module", dependencies=_project_access_dep)
app.include_router(api_suite_router, prefix="/api-module", dependencies=_project_access_dep)
app.include_router(api_records_router, prefix="/api-module", dependencies=_project_access_dep)
app.include_router(api_cron_router, prefix="/api-module", dependencies=_project_access_dep)
app.include_router(api_exec_router, prefix="/api-module", dependencies=_project_access_dep)
app.include_router(api_mock_router, prefix="/api-module", dependencies=_project_access_dep)
app.include_router(api_plan_router, prefix="/api-module", dependencies=_project_access_dep)
app.include_router(api_auth_config_router, prefix="/api-module", dependencies=_project_access_dep)
app.include_router(api_data_factory_router, prefix="/api-module", dependencies=_project_access_dep)
app.include_router(api_header_templates_router, prefix="/api-module", dependencies=_project_access_dep)
app.include_router(perf_router, dependencies=_project_access_dep)
app.include_router(workers_public_router, prefix="/perf")
ai_router.include_router(ai_assistant_router)
app.include_router(ai_router, dependencies=_project_access_dep)

if __name__ == '__main__':
    uvicorn.run(app="app.main:app", host="0.0.0.0", port=8000, reload=False)
