"""模板变量注册表"""
from __future__ import annotations

import re
from typing import Any, Optional

# 内置变量（平台注入，不可删除）
BUILTIN_TEMPLATE_VARIABLES: dict[str, dict[str, str]] = {
    # 系统变量
    "project_name": {"category": "system", "label": "项目名称", "description": "当前测试项目名"},
    "iteration_name": {"category": "system", "label": "迭代名称", "description": "资料文件夹名称或迭代标签"},
    "report_date": {"category": "system", "label": "报告日期", "description": "YYYY-MM-DD"},
    "author": {"category": "system", "label": "编写人", "description": "当前用户或向导填写"},
    "pass_rate": {"category": "system", "label": "通过率(%)", "description": "汇总执行记录计算"},
    "pass_rate_display": {"category": "system", "label": "通过率展示", "description": "含 % 或 -（无执行数据时）"},
    "total_cases": {"category": "system", "label": "用例总数", "description": "执行记录汇总"},
    "failed_case_count": {"category": "system", "label": "失败用例数", "description": "执行记录汇总"},
    "exec_duration": {"category": "system", "label": "执行耗时", "description": "如 12.5 分钟"},
    "failed_cases": {
        "category": "system",
        "label": "失败用例列表",
        "description": "表格循环：case_name, status, error_msg",
    },
    "exec_records": {
        "category": "system",
        "label": "执行记录摘要",
        "description": "表格循环：name, report_type, pass_rate, total_cases",
    },
    # 资料变量
    "knowledge_summary": {"category": "knowledge", "label": "资料库摘要", "description": "选中资料全文摘要"},
    "bug_export_summary": {"category": "knowledge", "label": "Bug 导出摘要", "description": "禅道 Bug 统计文字"},
    "bug_total": {"category": "knowledge", "label": "Bug 总数", "description": "由 Bug 导出解析"},
    "bug_open_count": {"category": "knowledge", "label": "未关闭 Bug 数", "description": "按状态推断未关闭"},
    "bug_closed_count": {"category": "knowledge", "label": "已关闭 Bug 数", "description": "按状态推断已关闭"},
    "bug_by_severity": {"category": "knowledge", "label": "按严重程度", "description": "文本：严重度:数量"},
    "bug_by_status": {"category": "knowledge", "label": "按状态", "description": "文本：状态:数量"},
    "bug_by_resolution": {"category": "knowledge", "label": "按解决方案", "description": "文本：解决方案:数量"},
    "bug_by_opened_by": {"category": "knowledge", "label": "按创建人", "description": "文本：创建人:数量"},
    "bug_by_assigned_to": {"category": "knowledge", "label": "按归属/指派人", "description": "文本：指派人:数量"},
    "bug_by_resolved_by": {"category": "knowledge", "label": "按解决人", "description": "文本：解决人:数量"},
    "bug_by_priority": {"category": "knowledge", "label": "按优先级", "description": "文本：优先级:数量"},
    "bug_by_module": {"category": "knowledge", "label": "按模块", "description": "文本：模块:数量（兼容旧模板）"},
    "bug_stats_rows": {
        "category": "knowledge",
        "label": "缺陷分布表格",
        "description": "表格循环：dimension, label, count（推荐替代 bug_by_* 文本）",
    },
    "bug_analysis_text": {
        "category": "knowledge",
        "label": "缺陷分析（整段）",
        "description": "预格式化缺陷统计与分布，自定义模板可用 {{ bug_analysis_text }}",
    },
    "bug_analysis_lines": {
        "category": "knowledge",
        "label": "缺陷分析（分行）",
        "description": "段落循环：line，与 bug_analysis_text 同源",
    },
    "bug_detail_rows": {
        "category": "knowledge",
        "label": "缺陷明细表格",
        "description": "表格循环：bug_id, title, module, severity, status, resolution, opened_by, assigned_to, resolved_by（可选，默认模板不含）",
    },
    "bugs": {
        "category": "knowledge",
        "label": "Bug 明细列表",
        "description": "表格循环：bug_id, title, ...（可选，默认模板已不含明细节选）",
    },
    "source_refs": {
        "category": "system",
        "label": "报告数据来源",
        "description": "表格/列表循环：kind_label, title, detail",
    },
    # AI 变量
    "overview": {"category": "ai", "label": "测试概述", "description": "LLM 生成"},
    "overview_lines": {"category": "ai", "label": "测试概述（分行）", "description": "段落循环：line"},
    "test_scope": {"category": "ai", "label": "测试范围", "description": "LLM 生成"},
    "test_scope_lines": {"category": "ai", "label": "测试范围（分行）", "description": "段落循环：line，推荐用于功能范围列表"},
    "test_objectives": {"category": "ai", "label": "测试目标", "description": "LLM 生成，适用于测试计划/方案"},
    "test_objectives_lines": {
        "category": "ai",
        "label": "测试目标（分行）",
        "description": "段落循环：line，与 test_objectives 同源",
    },
    "test_strategy": {"category": "ai", "label": "测试策略", "description": "LLM 生成，适用于测试计划/方案"},
    "test_strategy_lines": {
        "category": "ai",
        "label": "测试策略（分行）",
        "description": "段落循环：line，与 test_strategy 同源",
    },
    "ai_conclusion": {"category": "ai", "label": "测试结论", "description": "LLM 生成"},
    "ai_conclusion_lines": {
        "category": "ai",
        "label": "测试结论（分行）",
        "description": "段落循环：line，与 ai_conclusion 同源",
    },
    "ai_summary": {"category": "ai", "label": "AI 总结", "description": "LLM 生成"},
    "ai_risks": {"category": "ai", "label": "遗留风险", "description": "LLM 生成，可为列表"},
    "ai_risks_lines": {
        "category": "ai",
        "label": "遗留风险（分行）",
        "description": "段落循环：line，与 ai_risks 同源",
    },
    "ai_recommendations": {"category": "ai", "label": "改进建议", "description": "LLM 生成，可为列表"},
    "ai_recommendations_lines": {
        "category": "ai",
        "label": "改进建议（分行）",
        "description": "段落循环：line，与 ai_recommendations 同源",
    },
    "functional_summary": {"category": "ai", "label": "功能测试总结", "description": "LLM 生成，功能测试报告"},
    "functional_summary_lines": {
        "category": "ai",
        "label": "功能测试总结（分行）",
        "description": "段落循环：line，与 functional_summary 同源",
    },
    "functional_scope": {"category": "ai", "label": "功能测试范围", "description": "LLM 生成"},
    "functional_scope_lines": {"category": "ai", "label": "功能测试范围（分行）", "description": "段落循环：line"},
    "performance_summary": {"category": "ai", "label": "性能测试总结", "description": "LLM 生成，性能测试报告"},
    "performance_summary_lines": {
        "category": "ai",
        "label": "性能测试总结（分行）",
        "description": "段落循环：line，与 performance_summary 同源",
    },
    "performance_metrics": {"category": "ai", "label": "性能指标", "description": "LLM 生成，如 TPS、响应时间"},
    "performance_metrics_lines": {
        "category": "ai",
        "label": "性能指标（分行）",
        "description": "段落循环：line，与 performance_metrics 同源",
    },
    # 用户变量
    "tester_name": {"category": "user", "label": "测试人员", "description": "向导手工填写"},
    "approver": {"category": "user", "label": "审批人", "description": "向导手工填写"},
    "test_environment": {"category": "user", "label": "测试环境", "description": "向导手工填写或自定义变量默认值"},
    "plan_start_date": {"category": "user", "label": "计划开始日期", "description": "测试计划进度章节，如 2026-04-01"},
    "plan_end_date": {"category": "user", "label": "计划结束日期", "description": "测试计划进度章节，如 2026-06-30"},
    "plan_owner": {"category": "user", "label": "计划总负责人", "description": "测试计划进度与里程碑总负责人"},
    "milestone_rows": {
        "category": "user",
        "label": "里程碑表格",
        "description": "表格循环：name, start_date, end_date, owner, remark（报告向导填写）",
    },
}

# 兼容旧引用
TEMPLATE_VARIABLES = BUILTIN_TEMPLATE_VARIABLES
KNOWN_VARIABLE_NAMES = frozenset(BUILTIN_TEMPLATE_VARIABLES.keys())

VARIABLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

JINJA_BUILTINS = frozenset(
    {
        "loop",
        "super",
        "self",
        "var",
        "true",
        "false",
        "none",
        "True",
        "False",
        "None",
        # docxtpl 表格/段落循环中常见的迭代器名（非顶层上下文变量）
        "row",
        "ref",
        "line",
        "item",
        "rec",
    }
)


def is_valid_variable_name(name: str) -> bool:
    return bool(VARIABLE_NAME_RE.match(name or ""))


def list_builtin_variables() -> list[dict[str, Any]]:
    from app.modules.knowledge.template_variable_types import variable_to_dict

    return [variable_to_dict(name, meta, builtin=True) for name, meta in BUILTIN_TEMPLATE_VARIABLES.items()]


async def list_custom_variable_rows(project_id: int) -> list:
    from app.models.knowledge import AiKnowledgeTemplateVariable

    return await AiKnowledgeTemplateVariable.filter(project_id=project_id, is_del=False).order_by(
        "sort", "id"
    )


async def get_custom_variable_names(project_id: int) -> frozenset[str]:
    rows = await list_custom_variable_rows(project_id)
    return frozenset(r.name for r in rows)


async def get_known_variable_names(project_id: Optional[int] = None) -> frozenset[str]:
    if not project_id:
        return KNOWN_VARIABLE_NAMES
    custom = await get_custom_variable_names(project_id)
    return KNOWN_VARIABLE_NAMES | custom


async def list_template_variables(project_id: Optional[int] = None) -> list[dict[str, Any]]:
    from app.modules.knowledge.template_variable_types import variable_to_dict

    items = list_builtin_variables()
    if not project_id:
        return items
    rows = await list_custom_variable_rows(project_id)
    for row in rows:
        items.append(
            variable_to_dict(
                row.name,
                {
                    "category": row.category or "custom",
                    "label": row.label,
                    "description": row.description or "",
                    "value_type": getattr(row, "value_type", None) or "text",
                    "value_schema": getattr(row, "value_schema", None),
                    "default_value": row.default_value or "",
                },
                builtin=False,
                id=row.id,
                sort=row.sort,
                created_by=row.created_by,
                create_time=row.create_time.isoformat() if row.create_time else None,
            )
        )
    return items


def categorize_variables(names: set[str], extra_known: Optional[set[str]] = None) -> dict[str, list[str]]:
    known_set = KNOWN_VARIABLE_NAMES | set(extra_known or ())
    known = sorted(n for n in names if n in known_set)
    unknown = sorted(n for n in names if n not in known_set and n not in JINJA_BUILTINS)
    return {"known": known, "unknown": unknown}


async def categorize_variables_for_project(project_id: int, names: set[str]) -> dict[str, list[str]]:
    custom = await get_custom_variable_names(project_id)
    return categorize_variables(names, custom)


async def variables_response(project_id: int, found: set[str]) -> dict[str, Any]:
    cats = await categorize_variables_for_project(project_id, found)
    return {
        "placeholders": sorted(found),
        "known": cats["known"],
        "unknown": cats["unknown"],
        "has_unknown": bool(cats["unknown"]),
        "registry": await list_template_variables(project_id),
    }


BUG_TEMPLATE_PLACEHOLDERS = frozenset(
    {
        "bug_total",
        "bug_open_count",
        "bug_closed_count",
        "bug_export_summary",
        "bug_stats_rows",
        "bug_analysis_text",
        "bug_analysis_lines",
        "bug_by_severity",
        "bug_by_status",
        "bug_by_resolution",
        "bug_by_module",
        "bug_detail_rows",
    }
)


def template_covers_bug_data(known: list[str] | set[str]) -> bool:
    return bool(set(known) & BUG_TEMPLATE_PLACEHOLDERS)


def missing_bug_template_hints(known: list[str] | set[str]) -> list[str]:
    if template_covers_bug_data(known):
        return []
    return [
        "模板未包含缺陷相关占位符（如 bug_total、bug_stats_rows、bug_analysis_text），"
        "「缺陷分析」章节可能为空。建议在 Word 模板中加入 {{ bug_analysis_text }} 或使用内置模板。"
    ]


async def apply_custom_defaults(project_id: int, render_ctx: dict[str, Any]) -> None:
    rows = await list_custom_variable_rows(project_id)
    for row in rows:
        if row.name not in render_ctx and row.default_value:
            render_ctx[row.name] = row.default_value
