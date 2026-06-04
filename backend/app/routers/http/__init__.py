from fastapi import APIRouter
from .apis import router as definition_router
from .cases import router as case_router
from .suites import router as suite_router
from .cron import router as cron_router
from .plan import router as plan_router
from .mocks import router as mock_router
from .auth_config import router as auth_config_router
from .data_factory import router as data_factory_router
from .header_templates import router as header_templates_router

# 合并所有路由
router = APIRouter(prefix="/api-module")

# 从 apis.py 导入的路由
for route in definition_router.routes:
    router.routes.append(route)

# 从 cases.py 导入的路由
for route in case_router.routes:
    router.routes.append(route)

# 从 suites.py 导入的路由
for route in suite_router.routes:
    router.routes.append(route)

# 从 cron.py 导入的路由
for route in cron_router.routes:
    router.routes.append(route)

# 从 plan.py 导入的路由
for route in plan_router.routes:
    router.routes.append(route)

# 从 mocks.py 导入的路由
for route in mock_router.routes:
    router.routes.append(route)

# 从 auth_config.py 导入的路由
for route in auth_config_router.routes:
    router.routes.append(route)

for route in data_factory_router.routes:
    router.routes.append(route)

for route in header_templates_router.routes:
    router.routes.append(route)

__all__ = ["router"]


