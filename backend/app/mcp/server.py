"""BrickCore MCP Server（FastMCP）"""
from __future__ import annotations

import importlib
import inspect
from typing import Any, Callable

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

from app.core.platform.config import MCP_HTTP_PATH
from app.core.platform.edition import knowledge_feature_enabled, qa_eval_feature_enabled
from app.core.integration.mcp_config_service import get_mcp_runtime_config, resolve_public_base_url
from app.mcp import tools as mcp_tools
from app.mcp.auth import resolve_mcp_auth

mcp = FastMCP(
    name="BrickCore",
    instructions=(
        "BrickCore 一体化智能测试平台 MCP Server。"
        "提供项目上下文、需求用例、功能用例库、数据工厂、测试执行与失败分析能力。"
        "危险操作需先调用 preview_* 获取 confirm_token，再调用 confirm_* 执行。"
        "查询某项目全貌（环境、模块、需求、用例库规模）时，优先调用 get_project_overview(project_id)，"
        "不要连续多次调用 list_environments + list_modules + list_requirements。"
        "查看已生成功能用例列表时用 list_requirement_cases(requirement_id, project_id)。"
    ),
)

_MCP_AUTH_HEADER_NAMES = {"authorization", "x-mcp-api-key"}

MCP_TOOL_GROUPS: tuple[str, ...] = (
    "项目上下文",
    "需求用例",
    "功能用例库",
    "接口与 UI 测试",
    "执行记录与压测",
    "测试执行",
    "失败分析",
    "Skill",
    "日志与看板",
    "测试管理",
    "平台管理写操作",
)

MCP_DANGEROUS_OPS: tuple[str, ...] = (
    "preview_trigger_generate → confirm_trigger_generate",
    "preview_run_api_suite → confirm_run_api_suite",
    "preview_run_api_plan → confirm_run_api_plan",
    "preview_run_api_case → confirm_run_api_case",
    "preview_run_ui_case → confirm_run_ui_case",
    "preview_run_app_case → confirm_run_app_case",
    "preview_run_ui_task → confirm_run_ui_task",
    "preview_run_ui_suite → confirm_run_ui_suite",
    "preview_run_perf_scene → confirm_run_perf_scene",
    "preview_spawn_browser_lab → confirm_spawn_browser_lab",
    "preview_spawn_ui_agent → confirm_spawn_ui_agent",
    "preview_stop_browser_lab_task → confirm_stop_browser_lab_task",
    "preview_rerun_browser_lab_task → confirm_rerun_browser_lab_task",
    "preview_stop_ui_agent_job → confirm_stop_ui_agent_job",
    "preview_convert_browser_lab_to_ui_case → confirm_convert_browser_lab_to_ui_case",
    "preview_test_ai_config → confirm_test_ai_config",
    "preview_set_default_ai_config → confirm_set_default_ai_config",
    "preview_update_ai_config_api_key → confirm_update_ai_config_api_key",
    "preview_test_notification_config → confirm_test_notification_config",
    "preview_mark_inbox_read → confirm_mark_inbox_read",
    "preview_mark_inbox_all_read → confirm_mark_inbox_all_read",
    "preview_test_api_auth_config → confirm_test_api_auth_config",
    "preview_refresh_api_auth_token → confirm_refresh_api_auth_token",
    "preview_debug_api_definition → confirm_debug_api_definition",
    "preview_create_catalog → confirm_create_catalog",
    "preview_move_assets_to_catalog → confirm_move_assets_to_catalog",
    "preview_create_api_definition → confirm_create_api_definition",
    "preview_create_api_test_case → confirm_create_api_test_case",
    "preview_create_ui_case → confirm_create_ui_case",
    "preview_create_release → confirm_create_release",
    "preview_transition_release → confirm_transition_release",
    "preview_create_defect → confirm_create_defect",
    "preview_transition_defect → confirm_transition_defect",
    "preview_create_review → confirm_create_review",
    "preview_submit_review_decision → confirm_submit_review_decision",
    "preview_finalize_review → confirm_finalize_review",
    "preview_batch_env_vars → confirm_batch_env_vars",
    "preview_register_device → confirm_register_device",
    "preview_delete_device → confirm_delete_device",
    "preview_add_project_member → confirm_add_project_member",
    "preview_remove_project_member → confirm_remove_project_member",
    "preview_transfer_project_owner → confirm_transfer_project_owner",
    "preview_update_quality_gate_settings → confirm_update_quality_gate_settings",
    "preview_run_skill → confirm_run_skill",
    "analyze_failure（外部 MCP 直接调用；平台助手走 preview_analyze_failure → confirm_analyze_failure）",
)

_REGISTERED_TOOL_NAMES: list[str] = []


def _read_request_headers() -> dict[str, str]:
    return get_http_headers(include=_MCP_AUTH_HEADER_NAMES)


def _register(name: str, handler: Callable, description: str = "") -> None:
    """注册 MCP 工具：ctx 由服务端注入，不暴露给客户端 schema。"""
    sig = inspect.signature(handler)
    if "ctx" not in sig.parameters:
        raise ValueError(f"MCP tool {name} must accept ctx as first parameter")

    user_params = [p for pname, p in sig.parameters.items() if pname != "ctx"]

    async def tool_impl(**kwargs):
        ctx = await resolve_mcp_auth(_read_request_headers())
        return await handler(ctx, **kwargs)

    tool_impl.__name__ = name
    tool_impl.__doc__ = description or handler.__doc__ or name
    tool_impl.__module__ = handler.__module__
    tool_impl.__signature__ = inspect.Signature(parameters=user_params)
    handler_module = importlib.import_module(handler.__module__)
    type_hints = inspect.get_annotations(handler, eval_str=True, globals=vars(handler_module))
    tool_impl.__annotations__ = {
        k: v for k, v in type_hints.items() if k not in ("ctx", "return")
    }
    if "return" in type_hints:
        tool_impl.__annotations__["return"] = type_hints["return"]

    mcp.tool(name=name)(tool_impl)
    _REGISTERED_TOOL_NAMES.append(name)


# 项目上下文
_register("list_projects", mcp_tools.tool_list_projects, "列出可访问项目")
_register("get_project", mcp_tools.tool_get_project, "获取项目详情")
_register(
    "get_project_overview",
    mcp_tools.tool_get_project_overview,
    "获取项目全貌摘要（环境/模块/需求/用例库/最近失败，推荐用于项目总结）",
)
_register("list_environments", mcp_tools.tool_list_environments, "列出项目环境")
_register("list_online_devices", mcp_tools.tool_list_online_devices, "列出在线 Runner 设备（含 Web/App 能力）")
_register("list_modules", mcp_tools.tool_list_modules, "列出项目测试目录（统一 TestCatalog）")
_register(
    "list_api_definitions",
    mcp_tools.tool_list_api_definitions,
    "列出项目接口定义（方法、路径、描述、用例数）",
)
_register("get_api_definition", mcp_tools.tool_get_api_definition, "获取单个接口定义详情")
_register("list_api_categories", mcp_tools.tool_list_api_categories, "列出测试目录与接口/用例统计")
_register("list_api_test_cases", mcp_tools.tool_list_api_test_cases, "列出接口测试用例（关联接口方法/路径）")
_register("list_api_suites", mcp_tools.tool_list_api_suites, "列出项目接口测试套件")
_register("list_api_plans", mcp_tools.tool_list_api_plans, "列出项目接口测试计划")
_register("list_api_run_records", mcp_tools.tool_list_api_run_records, "列出接口执行记录（套件+计划）")
_register("list_api_cron_jobs", mcp_tools.tool_list_api_cron_jobs, "列出接口定时任务")
_register("list_mock_apis", mcp_tools.tool_list_mock_apis, "列出 Mock 接口配置")
_register("list_data_factory_datasources", mcp_tools.tool_list_data_factory_datasources, "列出数据工厂数据源（只读）")
_register("list_sql_templates", mcp_tools.tool_list_sql_templates, "列出数据工厂 SQL 模板（只读）")
_register("get_sql_template", mcp_tools.tool_get_sql_template, "获取 SQL 模板详情（只读）")
_register("query_datasource", mcp_tools.tool_query_datasource, "对数据工厂数据源只读查询（结果截断，禁止写）")
_register("list_ui_tasks", mcp_tools.tool_list_ui_tasks, "列出项目 UI 测试计划")
_register("list_ui_cases", mcp_tools.tool_list_ui_cases, "列出项目 Web UI 用例（摘要）")
_register("list_ui_run_records", mcp_tools.tool_list_ui_run_records, "列出 UI 测试计划执行记录（计划级，非单用例失败详情）")
_register("list_ui_suites", mcp_tools.tool_list_ui_suites, "列出 Web UI 测试套件")
_register("list_ui_cron_jobs", mcp_tools.tool_list_ui_cron_jobs, "列出 UI 定时任务")
_register("list_app_cases", mcp_tools.tool_list_app_cases, "列出 App 用例")
_register("list_app_suites", mcp_tools.tool_list_app_suites, "列出 App 套件")
_register("list_app_plans", mcp_tools.tool_list_app_plans, "列出 App 测试计划")
_register("list_app_run_records", mcp_tools.tool_list_app_run_records, "列出 App 执行记录")
_register("list_app_cron_jobs", mcp_tools.tool_list_app_cron_jobs, "列出 App 定时任务")
_register("list_perf_scenes", mcp_tools.tool_list_perf_scenes, "列出性能测试场景")
_register("list_perf_records", mcp_tools.tool_list_perf_records, "列出性能测试执行记录")
_register("list_perf_cron_jobs", mcp_tools.tool_list_perf_cron_jobs, "列出性能测试定时任务")
_register("list_perf_workers", mcp_tools.tool_list_perf_workers, "列出性能 Worker 节点")

# 需求用例
_register("list_requirements", mcp_tools.tool_list_requirements, "列出需求文档（含 case_count 与最近生成摘要）")
_register("get_requirement", mcp_tools.tool_get_requirement, "获取需求详情（含章节标题与最近任务）")
_register(
    "list_requirement_cases",
    mcp_tools.tool_list_requirement_cases,
    "列出需求工作区用例（默认摘要模式，不含 steps 全文）",
)
_register("get_generate_job", mcp_tools.tool_get_generate_job, "查询生成任务进度")
_register("get_requirement_latest_job", mcp_tools.tool_get_requirement_latest_job, "获取需求最近一次生成任务")
_register("preview_trigger_generate", mcp_tools.tool_preview_trigger_generate, "预览需求用例生成影响（获取 confirm_token）")
_register("confirm_trigger_generate", mcp_tools.tool_confirm_trigger_generate, "确认提交需求用例生成任务")

# 功能用例库
_register("search_functional_cases", mcp_tools.tool_search_functional_cases, "搜索功能用例库")
_register("get_functional_case", mcp_tools.tool_get_functional_case, "获取功能用例详情")
if knowledge_feature_enabled():
    _register(
        "search_test_knowledge",
        mcp_tools.tool_search_test_knowledge,
        "检索迭代测试资料库（历史 Bug、测试计划、迭代文档等）",
    )
    _register(
        "ask_test_knowledge",
        mcp_tools.tool_ask_test_knowledge,
        "资料库问答（retrieve 仅检索 / smart 智能回答）",
    )
    _register(
        "list_knowledge_folders",
        mcp_tools.tool_list_knowledge_folders,
        "列出迭代测试资料库文件夹",
    )

# 测试执行
_register("preview_run_api_suite", mcp_tools.tool_preview_run_api_suite, "预览接口套件执行影响")
_register("preview_run_api_plan", mcp_tools.tool_preview_run_api_plan, "预览接口测试计划执行影响")
_register("confirm_run_api_suite", mcp_tools.tool_confirm_run_api_suite, "确认异步执行接口套件")
_register("confirm_run_api_plan", mcp_tools.tool_confirm_run_api_plan, "确认异步执行接口测试计划")
_register("preview_run_api_case", mcp_tools.tool_preview_run_api_case, "预览单条接口用例执行")
_register("confirm_run_api_case", mcp_tools.tool_confirm_run_api_case, "确认执行单条接口用例")
_register("preview_run_ui_case", mcp_tools.tool_preview_run_ui_case, "预览单条 Web UI 用例执行")
_register("confirm_run_ui_case", mcp_tools.tool_confirm_run_ui_case, "确认执行单条 Web UI 用例")
_register("preview_run_app_case", mcp_tools.tool_preview_run_app_case, "预览单条 App 用例执行")
_register("confirm_run_app_case", mcp_tools.tool_confirm_run_app_case, "确认执行单条 App 用例")
_register("preview_run_app_suite", mcp_tools.tool_preview_run_app_suite, "预览 App 套件执行影响")
_register("confirm_run_app_suite", mcp_tools.tool_confirm_run_app_suite, "确认执行 App 套件")
_register("preview_run_app_plan", mcp_tools.tool_preview_run_app_plan, "预览 App 测试计划执行影响")
_register("confirm_run_app_plan", mcp_tools.tool_confirm_run_app_plan, "确认执行 App 测试计划")
_register("preview_run_ui_task", mcp_tools.tool_preview_run_ui_task, "预览 UI 测试计划执行影响")
_register("preview_run_ui_suite", mcp_tools.tool_preview_run_ui_suite, "预览 Web UI 套件执行影响")
_register("preview_run_perf_scene", mcp_tools.tool_preview_run_perf_scene, "预览压测场景执行影响")
_register("preview_spawn_browser_lab", mcp_tools.tool_preview_spawn_browser_lab, "预览派发智能浏览器任务")
_register("preview_spawn_ui_agent", mcp_tools.tool_preview_spawn_ui_agent, "预览派发 UI Agent 探索任务")
_register("preview_stop_browser_lab_task", mcp_tools.tool_preview_stop_browser_lab_task, "预览停止智能浏览器任务")
_register("preview_rerun_browser_lab_task", mcp_tools.tool_preview_rerun_browser_lab_task, "预览重跑智能浏览器任务")
_register("preview_stop_ui_agent_job", mcp_tools.tool_preview_stop_ui_agent_job, "预览停止 UI Agent 任务")
_register("preview_convert_browser_lab_to_ui_case", mcp_tools.tool_preview_convert_browser_lab_to_ui_case, "预览将智能浏览器任务转为 Web UI 用例")
_register("confirm_run_ui_task", mcp_tools.tool_confirm_run_ui_task, "确认执行 UI 测试计划")
_register("confirm_run_ui_suite", mcp_tools.tool_confirm_run_ui_suite, "确认执行 Web UI 套件")
_register("confirm_run_perf_scene", mcp_tools.tool_confirm_run_perf_scene, "确认启动压测场景")
_register("confirm_spawn_browser_lab", mcp_tools.tool_confirm_spawn_browser_lab, "确认派发智能浏览器任务")
_register("confirm_spawn_ui_agent", mcp_tools.tool_confirm_spawn_ui_agent, "确认派发 UI Agent 探索任务")
_register("confirm_stop_browser_lab_task", mcp_tools.tool_confirm_stop_browser_lab_task, "确认停止智能浏览器任务")
_register("confirm_rerun_browser_lab_task", mcp_tools.tool_confirm_rerun_browser_lab_task, "确认重跑智能浏览器任务")
_register("confirm_stop_ui_agent_job", mcp_tools.tool_confirm_stop_ui_agent_job, "确认停止 UI Agent 任务")
_register("confirm_convert_browser_lab_to_ui_case", mcp_tools.tool_confirm_convert_browser_lab_to_ui_case, "确认将智能浏览器任务转为 Web UI 用例")
_register("get_execution_record", mcp_tools.tool_get_execution_record, "查询执行记录摘要")

# Browser Lab / UI Agent 任务闭环（Wave A）
_register("list_browser_lab_tasks", mcp_tools.tool_list_browser_lab_tasks, "列出智能浏览器执行任务")
_register("get_browser_lab_task", mcp_tools.tool_get_browser_lab_task, "获取智能浏览器任务状态摘要")
_register("get_browser_lab_task_report", mcp_tools.tool_get_browser_lab_task_report, "获取智能浏览器报告摘要")
_register("list_browser_lab_cases", mcp_tools.tool_list_browser_lab_cases, "列出智能浏览器用例库")
_register("get_browser_lab_case", mcp_tools.tool_get_browser_lab_case, "获取智能浏览器用例详情")
_register("list_ui_agent_jobs", mcp_tools.tool_list_ui_agent_jobs, "列出 UI Agent 探索任务")
_register("get_ui_agent_job", mcp_tools.tool_get_ui_agent_job, "获取 UI Agent 任务状态摘要")
_register("get_ui_agent_job_report", mcp_tools.tool_get_ui_agent_job_report, "获取 UI Agent 步骤结果摘要")

# Wave B：AI 配置 / 站内信 / 通知
_register("list_ai_configs", mcp_tools.tool_list_ai_configs, "列出 LLM 配置（Key 脱敏）")
_register("get_ai_config", mcp_tools.tool_get_ai_config, "获取 LLM 配置详情（含 supports_vision）")
_register("list_ai_config_select_options", mcp_tools.tool_list_ai_config_select_options, "列出可用模型下拉选项")
_register("list_ai_scene_bindings", mcp_tools.tool_list_ai_scene_bindings, "列出 AI 场景模型绑定")
_register("preview_test_ai_config", mcp_tools.tool_preview_test_ai_config, "预览测试 LLM 连通性")
_register("confirm_test_ai_config", mcp_tools.tool_confirm_test_ai_config, "确认测试 LLM 连通性")
_register("get_ai_usage_logs", mcp_tools.tool_get_ai_usage_logs, "查询 AI 用量摘要与近期记录")
_register("list_inbox_messages", mcp_tools.tool_list_inbox_messages, "列出当前用户站内信")
_register("get_inbox_unread_count", mcp_tools.tool_get_inbox_unread_count, "获取站内信未读数")
_register("get_inbox_preferences", mcp_tools.tool_get_inbox_preferences, "获取站内信/通知偏好")
_register("preview_mark_inbox_read", mcp_tools.tool_preview_mark_inbox_read, "预览将站内信标为已读")
_register("confirm_mark_inbox_read", mcp_tools.tool_confirm_mark_inbox_read, "确认将站内信标为已读")
_register("preview_mark_inbox_all_read", mcp_tools.tool_preview_mark_inbox_all_read, "预览全部标为已读")
_register("confirm_mark_inbox_all_read", mcp_tools.tool_confirm_mark_inbox_all_read, "确认全部标为已读")
_register("list_notification_configs", mcp_tools.tool_list_notification_configs, "列出项目通知渠道配置（脱敏）")
_register("list_notification_logs", mcp_tools.tool_list_notification_logs, "列出通知推送记录")

# Wave C：鉴权 / 调试 / 执行详情
_register("list_api_auth_configs", mcp_tools.tool_list_api_auth_configs, "列出 Token 授权配置（脱敏）")
_register("get_api_auth_config", mcp_tools.tool_get_api_auth_config, "获取授权配置详情（脱敏）")
_register("preview_test_api_auth_config", mcp_tools.tool_preview_test_api_auth_config, "预览调试授权配置")
_register("confirm_test_api_auth_config", mcp_tools.tool_confirm_test_api_auth_config, "确认调试授权配置")
_register("preview_refresh_api_auth_token", mcp_tools.tool_preview_refresh_api_auth_token, "预览刷新授权 Token")
_register("confirm_refresh_api_auth_token", mcp_tools.tool_confirm_refresh_api_auth_token, "确认刷新授权 Token")
_register("preview_debug_api_definition", mcp_tools.tool_preview_debug_api_definition, "预览单次接口调试")
_register("confirm_debug_api_definition", mcp_tools.tool_confirm_debug_api_definition, "确认单次接口调试")
_register("debug_api_definition", mcp_tools.tool_debug_api_definition, "接口调试入口（等同 preview，须再 confirm）")
_register("get_api_case_execution_detail", mcp_tools.tool_get_api_case_execution_detail, "获取接口用例执行详情摘要")
_register("get_ui_case_execution_detail", mcp_tools.tool_get_ui_case_execution_detail, "获取 Web UI 用例执行详情摘要")
_register("get_app_case_execution_detail", mcp_tools.tool_get_app_case_execution_detail, "获取 App 用例执行详情摘要")
_register("get_perf_record_detail", mcp_tools.tool_get_perf_record_detail, "获取压测执行记录摘要")
_register("get_execution_report", mcp_tools.tool_get_execution_report, "获取执行报告链接与摘要")

# Wave E：项目设置 / 环境 / 设备 / 成员（只读）
_register("get_project_settings_overview", mcp_tools.tool_get_project_settings_overview, "获取项目设置概览（含调试超时）")
_register("get_project_execution_settings", mcp_tools.tool_get_project_execution_settings, "获取项目执行设置与超时")
_register("get_environment_detail", mcp_tools.tool_get_environment_detail, "获取环境详情（变量脱敏，含 UI 超时倍率）")
_register("list_devices", mcp_tools.tool_list_devices, "列出 Runner 设备与在线状态")
_register("get_device_detail", mcp_tools.tool_get_device_detail, "获取 Runner 设备详情（在线/心跳/引擎）")
_register("list_project_members", mcp_tools.tool_list_project_members, "列出项目成员与角色")

# Wave D：目录定位 + 显式创建
_register("get_catalog_detail", mcp_tools.tool_get_catalog_detail, "获取目录详情与资产数量")
_register("list_catalog_assets", mcp_tools.tool_list_catalog_assets, "列出目录下的资产摘要")
_register("preview_create_catalog", mcp_tools.tool_preview_create_catalog, "预览创建测试目录")
_register("confirm_create_catalog", mcp_tools.tool_confirm_create_catalog, "确认创建测试目录")
_register("preview_move_assets_to_catalog", mcp_tools.tool_preview_move_assets_to_catalog, "预览将资产移入目录")
_register("confirm_move_assets_to_catalog", mcp_tools.tool_confirm_move_assets_to_catalog, "确认将资产移入目录")
_register("preview_create_api_definition", mcp_tools.tool_preview_create_api_definition, "预览创建接口定义")
_register("confirm_create_api_definition", mcp_tools.tool_confirm_create_api_definition, "确认创建接口定义")
_register("preview_create_api_test_case", mcp_tools.tool_preview_create_api_test_case, "预览创建接口用例")
_register("confirm_create_api_test_case", mcp_tools.tool_confirm_create_api_test_case, "确认创建接口用例")
_register("preview_create_ui_case", mcp_tools.tool_preview_create_ui_case, "预览创建 Web UI 用例")
_register("confirm_create_ui_case", mcp_tools.tool_confirm_create_ui_case, "确认创建 Web UI 用例")

# Wave F：日志 / 看板 / 搜索 / 测试管理
_register("list_operation_logs", mcp_tools.tool_list_operation_logs, "列出平台操作日志（不含请求体）")
_register("list_assistant_traces", mcp_tools.tool_list_assistant_traces, "列出小测回合追踪（不含 Prompt）")
_register("get_dashboard_summary", mcp_tools.tool_get_dashboard_summary, "获取首页看板摘要")
_register("search_project_assets", mcp_tools.tool_search_project_assets, "项目内资产关键词搜索")
_register("list_releases", mcp_tools.tool_list_releases, "列出发布版本")
_register("get_release", mcp_tools.tool_get_release, "获取发布版本详情")
_register("preview_create_release", mcp_tools.tool_preview_create_release, "预览创建发布版本")
_register("confirm_create_release", mcp_tools.tool_confirm_create_release, "确认创建发布版本")
_register("preview_transition_release", mcp_tools.tool_preview_transition_release, "预览发布版本状态流转")
_register("confirm_transition_release", mcp_tools.tool_confirm_transition_release, "确认发布版本状态流转")
_register("list_defects", mcp_tools.tool_list_defects, "列出缺陷")
_register("get_defect", mcp_tools.tool_get_defect, "获取缺陷详情")
_register("preview_create_defect", mcp_tools.tool_preview_create_defect, "预览创建缺陷")
_register("confirm_create_defect", mcp_tools.tool_confirm_create_defect, "确认创建缺陷")
_register("preview_transition_defect", mcp_tools.tool_preview_transition_defect, "预览缺陷状态流转")
_register("confirm_transition_defect", mcp_tools.tool_confirm_transition_defect, "确认缺陷状态流转")
_register("list_reviews", mcp_tools.tool_list_reviews, "列出用例评审批次")
_register("get_review", mcp_tools.tool_get_review, "获取用例评审详情")
_register("preview_create_review", mcp_tools.tool_preview_create_review, "预览创建用例评审批次")
_register("confirm_create_review", mcp_tools.tool_confirm_create_review, "确认创建用例评审批次")
_register("preview_submit_review_decision", mcp_tools.tool_preview_submit_review_decision, "预览提交评审条目结论")
_register("confirm_submit_review_decision", mcp_tools.tool_confirm_submit_review_decision, "确认提交评审条目结论")
_register("preview_finalize_review", mcp_tools.tool_preview_finalize_review, "预览评审批次最终定版")
_register("confirm_finalize_review", mcp_tools.tool_confirm_finalize_review, "确认评审批次最终定版")

# 管理写操作
_register("preview_set_default_ai_config", mcp_tools.tool_preview_set_default_ai_config, "预览设为默认 LLM 配置")
_register("confirm_set_default_ai_config", mcp_tools.tool_confirm_set_default_ai_config, "确认设为默认 LLM 配置")
_register("preview_update_ai_config_api_key", mcp_tools.tool_preview_update_ai_config_api_key, "预览更新 LLM API Key")
_register("confirm_update_ai_config_api_key", mcp_tools.tool_confirm_update_ai_config_api_key, "确认更新 LLM API Key")
_register("preview_test_notification_config", mcp_tools.tool_preview_test_notification_config, "预览发送测试通知")
_register("confirm_test_notification_config", mcp_tools.tool_confirm_test_notification_config, "确认发送测试通知")
_register("preview_batch_env_vars", mcp_tools.tool_preview_batch_env_vars, "预览跨环境批量改变量")
_register("confirm_batch_env_vars", mcp_tools.tool_confirm_batch_env_vars, "确认跨环境批量改变量")
_register("preview_register_device", mcp_tools.tool_preview_register_device, "预览注册 Runner 设备")
_register("confirm_register_device", mcp_tools.tool_confirm_register_device, "确认注册 Runner 设备")
_register("preview_delete_device", mcp_tools.tool_preview_delete_device, "预览删除 Runner 设备")
_register("confirm_delete_device", mcp_tools.tool_confirm_delete_device, "确认删除 Runner 设备")
_register("preview_add_project_member", mcp_tools.tool_preview_add_project_member, "预览添加项目成员")
_register("confirm_add_project_member", mcp_tools.tool_confirm_add_project_member, "确认添加项目成员")
_register("preview_remove_project_member", mcp_tools.tool_preview_remove_project_member, "预览移除项目成员")
_register("confirm_remove_project_member", mcp_tools.tool_confirm_remove_project_member, "确认移除项目成员")
_register("preview_transfer_project_owner", mcp_tools.tool_preview_transfer_project_owner, "预览转让项目负责人")
_register("confirm_transfer_project_owner", mcp_tools.tool_confirm_transfer_project_owner, "确认转让项目负责人")
_register("get_quality_gate_settings", mcp_tools.tool_get_quality_gate_settings, "获取质量门禁阈值")
_register("preview_update_quality_gate_settings", mcp_tools.tool_preview_update_quality_gate_settings, "预览更新质量门禁阈值")
_register("confirm_update_quality_gate_settings", mcp_tools.tool_confirm_update_quality_gate_settings, "确认更新质量门禁阈值")

# Skill（W4）
_register("list_skills", mcp_tools.tool_list_skills, "列出内置 Skill（无包返回空列表）")
_register("preview_run_skill", mcp_tools.tool_preview_run_skill, "预览运行生成类 Skill（获取 confirm_token）")
_register("confirm_run_skill", mcp_tools.tool_confirm_run_skill, "确认执行 Skill 写操作")

# 失败分析
_register(
    "get_case_latest_failure",
    mcp_tools.tool_get_case_latest_failure,
    "按用例名/ID 取最新失败的轻量错误摘要",
)
_register("analyze_failure", mcp_tools.tool_analyze_failure, "AI 分析单条失败记录")
_register("list_recent_failures", mcp_tools.tool_list_recent_failures, "列出最近失败用例")


@mcp.tool(name="get_server_info")
async def get_server_info() -> dict[str, Any]:
    """获取 MCP Server 基本信息与认证状态（无需强权限）"""
    runtime = await get_mcp_runtime_config()
    authed = False
    username = ""
    try:
        ctx = await resolve_mcp_auth(_read_request_headers())
        authed = True
        username = ctx.username
    except ValueError:
        pass
    endpoint = f"{resolve_public_base_url(runtime)}{MCP_HTTP_PATH}" if resolve_public_base_url(runtime) else MCP_HTTP_PATH
    return {
        "name": "BrickCore MCP Server",
        "enabled": runtime.enabled,
        "config_source": runtime.source,
        "endpoint": endpoint,
        "authenticated": authed,
        "username": username,
        "transport": "streamable-http",
        "tool_groups": list(MCP_TOOL_GROUPS),
        "tool_count": len(_REGISTERED_TOOL_NAMES) + 1,
        "dangerous_ops": list(MCP_DANGEROUS_OPS),
    }


_mcp_asgi_app = None


def get_mcp_asgi_app():
    """返回可 mount 到 FastAPI 的 MCP ASGI 应用（单例，lifespan 需由主应用托管）"""
    global _mcp_asgi_app
    if _mcp_asgi_app is None:
        _mcp_asgi_app = mcp.http_app(path="/", transport="streamable-http")
    return _mcp_asgi_app


def get_registered_tool_count() -> int:
    """已注册 MCP 工具数（含 get_server_info）。"""
    return len(_REGISTERED_TOOL_NAMES) + 1


def build_client_config(base_url: str, api_key: str = "") -> dict[str, Any]:
    """生成 Claude Desktop / Codex 风格的 MCP 客户端配置片段"""
    url = f"{base_url.rstrip('/')}{MCP_HTTP_PATH}"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return {
        "mcpServers": {
            "brickcore": {
                "url": url,
                "headers": headers,
            }
        }
    }
