"""平台内 AI 助手 — 工具注册（复用 MCP tools 实现）"""
from __future__ import annotations

import json
from typing import Any, Callable, Awaitable

from fastapi import HTTPException

from app.core.platform.edition import (
    KNOWLEDGE_TOOL_NAMES,
    QA_EVAL_TOOL_NAMES,
    knowledge_feature_enabled,
    qa_eval_feature_enabled,
)
from app.core.integration.mcp_confirm import consume_confirm_token, create_confirm_token
from app.mcp.auth import McpAuthContext

ToolHandler = Callable[..., Awaitable[dict[str, Any]]]

READONLY_TOOL_NAMES: tuple[str, ...] = (
    "list_projects",
    "get_project",
    "get_project_overview",
    "list_environments",
    "list_online_devices",
    "list_modules",
    "list_api_definitions",
    "get_api_definition",
    "list_api_categories",
    "list_api_test_cases",
    "list_api_suites",
    "list_api_plans",
    "list_api_run_records",
    "list_api_cron_jobs",
    "list_mock_apis",
    "list_data_factory_datasources",
    "list_sql_templates",
    "get_sql_template",
    "list_ui_tasks",
    "list_ui_cases",
    "list_ui_run_records",
    "list_ui_suites",
    "list_ui_cron_jobs",
    "list_app_cases",
    "list_app_suites",
    "list_app_plans",
    "list_app_run_records",
    "list_app_cron_jobs",
    "list_perf_scenes",
    "list_perf_records",
    "list_perf_cron_jobs",
    "list_perf_workers",
    "list_requirements",
    "get_requirement",
    "list_requirement_cases",
    "search_functional_cases",
    "get_functional_case",
    "search_test_knowledge",
    "ask_test_knowledge",
    "list_knowledge_folders",
    "list_recent_failures",
    "get_execution_record",
    "get_generate_job",
    "get_requirement_latest_job",
)

PREVIEW_TOOL_NAMES: tuple[str, ...] = (
    "preview_trigger_generate",
    "preview_run_api_suite",
    "preview_run_api_plan",
    "preview_run_api_case",
    "preview_run_ui_case",
    "preview_run_ui_task",
    "preview_run_ui_suite",
    "preview_run_app_case",
    "preview_run_app_suite",
    "preview_run_app_plan",
    "preview_run_perf_scene",
    "preview_analyze_failure",
)

CONFIRM_ACTION_MAP: dict[str, str] = {
    "trigger_generate": "confirm_trigger_generate",
    "run_api_suite": "confirm_run_api_suite",
    "run_api_plan": "confirm_run_api_plan",
    "run_api_case": "confirm_run_api_case",
    "run_ui_case": "confirm_run_ui_case",
    "run_ui_task": "confirm_run_ui_task",
    "run_ui_suite": "confirm_run_ui_suite",
    "run_app_case": "confirm_run_app_case",
    "run_app_suite": "confirm_run_app_suite",
    "run_app_plan": "confirm_run_app_plan",
    "run_perf_scene": "confirm_run_perf_scene",
    "analyze_failure": "confirm_analyze_failure",
}

CONFIRM_TOOL_NAMES: tuple[str, ...] = tuple(CONFIRM_ACTION_MAP.values())

READONLY_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_projects",
            "description": "列出当前用户可访问的项目",
            "parameters": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "description": "页码，默认 1"},
                    "size": {"type": "integer", "description": "每页条数，默认 20"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project",
            "description": "获取单个项目基本信息",
            "parameters": {
                "type": "object",
                "properties": {"project_id": {"type": "integer", "description": "项目 ID"}},
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_overview",
            "description": "一次获取项目全貌：环境、模块、需求摘要、用例库规模、最近失败（推荐用于项目总结）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "项目 ID"},
                    "requirement_limit": {"type": "integer", "description": "需求摘要条数上限，默认 10"},
                    "include_failures": {"type": "boolean", "description": "是否包含最近失败，默认 true"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_environments",
            "description": "列出项目下的测试环境",
            "parameters": {
                "type": "object",
                "properties": {"project_id": {"type": "integer"}},
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_online_devices",
            "description": "列出当前在线 Web UI Runner 设备（执行 UI 用例/计划/套件时需 device_id）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "当前项目 ID（可选，设备为全局）"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_modules",
            "description": "列出项目下的 Web/API 测试模块",
            "parameters": {
                "type": "object",
                "properties": {"project_id": {"type": "integer"}},
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_api_definitions",
            "description": "列出项目接口定义（HTTP 方法、路径、描述、关联用例数）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "keyword": {"type": "string", "description": "按名称/路径/描述搜索"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_api_definition",
            "description": "获取单个接口定义详情（方法、路径、参数等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "api_id": {"type": "integer", "description": "接口 ID"},
                    "project_id": {"type": "integer"},
                    "include_body": {"type": "boolean", "description": "是否包含完整 body，默认 false"},
                },
                "required": ["api_id", "project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_api_categories",
            "description": "列出项目接口分类及接口/用例/套件数量统计（接口管理概览）",
            "parameters": {
                "type": "object",
                "properties": {"project_id": {"type": "integer"}},
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_api_test_cases",
            "description": "列出项目接口测试用例（名称、关联接口方法/路径、优先级、断言数）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "api_id": {"type": "integer", "description": "按接口 ID 筛选，可选"},
                    "keyword": {"type": "string", "description": "按用例名称搜索"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_api_suites",
            "description": "列出项目接口测试套件（执行前查 suite_id）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_ui_tasks",
            "description": "列出项目 UI 测试计划（Task）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_ui_cases",
            "description": "列出项目 Web UI 用例（摘要，不含 steps 全文）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_requirements",
            "description": "列出项目需求文档（含 case_count 与最近生成摘要）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_requirement",
            "description": "获取需求详情（含章节标题、用例数、最近生成任务）",
            "parameters": {
                "type": "object",
                "properties": {
                    "requirement_id": {"type": "integer"},
                    "project_id": {"type": "integer"},
                    "include_section_titles": {"type": "boolean"},
                },
                "required": ["requirement_id", "project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_requirement_cases",
            "description": "列出需求工作区已生成的功能用例（默认摘要，不含 steps 全文）",
            "parameters": {
                "type": "object",
                "properties": {
                    "requirement_id": {"type": "integer"},
                    "project_id": {"type": "integer"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                    "summary_only": {"type": "boolean"},
                },
                "required": ["requirement_id", "project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_functional_cases",
            "description": "按关键词搜索功能用例库",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_test_knowledge",
            "description": "检索迭代测试资料库（历史 Bug、测试计划、迭代文档等），返回相关片段与上下文",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "query": {"type": "string", "description": "检索问题或关键词"},
                    "folder_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "限定文件夹 ID",
                    },
                    "document_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "限定文档 ID",
                    },
                    "top_k": {"type": "integer", "description": "返回分块数量，默认 12"},
                    "strategy": {
                        "type": "string",
                        "description": "检索策略：lexical|vector|hybrid，默认跟随项目配置",
                    },
                },
                "required": ["project_id", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_test_knowledge",
            "description": "资料库问答：retrieve 返回 Top-K 片段；smart 基于资料生成回答并附引用",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "query": {"type": "string", "description": "问题"},
                    "mode": {
                        "type": "string",
                        "description": "retrieve=仅检索 | smart=智能回答，默认 smart",
                    },
                    "folder_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "限定文件夹 ID",
                    },
                    "document_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "限定文档 ID",
                    },
                    "top_k": {"type": "integer", "description": "检索分块数量，默认 12"},
                    "strategy": {
                        "type": "string",
                        "description": "检索策略：lexical|vector|hybrid",
                    },
                },
                "required": ["project_id", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_knowledge_folders",
            "description": "列出迭代测试资料库文件夹（含文档数量、迭代标签）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "keyword": {"type": "string", "description": "按名称/迭代标签筛选"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_functional_case",
            "description": "获取单条功能用例详情",
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "integer"},
                    "project_id": {"type": "integer"},
                },
                "required": ["case_id", "project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent_failures",
            "description": "列出项目最近失败的用例/执行记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "limit": {"type": "integer", "description": "条数上限，默认 8"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_execution_record",
            "description": "查询执行记录摘要（api_suite / api_plan / ui_plan / ui_case / app_plan / app_suite / app_case / perf）",
            "parameters": {
                "type": "object",
                "properties": {
                    "record_type": {
                        "type": "string",
                        "enum": [
                            "api_suite",
                            "api_plan",
                            "ui_plan",
                            "ui_case",
                            "app_plan",
                            "app_suite",
                            "app_case",
                            "perf",
                        ],
                    },
                    "record_id": {"type": "integer"},
                },
                "required": ["record_type", "record_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_api_plans",
            "description": "列出项目接口测试计划（编排套件/用例）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_api_run_records",
            "description": "列出接口执行记录（套件 + 测试计划，按时间倒序）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "record_type": {"type": "string", "enum": ["", "suite", "plan"], "description": "可选筛选类型"},
                    "status": {"type": "string", "description": "如 success/failed/running"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_ui_run_records",
            "description": "列出 UI 测试计划执行记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "task_id": {"type": "integer", "description": "按 UI 计划 ID 筛选"},
                    "keyword": {"type": "string", "description": "按计划名称搜索"},
                    "status": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_perf_scenes",
            "description": "列出性能测试场景（压测配置摘要）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_perf_records",
            "description": "列出性能测试执行记录（QPS、响应时间、错误率）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "scene_id": {"type": "integer", "description": "按场景 ID 筛选"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_mock_apis",
            "description": "列出项目 Mock 接口配置",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_data_factory_datasources",
            "description": "列出数据工厂数据源（只读，不含密码明文）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "environment_id": {"type": "integer", "description": "按环境 ID 筛选"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_sql_templates",
            "description": "列出数据工厂 SQL 模板（setup/teardown 等，只读）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "environment_id": {"type": "integer", "description": "按环境 ID 筛选"},
                    "template_type": {"type": "string", "description": "setup / teardown / 留空表示全部"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sql_template",
            "description": "获取单个 SQL 模板详情（只读）",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {"type": "integer", "description": "SQL 模板 ID"},
                },
                "required": ["template_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_api_cron_jobs",
            "description": "列出项目接口定时任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_ui_suites",
            "description": "列出项目 Web UI 测试套件",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_ui_cron_jobs",
            "description": "列出项目 UI 定时任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_app_cases",
            "description": "列出项目 App 用例（Android 移动端，摘要）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_app_suites",
            "description": "列出项目 App 测试套件",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_app_plans",
            "description": "列出项目 App 测试计划",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_app_run_records",
            "description": "列出 App 执行记录（计划+套件）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "record_type": {"type": "string", "description": "plan|suite|空为全部"},
                    "keyword": {"type": "string"},
                    "status": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_app_cron_jobs",
            "description": "列出项目 App 定时任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_perf_cron_jobs",
            "description": "列出项目性能测试定时任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "keyword": {"type": "string"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_perf_workers",
            "description": "列出项目性能测试 Worker 节点",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_generate_job",
            "description": "查询需求用例 AI 生成任务进度",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "integer"},
                    "project_id": {"type": "integer"},
                },
                "required": ["job_id", "project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_requirement_latest_job",
            "description": "获取需求最近一次 AI 生成任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "requirement_id": {"type": "integer"},
                    "project_id": {"type": "integer"},
                },
                "required": ["requirement_id", "project_id"],
            },
        },
    },
]

PREVIEW_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "preview_trigger_generate",
            "description": "预览需求用例 AI 生成影响（需用户确认后才真正提交）",
            "parameters": {
                "type": "object",
                "properties": {
                    "requirement_id": {"type": "integer"},
                    "project_id": {"type": "integer"},
                    "batch_count": {"type": "integer", "description": "计划生成条数，默认 10"},
                },
                "required": ["requirement_id", "project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_run_api_suite",
            "description": "预览接口套件执行影响（需用户确认后才真正执行）",
            "parameters": {
                "type": "object",
                "properties": {
                    "suite_id": {"type": "integer"},
                    "env_id": {"type": "integer", "description": "环境 ID，可省略使用套件默认环境"},
                },
                "required": ["suite_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_run_api_plan",
            "description": "预览接口测试计划执行影响（需用户确认后才真正执行）",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "integer"},
                    "env_id": {"type": "integer", "description": "环境 ID，可省略使用计划默认环境"},
                },
                "required": ["plan_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_run_api_case",
            "description": "预览单条接口用例执行（按 case_id 或 case_name，需 env_id；确认后同步返回 HTTP 结果）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "env_id": {"type": "integer", "description": "执行环境 ID"},
                    "case_id": {"type": "integer", "description": "用例 ID，与 case_name 二选一"},
                    "case_name": {"type": "string", "description": "用例名称（精确或模糊匹配）"},
                },
                "required": ["project_id", "env_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_run_ui_case",
            "description": "预览单条 Web UI 用例执行（case_id 或 case_name + env_id + device_id）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "env_id": {"type": "integer", "description": "运行环境 ID"},
                    "device_id": {"type": "string", "description": "在线 Runner 设备 ID"},
                    "case_id": {"type": "integer", "description": "用例 ID，与 case_name 二选一"},
                    "case_name": {"type": "string", "description": "用例名称（精确或模糊匹配）"},
                },
                "required": ["project_id", "env_id", "device_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_run_app_case",
            "description": "预览单条 App 用例执行（case_id 或 case_name + env_id + 在线 App Runner 的 device_id）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "env_id": {"type": "integer", "description": "运行环境 ID"},
                    "device_id": {"type": "string", "description": "在线 App Runner 设备 ID"},
                    "case_id": {"type": "integer", "description": "App 用例 ID，与 case_name 二选一"},
                    "case_name": {"type": "string", "description": "App 用例名称（精确或模糊匹配）"},
                },
                "required": ["project_id", "env_id", "device_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_run_app_suite",
            "description": "预览 App 套件执行影响（需用户确认后才真正执行）",
            "parameters": {
                "type": "object",
                "properties": {
                    "suite_id": {"type": "integer"},
                    "env_id": {"type": "integer"},
                    "device_id": {"type": "string", "description": "在线 App Runner 设备 ID"},
                },
                "required": ["suite_id", "env_id", "device_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_run_app_plan",
            "description": "预览 App 测试计划执行影响（需用户确认后才真正执行）",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "integer"},
                    "env_id": {"type": "integer"},
                    "device_id": {"type": "string", "description": "在线 App Runner 设备 ID"},
                },
                "required": ["plan_id", "env_id", "device_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_run_ui_task",
            "description": "预览 UI 测试计划执行影响（需用户确认后才真正执行）",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"},
                    "env_id": {"type": "integer"},
                    "device_id": {"type": "string", "description": "在线 Runner 设备 ID"},
                },
                "required": ["task_id", "env_id", "device_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_run_ui_suite",
            "description": "预览 Web UI 套件执行影响（需用户确认后才真正执行）",
            "parameters": {
                "type": "object",
                "properties": {
                    "suite_id": {"type": "integer"},
                    "env_id": {"type": "integer"},
                    "device_id": {"type": "string", "description": "在线 Runner 设备 ID"},
                },
                "required": ["suite_id", "env_id", "device_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_run_perf_scene",
            "description": "预览压测场景执行影响（需用户确认后才真正启动）",
            "parameters": {
                "type": "object",
                "properties": {
                    "scene_id": {"type": "integer"},
                    "env_id": {"type": "integer"},
                },
                "required": ["scene_id", "env_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_analyze_failure",
            "description": "预览失败 AI 分析影响（消耗 Token，需用户确认）",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "target_type": {"type": "string", "enum": ["api", "ui", "app"]},
                    "target_id": {"type": "integer"},
                    "force_refresh": {"type": "boolean"},
                },
                "required": ["project_id", "target_type", "target_id"],
            },
        },
    },
]

TOOL_SELECTION_SCHEMAS: list[dict[str, Any]] = READONLY_TOOL_SCHEMAS + PREVIEW_TOOL_SCHEMAS


def get_tool_selection_schemas() -> list[dict[str, Any]]:
    denied: set[str] = set()
    if not qa_eval_feature_enabled():
        denied |= QA_EVAL_TOOL_NAMES
    if not knowledge_feature_enabled():
        denied |= KNOWLEDGE_TOOL_NAMES
    if not denied:
        return TOOL_SELECTION_SCHEMAS
    return [
        schema
        for schema in TOOL_SELECTION_SCHEMAS
        if schema.get("function", {}).get("name") not in denied
    ]


def _assistant_allowed_tool_names() -> set[str]:
    allowed = set(READONLY_TOOL_NAMES) | set(PREVIEW_TOOL_NAMES)
    if not qa_eval_feature_enabled():
        allowed -= QA_EVAL_TOOL_NAMES
    if not knowledge_feature_enabled():
        allowed -= KNOWLEDGE_TOOL_NAMES
    return allowed


_handler_map_cache: dict[str, ToolHandler] | None = None


def _get_handler_map() -> dict[str, ToolHandler]:
    global _handler_map_cache
    if _handler_map_cache is None:
        from app.mcp import tools as mcp_tools

        _handler_map_cache = {
            "list_projects": mcp_tools.tool_list_projects,
            "get_project": mcp_tools.tool_get_project,
            "get_project_overview": mcp_tools.tool_get_project_overview,
            "list_environments": mcp_tools.tool_list_environments,
            "list_online_devices": mcp_tools.tool_list_online_devices,
            "list_modules": mcp_tools.tool_list_modules,
            "list_api_definitions": mcp_tools.tool_list_api_definitions,
            "get_api_definition": mcp_tools.tool_get_api_definition,
            "list_api_categories": mcp_tools.tool_list_api_categories,
            "list_api_test_cases": mcp_tools.tool_list_api_test_cases,
            "list_api_suites": mcp_tools.tool_list_api_suites,
            "list_api_plans": mcp_tools.tool_list_api_plans,
            "list_api_run_records": mcp_tools.tool_list_api_run_records,
            "list_api_cron_jobs": mcp_tools.tool_list_api_cron_jobs,
            "list_mock_apis": mcp_tools.tool_list_mock_apis,
            "list_data_factory_datasources": mcp_tools.tool_list_data_factory_datasources,
            "list_sql_templates": mcp_tools.tool_list_sql_templates,
            "get_sql_template": mcp_tools.tool_get_sql_template,
            "list_ui_tasks": mcp_tools.tool_list_ui_tasks,
            "list_ui_cases": mcp_tools.tool_list_ui_cases,
            "list_ui_run_records": mcp_tools.tool_list_ui_run_records,
            "list_ui_suites": mcp_tools.tool_list_ui_suites,
            "list_ui_cron_jobs": mcp_tools.tool_list_ui_cron_jobs,
            "list_app_cases": mcp_tools.tool_list_app_cases,
            "list_app_suites": mcp_tools.tool_list_app_suites,
            "list_app_plans": mcp_tools.tool_list_app_plans,
            "list_app_run_records": mcp_tools.tool_list_app_run_records,
            "list_app_cron_jobs": mcp_tools.tool_list_app_cron_jobs,
            "list_perf_scenes": mcp_tools.tool_list_perf_scenes,
            "list_perf_records": mcp_tools.tool_list_perf_records,
            "list_perf_cron_jobs": mcp_tools.tool_list_perf_cron_jobs,
            "list_perf_workers": mcp_tools.tool_list_perf_workers,
            "list_requirements": mcp_tools.tool_list_requirements,
            "get_requirement": mcp_tools.tool_get_requirement,
            "list_requirement_cases": mcp_tools.tool_list_requirement_cases,
            "search_functional_cases": mcp_tools.tool_search_functional_cases,
            "get_functional_case": mcp_tools.tool_get_functional_case,
            "search_test_knowledge": mcp_tools.tool_search_test_knowledge,
            "ask_test_knowledge": mcp_tools.tool_ask_test_knowledge,
            "list_knowledge_folders": mcp_tools.tool_list_knowledge_folders,
            "list_recent_failures": mcp_tools.tool_list_recent_failures,
            "get_execution_record": mcp_tools.tool_get_execution_record,
            "get_generate_job": mcp_tools.tool_get_generate_job,
            "get_requirement_latest_job": mcp_tools.tool_get_requirement_latest_job,            "preview_trigger_generate": mcp_tools.tool_preview_trigger_generate,
            "preview_run_api_suite": mcp_tools.tool_preview_run_api_suite,
            "preview_run_api_plan": mcp_tools.tool_preview_run_api_plan,
            "preview_run_api_case": mcp_tools.tool_preview_run_api_case,            "preview_run_ui_case": mcp_tools.tool_preview_run_ui_case,
            "preview_run_app_case": mcp_tools.tool_preview_run_app_case,
            "preview_run_app_suite": mcp_tools.tool_preview_run_app_suite,
            "preview_run_app_plan": mcp_tools.tool_preview_run_app_plan,
            "preview_run_ui_task": mcp_tools.tool_preview_run_ui_task,
            "preview_run_ui_suite": mcp_tools.tool_preview_run_ui_suite,
            "preview_run_perf_scene": mcp_tools.tool_preview_run_perf_scene,
            "confirm_trigger_generate": mcp_tools.tool_confirm_trigger_generate,
            "confirm_run_api_suite": mcp_tools.tool_confirm_run_api_suite,
            "confirm_run_api_plan": mcp_tools.tool_confirm_run_api_plan,
            "confirm_run_api_case": mcp_tools.tool_confirm_run_api_case,            "confirm_run_ui_case": mcp_tools.tool_confirm_run_ui_case,
            "confirm_run_app_case": mcp_tools.tool_confirm_run_app_case,
            "confirm_run_app_suite": mcp_tools.tool_confirm_run_app_suite,
            "confirm_run_app_plan": mcp_tools.tool_confirm_run_app_plan,
            "confirm_run_ui_task": mcp_tools.tool_confirm_run_ui_task,
            "confirm_run_ui_suite": mcp_tools.tool_confirm_run_ui_suite,
            "confirm_run_perf_scene": mcp_tools.tool_confirm_run_perf_scene,
        }
    return _handler_map_cache


_PROJECT_SCOPED_TOOLS = {
    "get_project",
    "get_project_overview",
    "list_environments",
    "list_online_devices",
    "list_modules",
    "list_api_definitions",
    "get_api_definition",
    "list_api_categories",
    "list_api_test_cases",
    "list_api_suites",
    "list_api_plans",
    "list_api_run_records",
    "list_api_cron_jobs",
    "list_mock_apis",
    "list_data_factory_datasources",
    "list_sql_templates",
    "get_sql_template",
    "list_ui_tasks",
    "list_ui_cases",
    "list_ui_run_records",
    "list_ui_suites",
    "list_ui_cron_jobs",
    "list_app_cases",
    "list_app_suites",
    "list_app_plans",
    "list_app_run_records",
    "list_app_cron_jobs",
    "list_perf_scenes",
    "list_perf_records",
    "list_perf_cron_jobs",
    "list_perf_workers",
    "list_requirements",
    "get_requirement",
    "list_requirement_cases",
    "search_functional_cases",
    "get_functional_case",
    "search_test_knowledge",
    "ask_test_knowledge",
    "list_knowledge_folders",
    "list_recent_failures",
    "get_generate_job",
    "get_requirement_latest_job",
    "preview_trigger_generate",
    "preview_run_api_case",
    "preview_run_ui_case",
    "preview_run_app_case",
    "preview_run_app_suite",
    "preview_run_app_plan",
    "preview_analyze_failure",
}

MAX_TOOL_RESULT_CHARS = 14000
LIST_ITEM_LIMIT = 15


def _permission_label_map() -> dict[str, str]:
    from app.core.platform.permissions import PERMISSIONS

    labels: dict[str, str] = {}
    for group in PERMISSIONS:
        for child in group.get("children") or []:
            value = child.get("value")
            if value:
                labels[value] = child.get("label") or value
    return labels


def format_tool_error(exc: Exception) -> dict[str, Any]:
    msg = str(exc)
    if "权限不足" not in msg:
        return {"error": msg}
    required: list[str] = []
    if "需要:" in msg:
        part = msg.split("需要:", 1)[1].strip()
        required = [p.strip() for p in part.split(",") if p.strip()]
    label_map = _permission_label_map()
    labels = [label_map.get(p, p) for p in required]
    hint = f"您缺少权限：{'、'.join(labels)}。请联系管理员在「角色管理」中分配相应权限后重试。"
    return {
        "error": msg,
        "permission_denied": True,
        "required_permissions": required,
        "permission_labels": labels,
        "user_hint": hint,
    }


def _compact_list_items(items: list[Any], limit: int = LIST_ITEM_LIMIT) -> tuple[list[Any], bool]:
    if len(items) <= limit:
        return items, False
    return items[:limit], True


def compact_tool_result(data: Any, *, list_limit: int = LIST_ITEM_LIMIT) -> Any:
    """压缩工具 JSON：长列表只保留前 N 条，便于 LLM 上下文。"""
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        truncated = False
        for key, value in data.items():
            if key == "items" and isinstance(value, list):
                compact_items, cut = _compact_list_items(value, list_limit)
                out[key] = compact_items
                truncated = truncated or cut
            elif key in ("cases", "definitions", "suites", "requirements", "failures", "categories") and isinstance(
                value, list
            ):
                compact_items, cut = _compact_list_items(value, list_limit)
                out[key] = compact_items
                truncated = truncated or cut
            elif isinstance(value, (dict, list)):
                out[key] = compact_tool_result(value, list_limit=list_limit)
            else:
                out[key] = value
        if truncated and "truncated" not in out:
            out["_truncated"] = True
            out["_truncated_note"] = f"列表已截断，仅展示前 {list_limit} 条"
        return out
    if isinstance(data, list):
        compact_items, cut = _compact_list_items(data, list_limit)
        if cut:
            return compact_items + [{"_truncated_note": f"列表已截断，仅展示前 {list_limit} 条"}]
        return compact_items
    return data


def compact_tools_payload(payload: dict[str, Any], *, list_limit: int = LIST_ITEM_LIMIT) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for name, data in payload.items():
        if isinstance(data, dict) and data.get("error"):
            compacted[name] = data
        else:
            compacted[name] = compact_tool_result(data, list_limit=list_limit)
    return compacted


def truncate_tool_result(data: Any) -> str:
    text = json.dumps(data, ensure_ascii=False, default=str)
    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return text
    return text[:MAX_TOOL_RESULT_CHARS] + "…（结果已截断）"


async def preview_analyze_failure(
    ctx: McpAuthContext,
    project_id: int,
    target_type: str,
    target_id: int,
    force_refresh: bool = False,
) -> dict[str, Any]:
    from app.core.platform.permissions import AI_TEST_EXECUTE
    from app.mcp.auth import ensure_permission

    ensure_permission(ctx, AI_TEST_EXECUTE)
    target_type = (target_type or "").lower()
    if target_type not in ("api", "ui", "app"):
        raise ValueError("target_type 支持 api、ui 或 app")
    impact = {
        "project_id": project_id,
        "target_type": target_type,
        "target_id": target_id,
        "force_refresh": force_refresh,
        "warning": "将调用 LLM 进行失败分析，消耗 Token",
    }
    confirm_token = await create_confirm_token(
        "analyze_failure",
        {
            "project_id": project_id,
            "target_type": target_type,
            "target_id": target_id,
            "force_refresh": force_refresh,
        },
        ctx.username,
    )
    return {
        "impact": impact,
        "confirm_token": confirm_token,
        "expires_in_seconds": 300,
        "next_step": "用户确认后调用 confirm_analyze_failure",
    }


async def confirm_analyze_failure(
    ctx: McpAuthContext,
    confirm_token: str,
    project_id: int,
) -> dict[str, Any]:
    from app.mcp import tools as mcp_tools

    payload = await consume_confirm_token(confirm_token, "analyze_failure", ctx.username)
    if int(payload.get("project_id", 0)) != project_id:
        raise ValueError("project_id 与确认 Token 不匹配")
    return await mcp_tools.tool_analyze_failure(
        ctx,
        project_id=project_id,
        target_type=str(payload["target_type"]),
        target_id=int(payload["target_id"]),
        force_refresh=bool(payload.get("force_refresh")),
    )


async def invoke_assistant_tool(
    ctx: McpAuthContext,
    name: str,
    arguments: dict[str, Any],
    default_project_id: int | None = None,
) -> dict[str, Any]:
    allowed = _assistant_allowed_tool_names()
    if name not in allowed:
        return {"error": f"工具 {name} 不可用"}
    if name == "preview_analyze_failure":
        args = dict(arguments or {})
        if default_project_id and "project_id" not in args:
            args["project_id"] = default_project_id
        try:
            return await preview_analyze_failure(ctx, **args)
        except TypeError as exc:
            return {"error": f"参数错误: {exc}"}
        except ValueError as exc:
            return format_tool_error(exc)
        except HTTPException as exc:
            detail = exc.detail
            return {"error": detail if isinstance(detail, str) else str(detail)}
        except Exception as exc:
            return {"error": f"工具执行失败: {exc}"}

    handler = _get_handler_map().get(name)
    if not handler:
        return {"error": f"未知工具: {name}"}
    args = dict(arguments or {})
    if default_project_id and name in _PROJECT_SCOPED_TOOLS and "project_id" not in args:
        args["project_id"] = default_project_id
    try:
        return await handler(ctx, **args)
    except TypeError as exc:
        return {"error": f"参数错误: {exc}"}
    except ValueError as exc:
        return format_tool_error(exc)
    except HTTPException as exc:
        detail = exc.detail
        return {"error": detail if isinstance(detail, str) else str(detail)}
    except Exception as exc:
        return {"error": f"工具执行失败: {exc}"}


async def invoke_confirm_tool(
    ctx: McpAuthContext,
    action: str,
    confirm_token: str,
    confirm_args: dict[str, Any],
) -> dict[str, Any]:
    tool_name = CONFIRM_ACTION_MAP.get(action)
    if not tool_name:
        raise ValueError(f"不支持的操作: {action}")

    if tool_name == "confirm_analyze_failure":
        return await confirm_analyze_failure(
            ctx,
            confirm_token=confirm_token,
            project_id=int(confirm_args.get("project_id") or 0),
        )

    handler = _get_handler_map().get(tool_name)
    if not handler:
        raise ValueError(f"未知确认工具: {tool_name}")
    args = {"confirm_token": confirm_token, **(confirm_args or {})}
    try:
        return await handler(ctx, **args)
    except HTTPException as exc:
        detail = exc.detail
        raise ValueError(detail if isinstance(detail, str) else str(detail)) from exc


def extract_pending_confirm(tool_name: str, result: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(result, dict) or not result.get("confirm_token"):
        return None
    impact = result.get("impact") or {}
    action = ""
    if tool_name == "preview_trigger_generate":
        action = "trigger_generate"
    elif tool_name == "preview_run_api_suite":
        action = "run_api_suite"
    elif tool_name == "preview_run_api_plan":
        action = "run_api_plan"
    elif tool_name == "preview_run_api_case":
        action = "run_api_case"
    elif tool_name == "preview_run_ui_case":
        action = "run_ui_case"
    elif tool_name == "preview_run_app_case":
        action = "run_app_case"
    elif tool_name == "preview_run_app_suite":
        action = "run_app_suite"
    elif tool_name == "preview_run_app_plan":
        action = "run_app_plan"
    elif tool_name == "preview_run_ui_task":
        action = "run_ui_task"
    elif tool_name == "preview_run_ui_suite":
        action = "run_ui_suite"
    elif tool_name == "preview_run_perf_scene":
        action = "run_perf_scene"
    elif tool_name == "preview_analyze_failure":
        action = "analyze_failure"
    if not action:
        return None

    confirm_args: dict[str, Any] = {"project_id": impact.get("project_id")}
    if action == "trigger_generate":
        confirm_args = {
            "project_id": impact.get("project_id"),
            "requirement_id": impact.get("requirement_id"),
        }
    elif action == "run_api_suite":
        confirm_args = {
            "suite_id": impact.get("suite_id"),
            "env_id": impact.get("env_id"),
        }
    elif action == "run_api_plan":
        confirm_args = {
            "plan_id": impact.get("plan_id"),
            "env_id": impact.get("env_id"),
        }
    elif action == "run_api_case":
        confirm_args = {
            "project_id": impact.get("project_id"),
            "case_id": impact.get("case_id"),
            "env_id": impact.get("env_id"),
        }

    elif action == "run_ui_case":
        confirm_args = {
            "project_id": impact.get("project_id"),
            "case_id": impact.get("case_id"),
            "env_id": impact.get("env_id"),
            "device_id": impact.get("device_id"),
        }
    elif action == "run_app_case":
        confirm_args = {
            "project_id": impact.get("project_id"),
            "case_id": impact.get("case_id"),
            "env_id": impact.get("env_id"),
            "device_id": impact.get("device_id"),
        }
    elif action == "run_app_suite":
        confirm_args = {
            "suite_id": impact.get("suite_id"),
            "env_id": impact.get("env_id"),
            "device_id": impact.get("device_id"),
        }
    elif action == "run_app_plan":
        confirm_args = {
            "plan_id": impact.get("plan_id"),
            "env_id": impact.get("env_id"),
            "device_id": impact.get("device_id"),
        }
    elif action == "run_ui_task":
        confirm_args = {
            "task_id": impact.get("task_id"),
            "env_id": impact.get("env_id"),
            "device_id": impact.get("device_id"),
        }
    elif action == "run_ui_suite":
        confirm_args = {
            "suite_id": impact.get("suite_id"),
            "env_id": impact.get("env_id"),
            "device_id": impact.get("device_id"),
        }
    elif action == "run_perf_scene":
        confirm_args = {
            "scene_id": impact.get("scene_id"),
            "env_id": impact.get("env_id"),
        }
    elif action == "analyze_failure":
        confirm_args = {"project_id": impact.get("project_id")}

    return {
        "action": action,
        "confirm_tool": CONFIRM_ACTION_MAP[action],
        "confirm_token": result["confirm_token"],
        "expires_in_seconds": result.get("expires_in_seconds", 300),
        "impact": impact,
        "confirm_args": confirm_args,
        "preview_tool": tool_name,
    }


async def invoke_readonly_tool(
    ctx: McpAuthContext,
    name: str,
    arguments: dict[str, Any],
    default_project_id: int | None = None,
) -> dict[str, Any]:
    return await invoke_assistant_tool(ctx, name, arguments, default_project_id)
