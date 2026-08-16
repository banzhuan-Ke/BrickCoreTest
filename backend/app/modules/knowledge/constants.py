"""迭代测试资料库 — 文档类型与常量"""

DOC_TYPES: dict[str, str] = {
    "requirement": "需求文档",
    "test_plan": "测试计划",
    "test_scheme": "测试方案",
    "iteration_plan": "迭代计划",
    "bug_export": "Bug 导出",
    "task_export": "任务导出",
    "case_export": "用例导出",
    "summary": "测试总结",
    "report_template": "报告模板",
    "plan_template": "方案模板",
    "quality_pptx_template": "质量回顾模板",
    "other": "其他",
}

TEMPLATE_DOC_TYPES = frozenset({"report_template", "plan_template", "quality_pptx_template"})

ALLOWED_UPLOAD_EXTENSIONS = frozenset(
    {
        ".doc",
        ".docx",
        ".pdf",
        ".md",
        ".txt",
        ".xlsx",
        ".xls",
        ".csv",
        ".ppt",
        ".pptx",
    }
)

# 报告/方案模板渲染（docxtpl）仅支持 docx；xlsx 仅单元格占位
TEMPLATE_RENDER_EXTENSIONS = frozenset({".docx", ".xlsx", ".xls"})

PARSE_STATUS_PENDING = "pending"
PARSE_STATUS_PARSING = "parsing"
PARSE_STATUS_READY = "ready"
PARSE_STATUS_FAILED = "failed"

# sections_json v2 入库体量保护（全量入库 ≠ 无上限）
KNOWLEDGE_INGEST_MAX_ROWS_PER_SHEET = 10000
KNOWLEDGE_INGEST_MAX_SHEETS = 50
KNOWLEDGE_INGEST_MAX_PROSE_CHARS = 2_000_000

SECTIONS_JSON_VERSION_V2 = 2
