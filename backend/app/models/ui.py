"""
Web自动化测试相关模型
"""
from tortoise import models, fields


class Case(models.Model):
    """测试用例的模型定义"""
    id = fields.IntField(pk=True, description="用例id", auto_increment=True)
    name = fields.CharField(max_length=50, description="用例名称")
    project = fields.ForeignKeyField("models.Project", related_name="cases", description="所属项目")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    steps = fields.JSONField(description="用例执行步骤", default=list)
    level = fields.CharField(max_length=10, description="用例等级", default="P2")
    source_functional_case_id = fields.IntField(null=True, description="来源功能用例库ID")
    source_functional_case_title = fields.CharField(
        max_length=500, null=True, description="来源功能用例标题快照"
    )
    description = fields.TextField(null=True, description="用例描述（功能背景/步骤预期，供 AI 优化）")
    tags = fields.JSONField(default=list, description="用例标签（含 quarantine）")
    username = fields.CharField(max_length=50, description="创建人")
    update_by = fields.CharField(max_length=50, null=True, description="最后更新人")
    is_del = fields.BooleanField(description="是否删除", default=False)
    catalog = fields.ForeignKeyField(
        "models.TestCatalog", null=True, related_name="ui_cases", description="所属目录"
    )

    class Meta:
        table = "case"
        table_description = "测试用例"


class Suite(models.Model):
    """测试套件的模型定义"""
    id = fields.IntField(pk=True, description="套件id")
    name = fields.CharField(max_length=50, description="套件名称")
    project = fields.ForeignKeyField("models.Project", related_name="suites", description="所属项目")
    catalog = fields.ForeignKeyField(
        "models.TestCatalog", related_name="ui_suites", description="所属目录", null=True
    )
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    pre_actions = fields.JSONField(description="前置执行步骤", default=list)
    setup_sql_ids = fields.JSONField(default=list, description="前置 SQL 模板 ID 列表")
    teardown_sql_ids = fields.JSONField(default=list, description="后置 SQL 模板 ID 列表")
    db_assertions = fields.JSONField(default=list, description="套件级数据库断言")
    suite_type = fields.CharField(max_length=50, description="套件类型", choices=[("1", "功能"), ("2", "场景")], default="1")
    stop_on_failure = fields.BooleanField(default=False, description="用例失败时停止后续用例")
    propagate_variables = fields.BooleanField(
        default=False, description="是否将链路用例变量传递给后续链路用例"
    )
    username = fields.CharField(max_length=50, description="创建人")
    update_by = fields.CharField(max_length=50, null=True, description="最后更新人")
    is_del = fields.BooleanField(description="是否删除", default=False)

    class Meta:
        table = "suite"
        table_description = "测试套件"


class Step(models.Model):
    """套件中的用例模型定义"""
    id = fields.IntField(pk=True, description="用例id")
    suite = fields.ForeignKeyField("models.Suite", related_name="steps", description="所属套件")
    cases = fields.ForeignKeyField("models.Case", related_name="suite_steps", description="所属用例")
    sort = fields.IntField(description="用例执行顺序", default=0)
    skip = fields.BooleanField(description="是否跳过", default=False)
    run_mode = fields.CharField(
        max_length=20,
        default="standalone",
        description="运行模式：chain=链路用例 standalone=独立用例",
    )
    is_del = fields.BooleanField(description="是否删除", default=False)

    class Meta:
        table = "step"
        table_description = "套件中的用例"


class Task(models.Model):
    """测试计划的模型类"""
    id = fields.IntField(pk=True, description="任务id", auto_increment=True)
    name = fields.CharField(max_length=255, description="任务名称")
    project = fields.ForeignKeyField("models.Project", related_name="tasks", description="所属项目")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    suites = fields.ManyToManyField("models.Suite", related_name="tasks", description="任务中套件")
    catalog = fields.ForeignKeyField(
        "models.TestCatalog", null=True, related_name="ui_tasks", description="所属目录"
    )
    username = fields.CharField(max_length=50, description="创建人")
    update_by = fields.CharField(max_length=50, null=True, description="最后更新人")
    is_del = fields.BooleanField(description="是否删除", default=False)
    parallel = fields.BooleanField(default=False, description="计划级并行（按执行器权重分配套件）")

    class Meta:
        table = "task"
        table_description = "测试计划"


class UiPlanExecution(models.Model):
    """测试计划运行记录"""
    id = fields.IntField(pk=True, description="计划执行id")
    project = fields.ForeignKeyField("models.Project", related_name="plan_executions", description="所属项目")
    task = fields.ForeignKeyField("models.Task", related_name="ui_plan_executions", description="执行的任务")
    cronjob_id = fields.CharField(max_length=100, description="关联的定时任务ID", null=True, default=None)
    env = fields.JSONField(description="执行环境", default=dict)
    start_time = fields.DatetimeField(auto_now_add=True, description="开始执行时间")
    duration = fields.FloatField(description="执行时间", default=0)
    device_id = fields.CharField(max_length=100, null=True, description="执行设备ID")
    status = fields.CharField(max_length=255, description="运行状态",
                              choices=[("等待执行", "等待执行"), ("执行完成", "执行完成"), ("执行中", "执行中"), ("已停止", "已停止")],
                              default="执行中")
    case_count = fields.IntField(description="总用例数", default=0)
    run_all = fields.IntField(description="执行用例数", default=0)
    no_run = fields.IntField(description="未执行用例数", default=0)
    success = fields.IntField(description="成功用例数", default=0)
    pass_rate = fields.FloatField(description="通过率", default=0)
    execution_log = fields.JSONField(description="任务执行日志", default=list, null=True)
    fail = fields.IntField(description="失败用例数", default=0)
    error = fields.IntField(description="错误用例数", default=0)
    skip = fields.IntField(description="跳过用例数", default=0)
    quarantine_skip = fields.IntField(description="已隔离未跑数", default=0)
    username = fields.CharField(max_length=50, description="创建人")
    is_del = fields.BooleanField(description="是否删除", default=False)

    class Meta:
        table = "ui_plan_execution"
        table_description = "测试计划运行记录"


class UiSuiteExecution(models.Model):
    """测试套件运行记录"""
    id = fields.IntField(pk=True, description="执行记录id")
    suite = fields.ForeignKeyField("models.Suite", related_name="suite_executions", description="执行的套件")
    plan_execution = fields.ForeignKeyField("models.UiPlanExecution", related_name="ui_suite_executions",
                                            description="关联的运行计划记录", null=True)
    device_id = fields.CharField(max_length=100, null=True, description="执行设备ID")
    status = fields.CharField(max_length=255, description="运行状态",
                              choices=[("等待执行", "等待执行"), ("执行中", "执行中"), ("执行完成", "执行完成"), ("已停止", "已停止")],
                              default="执行中")
    case_count = fields.IntField(description="总用例数", default=0)
    run_all = fields.IntField(description="执行用例数", default=0)
    no_run = fields.IntField(description="未执行用例数", default=0)
    success = fields.IntField(description="成功用例数", default=0)
    fail = fields.IntField(description="失败用例数", default=0)
    error = fields.IntField(description="错误用例数", default=0)
    skip = fields.IntField(description="跳过用例数", default=0)
    quarantine_skip = fields.IntField(description="已隔离未跑数", default=0)
    start_time = fields.DatetimeField(auto_now_add=True, description="开始执行时间")
    duration = fields.FloatField(description="执行时间", default=0)
    execution_log = fields.JSONField(description="套件执行日志", default=list)
    pass_rate = fields.FloatField(description="通过率", default=0)
    env = fields.JSONField(description="执行环境", default=dict, null=True)
    username = fields.CharField(max_length=50, description="创建人")
    is_del = fields.BooleanField(description="是否删除", default=False)

    class Meta:
        table = "ui_suite_execution"
        table_description = "测试套件运行记录"


class UiStepFragment(models.Model):
    """UI 可复用步骤片段"""
    id = fields.IntField(pk=True, description="片段id", auto_increment=True)
    name = fields.CharField(max_length=100, description="片段名称")
    project = fields.ForeignKeyField("models.Project", related_name="ui_fragments", description="所属项目")
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
        table = "ui_step_fragment"
        table_description = "UI步骤片段"


class UiCaseExecution(models.Model):
    """测试用例运行记录"""
    id = fields.IntField(pk=True, description="用例执行id")
    case = fields.ForeignKeyField("models.Case", related_name="case_executions", description="执行的用例")
    suite_execution = fields.ForeignKeyField("models.UiSuiteExecution", related_name="ui_case_executions",
                                             description="关联的运行套件记录", null=True, default=None)
    status = fields.CharField(max_length=255, description="运行状态",
                              choices=[("success", "执行成功"), ("fail", "执行失败"),
                                       ("error", "执行错误"), ("skip", "跳过执行"), ("no_run", "未执行"),
                                       ("running", "执行中")], default="running")
    result_data = fields.JSONField(description="用例执行详情", default=dict)
    start_time = fields.DatetimeField(auto_now_add=True, description="开始执行时间")
    env = fields.JSONField(description="执行环境", default=dict)
    username = fields.CharField(max_length=50, description="创建人")
    is_del = fields.BooleanField(description="是否删除", default=False)

    class Meta:
        table = "ui_case_execution"
        table_description = "测试用例运行记录"


class UiDebugSession(models.Model):
    """UI 交互调试会话：Runner 保活浏览器，用户手动就位后按步试跑"""
    id = fields.IntField(pk=True, auto_increment=True, description="会话ID")
    case_id = fields.IntField(description="用例ID")
    project_id = fields.IntField(description="项目ID")
    device_id = fields.CharField(max_length=100, description="Runner 设备ID")
    username = fields.CharField(max_length=50, description="创建人")
    status = fields.CharField(
        max_length=20,
        default="starting",
        description="starting/ready/running/closing/closed/error",
    )
    env = fields.JSONField(default=dict, description="执行环境")
    steps = fields.JSONField(default=list, description="步骤快照")
    pending_command = fields.JSONField(null=True, description="待执行命令")
    last_result = fields.JSONField(default=dict, description="最近执行结果")
    error = fields.TextField(null=True, description="错误信息")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "ui_debug_session"
        table_description = "UI交互调试会话"


class UiTestFile(models.Model):
    """Web 自动化 input 文件上传测试素材（MinIO ui-test-files）"""
    id = fields.IntField(pk=True, auto_increment=True)
    project = fields.ForeignKeyField("models.Project", related_name="ui_test_files", description="所属项目")
    file_name = fields.CharField(max_length=255, description="原始文件名")
    file_key = fields.CharField(max_length=500, description="MinIO 对象键")
    file_bucket = fields.CharField(max_length=100, description="MinIO bucket")
    mime_type = fields.CharField(max_length=128, default="application/octet-stream", description="MIME 类型")
    size = fields.IntField(default=0, description="文件大小（字节）")
    username = fields.CharField(max_length=50, description="上传人")
    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "ui_test_file"
        table_description = "UI自动化测试文件"


class UiTestFolder(models.Model):
    """Web 自动化文件夹上传测试素材（MinIO 前缀 + 相对路径保留目录结构）"""
    id = fields.IntField(pk=True, auto_increment=True)
    project = fields.ForeignKeyField("models.Project", related_name="ui_test_folders", description="所属项目")
    folder_name = fields.CharField(max_length=255, description="文件夹显示名称")
    folder_key = fields.CharField(max_length=500, description="MinIO 对象前缀 project_id/uuid")
    file_bucket = fields.CharField(max_length=100, description="MinIO bucket")
    file_count = fields.IntField(default=0, description="文件数量")
    total_size = fields.IntField(default=0, description="总大小（字节）")
    entries = fields.JSONField(default=list, description="文件清单 [{relative_path, object_key, size, mime_type}]")
    username = fields.CharField(max_length=50, description="上传人")
    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "ui_test_folder"
        table_description = "UI自动化测试文件夹"
