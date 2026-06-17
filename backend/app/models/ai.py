"""
AI 测试模块相关模型
"""
from tortoise import models, fields


class AiConfig(models.Model):
    """LLM 配置表（支持多供应商多密钥）"""
    id = fields.IntField(pk=True, description="配置ID")
    name = fields.CharField(max_length=100, description="配置名称", default="默认配置")

    # 供应商
    provider = fields.CharField(
        max_length=20,
        description="供应商",
        choices=[
            ("openai", "OpenAI"),
            ("deepseek", "DeepSeek"),
            ("qwen", "通义千问"),
            ("claude", "Claude"),
            ("custom", "自定义"),
        ],
    )

    # API 配置
    api_key = fields.CharField(max_length=255, description="API Key（加密存储）")
    api_base = fields.CharField(max_length=500, null=True, description="自定义 Base URL")
    model = fields.CharField(max_length=100, description="模型名称", default="gpt-4o")

    # 生成参数
    temperature = fields.FloatField(default=0.7, description="温度(0-2)")
    max_tokens = fields.IntField(default=4096, description="最大输出长度")
    timeout = fields.IntField(default=60, description="请求超时(秒)")

    # 思考模式（DeepSeek / OpenAI o-series 等支持）
    thinking_enabled = fields.BooleanField(default=False, description="是否启用思考模式")
    reasoning_effort = fields.CharField(
        max_length=20,
        default="medium",
        description="推理努力程度",
        choices=[("low", "低"), ("medium", "中"), ("high", "高")],
    )

    # 状态
    is_default = fields.BooleanField(default=False, description="是否为默认配置")
    is_enabled = fields.BooleanField(default=True, description="是否启用")
    is_del = fields.BooleanField(default=False, description="是否删除")

    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, description="创建人")

    class Meta:
        table = "ai_config"
        table_description = "AI LLM 配置"


class AiSceneBinding(models.Model):
    """AI 业务场景与 LLM 配置绑定"""
    id = fields.IntField(pk=True)
    scene = fields.CharField(max_length=64, unique=True, description="场景编码")
    config_id = fields.IntField(null=True, description="绑定的 ai_config.id，空表示跟随全局默认")
    overrides = fields.JSONField(default=dict, description="场景级参数覆盖")
    update_by = fields.CharField(max_length=50, default="", description="最后修改人")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ai_scene_binding"
        table_description = "AI 场景模型绑定"


class AiGenerateRecord(models.Model):
    """AI 生成历史记录"""
    id = fields.IntField(pk=True, description="记录ID")
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="ai_generate_records",
        description="所属项目",
    )

    # 生成类型
    generate_type = fields.CharField(
        max_length=30,
        description="生成类型",
        choices=[
            ("api_case", "API测试用例"),
            ("ui_case", "UI功能测试用例"),
            ("api_suite", "API测试套件"),
            ("perf_scene", "性能测试场景"),
            ("test_data", "测试数据"),
            ("requirement_case", "需求导入生成用例"),
            ("requirement_test_point", "需求测试点"),
            ("requirement_test_scheme", "需求测试方案"),
            ("failure_analysis", "失败分析"),
            ("report_summary", "报告摘要"),
        ],
    )

    # 输入摘要
    input_summary = fields.JSONField(default=dict, description="输入摘要")

    # 生成结果
    output_content = fields.JSONField(default=dict, description="生成结果")

    # 使用状态
    status = fields.CharField(
        max_length=20,
        default="pending",
        description="状态: pending/imported/rejected",
    )

    # 关联信息（生成后被导入到哪个实体）
    imported_target_id = fields.IntField(null=True, description="导入目标ID")
    imported_target_type = fields.CharField(max_length=30, null=True, description="导入目标类型")

    # 使用的配置
    ai_config_id = fields.IntField(null=True, description="使用的 AI 配置ID")

    # Token 消耗（若供应商返回）
    tokens_used = fields.IntField(default=0, description="消耗 Token 数")

    # 耗时
    duration_ms = fields.IntField(default=0, description="生成耗时(ms)")

    create_time = fields.DatetimeField(auto_now_add=True)
    create_by = fields.CharField(max_length=50, description="创建人")

    class Meta:
        table = "ai_generate_record"
        table_description = "AI 生成历史记录"


class AiPromptTemplate(models.Model):
    """AI Prompt 模板"""
    id = fields.IntField(pk=True, description="模板ID")
    name = fields.CharField(max_length=100, description="模板名称")
    code = fields.CharField(max_length=50, description="模板编码", unique=True)
    description = fields.TextField(null=True, description="模板描述")

    # 适用场景
    scene_type = fields.CharField(
        max_length=30,
        description="场景类型",
        choices=[
            ("api_case", "API测试用例生成"),
            ("ui_case", "UI测试用例生成"),
            ("requirement_parse", "需求解析"),
            ("requirement_case", "基于需求生成用例"),
            ("failure_analysis", "失败原因分析"),
            ("report_summary", "报告摘要生成"),
            ("test_data", "测试数据生成"),
            ("test_analysis", "测试分析"),
        ],
    )

    # Prompt 内容
    system_prompt = fields.TextField(description="System Prompt")
    user_prompt_template = fields.TextField(description="User Prompt 模板（支持 Jinja2 变量）")

    # 示例（Few-shot）
    examples = fields.JSONField(default=list, description="Few-shot 示例")

    # 版本
    version = fields.IntField(default=1, description="版本号")
    is_default = fields.BooleanField(default=False, description="是否为默认模板")
    is_enabled = fields.BooleanField(default=True, description="是否启用")

    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ai_prompt_template"
        table_description = "AI Prompt 模板"


class AiRequirement(models.Model):
    """AI 需求文档表"""
    id = fields.IntField(pk=True, description="需求ID")
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="ai_requirements",
        description="所属项目",
    )

    # 基本信息
    name = fields.CharField(max_length=200, description="需求名称")
    source_type = fields.CharField(
        max_length=20,
        default="text",
        description="来源: text/markdown/pdf/docx/url",
    )

    # 原始内容
    original_content = fields.TextField(description="原始需求文本内容")

    # AI 解析结果
    parsed_content = fields.JSONField(
        default=dict,
        description="解析后的结构化内容",
    )

    # 关联生成记录
    generated_cases = fields.JSONField(default=list, description="已生成的用例ID列表")

    # 状态
    parse_status = fields.CharField(
        max_length=20,
        default="pending",
        description="解析状态: pending/parsing/parsed/failed",
    )
    parse_error = fields.TextField(null=True, description="解析失败原因")

    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, description="创建人")

    class Meta:
        table = "ai_requirement"
        table_description = "AI 需求文档"


class AiRequirementCase(models.Model):
    """需求文档生成的功能测试用例（禅道格式）"""
    id = fields.IntField(pk=True, description="用例ID")
    requirement = fields.ForeignKeyField(
        "models.AiRequirement",
        related_name="cases",
        description="所属需求",
        on_delete=fields.CASCADE,
    )
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="ai_requirement_cases",
        description="所属项目",
    )

    product = fields.CharField(max_length=200, default="", description="所属产品")
    module = fields.CharField(max_length=200, default="", description="所属模块")
    related_story = fields.TextField(null=True, description="相关研发需求")
    title = fields.CharField(max_length=500, description="用例标题")
    naming_template_id = fields.CharField(max_length=50, null=True, description="标题模板ID")
    naming_template_version = fields.IntField(null=True, description="标题模板版本")
    naming_slots = fields.JSONField(default=dict, description="标题语义槽位快照")
    precondition = fields.TextField(null=True, description="前置条件")
    steps = fields.JSONField(default=list, description="步骤列表 [{step, expect}]")
    priority = fields.CharField(max_length=10, default="2", description="优先级 1-4")
    type = fields.CharField(max_length=50, default="功能测试", description="用例类型")
    stage = fields.CharField(max_length=50, default="系统测试阶段", description="适用阶段")
    keywords = fields.CharField(max_length=500, default="", description="关键词")

    status = fields.CharField(
        max_length=20,
        default="draft",
        description="状态: draft/confirmed/exported",
    )
    source_ref = fields.CharField(max_length=200, null=True, description="来源引用")
    section_ids = fields.JSONField(default=list, description="来源章节ID列表")
    extra = fields.JSONField(default=dict, description="扩展字段（如 test_point_ids）")

    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, description="创建人")

    class Meta:
        table = "ai_requirement_case"
        table_description = "AI 需求功能测试用例"


class AiFunctionalCase(models.Model):
    """功能测试用例库（禅道格式，与需求工作区解耦）"""
    id = fields.IntField(pk=True, description="用例ID")
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="ai_functional_cases",
        description="所属项目",
    )

    product = fields.CharField(max_length=200, default="", description="所属产品")
    module = fields.CharField(max_length=200, default="", description="所属模块")
    related_story = fields.TextField(null=True, description="相关研发需求")
    title = fields.CharField(max_length=500, description="用例标题")
    zentao_case_id = fields.CharField(max_length=64, null=True, description="禅道用例ID（导入时填写）")
    naming_template_id = fields.CharField(max_length=50, null=True, description="标题模板ID")
    naming_template_version = fields.IntField(null=True, description="标题模板版本")
    naming_slots = fields.JSONField(default=dict, description="标题语义槽位快照")
    precondition = fields.TextField(null=True, description="前置条件")
    steps = fields.JSONField(default=list, description="步骤列表 [{step, expect}]")
    priority = fields.CharField(max_length=10, default="2", description="优先级 1-4")
    type = fields.CharField(max_length=50, default="功能测试", description="用例类型")
    stage = fields.CharField(max_length=50, default="系统测试阶段", description="适用阶段")
    keywords = fields.CharField(max_length=500, default="", description="关键词")

    status = fields.CharField(
        max_length=20,
        default="confirmed",
        description="状态: draft/confirmed/archived",
    )
    source_type = fields.CharField(
        max_length=30,
        default="manual",
        description="来源: requirement_copy/test_analysis_copy/zentao_xlsx/manual",
    )
    source_requirement_id = fields.IntField(null=True, description="来源需求ID")
    source_requirement_case_id = fields.IntField(null=True, description="来源工作区用例ID")
    source_import_batch = fields.CharField(max_length=64, null=True, description="禅道导入批次")
    source_file_name = fields.CharField(max_length=255, null=True, description="导入文件名")
    extra = fields.JSONField(default=dict, description="扩展字段")

    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, description="创建人")
    update_by = fields.CharField(max_length=50, null=True, description="修改人")

    class Meta:
        table = "ai_functional_case"
        table_description = "功能测试用例库"


class AiRequirementGenerateJob(models.Model):
    """需求文档批量/补充生成异步任务"""
    id = fields.IntField(pk=True, description="任务ID")
    requirement = fields.ForeignKeyField(
        "models.AiRequirement",
        related_name="generate_jobs",
        description="所属需求",
        on_delete=fields.CASCADE,
    )
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="ai_requirement_generate_jobs",
        description="所属项目",
    )

    status = fields.CharField(
        max_length=20,
        default="pending",
        description="pending/running/completed/failed/cancelled",
    )
    total_batches = fields.IntField(default=0, description="总批次数")
    done_batches = fields.IntField(default=0, description="已完成批次数")
    current_batch_name = fields.CharField(max_length=200, default="", description="当前批次名")
    payload = fields.JSONField(default=dict, description="生成配置快照")
    batch_results = fields.JSONField(default=list, description="各批结果")
    generate_report = fields.JSONField(default=dict, description="汇总报告")
    error = fields.TextField(null=True, description="失败原因")
    tokens_used = fields.IntField(default=0, description="Token消耗")
    duration_ms = fields.IntField(default=0, description="耗时ms")
    is_del = fields.BooleanField(default=False, description="软删除")
    create_by = fields.CharField(max_length=50, default="", description="创建人")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    finish_time = fields.DatetimeField(null=True, description="结束时间")

    class Meta:
        table = "ai_requirement_generate_job"
        table_description = "AI需求用例批量生成任务"


class AiRequirementTestPoint(models.Model):
    """需求文档 AI 测试点（思维导图节点）"""
    id = fields.IntField(pk=True, description="测试点ID")
    requirement = fields.ForeignKeyField(
        "models.AiRequirement",
        related_name="test_points",
        description="所属需求",
        on_delete=fields.CASCADE,
    )
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="ai_requirement_test_points",
        description="所属项目",
    )

    title = fields.CharField(max_length=300, description="测试点标题")
    description = fields.TextField(null=True, description="验证说明")
    test_type = fields.CharField(max_length=30, default="正向", description="测试类型")
    priority = fields.CharField(max_length=10, default="P2", description="优先级")
    module_path = fields.CharField(max_length=200, default="", description="模块路径")
    main_module = fields.CharField(max_length=100, default="", description="主模块")
    sub_module = fields.CharField(max_length=100, default="", description="子模块")
    acceptance_ref = fields.TextField(null=True, description="验收依据")
    section_ids = fields.JSONField(default=list, description="来源章节ID")
    source_ref = fields.CharField(max_length=200, null=True, description="来源批次")
    status = fields.CharField(
        max_length=20,
        default="draft",
        description="draft/confirmed",
    )
    sort_order = fields.IntField(default=0, description="排序")
    extra = fields.JSONField(default=dict, description="扩展字段")

    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, description="创建人")

    class Meta:
        table = "ai_requirement_test_point"
        table_description = "AI 需求测试点"


class AiRequirementTestScheme(models.Model):
    """需求文档 AI 测试方案"""
    id = fields.IntField(pk=True, description="方案ID")
    requirement = fields.ForeignKeyField(
        "models.AiRequirement",
        related_name="test_schemes",
        description="所属需求",
        on_delete=fields.CASCADE,
    )
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="ai_requirement_test_schemes",
        description="所属项目",
    )

    title = fields.CharField(max_length=200, description="方案标题")
    version = fields.IntField(default=1, description="版本号")
    status = fields.CharField(
        max_length=20,
        default="draft",
        description="draft/confirmed",
    )
    content = fields.JSONField(default=dict, description="结构化方案内容")
    content_md = fields.TextField(null=True, description="Markdown 正文")
    test_point_ids = fields.JSONField(default=list, description="引用的测试点ID")
    scope_section_ids = fields.JSONField(default=list, description="章节范围")
    generate_report = fields.JSONField(default=dict, description="生成报告")

    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, description="创建人")

    class Meta:
        table = "ai_requirement_test_scheme"
        table_description = "AI 需求测试方案"


class AiUsageLog(models.Model):
    """AI 模型调用使用记录（全场景审计）"""
    id = fields.IntField(pk=True, description="记录ID")
    scene = fields.CharField(max_length=64, description="场景编码")
    scene_label = fields.CharField(max_length=100, default="", description="场景名称")
    user_id = fields.IntField(null=True, description="用户ID")
    username = fields.CharField(max_length=50, default="", description="用户名")
    project_id = fields.IntField(null=True, description="项目ID")
    project_name = fields.CharField(max_length=100, default="", description="项目名称")
    ai_config_id = fields.IntField(null=True, description="AI 配置ID")
    model = fields.CharField(max_length=100, default="", description="模型名称")
    provider = fields.CharField(max_length=20, default="", description="供应商")
    tokens_used = fields.IntField(default=0, description="Token 消耗")
    duration_ms = fields.IntField(default=0, description="耗时(ms)")
    status = fields.CharField(
        max_length=20,
        default="success",
        description="状态: success/failed",
    )
    input_summary = fields.TextField(default="", description="输入摘要")
    output_summary = fields.TextField(null=True, description="输出摘要")
    extra = fields.JSONField(default=dict, description="扩展信息")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")

    class Meta:
        table = "ai_usage_log"
        table_description = "AI 模型使用记录"


class AiRecordSession(models.Model):
    """AI 录制会话表"""
    id = fields.IntField(pk=True, description="录制ID")
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="ai_record_sessions",
        description="所属项目",
        null=True,
    )

    # 执行设备
    device_id = fields.CharField(max_length=100, null=True, description="Runner 设备ID")

    # 录制目标
    url = fields.CharField(max_length=500, description="录制起始页面 URL")
    description = fields.TextField(null=True, description="用户填写的描述")

    # AI 优化配置
    use_ai_optimize = fields.BooleanField(default=False, description="是否使用 LLM 优化步骤描述")

    # 状态
    status = fields.CharField(
        max_length=20,
        default="pending",
        description="状态: pending/recording/converting/completed/failed",
    )

    # 原始录制数据
    raw_actions = fields.JSONField(default=list, description="Runner 上报的原始操作列表")
    screenshots = fields.JSONField(default=list, description="截图文件路径列表")
    actions_count = fields.IntField(default=0, description="当前已记录的操作数量")

    # 转换后的步骤
    steps = fields.JSONField(default=list, description="转换后的平台标准步骤")
    
    # AI 优化后的步骤（用户手动触发优化后保存）
    optimized_steps = fields.JSONField(default=list, description="AI 优化后的步骤")

    # 错误信息
    error = fields.TextField(null=True, description="错误信息")

    # 耗时
    duration_ms = fields.IntField(default=0, description="录制耗时(ms)")

    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, description="创建人")

    class Meta:
        table = "ai_record_session"
        table_description = "AI 录制会话"


class AiQaEvalSet(models.Model):
    """问答准确性评测集"""
    id = fields.IntField(pk=True)
    project_id = fields.IntField(description="项目ID")
    name = fields.CharField(max_length=200, description="评测集名称")
    description = fields.TextField(null=True, description="描述")
    is_del = fields.BooleanField(default=False)
    create_by = fields.CharField(max_length=50, default="")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ai_qa_eval_set"
        table_description = "问答评测集"


class AiQaEvalCase(models.Model):
    """问答评测用例"""
    id = fields.IntField(pk=True)
    set_id = fields.IntField(description="评测集ID")
    seq_no = fields.IntField(null=True, description="Excel序号")
    question = fields.TextField(description="测试问题")
    expected_points = fields.JSONField(default=list, description="标准要点")
    expected_answer = fields.TextField(null=True, description="标准完整答案")
    preset_answer = fields.TextField(null=True, description="预置实际回答(导入或批量拉取)")
    chat_path = fields.JSONField(default=list, description="问答目录")
    multi_turn = fields.BooleanField(default=False, description="是否多轮")
    scenario_type = fields.CharField(max_length=64, default="", description="场景类型")
    source_file = fields.CharField(max_length=500, default="", description="来源文件")
    file_type = fields.CharField(max_length=100, default="", description="文件类型")
    category = fields.CharField(max_length=100, default="", description="分类")
    case_type = fields.CharField(max_length=32, default="事实", description="题型")
    sort_order = fields.IntField(default=0)
    is_del = fields.BooleanField(default=False)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ai_qa_eval_case"
        table_description = "问答评测用例"


class AiQaEvalTarget(models.Model):
    """被测问答 API 配置"""
    id = fields.IntField(pk=True)
    project_id = fields.IntField(description="项目ID")
    name = fields.CharField(max_length=200, description="配置名称")
    config = fields.JSONField(default=dict, description="API 配置")
    is_del = fields.BooleanField(default=False)
    create_by = fields.CharField(max_length=50, default="")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ai_qa_eval_target"
        table_description = "被测问答API"


class AiQaEvalRun(models.Model):
    """问答评测跑批记录"""
    id = fields.IntField(pk=True)
    project_id = fields.IntField()
    set_id = fields.IntField()
    target_id = fields.IntField(null=True, description="被测API，仅评判模式可为空")
    judge_config_id = fields.IntField(null=True)
    status = fields.CharField(max_length=20, default="pending")
    total_count = fields.IntField(default=0)
    passed_count = fields.IntField(default=0)
    failed_count = fields.IntField(default=0)
    avg_score = fields.FloatField(default=0)
    pass_rate = fields.FloatField(default=0)
    error = fields.TextField(null=True)
    extra = fields.JSONField(default=dict)
    create_by = fields.CharField(max_length=50, default="")
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)
    create_time = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "ai_qa_eval_run"
        table_description = "问答评测跑批"


class AiQaEvalResult(models.Model):
    """问答评测单题结果"""
    id = fields.IntField(pk=True)
    run_id = fields.IntField()
    case_id = fields.IntField()
    question = fields.TextField()
    actual_answer = fields.TextField(null=True)
    score = fields.FloatField(default=0)
    passed = fields.BooleanField(default=False)
    hallucination = fields.BooleanField(default=False)
    level = fields.CharField(max_length=20, default="")
    dimension_scores = fields.JSONField(default=dict)
    missed_points = fields.JSONField(default=list)
    extra_issues = fields.JSONField(default=list)
    reason = fields.TextField(null=True)
    judge_raw = fields.TextField(null=True)
    api_error = fields.TextField(null=True)
    api_latency_ms = fields.IntField(default=0)
    api_meta = fields.JSONField(default=dict, description="API扩展字段")
    judge_tokens = fields.IntField(default=0)
    status = fields.CharField(max_length=20, default="pending")
    manual_status = fields.CharField(max_length=20, default="pending", description="人工审核状态")
    manual_comment = fields.TextField(null=True, description="人工审核备注")
    manual_reviewed_by = fields.CharField(max_length=50, default="", description="审核人")
    manual_reviewed_at = fields.DatetimeField(null=True, description="审核时间")
    create_time = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "ai_qa_eval_result"
        table_description = "问答评测结果"


class BrowserLabCase(models.Model):
    """智能浏览器用例库（可重复执行的自然语言场景）"""
    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="browser_lab_cases",
        description="所属项目",
    )
    name = fields.CharField(max_length=200, description="用例名称")
    description = fields.TextField(null=True, description="用例说明")
    task_text = fields.TextField(description="自然语言任务描述")
    start_url = fields.CharField(max_length=500, description="起始 URL")
    config_json = fields.JSONField(default=dict, description="默认运行配置")
    tags = fields.CharField(max_length=200, default="", description="标签，逗号分隔")
    created_by = fields.CharField(max_length=50, default="", description="创建人")
    update_by = fields.CharField(max_length=50, default="", description="更新人")
    run_count = fields.IntField(default=0, description="累计执行次数")
    last_run_at = fields.DatetimeField(null=True, description="最近执行时间")
    last_status = fields.CharField(max_length=20, null=True, description="最近执行状态")
    is_del = fields.BooleanField(default=False, description="软删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "browser_lab_case"
        table_description = "智能浏览器用例"


class BrowserLabTask(models.Model):
    """智能浏览器（browser-use）演示/探索任务"""
    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="browser_lab_tasks",
        description="所属项目",
    )
    case_id = fields.IntField(null=True, description="来源用例ID")
    case_name = fields.CharField(max_length=200, null=True, description="用例名称快照")
    source_task_id = fields.IntField(null=True, description="重跑来源任务ID")
    created_by = fields.CharField(max_length=50, default="", description="创建人")
    task_text = fields.TextField(description="自然语言任务描述")
    start_url = fields.CharField(max_length=500, description="起始 URL")
    status = fields.CharField(
        max_length=20,
        default="pending",
        description="pending|running|done|failed|stopped",
    )
    engine = fields.CharField(max_length=32, default="browser_use", description="执行引擎")
    config_json = fields.JSONField(default=dict, description="运行配置")
    step_log = fields.JSONField(default=list, description="步骤事件日志")
    result_summary = fields.TextField(null=True, description="最终结果摘要")
    tokens_used = fields.IntField(default=0, description="Token 消耗（估算）")
    steps_count = fields.IntField(default=0, description="实际步数")
    gif_path = fields.CharField(max_length=500, null=True, description="回放 GIF 相对路径")
    error_message = fields.TextField(null=True, description="失败原因")
    ai_config_id = fields.IntField(null=True, description="使用的 AI 配置")
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)
    create_time = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "browser_lab_task"
        table_description = "智能浏览器任务"


class AssistantSession(models.Model):
    """平台内 AI 助手会话（按用户 + 项目，支持多会话）"""
    id = fields.IntField(pk=True, description="会话ID")
    user_id = fields.IntField(description="用户ID")
    project_id = fields.IntField(null=True, description="项目ID")
    title = fields.CharField(max_length=200, default="", description="会话标题")
    messages = fields.JSONField(default=list, description="消息列表（最多 40 条）")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "assistant_session"
        table_description = "平台 AI 助手会话"
