"""
核心配置文件
"""
import os
import app

# ========================= 项目路径配置（Docker / 本地直接运行均兼容） =========================
# 通过 app 包定位项目根目录（backend/），避免硬编码 dirname 层数
BASE_DIR = os.path.dirname(app.__path__[0])
STATIC_DIR = os.path.join(BASE_DIR, "static")
AVATAR_DIR = os.path.join(STATIC_DIR, "avatars")
LOGIN_BG_DIR = os.path.join(STATIC_DIR, "login-bg")
BROWSER_LAB_DIR = os.path.join(STATIC_DIR, "browser_lab")

BROWSER_LAB_MAX_CONCURRENT = int(os.getenv("BROWSER_LAB_MAX_CONCURRENT", "2"))
BROWSER_LAB_DAILY_LIMIT = int(os.getenv("BROWSER_LAB_DAILY_LIMIT", "0"))
BROWSER_LAB_DEFAULT_MAX_STEPS = int(os.getenv("BROWSER_LAB_DEFAULT_MAX_STEPS", "25"))
BROWSER_LAB_MAX_STEPS_CAP = int(os.getenv("BROWSER_LAB_MAX_STEPS_CAP", "50"))
# 单步超时（含 LLM + 浏览器操作）；云环境 / Vision 模型建议 360～600
BROWSER_LAB_STEP_TIMEOUT = int(os.getenv("BROWSER_LAB_STEP_TIMEOUT", "360"))
# CDP 截图连续失败时自动重启浏览器并续跑（0=关闭）
BROWSER_LAB_MAX_BROWSER_RESTARTS = int(os.getenv("BROWSER_LAB_MAX_BROWSER_RESTARTS", "2"))
BROWSER_LAB_MAX_BROWSER_RESTARTS_CAP = int(os.getenv("BROWSER_LAB_MAX_BROWSER_RESTARTS_CAP", "5"))
# 同一操作模式（如重复搜索/点击）连续出现 N 次则自动停止，避免浪费 Token
BROWSER_LAB_MAX_REPEAT_STEPS = int(os.getenv("BROWSER_LAB_MAX_REPEAT_STEPS", "3"))
BROWSER_LAB_MAX_REPEAT_STEPS_CAP = int(os.getenv("BROWSER_LAB_MAX_REPEAT_STEPS_CAP", "8"))
# browser-use 单步 LLM 解析失败最大重试次数
BROWSER_LAB_MAX_LLM_FAILURES = int(os.getenv("BROWSER_LAB_MAX_LLM_FAILURES", "3"))
# 无头浏览器视口（宽表格场景建议 1920×1080）
BROWSER_LAB_VIEWPORT_WIDTH = int(os.getenv("BROWSER_LAB_VIEWPORT_WIDTH", "1920"))
BROWSER_LAB_VIEWPORT_HEIGHT = int(os.getenv("BROWSER_LAB_VIEWPORT_HEIGHT", "1080"))

# ========================= MySQL数据库的配置 =========================
DATABASE = {
    'host': os.getenv('DATABASE_HOST', 'localhost'),
    'port': int(os.getenv('DATABASE_PORT', '3306')),
    'user': os.getenv('DATABASE_USER', 'fastapi'),
    'password': os.getenv('DATABASE_PASSWORD', 'F@stAp1_ecure#2026'),
    'database': os.getenv('DATABASE_NAME', 'fastapi')
}

# ========================= RabbitMQ的配置 =========================
MQ_CONFIG = {
    'host': os.getenv('MQ_HOST', 'localhost'),
    'port': int(os.getenv('MQ_PORT', '25672')),
    'username': os.getenv('MQ_USERNAME', 'admin'),
    'password': os.getenv('MQ_PASSWORD', 'R4bb1t_MQ#2026')
}
MQ_MANAGEMENT_HOST = os.getenv('MQ_MANAGEMENT_HOST', MQ_CONFIG['host'])
MQ_MANAGEMENT_PORT = int(os.getenv('MQ_MANAGEMENT_PORT', '15672'))
MQ_VHOST = os.getenv('MQ_VHOST', '/')

# ========================== Redis的配置 ==========================
REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'localhost'),
    'port': int(os.getenv('REDIS_PORT', '26379')),
    'db': int(os.getenv('REDIS_DB', '15')),
    'password': os.getenv('REDIS_PASSWORD', 'R3d1s_S3cur3#2026')
}

# ========================== APScheduler的配置 ==========================
APSCHEDULER_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'localhost'),
    'port': int(os.getenv('REDIS_PORT', '26379')),
    'db': int(os.getenv('SCHEDULER_REDIS_DB', '7')),
    'password': os.getenv('REDIS_PASSWORD', 'R3d1s_S3cur3#2026')
}

# TORTOISE_ORM配置
TORTOISE_ORM = {
    'connections': {
        'default': {
            'engine': 'tortoise.backends.mysql',
            'credentials': DATABASE
        }
    },
    "timezone": "Asia/Shanghai",
    'apps': {
        'models': {
            'models': ['aerich.models', 'app.models.sys', 'app.models.ui', 'app.models.app', 'app.models.http', 'app.models.schedule', 'app.models.perf', 'app.models.ai'],
            'default_connection': 'default'
        },
    }
}

# ========================== Token的配置 =========================
SECRET_KEY = os.getenv(
    'SECRET_KEY',
    "8beac45e868942b7157e25a0396f36db16ea92dd6713c9ebd116c5259e3fb3d3"
)
ALGORITHM = "HS256"
TOKEN_TIMEOUT = 60 * 60 * 24 * 1
# Runner 客户端会话 token 有效期（秒），默认 7 天
RUNNER_TOKEN_TIMEOUT = int(os.getenv("RUNNER_TOKEN_TIMEOUT", str(60 * 60 * 24 * 7)))
RUNNER_ENGINE_VERSION = os.getenv("RUNNER_ENGINE_VERSION", "1.0.2")
RUNNER_CLIENT_VERSION_MIN = os.getenv("RUNNER_CLIENT_VERSION_MIN", "1.3.8")
RUNNER_CLIENT_VERSION_LATEST = os.getenv("RUNNER_CLIENT_VERSION_LATEST", "1.4.0")
# 平台产品版本（页脚、/runner/version 展示，与 Runner 客户端版本独立）
PLATFORM_VERSION = os.getenv("PLATFORM_VERSION", "1.2.0")
# Runner 客户端安装包下载地址（zip 或文档页）；为空时客户端根据平台地址推导
RUNNER_CLIENT_DOWNLOAD_URL = os.getenv("RUNNER_CLIENT_DOWNLOAD_URL", "").strip()
# Phase 6：connect 下发按设备隔离的 MQ/Redis 凭证（需 RabbitMQ Management + Redis ACL）
RUNNER_MIDDLEWARE_ISOLATION = os.getenv("RUNNER_MIDDLEWARE_ISOLATION", "1").lower() in ("1", "true", "yes")

# Runner 客户端（Windows 等外网）连接 MQ/Redis 的公网地址；Docker 内网服务名对外不可解析
_DOCKER_INTERNAL_HOSTS = frozenset({"rabbitmq", "redis", "mysql", "minio", "backend"})


def _host_from_endpoint(endpoint: str) -> str:
    if not endpoint:
        return ""
    return endpoint.split(":")[0].strip()


def runner_client_mq_endpoint() -> tuple[str, int]:
    """返回下发给 Runner 客户端的 MQ host/port（非 Docker 内网地址）。"""
    if host := os.getenv("RUNNER_MQ_PUBLIC_HOST"):
        return host, int(os.getenv("RUNNER_MQ_PUBLIC_PORT", "25672"))
    internal_host = MQ_CONFIG["host"]
    internal_port = int(MQ_CONFIG["port"])
    if internal_host in _DOCKER_INTERNAL_HOSTS:
        public_host = _host_from_endpoint(os.getenv("MINIO_PUBLIC_ENDPOINT", ""))
        if public_host:
            return public_host, int(os.getenv("RUNNER_MQ_PUBLIC_PORT", "25672"))
    return internal_host, internal_port


def runner_client_redis_endpoint() -> tuple[str, int]:
    """返回下发给 Runner 客户端的 Redis host/port。"""
    if host := os.getenv("RUNNER_REDIS_PUBLIC_HOST"):
        return host, int(os.getenv("RUNNER_REDIS_PUBLIC_PORT", "26379"))
    internal_host = REDIS_CONFIG["host"]
    internal_port = int(REDIS_CONFIG["port"])
    if internal_host in _DOCKER_INTERNAL_HOSTS:
        public_host = _host_from_endpoint(os.getenv("MINIO_PUBLIC_ENDPOINT", ""))
        if public_host:
            return public_host, int(os.getenv("RUNNER_REDIS_PUBLIC_PORT", "26379"))
    return internal_host, internal_port

# 接口文档访问认证信息
DOC_USERNAME = os.getenv('DOC_USERNAME', 'admin')
DOC_PASSWORD = os.getenv('DOC_PASSWORD', 'Sw4gg3r$D0c#2026')

# Runner / 内部服务调用 API 的共享密钥
INTERNAL_API_KEY = os.getenv('INTERNAL_API_KEY', 'brickcore-internal-2026')

# BrickCore MCP Server
MCP_ENABLED = os.getenv('MCP_ENABLED', 'true').lower() in ('1', 'true', 'yes', 'on')
MCP_API_KEY = os.getenv('MCP_API_KEY', '')
# 非默认路径，降低公网扫描命中概率（勿使用 /mcp、/jsonrpc 等常见路径）
_DEFAULT_MCP_HTTP_PATH = '/brickcore/agent-hub'


def normalize_mcp_http_path(path: str | None = None) -> str:
    raw = (path if path is not None else os.getenv('MCP_HTTP_PATH', _DEFAULT_MCP_HTTP_PATH)).strip()
    if not raw:
        raw = _DEFAULT_MCP_HTTP_PATH
    if not raw.startswith('/'):
        raw = f'/{raw}'
    return raw.rstrip('/') or _DEFAULT_MCP_HTTP_PATH


MCP_HTTP_PATH = normalize_mcp_http_path()

# 平台 Base URL（Runner 回调等场景使用）
BASE_URL = os.getenv('BASE_URL', '')

# ========================== MinIO 配置 ==========================
# 存储类型: 'aliyun' 或 'minio'
STORAGE_TYPE = os.getenv('STORAGE_TYPE', 'minio')

# MinIO 配置
MINIO_CONFIG = {
    'endpoint': os.getenv('MINIO_ENDPOINT', 'localhost:9200'),
    'access_key': os.getenv('MINIO_ACCESS_KEY', 'admin'),
    'secret_key': os.getenv('MINIO_SECRET_KEY', 'M1n10_S3cur3#2026'),
    'bucket_name': os.getenv('MINIO_BUCKET', 'test-results'),
    'secure': os.getenv('MINIO_SECURE', 'false').lower() == 'true'
}

API_FILE_BUCKET = os.getenv('API_FILE_BUCKET', 'api-test-files')
AI_REQUIREMENT_BUCKET = os.getenv('AI_REQUIREMENT_BUCKET', 'ai-requirements')
UI_TEST_FILE_BUCKET = os.getenv('UI_TEST_FILE_BUCKET', 'ui-test-files')

# Web 自动化测试文件单文件上限（字节），默认 50MB
UI_TEST_FILE_MAX_BYTES = int(os.getenv('UI_TEST_FILE_MAX_BYTES', str(50 * 1024 * 1024)))
UI_TEST_FOLDER_MAX_BYTES = int(os.getenv('UI_TEST_FOLDER_MAX_BYTES', str(200 * 1024 * 1024)))
UI_TEST_FOLDER_MAX_FILES = int(os.getenv('UI_TEST_FOLDER_MAX_FILES', '500'))
