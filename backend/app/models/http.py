from tortoise import fields, models


class ApiDefinition(models.Model):
    """接口定义表"""
    id = fields.IntField(pk=True, description="接口ID")
    name = fields.CharField(max_length=100, description="接口名称")
    project = fields.ForeignKeyField("models.Project", related_name="api_definitions", description="所属项目")
    catalog = fields.ForeignKeyField("models.TestCatalog", related_name="api_defs", null=True, description="所属目录")
    
    # 请求基本信息
    method = fields.CharField(max_length=10, description="请求方法")
    path = fields.CharField(max_length=500, description="接口路径")
    description = fields.TextField(null=True, description="接口描述")
    
    # 请求配置
    base_url = fields.CharField(max_length=500, null=True, description="基础URL")
    headers = fields.JSONField(default=dict, description="请求头")
    global_header_policy = fields.JSONField(default=dict, description="全局Header使用策略")
    params = fields.JSONField(default=list, description="查询参数列表")
    body = fields.JSONField(default=dict, description="请求体")
    body_type = fields.CharField(max_length=20, default="json", description="请求体类型")
    body_fields = fields.JSONField(default=list, description="form-data 字段")
    
    # 响应结构定义（支持从 Swagger/Postman 导入或手动维护）
    response_schema = fields.JSONField(default=dict, null=True, description="响应结构定义")
    
    # 版本管理
    version = fields.IntField(default=1, description="版本号")
    version_history = fields.JSONField(default=list, description="版本历史")
    
    # 导入来源
    source = fields.CharField(max_length=50, null=True, description="来源")
    source_id = fields.CharField(max_length=200, null=True, description="来源ID")
    
    # 状态
    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, description="创建人")
    update_by = fields.CharField(max_length=50, null=True, description="修改人")

    class Meta:
        table = "api_definition"
        table_description = "接口定义"


class ApiTestCase(models.Model):
    """接口测试用例表"""
    id = fields.IntField(pk=True, description="用例ID")
    name = fields.CharField(max_length=100, description="用例名称")
    api = fields.ForeignKeyField("models.ApiDefinition", related_name="test_cases", description="关联接口")
    project = fields.ForeignKeyField("models.Project", related_name="api_test_cases", description="所属项目")
    catalog = fields.ForeignKeyField("models.TestCatalog", related_name="api_cases", null=True, description="所属目录")
    
    # 请求配置（覆盖接口定义）
    request_headers = fields.JSONField(default=dict, description="请求头覆盖")
    global_header_policy = fields.JSONField(default=dict, description="全局Header使用策略")
    request_params = fields.JSONField(default=list, description="请求参数覆盖")
    request_body = fields.JSONField(default=dict, description="请求体覆盖")
    request_body_type = fields.CharField(max_length=20, default="json", description="请求体类型")
    request_body_fields = fields.JSONField(default=list, description="form-data 字段覆盖")
    
    # 断言配置
    assertions = fields.JSONField(default=list, description="断言规则")
    assertion_groups = fields.JSONField(default=list, description="条件分支断言组")
    
    # 变量提取
    extractors = fields.JSONField(default=list, description="变量提取规则")
    
    # 依赖配置
    depends_on = fields.JSONField(default=list, description="依赖用例ID列表")
    
    # 执行配置
    timeout = fields.IntField(default=30, description="超时时间(秒)")
    retry_count = fields.IntField(default=0, description="重试次数")

    # 前置/后置脚本
    pre_script = fields.TextField(null=True, description="前置脚本（Python，请求前执行）")
    post_script = fields.TextField(null=True, description="后置脚本（Python，请求后执行）")

    # 数据库断言（执行后 SELECT 校验）
    db_assertions = fields.JSONField(default=list, description="数据库断言规则")

    # 数据集（数据驱动）
    data_set = fields.JSONField(default=list, description="数据集，格式: [{col1:v1, col2:v2}, ...]")

    # 分类和标签
    tags = fields.JSONField(default=list, description="标签")
    priority = fields.CharField(max_length=10, default="P2", description="优先级 P0/P1/P2/P3")

    # 版本快照（记录用例创建/更新时关联接口的版本号，用于过期检测）
    api_version_snapshot = fields.IntField(default=1, description="创建/更新时接口版本快照")
    
    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, description="创建人")
    update_by = fields.CharField(max_length=50, null=True, description="修改人")

    class Meta:
        table = "api_test_case"
        table_description = "接口测试用例"


class ApiRunRecord(models.Model):
    """接口用例执行记录"""
    id = fields.IntField(pk=True, description="记录ID")
    case = fields.ForeignKeyField("models.ApiTestCase", related_name="run_records", description="关联用例")
    project = fields.ForeignKeyField("models.Project", related_name="api_run_records", description="所属项目")
    
    # 关联套件执行记录（用于套件执行时关联）
    suite_run_record = fields.ForeignKeyField("models.ApiSuiteRunRecord", related_name="case_records", null=True, description="套件执行记录")
    
    # 执行状态
    status = fields.CharField(max_length=20, default="pending", description="执行状态")
    
    # 请求数据
    request_url = fields.CharField(max_length=1000, null=True, description="请求URL")
    request_method = fields.CharField(max_length=10, null=True, description="请求方法")
    request_headers = fields.JSONField(default=dict, description="请求头")
    request_body = fields.TextField(null=True, description="请求体")
    
    # 响应数据
    response_status = fields.IntField(null=True, description="响应状态码")
    response_headers = fields.JSONField(default=dict, description="响应头")
    response_body = fields.TextField(null=True, description="响应体")
    response_time = fields.FloatField(default=0, description="响应时间(ms)")
    
    # 断言结果
    assertions_result = fields.JSONField(default=list, description="断言结果")
    error_msg = fields.TextField(null=True, description="错误信息")
    
    # 提取的变量
    extracted_vars = fields.JSONField(default=dict, description="提取的变量")
    
    # 请求详情（包含变量替换信息）
    request_detail = fields.JSONField(default=dict, description="请求详情")
    
    start_time = fields.DatetimeField(auto_now_add=True)
    end_time = fields.DatetimeField(null=True)
    run_by = fields.CharField(max_length=50, description="执行人")

    # 数据驱动字段
    data_run_index = fields.IntField(null=True, description="数据驱动第几轮（0-based），null 表示非数据驱动")
    data_row_label = fields.CharField(max_length=200, null=True, description="本轮数据摘要（用于展示）")

    class Meta:
        table = "api_run_record"
        table_description = "接口执行记录"


class MockApi(models.Model):
    """Mock接口表"""
    id = fields.IntField(pk=True, description="Mock ID")
    name = fields.CharField(max_length=100, description="Mock名称")
    project = fields.ForeignKeyField("models.Project", related_name="mock_apis", description="所属项目")
    
    # 匹配规则
    method = fields.CharField(max_length=10, description="请求方法")
    path = fields.CharField(max_length=500, description="匹配路径")
    match_rules = fields.JSONField(default=dict, description="高级匹配规则")
    
    # 响应配置
    response_status = fields.IntField(default=200, description="响应状态码")
    response_headers = fields.JSONField(default=dict, description="响应头")
    response_body = fields.JSONField(default=dict, description="响应体")
    response_delay = fields.IntField(default=0, description="延迟响应(ms)")
    
    # 统计
    call_count = fields.IntField(default=0, description="调用次数")
    last_call_time = fields.DatetimeField(null=True, description="最后调用时间")
    
    is_enabled = fields.BooleanField(default=True, description="是否启用")
    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "mock_api"
        table_description = "Mock接口"



class ApiTestSuite(models.Model):
    """接口测试套件表"""
    id = fields.IntField(pk=True, description="套件ID")
    name = fields.CharField(max_length=100, description="套件名称")
    project = fields.ForeignKeyField("models.Project", related_name="api_test_suites", description="所属项目")
    catalog = fields.ForeignKeyField(
        "models.TestCatalog", related_name="api_suites", null=True, description="所属目录"
    )
    
    # 执行配置
    env_id = fields.IntField(null=True, description="默认环境ID")
    timeout = fields.IntField(default=300, description="总超时时间(秒)")
    retry_count = fields.IntField(default=0, description="失败重试次数")
    
    # 执行策略
    stop_on_failure = fields.BooleanField(default=False, description="失败时停止")
    parallel = fields.BooleanField(default=False, description="并行执行")

    # 数据工厂：套件级 SQL 模板与库断言
    setup_sql_ids = fields.JSONField(default=list, description="前置 SQL 模板 ID 列表")
    teardown_sql_ids = fields.JSONField(default=list, description="后置 SQL 模板 ID 列表")
    db_assertions = fields.JSONField(default=list, description="套件级数据库断言")

    description = fields.TextField(null=True, description="描述")
    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, description="创建人")
    update_by = fields.CharField(max_length=50, null=True, description="修改人")

    class Meta:
        table = "api_test_suite"
        table_description = "接口测试套件"


class ApiSuiteCase(models.Model):
    """套件与用例关联表"""
    id = fields.IntField(pk=True, description="ID")
    suite = fields.ForeignKeyField("models.ApiTestSuite", related_name="suite_cases", description="所属套件")
    case = fields.ForeignKeyField("models.ApiTestCase", related_name="case_suites", description="关联用例")
    sort = fields.IntField(default=0, description="排序")
    
    class Meta:
        table = "api_suite_case"
        table_description = "套件用例关联"


class ApiSuiteRunRecord(models.Model):
    """套件执行记录"""
    id = fields.IntField(pk=True, description="记录ID")
    suite = fields.ForeignKeyField("models.ApiTestSuite", related_name="run_records", description="关联套件")
    project = fields.ForeignKeyField("models.Project", related_name="api_suite_run_records", description="所属项目")
    
    # 执行信息
    status = fields.CharField(max_length=20, default="running", description="状态: pending/running/success/failed")
    trigger_type = fields.CharField(max_length=20, default="manual", description="触发方式: manual/cron/plan/assistant")
    
    # 执行统计
    total_cases = fields.IntField(default=0, description="总用例数")
    success_cases = fields.IntField(default=0, description="成功数")
    failed_cases = fields.IntField(default=0, description="失败数")
    skipped_cases = fields.IntField(default=0, description="跳过数")
    
    # 时间
    start_time = fields.DatetimeField(auto_now_add=True)
    end_time = fields.DatetimeField(null=True)
    duration = fields.FloatField(default=0, description="执行耗时(ms)")
    
    # 环境
    env_id = fields.IntField(null=True, description="执行环境ID")
    env_name = fields.CharField(max_length=100, null=True, description="环境名称")
    
    # 报告
    report_url = fields.CharField(max_length=500, null=True, description="报告链接")
    
    run_by = fields.CharField(max_length=50, description="执行人")

    hooks_result = fields.JSONField(default=dict, description="数据工厂 setup/teardown/套件断言结果")
    
    class Meta:
        table = "api_suite_run_record"
        table_description = "接口套件执行记录"


class ApiCronJob(models.Model):
    """接口定时任务"""
    id = fields.CharField(pk=True, max_length=100, description="任务ID")
    name = fields.CharField(max_length=100, description="任务名称")
    project = fields.ForeignKeyField("models.Project", related_name="api_cron_jobs", description="所属项目")
    suite = fields.ForeignKeyField("models.ApiTestSuite", related_name="cron_jobs", null=True, on_delete=fields.SET_NULL, description="关联套件（与 plan 二选一）")
    plan = fields.ForeignKeyField("models.ApiTestPlan", related_name="cron_jobs", null=True, on_delete=fields.SET_NULL, description="关联测试计划（与 suite 二选一）")

    # 定时配置
    run_type = fields.CharField(max_length=20, description="类型: Interval/date/crontab")
    interval = fields.IntField(default=3600, description="间隔(秒)")
    run_date = fields.DatetimeField(null=True, description="固定执行时间")
    crontab = fields.JSONField(default=dict, description="cron表达式")

    # 环境
    env_id = fields.IntField(description="执行环境ID")

    # 执行记录关联
    last_run_record_id = fields.IntField(null=True, description="最后一次执行记录ID")
    last_run_time = fields.DatetimeField(null=True, description="最后一次执行时间")
    last_run_status = fields.CharField(max_length=20, null=True, description="最后一次执行状态")

    state = fields.BooleanField(default=False, description="是否启用")
    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, description="创建人")
    update_by = fields.CharField(max_length=50, null=True, description="修改人")

    class Meta:
        table = "api_cron_job"
        table_description = "接口定时任务"


class ApiTestPlan(models.Model):
    """接口测试计划"""
    id = fields.IntField(pk=True, description="计划ID")
    name = fields.CharField(max_length=100, description="计划名称")
    project = fields.ForeignKeyField("models.Project", related_name="api_test_plans", description="所属项目")
    description = fields.TextField(null=True, description="计划描述")
    env_id = fields.IntField(null=True, description="默认执行环境ID")
    variables = fields.JSONField(default=dict, description="计划级全局变量")
    parallel = fields.BooleanField(default=False, description="是否并行执行各 Item")
    is_template = fields.BooleanField(default=False, description="是否为计划模板")
    catalog = fields.ForeignKeyField(
        "models.TestCatalog", null=True, related_name="api_plans", description="所属目录"
    )
    is_del = fields.BooleanField(default=False, description="是否删除")
    create_by = fields.CharField(max_length=50, description="创建人")
    update_by = fields.CharField(max_length=50, null=True, description="修改人")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "api_test_plan"
        table_description = "接口测试计划"


class ApiPlanItem(models.Model):
    """测试计划内容项"""
    id = fields.IntField(pk=True, description="ID")
    plan = fields.ForeignKeyField("models.ApiTestPlan", related_name="items", on_delete=fields.CASCADE, description="所属计划")
    item_type = fields.CharField(max_length=10, description="类型: suite/case")
    suite = fields.ForeignKeyField("models.ApiTestSuite", related_name="plan_items", null=True, on_delete=fields.SET_NULL, description="关联套件")
    case = fields.ForeignKeyField("models.ApiTestCase", related_name="plan_items", null=True, on_delete=fields.SET_NULL, description="关联用例")
    sort = fields.IntField(default=0, description="排序")
    depends_on = fields.JSONField(default=list, description="依赖 item ID 列表（前置 item 必须成功）")

    class Meta:
        table = "api_plan_item"
        table_description = "测试计划内容项"


class ApiPlanRunRecord(models.Model):
    """测试计划执行记录"""
    id = fields.IntField(pk=True, description="记录ID")
    plan = fields.ForeignKeyField("models.ApiTestPlan", related_name="run_records", on_delete=fields.CASCADE, description="所属计划")
    project = fields.ForeignKeyField("models.Project", related_name="plan_run_records", description="所属项目")
    status = fields.CharField(max_length=20, description="执行状态: running/success/failed")
    trigger_type = fields.CharField(max_length=20, default="manual", description="触发类型: manual/cron/assistant")
    total_cases = fields.IntField(default=0, description="总用例数")
    success_cases = fields.IntField(default=0, description="成功用例数")
    failed_cases = fields.IntField(default=0, description="失败用例数")
    env_id = fields.IntField(null=True, description="执行环境ID")
    env_name = fields.CharField(max_length=100, null=True, description="执行环境名称")
    duration = fields.FloatField(null=True, description="总耗时(ms)")
    item_results = fields.JSONField(default=list, description="各 Item 执行结果快照")
    run_by = fields.CharField(max_length=50, default="admin", description="执行人")
    start_time = fields.DatetimeField(auto_now_add=True, description="开始时间")
    end_time = fields.DatetimeField(null=True, description="结束时间")

    class Meta:
        table = "api_plan_run_record"
        table_description = "测试计划执行记录"


class ApiAuthConfig(models.Model):
    """API Token 授权配置"""
    id = fields.IntField(pk=True, description="配置ID")
    project = fields.ForeignKeyField("models.Project", related_name="api_auth_configs", description="所属项目")
    environment = fields.ForeignKeyField("models.Environment", related_name="api_auth_configs", description="生效环境")
    name = fields.CharField(max_length=100, description="授权名称")
    auth_type = fields.CharField(max_length=20, default="api_login", description="api_login/custom_code")
    login_api = fields.ForeignKeyField(
        "models.ApiDefinition", related_name="auth_configs", null=True, on_delete=fields.SET_NULL,
        description="登录接口",
    )
    extractors = fields.JSONField(default=list, description="登录响应提取规则")
    custom_code = fields.TextField(null=True, description="自定义授权代码")
    ttl_minutes = fields.IntField(default=1440, description="缓存有效期(分钟)")
    refresh_before_minutes = fields.IntField(default=5, description="提前刷新(分钟)")
    refresh_mode = fields.CharField(max_length=30, default="on_execute", description="刷新模式")
    is_enabled = fields.BooleanField(default=True, description="是否启用")
    cache_data = fields.JSONField(default=dict, description="授权缓存数据")
    cache_expires_at = fields.DatetimeField(null=True, description="缓存过期时间")
    last_refresh_time = fields.DatetimeField(null=True, description="最近刷新时间")
    last_refresh_error = fields.TextField(null=True, description="最近刷新错误")
    is_del = fields.BooleanField(default=False, description="是否删除")
    create_by = fields.CharField(max_length=50, default="", description="创建人")
    update_by = fields.CharField(max_length=50, null=True, description="修改人")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "api_auth_config"
        table_description = "API Token 授权配置"


class HeaderTemplate(models.Model):
    """Header 模板（编辑时导入用，不参与运行时自动合并）"""
    id = fields.IntField(pk=True, description="模板ID")
    project = fields.ForeignKeyField("models.Project", related_name="header_templates", description="所属项目")
    name = fields.CharField(max_length=100, description="模板名称")
    description = fields.TextField(null=True, description="模板说明")
    headers = fields.JSONField(default=list, description="Header 列表 [{key, value, description}]")
    is_default = fields.BooleanField(default=False, description="是否默认模板")
    sort_order = fields.IntField(default=0, description="排序")
    is_del = fields.BooleanField(default=False, description="是否删除")
    create_by = fields.CharField(max_length=50, default="", description="创建人")
    update_by = fields.CharField(max_length=50, null=True, description="修改人")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "header_template"
        table_description = "Header 模板"


class EnvDatasource(models.Model):
    """环境级数据库数据源（数据工厂）"""
    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField("models.Project", related_name="env_datasources", description="所属项目")
    environment = fields.ForeignKeyField("models.Environment", related_name="datasources", description="生效环境")
    name = fields.CharField(max_length=100, description="数据源名称")
    db_type = fields.CharField(max_length=20, default="mysql", description="数据库类型")
    host = fields.CharField(max_length=255, description="主机")
    port = fields.IntField(default=3306, description="端口")
    database_name = fields.CharField(max_length=128, description="数据库名")
    username = fields.CharField(max_length=128, description="用户名")
    password_encrypted = fields.TextField(null=True, description="加密密码")
    allow_write = fields.BooleanField(default=False, description="是否允许写操作")
    max_rows = fields.IntField(default=100, description="查询最大返回行数")
    timeout_seconds = fields.IntField(default=10, description="超时秒数")
    is_default = fields.BooleanField(default=False, description="环境默认数据源")
    is_enabled = fields.BooleanField(default=True, description="是否启用")
    is_del = fields.BooleanField(default=False)
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "env_datasource"
        table_description = "环境级数据库数据源"


class SqlTemplate(models.Model):
    """数据工厂 SQL 模板"""
    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField("models.Project", related_name="sql_templates", description="所属项目")
    environment = fields.ForeignKeyField(
        "models.Environment", related_name="sql_templates", null=True, on_delete=fields.SET_NULL,
        description="可选绑定环境",
    )
    datasource = fields.ForeignKeyField("models.EnvDatasource", related_name="sql_templates", description="数据源")
    name = fields.CharField(max_length=100, description="模板名称")
    template_type = fields.CharField(max_length=20, default="setup", description="setup/teardown/query")
    sql_text = fields.TextField(description="SQL 模板")
    description = fields.TextField(null=True, description="描述")
    is_enabled = fields.BooleanField(default=True, description="是否启用")
    is_del = fields.BooleanField(default=False)
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "sql_template"
        table_description = "数据工厂 SQL 模板"
