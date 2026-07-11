"""
系统预置角色定义（部署时自动种子，code 不可变）
"""
from app.core.platform.permissions import (
    ALL_PERMISSIONS,
    ROLE_EDIT,
    ROLE_VIEW,
    USER_EDIT,
    USER_VIEW,
    PROJECT_VIEW,
    PROJECT_EDIT,
    ENVIRONMENT_VIEW,
    ENVIRONMENT_EDIT,
    MODULE_VIEW,
    MODULE_EDIT,
    UI_CASE_VIEW,
    UI_CASE_EDIT,
    UI_CASE_EXECUTE,
    UI_SUITE_VIEW,
    UI_SUITE_EDIT,
    UI_SUITE_EXECUTE,
    UI_TASK_VIEW,
    UI_TASK_EDIT,
    UI_TASK_EXECUTE,
    UI_CRON_VIEW,
    UI_CRON_EDIT,
    UI_RECORD_VIEW,
    UI_RECORD_EDIT,
    APP_CASE_VIEW,
    APP_CASE_EDIT,
    APP_CASE_EXECUTE,
    APP_ELEMENT_VIEW,
    APP_ELEMENT_EDIT,
    APP_SUITE_VIEW,
    APP_SUITE_EDIT,
    APP_SUITE_EXECUTE,
    APP_PLAN_VIEW,
    APP_PLAN_EDIT,
    APP_PLAN_EXECUTE,
    APP_RECORD_VIEW,
    DEVICE_VIEW,
    DEVICE_EDIT,
    API_MANAGE_VIEW,
    API_MANAGE_EDIT,
    API_CASE_VIEW,
    API_CASE_EDIT,
    API_CASE_EXECUTE,
    API_SUITE_VIEW,
    API_SUITE_EDIT,
    API_SUITE_EXECUTE,
    API_CRON_VIEW,
    API_CRON_EDIT,
    API_RECORD_VIEW,
    API_PLAN_VIEW,
    API_PLAN_EDIT,
    API_MOCK_VIEW,
    API_MOCK_EDIT,
    API_AUTH_VIEW,
    API_AUTH_EDIT,
    DATA_FACTORY_VIEW,
    DATA_FACTORY_EDIT,
    PERF_SCENE_VIEW,
    PERF_SCENE_EDIT,
    PERF_SCENE_EXECUTE,
    PERF_CRON_VIEW,
    PERF_CRON_EDIT,
    PERF_WORKER_VIEW,
    PERF_RECORD_VIEW,
    AI_TEST_VIEW,
    AI_TEST_EXECUTE,
    AI_CONFIG_VIEW,
    DOCS_VIEW,
    OPERATION_LOG_VIEW,
)

SYSTEM_ADMIN_CODE = "system_admin"
MEMBER_CODE = "member"

# 系统管理员：可查看用户/角色，不可新增或编辑（编辑权限仅 is_superuser）
_SYSTEM_ADMIN_DENIED = {USER_EDIT, ROLE_EDIT}
SYSTEM_ADMIN_PERMISSIONS = sorted(p for p in ALL_PERMISSIONS if p not in _SYSTEM_ADMIN_DENIED)


def sanitize_system_admin_permissions(permissions: list[str] | None) -> list[str] | None:
    """系统管理员角色不可包含用户/角色编辑权限。"""
    if permissions is None:
        return None
    perms = [p for p in permissions if p not in _SYSTEM_ADMIN_DENIED]
    # 确保保留查看权限
    for p in (USER_VIEW, ROLE_VIEW):
        if p not in perms:
            perms.append(p)
    return sorted(perms)

# 各模块只读基础（项目配置入口）
_BASE_READ = [
    PROJECT_VIEW,
    ENVIRONMENT_VIEW,
    MODULE_VIEW,
]

# 各模块只读（普通成员 / 只读观察员共用）
_VIEWER_PERMISSIONS = _BASE_READ + [
    UI_CASE_VIEW,
    UI_SUITE_VIEW,
    UI_TASK_VIEW,
    UI_CRON_VIEW,
    UI_RECORD_VIEW,
    UI_RECORD_EDIT,
    APP_CASE_VIEW,
    APP_SUITE_VIEW,
    APP_PLAN_VIEW,
    APP_RECORD_VIEW,
    APP_ELEMENT_VIEW,
    DEVICE_VIEW,
    API_MANAGE_VIEW,
    API_CASE_VIEW,
    API_SUITE_VIEW,
    API_CRON_VIEW,
    API_RECORD_VIEW,
    API_PLAN_VIEW,
    API_MOCK_VIEW,
    API_AUTH_VIEW,
    DATA_FACTORY_VIEW,
    PERF_SCENE_VIEW,
    PERF_CRON_VIEW,
    PERF_WORKER_VIEW,
    PERF_RECORD_VIEW,
    AI_TEST_VIEW,
    AI_CONFIG_VIEW,
    DOCS_VIEW,
    OPERATION_LOG_VIEW,
]

DEFAULT_ROLES: list[dict] = [
    {
        "code": SYSTEM_ADMIN_CODE,
        "name": "系统管理员",
        "description": "拥有全部功能权限；用户/角色仅可查看，新增与编辑需超级管理员",
        "permissions": SYSTEM_ADMIN_PERMISSIONS,
    },
    {
        "code": MEMBER_CODE,
        "name": "普通成员",
        "description": "注册默认角色：各模块只读；加入项目后可查看用例/接口等，编辑需额外分配工程师角色",
        "permissions": list(_VIEWER_PERMISSIONS),
    },
    {
        "code": "project_manager",
        "name": "项目管理员",
        "description": "管理项目、环境、测试目录配置",
        "permissions": [
            PROJECT_VIEW,
            PROJECT_EDIT,
            ENVIRONMENT_VIEW,
            ENVIRONMENT_EDIT,
            MODULE_VIEW,
            MODULE_EDIT,
            DOCS_VIEW,
        ],
    },
    {
        "code": "web_tester",
        "name": "Web测试工程师",
        "description": "Web 自动化测试全套权限",
        "permissions": _BASE_READ
        + [
            UI_CASE_VIEW,
            UI_CASE_EDIT,
            UI_CASE_EXECUTE,
            UI_SUITE_VIEW,
            UI_SUITE_EDIT,
            UI_SUITE_EXECUTE,
            UI_TASK_VIEW,
            UI_TASK_EDIT,
            UI_TASK_EXECUTE,
            UI_CRON_VIEW,
            UI_CRON_EDIT,
            UI_RECORD_VIEW,
            UI_RECORD_EDIT,
            DEVICE_VIEW,
            DEVICE_EDIT,
        ],
    },
    {
        "code": "app_tester",
        "name": "App测试工程师",
        "description": "App 自动化测试全套权限",
        "permissions": _BASE_READ
        + [
            APP_CASE_VIEW,
            APP_CASE_EDIT,
            APP_CASE_EXECUTE,
            APP_SUITE_VIEW,
            APP_SUITE_EDIT,
            APP_SUITE_EXECUTE,
            APP_PLAN_VIEW,
            APP_PLAN_EDIT,
            APP_PLAN_EXECUTE,
            APP_RECORD_VIEW,
            APP_ELEMENT_VIEW,
            APP_ELEMENT_EDIT,
            DEVICE_VIEW,
            DEVICE_EDIT,
        ],
    },
    {
        "code": "api_tester",
        "name": "接口测试工程师",
        "description": "接口自动化测试全套权限",
        "permissions": _BASE_READ
        + [
            API_MANAGE_VIEW,
            API_MANAGE_EDIT,
            API_CASE_VIEW,
            API_CASE_EDIT,
            API_CASE_EXECUTE,
            API_SUITE_VIEW,
            API_SUITE_EDIT,
            API_SUITE_EXECUTE,
            API_CRON_VIEW,
            API_CRON_EDIT,
            API_RECORD_VIEW,
            API_PLAN_VIEW,
            API_PLAN_EDIT,
            API_MOCK_VIEW,
            API_MOCK_EDIT,
            API_AUTH_VIEW,
            API_AUTH_EDIT,
            DATA_FACTORY_VIEW,
            DATA_FACTORY_EDIT,
        ],
    },
    {
        "code": "perf_tester",
        "name": "性能测试工程师",
        "description": "性能压测全套权限",
        "permissions": [
            PROJECT_VIEW,
            ENVIRONMENT_VIEW,
            PERF_SCENE_VIEW,
            PERF_SCENE_EDIT,
            PERF_SCENE_EXECUTE,
            PERF_CRON_VIEW,
            PERF_CRON_EDIT,
            PERF_WORKER_VIEW,
            PERF_RECORD_VIEW,
        ],
    },
    {
        "code": "ai_tester",
        "name": "AI测试工程师",
        "description": "AI 测试分析与执行（不含 AI 配置编辑）",
        "permissions": _BASE_READ
        + [
            AI_TEST_VIEW,
            AI_TEST_EXECUTE,
            AI_CONFIG_VIEW,
            DOCS_VIEW,
        ],
    },
    {
        "code": "viewer",
        "name": "只读观察员",
        "description": "各模块只读，适合审计与查看",
        "permissions": list(_VIEWER_PERMISSIONS),
    },
]
