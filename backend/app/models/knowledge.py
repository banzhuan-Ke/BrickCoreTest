"""迭代测试资料库模型"""
from tortoise import fields, models


class AiKnowledgeFolder(models.Model):
    """迭代/版本资料文件夹"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="knowledge_folders",
        description="所属项目",
    )
    name = fields.CharField(max_length=100, description="文件夹名称")
    description = fields.TextField(null=True, description="说明")
    iteration_label = fields.CharField(max_length=50, null=True, description="迭代标签")
    date_start = fields.DateField(null=True, description="迭代开始日期")
    date_end = fields.DateField(null=True, description="迭代结束日期")
    sort = fields.IntField(default=0, description="排序")
    is_del = fields.BooleanField(default=False, description="逻辑删除")
    created_by = fields.CharField(max_length=50, null=True, description="创建人")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ai_knowledge_folder"
        table_description = "迭代测试资料库-文件夹"


class AiKnowledgeDocument(models.Model):
    """资料库文档"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="knowledge_documents",
        description="所属项目",
    )
    folder = fields.ForeignKeyField(
        "models.AiKnowledgeFolder",
        related_name="documents",
        null=True,
        description="所属文件夹",
    )
    title = fields.CharField(max_length=200, description="标题")
    doc_type = fields.CharField(max_length=32, description="文档类型")
    file_name = fields.CharField(max_length=255, description="原始文件名")
    storage = fields.JSONField(default=dict, description="存储元数据")
    parse_status = fields.CharField(max_length=20, default="pending", description="解析状态")
    parse_error = fields.TextField(null=True, description="解析错误")
    char_count = fields.IntField(default=0, description="字符数")
    chunk_count = fields.IntField(default=0, description="分块数")
    sections_json = fields.JSONField(null=True, description="章节结构")
    source_requirement_id = fields.IntField(null=True, description="来源需求ID")
    embed_status = fields.CharField(max_length=20, default="none", description="词法索引状态")
    embed_mode = fields.CharField(max_length=20, default="inherit", description="Embedding策略")
    vector_status = fields.CharField(max_length=20, default="none", description="向量索引状态")
    vector_model = fields.CharField(max_length=80, null=True, description="向量Embedding模型")
    vector_error = fields.TextField(null=True, description="向量索引错误")
    digest_status = fields.CharField(max_length=20, default="none", description="AI摘要状态")
    digest_error = fields.TextField(null=True, description="AI摘要错误")
    template_schema = fields.JSONField(null=True, description="模板占位符校验结果")
    is_default_template = fields.BooleanField(default=False, description="项目默认输出模板")
    is_del = fields.BooleanField(default=False, description="逻辑删除")
    created_by = fields.CharField(max_length=50, null=True, description="创建人")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ai_knowledge_document"
        table_description = "迭代测试资料库-文档"


class AiKnowledgeChunk(models.Model):
    """文档分块（Phase 2 RAG）"""

    id = fields.IntField(pk=True)
    document = fields.ForeignKeyField(
        "models.AiKnowledgeDocument",
        related_name="chunks",
        description="所属文档",
    )
    project_id = fields.IntField(description="项目ID")
    chunk_index = fields.IntField(description="分块序号")
    section_title = fields.CharField(max_length=200, null=True, description="章节标题")
    chunk_text = fields.TextField(description="分块文本")
    char_count = fields.IntField(default=0, description="字符数")
    embedding = fields.JSONField(null=True, description="词法/向量混合元数据")
    embedding_model = fields.CharField(max_length=80, null=True, description="Embedding模型")
    vector_json = fields.JSONField(null=True, description="向量Embedding float[]")
    create_time = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "ai_knowledge_chunk"
        table_description = "迭代测试资料库-分块"


class AiKnowledgeTemplateVariable(models.Model):
    """项目级自定义模板变量"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="knowledge_template_variables",
        description="所属项目",
    )
    name = fields.CharField(max_length=64, description="变量名 snake_case")
    label = fields.CharField(max_length=100, description="显示名称")
    category = fields.CharField(max_length=32, default="custom", description="类别")
    value_type = fields.CharField(max_length=20, default="text", description="变量值类型")
    value_schema = fields.JSONField(null=True, description="结构化类型配置")
    description = fields.TextField(null=True, description="说明")
    default_value = fields.TextField(null=True, description="渲染默认值")
    sort = fields.IntField(default=0, description="排序")
    is_del = fields.BooleanField(default=False, description="逻辑删除")
    created_by = fields.CharField(max_length=50, null=True, description="创建人")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ai_knowledge_template_variable"
        table_description = "迭代测试资料库-自定义模板变量"


class AiIterationReport(models.Model):
    """迭代报告/方案生成记录（Phase 1+）"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="iteration_reports",
        description="所属项目",
    )
    folder = fields.ForeignKeyField(
        "models.AiKnowledgeFolder",
        related_name="iteration_reports",
        null=True,
        description="关联文件夹",
    )
    title = fields.CharField(max_length=200, description="标题")
    report_kind = fields.CharField(max_length=32, default="iteration_report", description="报告类型")
    config_json = fields.JSONField(default=dict, description="生成配置")
    content_md = fields.TextField(null=True, description="Markdown内容")
    file_path = fields.CharField(max_length=500, null=True, description="输出文件路径")
    status = fields.CharField(max_length=20, default="pending", description="状态")
    ai_usage_tokens = fields.IntField(default=0, description="Token消耗")
    created_by = fields.CharField(max_length=50, null=True, description="创建人")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    is_del = fields.BooleanField(default=False, description="逻辑删除")

    class Meta:
        table = "ai_iteration_report"
        table_description = "迭代测试资料库-生成记录"


class AiKnowledgeQaRecord(models.Model):
    """资料库问答历史记录"""

    id = fields.IntField(pk=True)
    project_id = fields.IntField(description="项目ID")
    username = fields.CharField(max_length=50, default="", description="提问人")
    mode = fields.CharField(max_length=20, default="retrieve", description="retrieve|smart")
    query = fields.CharField(max_length=500, description="问题")
    answer = fields.TextField(null=True, description="智能模式回答")
    strategy = fields.CharField(max_length=20, default="none", description="检索策略")
    folder_ids = fields.JSONField(default=list, description="限定文件夹")
    document_ids = fields.JSONField(default=list, description="限定文档")
    top_k = fields.IntField(default=12, description="返回条数")
    hit_count = fields.IntField(default=0, description="命中分块数")
    doc_count = fields.IntField(default=0, description="涉及文档数")
    tokens_used = fields.IntField(default=0, description="Token消耗")
    duration_ms = fields.IntField(default=0, description="耗时ms")
    sources_json = fields.JSONField(default=list, description="引用来源摘要")
    result_json = fields.JSONField(default=dict, description="完整结果快照")
    is_del = fields.BooleanField(default=False, description="逻辑删除")
    create_time = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "ai_knowledge_qa_record"
        table_description = "资料库问答历史"
