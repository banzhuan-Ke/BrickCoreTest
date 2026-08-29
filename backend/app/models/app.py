"""
App 自动化测试相关模型（Android 优先，u2 + Airtest 图像）
"""
from tortoise import fields, models


class AppCase(models.Model):
    """App 测试用例"""
    id = fields.IntField(pk=True, auto_increment=True, description="用例id")
    name = fields.CharField(max_length=100, description="用例名称")
    project = fields.ForeignKeyField("models.Project", related_name="app_cases", description="所属项目")
    catalog = fields.ForeignKeyField(
        "models.TestCatalog", null=True, related_name="app_cases", description="所属目录"
    )
    steps = fields.JSONField(default=list, description="用例执行步骤")
    level = fields.CharField(max_length=10, default="P2", description="用例等级 P0-P4")
    platform_scope = fields.CharField(
        max_length=20, default="android", description="目标平台 android|ios|harmony|all"
    )
    driver_mode = fields.CharField(
        max_length=20, default="hybrid", description="native|vision|hybrid|hybrid_web|mobile_chrome"
    )
    description = fields.TextField(null=True, description="用例描述")
    tags = fields.JSONField(default=list, description="用例标签（含 quarantine）")
    username = fields.CharField(max_length=50, description="创建人")
    update_by = fields.CharField(max_length=50, null=True, description="最后更新人")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    is_del = fields.BooleanField(default=False, description="是否删除")

    class Meta:
        table = "app_case"
        table_description = "App测试用例"


class AppElement(models.Model):
    """App 元素库（控件 + 图像模板）"""
    id = fields.IntField(pk=True, auto_increment=True, description="元素id")
    name = fields.CharField(max_length=100, description="逻辑元素名")
    project = fields.ForeignKeyField("models.Project", related_name="app_elements", description="所属项目")
    element_type = fields.CharField(max_length=20, description="control|image")
    locator = fields.JSONField(default=dict, description="Locator DSL")
    platform_map = fields.JSONField(default=dict, description="多平台定位覆盖")
    remark = fields.CharField(max_length=255, default="", description="备注")
    username = fields.CharField(max_length=50, description="创建人")
    update_by = fields.CharField(max_length=50, null=True, description="最后更新人")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    is_del = fields.BooleanField(default=False, description="是否删除")

    class Meta:
        table = "app_element"
        table_description = "App元素库"


class AppSuite(models.Model):
    """App 测试套件"""
    id = fields.IntField(pk=True, auto_increment=True, description="套件id")
    name = fields.CharField(max_length=100, description="套件名称")
    project = fields.ForeignKeyField("models.Project", related_name="app_suites", description="所属项目")
    catalog = fields.ForeignKeyField(
        "models.TestCatalog", null=True, related_name="app_suites", description="所属目录"
    )
    pre_actions = fields.JSONField(default=list, description="前置步骤")
    setup_sql_ids = fields.JSONField(default=list, description="前置 SQL 模板 ID")
    teardown_sql_ids = fields.JSONField(default=list, description="后置 SQL 模板 ID")
    db_assertions = fields.JSONField(default=list, description="套件级数据库断言")
    suite_type = fields.CharField(
        max_length=10, default="1", description="1 功能 / 2 场景"
    )
    stop_on_failure = fields.BooleanField(default=False, description="用例失败时停止后续用例")
    propagate_variables = fields.BooleanField(default=False, description="链路变量传递")
    username = fields.CharField(max_length=50, description="创建人")
    update_by = fields.CharField(max_length=50, null=True, description="最后更新人")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    is_del = fields.BooleanField(default=False, description="是否删除")

    class Meta:
        table = "app_suite"
        table_description = "App测试套件"


class AppSuiteStep(models.Model):
    """套件-用例关联"""
    id = fields.IntField(pk=True, auto_increment=True, description="关联id")
    suite = fields.ForeignKeyField("models.AppSuite", related_name="steps", description="所属套件")
    case = fields.ForeignKeyField("models.AppCase", related_name="suite_steps", description="关联用例")
    sort = fields.IntField(default=0, description="执行顺序")
    skip = fields.BooleanField(default=False, description="是否跳过")
    is_del = fields.BooleanField(default=False, description="是否删除")

    class Meta:
        table = "app_suite_step"
        table_description = "App套件用例关联"


class AppPlan(models.Model):
    """App 测试计划"""
    id = fields.IntField(pk=True, auto_increment=True, description="计划id")
    name = fields.CharField(max_length=255, description="计划名称")
    project = fields.ForeignKeyField("models.Project", related_name="app_plans", description="所属项目")
    catalog = fields.ForeignKeyField(
        "models.TestCatalog", null=True, related_name="app_plans", description="所属目录"
    )
    suites = fields.ManyToManyField(
        "models.AppSuite",
        related_name="app_plans",
        through="app_plan_app_suite",
        forward_key="appsuite_id",
        backward_key="app_plan_id",
        description="计划套件",
    )
    parallel = fields.BooleanField(default=False, description="计划级并行")
    record_video = fields.BooleanField(default=True, description="执行时录制用例视频")
    username = fields.CharField(max_length=50, description="创建人")
    update_by = fields.CharField(max_length=50, null=True, description="最后更新人")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    is_del = fields.BooleanField(default=False, description="是否删除")

    class Meta:
        table = "app_plan"
        table_description = "App测试计划"


class AppPlanExecution(models.Model):
    """App 计划执行记录"""
    id = fields.IntField(pk=True, auto_increment=True, description="计划执行id")
    project = fields.ForeignKeyField("models.Project", related_name="app_plan_executions", description="所属项目")
    plan = fields.ForeignKeyField("models.AppPlan", related_name="plan_executions", description="执行计划")
    cronjob_id = fields.CharField(max_length=100, null=True, default=None, description="定时任务ID")
    env = fields.JSONField(default=dict, description="执行环境")
    start_time = fields.DatetimeField(auto_now_add=True, description="开始时间")
    duration = fields.FloatField(default=0, description="耗时秒")
    device_id = fields.CharField(max_length=100, null=True, description="执行设备ID")
    status = fields.CharField(
        max_length=255,
        default="执行中",
        description="等待执行|执行中|执行完成|已停止",
    )
    case_count = fields.IntField(default=0)
    run_all = fields.IntField(default=0)
    no_run = fields.IntField(default=0)
    success = fields.IntField(default=0)
    fail = fields.IntField(default=0)
    error = fields.IntField(default=0)
    skip = fields.IntField(default=0)
    quarantine_skip = fields.IntField(default=0, description="已隔离未跑数")
    pass_rate = fields.FloatField(default=0)
    execution_log = fields.JSONField(default=list, null=True)
    username = fields.CharField(max_length=50, description="创建人")
    is_del = fields.BooleanField(default=False, description="是否删除")

    class Meta:
        table = "app_plan_execution"
        table_description = "App计划执行记录"


class AppSuiteExecution(models.Model):
    """App 套件执行记录"""
    id = fields.IntField(pk=True, auto_increment=True, description="套件执行id")
    suite = fields.ForeignKeyField("models.AppSuite", related_name="suite_executions", description="执行套件")
    plan_execution = fields.ForeignKeyField(
        "models.AppPlanExecution", null=True, related_name="suite_executions", description="关联计划执行"
    )
    device_id = fields.CharField(max_length=100, null=True, description="执行设备ID")
    status = fields.CharField(max_length=255, default="执行中")
    case_count = fields.IntField(default=0)
    run_all = fields.IntField(default=0)
    no_run = fields.IntField(default=0)
    success = fields.IntField(default=0)
    fail = fields.IntField(default=0)
    error = fields.IntField(default=0)
    skip = fields.IntField(default=0)
    quarantine_skip = fields.IntField(default=0, description="已隔离未跑数")
    start_time = fields.DatetimeField(auto_now_add=True)
    duration = fields.FloatField(default=0)
    execution_log = fields.JSONField(default=list)
    pass_rate = fields.FloatField(default=0)
    cronjob_id = fields.CharField(max_length=100, null=True, default=None, description="定时任务ID")
    env = fields.JSONField(default=dict, null=True)
    username = fields.CharField(max_length=50, description="创建人")
    is_del = fields.BooleanField(default=False, description="是否删除")

    class Meta:
        table = "app_suite_execution"
        table_description = "App套件执行记录"


class AppCaseExecution(models.Model):
    """App 用例执行记录"""
    id = fields.IntField(pk=True, auto_increment=True, description="用例执行id")
    case = fields.ForeignKeyField("models.AppCase", related_name="case_executions", description="执行用例")
    suite_execution = fields.ForeignKeyField(
        "models.AppSuiteExecution", null=True, related_name="case_executions", description="关联套件执行"
    )
    status = fields.CharField(max_length=255, default="running")
    result_data = fields.JSONField(default=dict, description="执行详情")
    start_time = fields.DatetimeField(auto_now_add=True)
    env = fields.JSONField(default=dict)
    username = fields.CharField(max_length=50, description="创建人")
    is_del = fields.BooleanField(default=False, description="是否删除")

    class Meta:
        table = "app_case_execution"
        table_description = "App用例执行记录"


class AppStepFragment(models.Model):
    """App 可复用步骤片段"""
    id = fields.IntField(pk=True, auto_increment=True, description="片段id")
    name = fields.CharField(max_length=100, description="片段名称")
    project = fields.ForeignKeyField("models.Project", related_name="app_fragments", description="所属项目")
    description = fields.CharField(max_length=500, null=True, description="片段描述")
    steps = fields.JSONField(description="步骤 JSON", default=list)
    tags = fields.CharField(max_length=200, null=True, description="分类标签，逗号分隔")
    version = fields.IntField(description="版本号", default=1)
    username = fields.CharField(max_length=50, description="创建人")
    update_by = fields.CharField(max_length=50, null=True, description="最后更新人")
    is_del = fields.BooleanField(description="是否删除", default=False)
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "app_step_fragment"
        table_description = "App步骤片段"


class AppCronJob(models.Model):
    """App 自动化定时任务"""
    id = fields.CharField(pk=True, max_length=100, description="任务ID")
    name = fields.CharField(max_length=100, description="任务名称")
    project = fields.ForeignKeyField("models.Project", related_name="app_cron_jobs", description="所属项目")
    plan = fields.ForeignKeyField(
        "models.AppPlan",
        related_name="cron_jobs",
        null=True,
        on_delete=fields.SET_NULL,
        description="关联 App 计划",
    )
    suite = fields.ForeignKeyField(
        "models.AppSuite",
        related_name="cron_jobs",
        null=True,
        on_delete=fields.SET_NULL,
        description="关联 App 套件（与 plan 二选一）",
    )
    run_type = fields.CharField(max_length=20, description="Interval|date|crontab")
    interval = fields.IntField(default=3600, description="间隔秒")
    run_date = fields.DatetimeField(null=True, description="固定执行时间")
    crontab = fields.JSONField(default=dict, description="cron 规则")
    env_id = fields.IntField(description="执行环境 ID")
    device_id = fields.CharField(max_length=100, null=True, description="默认执行设备")
    app_udid = fields.CharField(max_length=128, default="", description="覆盖 UDID")
    app_id = fields.CharField(max_length=255, default="", description="默认包名")
    last_run_record_id = fields.IntField(null=True, description="最近执行记录 ID")
    last_run_time = fields.DatetimeField(null=True)
    last_run_status = fields.CharField(max_length=20, null=True)
    state = fields.BooleanField(default=False, description="是否启用")
    is_del = fields.BooleanField(default=False)
    create_by = fields.CharField(max_length=50, description="创建人")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "app_cron_job"
        table_description = "App定时任务"
