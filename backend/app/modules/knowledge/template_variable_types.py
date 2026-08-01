"""模板变量值类型与内置变量取值说明"""
from __future__ import annotations

from typing import Any, Optional

# 自定义变量可选类型（不含 auto）
CUSTOM_VALUE_TYPES = frozenset({"text", "textarea", "date", "table", "lines"})

VALUE_TYPE_LABELS: dict[str, str] = {
    "auto": "自动注入",
    "text": "单行文本",
    "textarea": "多行文本",
    "date": "日期",
    "table": "表格循环",
    "lines": "多行列表",
}

TABLE_VARIABLES = frozenset(
    {
        "failed_cases",
        "exec_records",
        "bug_stats_rows",
        "bug_detail_rows",
        "bugs",
        "source_refs",
        "milestone_rows",
    }
)

LINES_VARIABLES = frozenset(
    {
        "bug_analysis_lines",
        "overview_lines",
        "test_scope_lines",
        "test_objectives_lines",
        "test_strategy_lines",
        "functional_scope_lines",
        "functional_summary_lines",
        "performance_summary_lines",
        "performance_metrics_lines",
        "ai_conclusion_lines",
        "ai_risks_lines",
        "ai_recommendations_lines",
    }
)

DATE_VARIABLES = frozenset({"report_date", "plan_start_date", "plan_end_date"})

TEXTAREA_VARIABLES = frozenset(
    {
        "knowledge_summary",
        "bug_export_summary",
        "bug_analysis_text",
        "bug_by_severity",
        "bug_by_status",
        "bug_by_resolution",
        "bug_by_opened_by",
        "bug_by_assigned_to",
        "bug_by_resolved_by",
        "bug_by_priority",
        "bug_by_module",
        "overview",
        "test_scope",
        "test_objectives",
        "test_strategy",
        "ai_conclusion",
        "ai_summary",
        "ai_risks",
        "ai_recommendations",
        "functional_summary",
        "functional_scope",
        "performance_summary",
        "performance_metrics",
    }
)

USER_WIZARD_VARIABLES = frozenset(
    {
        "tester_name",
        "approver",
        "test_environment",
        "plan_start_date",
        "plan_end_date",
        "plan_owner",
    }
)

MILESTONE_TABLE_SCHEMA: dict[str, Any] = {
    "columns": [
        {"key": "name", "label": "里程碑", "input": "text"},
        {"key": "start_date", "label": "开始", "input": "date"},
        {"key": "end_date", "label": "结束", "input": "date"},
        {"key": "owner", "label": "负责人", "input": "text"},
        {"key": "remark", "label": "说明", "input": "text"},
    ]
}

VALUE_HINTS: dict[str, str] = {
    "project_name": "当前测试项目名称，如「示例项目」",
    "iteration_name": "所选资料文件夹名称或迭代标签",
    "report_date": "报告生成日期，格式 YYYY-MM-DD",
    "author": "编写人姓名；向导未填时使用当前登录用户",
    "pass_rate": "自动化执行通过率数值（0–100），无执行数据时为 0",
    "pass_rate_display": "带百分号的通过率展示；无执行数据时为「-」",
    "total_cases": "所选执行记录的用例总数之和",
    "failed_case_count": "所选执行记录的失败用例数之和",
    "exec_duration": "执行耗时汇总，如「12.5 分钟」",
    "failed_cases": "Word 表格循环；每行含 case_name、status、error_msg",
    "exec_records": "Word 表格循环；每行含 name、report_type、pass_rate、total_cases",
    "knowledge_summary": "所选资料库文档拼接后的摘要正文",
    "bug_export_summary": "禅道 Bug 导出 xlsx 解析后的统计说明文字",
    "bug_total": "Bug 导出中的缺陷总条数",
    "bug_open_count": "按状态字段推断的未关闭 Bug 数",
    "bug_closed_count": "按状态字段推断的已关闭 Bug 数",
    "bug_by_severity": "按严重程度聚合的「严重度:数量」多行文本",
    "bug_by_status": "按状态聚合的「状态:数量」多行文本",
    "bug_by_resolution": "按解决方案聚合的多行文本",
    "bug_by_opened_by": "按创建人聚合的多行文本",
    "bug_by_assigned_to": "按指派人聚合的多行文本",
    "bug_by_resolved_by": "按解决人聚合的多行文本",
    "bug_by_priority": "按优先级聚合的多行文本",
    "bug_by_module": "按模块聚合的多行文本（兼容旧模板）",
    "bug_stats_rows": "Word 表格循环；每行 dimension、label、count，推荐用于缺陷分布",
    "bug_analysis_text": "预格式化的缺陷分析整段文字，可直接 {{ bug_analysis_text }}",
    "bug_analysis_lines": "Word 段落循环；每行变量 line，与 bug_analysis_text 同源",
    "bug_detail_rows": "Word 表格循环；含 bug_id、title、module、severity 等字段",
    "bugs": "Word 表格循环；Bug 明细（旧版占位符，可选）",
    "source_refs": "Word 表格/列表循环；报告引用的资料与执行记录摘要",
    "overview": "LLM 生成的测试概述段落",
    "overview_lines": "Word 段落循环；测试概述按行拆分",
    "test_scope": "LLM 生成的测试范围段落",
    "test_scope_lines": "Word 段落循环；测试范围按行拆分，适合条目列表",
    "test_objectives": "LLM 生成的测试目标，适用于计划/方案",
    "test_objectives_lines": "Word 段落循环；测试目标按行拆分",
    "test_strategy": "LLM 生成的测试策略，适用于计划/方案",
    "test_strategy_lines": "Word 段落循环；测试策略按行拆分",
    "ai_conclusion": "LLM 生成的测试结论",
    "ai_conclusion_lines": "Word 段落循环；测试结论按行拆分",
    "ai_summary": "LLM 生成的总结段落",
    "ai_risks": "LLM 生成的遗留风险（可为列表或多段）",
    "ai_risks_lines": "Word 段落循环；遗留风险按行拆分",
    "ai_recommendations": "LLM 生成的改进建议",
    "ai_recommendations_lines": "Word 段落循环；改进建议按行拆分",
    "functional_summary": "功能测试报告中的 LLM 总结",
    "functional_summary_lines": "Word 段落循环；功能测试总结按行拆分",
    "functional_scope": "功能测试范围说明",
    "functional_scope_lines": "Word 段落循环；功能范围按行拆分",
    "performance_summary": "性能测试报告 LLM 总结",
    "performance_summary_lines": "Word 段落循环；性能测试总结按行拆分",
    "performance_metrics": "性能指标说明，如 TPS、响应时间等",
    "performance_metrics_lines": "Word 段落循环；性能指标按行拆分",
    "tester_name": "报告向导手工填写，写入 {{ tester_name }}",
    "approver": "报告向导手工填写，写入 {{ approver }}",
    "test_environment": "测试环境说明，如「SIT / UAT」",
    "plan_start_date": "测试计划进度章节的计划开始日期 YYYY-MM-DD",
    "plan_end_date": "测试计划进度章节的计划结束日期 YYYY-MM-DD",
    "plan_owner": "测试计划总负责人姓名",
    "milestone_rows": "报告向导「进度与里程碑」表格；Word 中 {% for row in milestone_rows %} 循环",
}


def normalize_value_type(raw: Optional[str], *, custom: bool = False) -> str:
    value = (raw or "text").strip().lower()
    if custom:
        return value if value in CUSTOM_VALUE_TYPES else "text"
    return value if value in VALUE_TYPE_LABELS else "auto"


def infer_value_type(name: str, meta: dict[str, Any]) -> str:
    explicit = meta.get("value_type")
    if explicit:
        return normalize_value_type(str(explicit), custom=False)
    if name in DATE_VARIABLES or name.endswith("_date"):
        return "date"
    if name in TABLE_VARIABLES:
        return "table"
    if name in LINES_VARIABLES or name.endswith("_lines"):
        return "lines"
    if name in TEXTAREA_VARIABLES:
        return "textarea"
    if meta.get("category") == "user" or name in USER_WIZARD_VARIABLES:
        return "text"
    return "auto"


def infer_value_schema(name: str, meta: dict[str, Any], value_type: str) -> Optional[dict[str, Any]]:
    if meta.get("value_schema"):
        return meta["value_schema"]
    if name == "milestone_rows" or (value_type == "table" and name == "milestone_rows"):
        return MILESTONE_TABLE_SCHEMA
    return None


def variable_to_dict(
    name: str,
    meta: dict[str, Any],
    *,
    builtin: bool,
    **extra: Any,
) -> dict[str, Any]:
    value_type = infer_value_type(name, meta)
    return {
        "name": name,
        "builtin": builtin,
        "category": meta.get("category", "custom"),
        "label": meta.get("label", name),
        "description": meta.get("description") or "",
        "value_type": value_type,
        "value_hint": meta.get("value_hint") or VALUE_HINTS.get(name) or meta.get("description") or "",
        "value_schema": infer_value_schema(name, meta, value_type),
        "default_value": meta.get("default_value") or "",
        **extra,
    }


def is_wizard_fillable(meta: dict[str, Any]) -> bool:
    value_type = meta.get("value_type") or "text"
    return value_type in CUSTOM_VALUE_TYPES
