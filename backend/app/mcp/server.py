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
)

MCP_DANGEROUS_OPS: tuple[str, ...] = (
    "preview_trigger_generate → confirm_trigger_generate",
    "preview_run_api_suite → confirm_run_api_suite",
    "preview_run_api_plan → confirm_run_api_plan",
    "preview_run_api_case → confirm_run_api_case",
    "preview_run_qa_eval → confirm_run_qa_eval",
    "preview_run_ui_case → confirm_run_ui_case",
    "preview_run_app_case → confirm_run_app_case",
    "preview_run_ui_task → confirm_run_ui_task",
    "preview_run_ui_suite → confirm_run_ui_suite",
    "preview_run_perf_scene → confirm_run_perf_scene",
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
_register("list_ui_tasks", mcp_tools.tool_list_ui_tasks, "列出项目 UI 测试计划")
_register("list_ui_cases", mcp_tools.tool_list_ui_cases, "列出项目 Web UI 用例（摘要）")
_register("list_ui_run_records", mcp_tools.tool_list_ui_run_records, "列出 UI 测试计划执行记录")
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
if qa_eval_feature_enabled():
    _register("list_qa_eval_sets", mcp_tools.tool_list_qa_eval_sets, "列出问答准确性评测集")
    _register("get_qa_eval_run", mcp_tools.tool_get_qa_eval_run, "查询问答评测跑批进度")
    _register("preview_run_qa_eval", mcp_tools.tool_preview_run_qa_eval, "预览问答准确性评测跑批")
    _register("confirm_run_qa_eval", mcp_tools.tool_confirm_run_qa_eval, "确认提交问答准确性评测")
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
_register("confirm_run_ui_task", mcp_tools.tool_confirm_run_ui_task, "确认执行 UI 测试计划")
_register("confirm_run_ui_suite", mcp_tools.tool_confirm_run_ui_suite, "确认执行 Web UI 套件")
_register("confirm_run_perf_scene", mcp_tools.tool_confirm_run_perf_scene, "确认启动压测场景")
_register("get_execution_record", mcp_tools.tool_get_execution_record, "查询执行记录摘要")

# 失败分析
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
