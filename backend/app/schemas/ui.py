"""
Web自动化测试相关Schemas
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ==================== Case Schemas ====================

class CaseSchemas(BaseModel):
    """测试用例的响应结构模型定义"""
    id: int = Field(description="用例id")
    name: str = Field(description="用例名称")
    project_id: int = Field(description="所属项目")
    create_time: datetime = Field(description="创建时间")
    update_time: datetime = Field(description="更新时间")
    steps: list = Field(description="用例执行步骤")
    level: str = Field(default="P2", description="用例等级 P0/P1/P2/P3")
    source_functional_case_id: Optional[int] = Field(default=None, description="来源功能用例库ID")
    source_functional_case_title: Optional[str] = Field(default=None, description="来源功能用例标题")
    username: str = Field(description="创建人")
    is_del: bool = Field(description="是否删除", default=False)
    catalog_id: Optional[int] = Field(default=None, description="所属目录id")


class AddCaseForm(BaseModel):
    """创建测试用例表单"""
    name: str = Field(description="用例名称")
    level: str = Field(default="P2", description="用例等级 P0/P1/P2/P3")
    project_id: int = Field(description="所属项目")
    steps: list = Field(description="用例执行步骤")
    source_functional_case_id: Optional[int] = Field(default=None, description="来源功能用例库ID")
    source_functional_case_title: Optional[str] = Field(default=None, max_length=500, description="来源功能用例标题")
    username: str = Field(description="创建人")
    is_del: bool = Field(description="是否删除", default=False)
    catalog_id: Optional[int] = Field(default=None, description="所属目录id")


class UpdateCaseForm(BaseModel):
    """修改测试用例表单"""
    name: str | None = Field(default=None, description="用例名称")
    level: str | None = Field(default=None, description="用例等级 P0/P1/P2/P3")
    steps: list | None = Field(default=None, description="用例执行步骤")
    catalog_id: int | None = Field(default=None, description="所属目录id")
    is_del: bool = Field(description="是否删除", default=False)


# ==================== Suite Schemas ====================

class SuiteSchemas(BaseModel):
    """测试套件返回数据类型"""
    id: int = Field(description="套件id")
    name: str = Field(description="套件名称")
    project_id: int = Field(description="所属项目id")
    catalog_id: Optional[int] = Field(default=None, description="所属目录id")
    create_time: datetime = Field(description="创建时间")
    update_time: datetime = Field(description="更新时间")
    pre_actions: list = Field(description="前置执行步骤")
    setup_sql_ids: list = Field(default_factory=list, description="前置 SQL 模板 ID 列表")
    teardown_sql_ids: list = Field(default_factory=list, description="后置 SQL 模板 ID 列表")
    db_assertions: list = Field(default_factory=list, description="套件级数据库断言")
    suite_type: str = Field(description="套件类型")
    username: str = Field(description="创建人")
    is_del: bool = Field(description="是否删除", default=False)

    class Config:
        from_attributes = True


class AddSuiteForm(BaseModel):
    """创建测试套件的参数表单"""
    name: str = Field(description="套件名称")
    project_id: int = Field(description="所属项目id")
    catalog_id: Optional[int] = Field(default=None, description="所属目录id")
    pre_actions: list = Field(description="前置执行步骤")
    setup_sql_ids: list = Field(default_factory=list, description="前置 SQL 模板 ID 列表")
    teardown_sql_ids: list = Field(default_factory=list, description="后置 SQL 模板 ID 列表")
    db_assertions: list = Field(default_factory=list, description="套件级数据库断言")
    suite_type: str = Field(description="套件类型")
    username: str = Field(description="创建人")


class UpdateSuiteForm(BaseModel):
    """修改测试套件的参数表单"""
    name: str | None = Field(default=None, description="套件名称")
    catalog_id: int | None = Field(default=None, description="所属目录id")
    pre_actions: list | None = Field(default=None, description="前置执行步骤")
    setup_sql_ids: list | None = Field(default=None, description="前置 SQL 模板 ID 列表")
    teardown_sql_ids: list | None = Field(default=None, description="后置 SQL 模板 ID 列表")
    db_assertions: list | None = Field(default=None, description="套件级数据库断言")
    suite_type: str | None = Field(default=None, description="套件类型")
    is_del: bool | None = Field(default=None, description="是否删除（逻辑删除控制）")


class StepSchemas(BaseModel):
    """套件中的用例模型定义"""
    id: int = Field(description="用例id")
    suite_id: int = Field(description="所属套件")
    cases_id: int = Field(description="所属用例")
    sort: int = Field(description="用例执行顺序")
    skip: bool = Field(description="是否跳过")
    is_del: bool = Field(description="是否删除", default=False)

    class Config:
        from_attributes = True


class StepListSchemas(StepSchemas):
    """获取套件中的所有用例模型类"""
    suite_name: str = Field(description="套件名称")
    cases_name: str = Field(description="用例名称")


class AddStepForm(BaseModel):
    """添加用例到套件中的表单"""
    cases_id: int = Field(description="所属用例")
    sort: int = Field(description="用例执行顺序")


class SuiteCaseSortItem(BaseModel):
    """套件用例排序项"""
    cases_id: int = Field(description="用例ID")
    sort: int = Field(description="执行顺序")


class UpdateSuiteCaseSortForm(BaseModel):
    """修改套件中用例执行顺序的表单"""
    case_orders: List[SuiteCaseSortItem] = Field(description="用例排序列表")


# ==================== Task Schemas ====================

class TaskSchemas(BaseModel):
    """计划的模型类"""
    id: int = Field(description="任务id")
    create_time: datetime = Field(description="创建时间")
    update_time: datetime = Field(description="更新时间")
    name: str = Field(description="任务名称")
    project_id: int = Field(description="所属项目")
    catalog_id: Optional[int] = Field(default=None, description="所属目录id")
    username: str = Field(description="创建人")
    is_del: bool = Field(description="是否删除", default=False)

    class Config:
        from_attributes = True


class AddTaskForm(BaseModel):
    """创建计划的表单"""
    name: str = Field(description="任务名称")
    project_id: int = Field(description="所属项目")
    catalog_id: Optional[int] = Field(default=None, description="所属目录id")
    username: str = Field(description="创建人")


class UpdateTaskForm(BaseModel):
    """更新计划的表单"""
    name: str | None = Field(default=None, description="任务名称")
    catalog_id: int | None = Field(default=None, description="所属目录id")


class AddSuiteToTaskForm(BaseModel):
    """创建计划的套件的表单"""
    suite_id: int = Field(description="套件id")


class TaskToSuiteSchemas(BaseModel):
    suite_id: int = Field(description="套件id")
    suite_name: str = Field(description="套件名称")
    suite_type: str = Field(description="套件类型")
    create_time: datetime = Field(description="创建时间")
    update_time: datetime | None = Field(description="更新时间")
    is_del: bool = Field(description="是否删除", default=False)

    class Config:
        from_attributes = True


class TaskDetailSchemas(BaseModel):
    id: int = Field(description="任务id")
    create_time: datetime = Field(description="创建时间")
    update_time: datetime = Field(description="更新时间")
    name: str = Field(description="任务名称")
    suites: list[TaskToSuiteSchemas] = Field(description="任务中套件")
    username: str = Field(description="创建人")
    is_del: bool = Field(description="是否删除", default=False)

    class Config:
        from_attributes = True


# ==================== Runner/Exec Schemas ====================

class RunForm(BaseModel):
    """用例运行表单"""
    env_id: int = Field(description="运行环境的ID")
    browser_type: Optional[str] = Field(default=None, description="浏览器类型")
    device_id: Optional[str] = Field(default=None, description="设备ID")
    config: bool = Field(default=True, description="是否启用无头模式")
    username: str = Field(description="创建人")
    ai_heal_enabled: Optional[bool] = Field(
        default=None,
        description="本次执行是否启用 AI 定位器自愈；不传则使用 Runner 环境默认",
    )
    trigger_source: Optional[str] = Field(
        default=None,
        description="触发来源：manual / assistant / cron 等，写入执行 env",
    )


class CaseDebugForm(RunForm):
    """用例步骤级调试：执行 steps[0:through_index+1] 后停止"""
    steps: list = Field(description="当前编辑器步骤（可未保存）")
    through_index: int = Field(ge=0, description="调试到此步（含该步，0-based）")


class SuiteResultSchemas(BaseModel):
    """套件结果模型定义"""
    id: int = Field(description="套件记录id")
    status: str = Field(description="运行状态")
    suite_id: int = Field(description="套件id")
    suite_name: str = Field(description="套件名称")
    username: str = Field(description="创建人")
    start_time: datetime = Field(description="开始时间")
    success: int = Field(description="成功用例数")
    error: int = Field(description="错误用例数")
    skip: int = Field(description="跳过用例数")
    duration: float = Field(description="执行时间")
    pass_rate: float = Field(description="通过率")
    run_all: int = Field(description="执行用例数")
    case_count: int = Field(description="总用例数")
    fail: int = Field(description="失败用例数")
    execution_log: list = Field(description="套件执行日志")
    no_run: int = Field(description="未执行用例数")
    env: dict = Field(description="运行环境", default_factory=dict)
    is_del: bool = Field(description="是否删除", default=False)

    class Config:
        from_attributes = True


class TaskResultSchemas(BaseModel):
    """计划结果模型定义"""
    id: int = Field(description="任务记录id")
    project_id: int = Field(description="所属项目id")
    start_time: datetime = Field(description="开始时间")
    task_id: int = Field(description="任务id")
    task_name: str = Field(description="任务名称")
    username: str = Field(description="创建人")
    duration: float = Field(description="执行时间")
    pass_rate: float = Field(description="通过率")
    no_run: int = Field(description="未执行用例数")
    success: int = Field(description="成功用例数")
    error: int = Field(description="错误用例数")
    skip: int = Field(description="跳过用例数")
    case_count: int = Field(description="总用例数")
    fail: int = Field(description="失败用例数")
    run_all: int = Field(description="执行用例数")
    status: str = Field(description="运行状态")
    env: dict = Field(description="运行环境", default_factory=dict)
    execution_log: list = Field(description="任务执行日志", default_factory=list)
    is_del: bool = Field(description="是否删除", default=False)

    class Config:
        from_attributes = True


# ============ 用例导入/导出 ============

class UiCaseBatchExportRequest(BaseModel):
    """批量导出UI用例请求"""
    case_ids: List[int] = Field(..., description="要导出的用例ID列表")


class UiCaseBatchUpdateCatalogRequest(BaseModel):
    """批量修改UI用例目录"""
    case_ids: List[int] = Field(..., description="用例ID列表")
    catalog_id: Optional[int] = Field(None, description="目标目录ID，null 表示移出目录")


class UiCaseImportResult(BaseModel):
    """批量导入UI用例结果"""
    success: int = Field(default=0, description="成功创建数")
    failed: int = Field(default=0, description="失败数")
    warnings: List[str] = Field(default=[], description="警告信息")
    errors: List[str] = Field(default=[], description="错误信息")
    created_names: List[str] = Field(default=[], description="已创建的用例名列表")
