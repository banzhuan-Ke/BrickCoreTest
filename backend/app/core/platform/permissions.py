"""
权限常量定义
"""

# 项目管理
PROJECT_VIEW = "project:view"
PROJECT_EDIT = "project:edit"

# 环境配置
ENVIRONMENT_VIEW = "environment:view"
ENVIRONMENT_EDIT = "environment:edit"

# 模块管理
MODULE_VIEW = "module:view"
MODULE_EDIT = "module:edit"

# UI 用例
UI_CASE_VIEW = "ui_case:view"
UI_CASE_EDIT = "ui_case:edit"
UI_CASE_EXECUTE = "ui_case:execute"

# UI 套件
UI_SUITE_VIEW = "ui_suite:view"
UI_SUITE_EDIT = "ui_suite:edit"
UI_SUITE_EXECUTE = "ui_suite:execute"

# 执行计划
UI_TASK_VIEW = "ui_task:view"
UI_TASK_EDIT = "ui_task:edit"
UI_TASK_EXECUTE = "ui_task:execute"

# UI 定时任务
UI_CRON_VIEW = "ui_cron:view"
UI_CRON_EDIT = "ui_cron:edit"

# UI 执行记录
UI_RECORD_VIEW = "ui_record:view"
UI_RECORD_EDIT = "ui_record:edit"

# App 自动化
APP_CASE_VIEW = "app_case:view"
APP_CASE_EDIT = "app_case:edit"
APP_CASE_EXECUTE = "app_case:execute"
APP_SUITE_VIEW = "app_suite:view"
APP_SUITE_EDIT = "app_suite:edit"
APP_SUITE_EXECUTE = "app_suite:execute"
APP_PLAN_VIEW = "app_plan:view"
APP_PLAN_EDIT = "app_plan:edit"
APP_PLAN_EXECUTE = "app_plan:execute"
APP_RECORD_VIEW = "app_record:view"
APP_ELEMENT_VIEW = "app_element:view"
APP_ELEMENT_EDIT = "app_element:edit"

# 设备管理
DEVICE_VIEW = "device:view"
DEVICE_EDIT = "device:edit"

# 接口管理
API_MANAGE_VIEW = "api_manage:view"
API_MANAGE_EDIT = "api_manage:edit"

# 接口用例
API_CASE_VIEW = "api_case:view"
API_CASE_EDIT = "api_case:edit"
API_CASE_EXECUTE = "api_case:execute"

# 接口套件
API_SUITE_VIEW = "api_suite:view"
API_SUITE_EDIT = "api_suite:edit"
API_SUITE_EXECUTE = "api_suite:execute"

# 接口定时
API_CRON_VIEW = "api_cron:view"
API_CRON_EDIT = "api_cron:edit"

# 接口记录
API_RECORD_VIEW = "api_record:view"

# 接口测试计划
API_PLAN_VIEW = "api_plan:view"
API_PLAN_EDIT = "api_plan:edit"

# Mock 服务
API_MOCK_VIEW = "api_mock:view"
API_MOCK_EDIT = "api_mock:edit"

# API Token 授权
API_AUTH_VIEW = "api_auth:view"
API_AUTH_EDIT = "api_auth:edit"

# 数据工厂
DATA_FACTORY_VIEW = "data_factory:view"
DATA_FACTORY_EDIT = "data_factory:edit"

# 用户管理
USER_VIEW = "user:view"
USER_EDIT = "user:edit"

# 角色管理
ROLE_VIEW = "role:view"
ROLE_EDIT = "role:edit"

# 操作日志
OPERATION_LOG_VIEW = "operation_log:view"
OPERATION_LOG_EDIT = "operation_log:edit"

# 项目设置（自愈 / 录制 / 失败分析 / 功能用例等项目级策略）
PROJECT_SETTINGS_VIEW = "project_settings:view"
PROJECT_SETTINGS_EDIT = "project_settings:edit"

# 通知配置（项目级渠道；SMTP 仍为平台级）
NOTIFICATION_CONFIG_VIEW = "notification_config:view"
NOTIFICATION_CONFIG_EDIT = "notification_config:edit"

# SMTP 配置
SMTP_CONFIG_VIEW = "smtp_config:view"
SMTP_CONFIG_EDIT = "smtp_config:edit"

# MCP 配置
MCP_CONFIG_VIEW = "mcp_config:view"
MCP_CONFIG_EDIT = "mcp_config:edit"

# 登录页配置
LOGIN_PAGE_CONFIG_VIEW = "login_page_config:view"
LOGIN_PAGE_CONFIG_EDIT = "login_page_config:edit"

# 平台全局设置
PLATFORM_SETTINGS_VIEW = "platform_settings:view"
PLATFORM_SETTINGS_EDIT = "platform_settings:edit"

# 推送记录
NOTIFICATION_LOG_VIEW = "notification_log:view"
NOTIFICATION_LOG_EDIT = "notification_log:edit"

# 文档中心
DOCS_VIEW = "docs:view"
DOCS_EDIT = "docs:edit"

# 性能测试
PERF_SCENE_VIEW = "perf_scene:view"
PERF_SCENE_EDIT = "perf_scene:edit"
PERF_SCENE_EXECUTE = "perf_scene:execute"
PERF_RECORD_VIEW = "perf_record:view"
PERF_CRON_VIEW = "perf_cron:view"
PERF_CRON_EDIT = "perf_cron:edit"
PERF_WORKER_VIEW = "perf_worker:view"

# AI 测试
AI_TEST_VIEW = "ai_test:view"
AI_TEST_EXECUTE = "ai_test:execute"
AI_CONFIG_VIEW = "ai_config:view"
AI_CONFIG_EDIT = "ai_config:edit"

# 迭代资料库
KNOWLEDGE_VIEW = "knowledge:view"
KNOWLEDGE_EDIT = "knowledge:edit"
KNOWLEDGE_EXECUTE = "knowledge:execute"

# 测试管理（版本交付闭环）
TEST_RELEASE_VIEW = "test_release:view"
TEST_RELEASE_EDIT = "test_release:edit"
TEST_REVIEW_VIEW = "test_review:view"
TEST_REVIEW_SUBMIT = "test_review:submit"
TEST_REVIEW_MANAGE = "test_review:manage"
TEST_PLAN_VIEW = "test_plan:view"
TEST_PLAN_EDIT = "test_plan:edit"
TEST_PLAN_RUN = "test_plan:run"
TEST_MANUAL_EXECUTE = "test_manual:execute"
TEST_DEFECT_VIEW = "test_defect:view"
TEST_DEFECT_EDIT = "test_defect:edit"
TEST_QUALITY_VIEW = "test_quality:view"
TEST_QUALITY_APPROVE_EXCEPTION = "test_quality:approve_exception"


# 按模块分组，供前端渲染权限树使用
PERMISSIONS = [
    {
        "label": "项目配置",
        "children": [
            {"label": "项目管理-查看", "value": PROJECT_VIEW},
            {"label": "项目管理-编辑", "value": PROJECT_EDIT},
            {"label": "项目设置-查看", "value": PROJECT_SETTINGS_VIEW},
            {"label": "项目设置-编辑", "value": PROJECT_SETTINGS_EDIT},
            {"label": "环境配置-查看", "value": ENVIRONMENT_VIEW},
            {"label": "环境配置-编辑", "value": ENVIRONMENT_EDIT},
            {"label": "测试目录-查看", "value": MODULE_VIEW},
            {"label": "测试目录-编辑", "value": MODULE_EDIT},
            {"label": "通知渠道-查看", "value": NOTIFICATION_CONFIG_VIEW},
            {"label": "通知渠道-编辑", "value": NOTIFICATION_CONFIG_EDIT},
        ]
    },
    {
        "label": "Web 自动化",
        "children": [
            {"label": "用例管理-查看", "value": UI_CASE_VIEW},
            {"label": "用例管理-编辑", "value": UI_CASE_EDIT},
            {"label": "用例管理-执行", "value": UI_CASE_EXECUTE},
            {"label": "套件管理-查看", "value": UI_SUITE_VIEW},
            {"label": "套件管理-编辑", "value": UI_SUITE_EDIT},
            {"label": "套件管理-执行", "value": UI_SUITE_EXECUTE},
            {"label": "执行计划-查看", "value": UI_TASK_VIEW},
            {"label": "执行计划-编辑", "value": UI_TASK_EDIT},
            {"label": "执行计划-执行", "value": UI_TASK_EXECUTE},
            {"label": "定时任务-查看", "value": UI_CRON_VIEW},
            {"label": "定时任务-编辑", "value": UI_CRON_EDIT},
            {"label": "执行记录-查看", "value": UI_RECORD_VIEW},
            {"label": "执行记录-编辑", "value": UI_RECORD_EDIT},
            {"label": "设备管理-查看", "value": DEVICE_VIEW},
            {"label": "设备管理-编辑", "value": DEVICE_EDIT},
        ]
    },
    {
        "label": "App 自动化",
        "children": [
            {"label": "App用例-查看", "value": APP_CASE_VIEW},
            {"label": "App用例-编辑", "value": APP_CASE_EDIT},
            {"label": "App用例-执行", "value": APP_CASE_EXECUTE},
            {"label": "App套件-查看", "value": APP_SUITE_VIEW},
            {"label": "App套件-编辑", "value": APP_SUITE_EDIT},
            {"label": "App套件-执行", "value": APP_SUITE_EXECUTE},
            {"label": "App计划-查看", "value": APP_PLAN_VIEW},
            {"label": "App计划-编辑", "value": APP_PLAN_EDIT},
            {"label": "App计划-执行", "value": APP_PLAN_EXECUTE},
            {"label": "App记录-查看", "value": APP_RECORD_VIEW},
            {"label": "App元素库-查看", "value": APP_ELEMENT_VIEW},
            {"label": "App元素库-编辑", "value": APP_ELEMENT_EDIT},
        ],
    },
    {
        "label": "接口自动化",
        "children": [
            {"label": "接口管理-查看", "value": API_MANAGE_VIEW},
            {"label": "接口管理-编辑", "value": API_MANAGE_EDIT},
            {"label": "接口用例-查看", "value": API_CASE_VIEW},
            {"label": "接口用例-编辑", "value": API_CASE_EDIT},
            {"label": "接口用例-执行", "value": API_CASE_EXECUTE},
            {"label": "接口套件-查看", "value": API_SUITE_VIEW},
            {"label": "接口套件-编辑", "value": API_SUITE_EDIT},
            {"label": "接口套件-执行", "value": API_SUITE_EXECUTE},
            {"label": "接口定时-查看", "value": API_CRON_VIEW},
            {"label": "接口定时-编辑", "value": API_CRON_EDIT},
            {"label": "接口记录-查看", "value": API_RECORD_VIEW},
            {"label": "测试计划-查看", "value": API_PLAN_VIEW},
            {"label": "测试计划-编辑", "value": API_PLAN_EDIT},
            {"label": "Mock服务-查看", "value": API_MOCK_VIEW},
            {"label": "Mock服务-编辑", "value": API_MOCK_EDIT},
            {"label": "Token授权-查看", "value": API_AUTH_VIEW},
            {"label": "Token授权-编辑", "value": API_AUTH_EDIT},
            {"label": "数据工厂-查看", "value": DATA_FACTORY_VIEW},
            {"label": "数据工厂-编辑", "value": DATA_FACTORY_EDIT},
        ]
    },
    {
        "label": "性能测试",
        "children": [
            {"label": "场景管理-查看", "value": PERF_SCENE_VIEW},
            {"label": "场景管理-编辑", "value": PERF_SCENE_EDIT},
            {"label": "场景管理-执行", "value": PERF_SCENE_EXECUTE},
            {"label": "定时压测-查看", "value": PERF_CRON_VIEW},
            {"label": "定时压测-编辑", "value": PERF_CRON_EDIT},
            {"label": "Worker节点-查看", "value": PERF_WORKER_VIEW},
            {"label": "执行记录-查看", "value": PERF_RECORD_VIEW},
        ]
    },
    {
        "label": "AI 测试",
        "children": [
            {"label": "AI 测试-查看", "value": AI_TEST_VIEW},
            {"label": "AI 测试-执行", "value": AI_TEST_EXECUTE},
            {"label": "AI 模型配置-查看", "value": AI_CONFIG_VIEW},
            {"label": "AI 模型配置-编辑", "value": AI_CONFIG_EDIT},
        ]
    },
    {
        "label": "迭代资料库",
        "children": [
            {"label": "资料库-查看", "value": KNOWLEDGE_VIEW},
            {"label": "资料库-编辑", "value": KNOWLEDGE_EDIT},
            {"label": "资料库-执行", "value": KNOWLEDGE_EXECUTE},
        ]
    },
    {
        "label": "测试管理",
        "children": [
            {"label": "版本管理-查看", "value": TEST_RELEASE_VIEW},
            {"label": "版本管理-编辑", "value": TEST_RELEASE_EDIT},
            {"label": "用例评审-查看", "value": TEST_REVIEW_VIEW},
            {"label": "用例评审-提交结论", "value": TEST_REVIEW_SUBMIT},
            {"label": "用例评审-管理", "value": TEST_REVIEW_MANAGE},
            {"label": "测试计划-查看", "value": TEST_PLAN_VIEW},
            {"label": "测试计划-编辑", "value": TEST_PLAN_EDIT},
            {"label": "测试计划-运行", "value": TEST_PLAN_RUN},
            {"label": "手工执行", "value": TEST_MANUAL_EXECUTE},
            {"label": "缺陷-查看", "value": TEST_DEFECT_VIEW},
            {"label": "缺陷-编辑", "value": TEST_DEFECT_EDIT},
            {"label": "质量门禁-查看", "value": TEST_QUALITY_VIEW},
            {"label": "质量门禁-批准豁免", "value": TEST_QUALITY_APPROVE_EXCEPTION},
        ]
    },
    {
        "label": "系统管理",
        "children": [
            {"label": "用户管理-查看", "value": USER_VIEW},
            {"label": "用户管理-编辑", "value": USER_EDIT},
            {"label": "角色管理-查看", "value": ROLE_VIEW},
            {"label": "角色管理-编辑", "value": ROLE_EDIT},
            {"label": "操作日志-查看", "value": OPERATION_LOG_VIEW},
            {"label": "操作日志-编辑", "value": OPERATION_LOG_EDIT},
            {"label": "SMTP配置-查看", "value": SMTP_CONFIG_VIEW},
            {"label": "SMTP配置-编辑", "value": SMTP_CONFIG_EDIT},
            {"label": "MCP配置-查看", "value": MCP_CONFIG_VIEW},
            {"label": "MCP配置-编辑", "value": MCP_CONFIG_EDIT},
            {"label": "登录页配置-查看", "value": LOGIN_PAGE_CONFIG_VIEW},
            {"label": "登录页配置-编辑", "value": LOGIN_PAGE_CONFIG_EDIT},
            {"label": "平台设置-查看", "value": PLATFORM_SETTINGS_VIEW},
            {"label": "平台设置-编辑", "value": PLATFORM_SETTINGS_EDIT},
            {"label": "推送记录-查看", "value": NOTIFICATION_LOG_VIEW},
            {"label": "推送记录-编辑", "value": NOTIFICATION_LOG_EDIT},
            {"label": "文档中心-查看", "value": DOCS_VIEW},
            {"label": "文档中心-编辑", "value": DOCS_EDIT},
        ]
    },
]

# 全部权限码列表
ALL_PERMISSIONS = [
    PROJECT_VIEW, PROJECT_EDIT,
    PROJECT_SETTINGS_VIEW, PROJECT_SETTINGS_EDIT,
    ENVIRONMENT_VIEW, ENVIRONMENT_EDIT,
    MODULE_VIEW, MODULE_EDIT,
    UI_CASE_VIEW, UI_CASE_EDIT, UI_CASE_EXECUTE,
    UI_SUITE_VIEW, UI_SUITE_EDIT, UI_SUITE_EXECUTE,
    UI_TASK_VIEW, UI_TASK_EDIT, UI_TASK_EXECUTE,
    UI_CRON_VIEW, UI_CRON_EDIT,
    UI_RECORD_VIEW, UI_RECORD_EDIT,
    APP_CASE_VIEW, APP_CASE_EDIT, APP_CASE_EXECUTE,
    APP_SUITE_VIEW, APP_SUITE_EDIT, APP_SUITE_EXECUTE,
    APP_PLAN_VIEW, APP_PLAN_EDIT, APP_PLAN_EXECUTE,
    APP_RECORD_VIEW,
    APP_ELEMENT_VIEW, APP_ELEMENT_EDIT,
    DEVICE_VIEW, DEVICE_EDIT,
    API_MANAGE_VIEW, API_MANAGE_EDIT,
    API_CASE_VIEW, API_CASE_EDIT, API_CASE_EXECUTE,
    API_SUITE_VIEW, API_SUITE_EDIT, API_SUITE_EXECUTE,
    API_CRON_VIEW, API_CRON_EDIT,
    API_RECORD_VIEW,
    API_PLAN_VIEW, API_PLAN_EDIT,
    API_MOCK_VIEW, API_MOCK_EDIT,
    API_AUTH_VIEW, API_AUTH_EDIT,
    DATA_FACTORY_VIEW, DATA_FACTORY_EDIT,
    USER_VIEW, USER_EDIT,
    ROLE_VIEW, ROLE_EDIT,
    OPERATION_LOG_VIEW, OPERATION_LOG_EDIT,
    NOTIFICATION_CONFIG_VIEW, NOTIFICATION_CONFIG_EDIT,
    SMTP_CONFIG_VIEW, SMTP_CONFIG_EDIT,
    MCP_CONFIG_VIEW, MCP_CONFIG_EDIT,
    LOGIN_PAGE_CONFIG_VIEW, LOGIN_PAGE_CONFIG_EDIT,
    PLATFORM_SETTINGS_VIEW, PLATFORM_SETTINGS_EDIT,
    NOTIFICATION_LOG_VIEW, NOTIFICATION_LOG_EDIT,
    DOCS_VIEW, DOCS_EDIT,
    PERF_SCENE_VIEW, PERF_SCENE_EDIT, PERF_SCENE_EXECUTE,
    PERF_CRON_VIEW, PERF_CRON_EDIT,
    PERF_WORKER_VIEW,
    PERF_RECORD_VIEW,
    AI_TEST_VIEW, AI_TEST_EXECUTE,
    AI_CONFIG_VIEW, AI_CONFIG_EDIT,
    KNOWLEDGE_VIEW, KNOWLEDGE_EDIT, KNOWLEDGE_EXECUTE,
    TEST_RELEASE_VIEW, TEST_RELEASE_EDIT,
    TEST_REVIEW_VIEW, TEST_REVIEW_SUBMIT, TEST_REVIEW_MANAGE,
    TEST_PLAN_VIEW, TEST_PLAN_EDIT, TEST_PLAN_RUN,
    TEST_MANUAL_EXECUTE,
    TEST_DEFECT_VIEW, TEST_DEFECT_EDIT,
    TEST_QUALITY_VIEW, TEST_QUALITY_APPROVE_EXCEPTION,
]

async def get_user_permissions(user) -> list:
    """获取用户合并后的权限列表。无角色返回空列表。

    ``user`` 可为 User 实例或 user_id(int)。一律按 ID 查角色，避免
    ``user.roles`` / prefetch M2M 在高并发下 KeyError / 实例缺字段。
    """
    if user is None:
        return []
    user_id = user if isinstance(user, int) else getattr(user, "id", None)
    if user_id is None:
        return []
    from app.models.sys import Role

    rows = await Role.filter(users__id=user_id, is_del=False).values("permissions")
    perms: set[str] = set()
    for row in rows:
        perms.update(row.get("permissions") or [])
    return sorted(perms)
