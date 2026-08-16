from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# ============ 接口定义相关 ============

class ApiParam(BaseModel):
    """接口参数"""
    name: str = Field(..., description="参数名")
    value: str = Field(default="", description="参数值")
    type: str = Field(default="string", description="参数类型")
    required: bool = Field(default=True, description="是否必填")
    description: Optional[str] = Field(None, description="参数描述")


class ApiHeader(BaseModel):
    """接口请求头"""
    key: str = Field(..., description="Header名")
    value: str = Field(..., description="Header值")
    description: Optional[str] = Field(None, description="描述")
    enabled: Optional[bool] = Field(True, description="是否启用（全局Header配置用）")


class GlobalHeaderPolicy(BaseModel):
    """全局 Header 使用策略"""
    disabled_keys: List[str] = Field(default=[], description="禁用的全局Header key列表（legacy / 用例层）")
    enabled_keys: Optional[List[str]] = Field(default=None, description="启用的全局Header key列表（opt-in，存在该字段时仅合并列表内 key）")


class ApiDefinitionBase(BaseModel):
    """接口定义基础模型"""
    name: str = Field(..., max_length=100, description="接口名称")
    protocol: str = Field(default="http", description="协议 http/websocket/graphql/grpc")
    method: str = Field(..., description="请求方法 GET/POST/PUT/DELETE/PATCH/WS")
    path: str = Field(..., max_length=500, description="接口路径")
    description: Optional[str] = Field(None, description="接口描述")
    base_url: Optional[str] = Field(None, description="基础URL")
    headers: List[Dict[str, Any]] = Field(default=[], description="请求头")
    global_header_policy: Dict[str, Any] = Field(default_factory=dict, description="全局Header使用策略")
    params: List[Dict[str, Any]] = Field(default=[], description="查询参数")
    body: Optional[Any] = Field(default=None, description="请求体")
    body_type: str = Field(default="json", description="请求体类型 json/form/xml/raw")
    body_fields: List[Dict[str, Any]] = Field(default=[], description="form-data 字段")
    ws_config: Dict[str, Any] = Field(default_factory=dict, description="WebSocket 默认配置")
    grpc_config: Dict[str, Any] = Field(default_factory=dict, description="gRPC 配置")
    response_schema: Optional[Dict[str, Any]] = Field(default=None, description="响应结构定义")

    @field_validator("global_header_policy", "headers", "params", "body_fields", "ws_config", "grpc_config", mode="before")
    @classmethod
    def coerce_json_list_or_dict(cls, v, info):
        if info.field_name in ("global_header_policy", "ws_config", "grpc_config"):
            return v if isinstance(v, dict) else {}
        return v if isinstance(v, list) else []


class ApiDefinitionCreate(ApiDefinitionBase):
    """创建接口"""
    project_id: int = Field(..., description="所属项目ID")
    catalog_id: Optional[int] = Field(None, description="目录ID")


class ApiDefinitionUpdate(ApiDefinitionBase):
    """更新接口"""
    catalog_id: Optional[int] = Field(None, description="目录ID")


class ApiDefinitionOut(ApiDefinitionBase):
    """接口定义输出"""
    id: int
    project_id: int
    catalog_id: Optional[int]
    catalog_name: Optional[str] = Field(None, description="目录名称")
    case_count: int = Field(default=0, description="关联用例数量")
    version: int
    source: Optional[str]
    create_by: str
    update_by: Optional[str] = None
    create_time: datetime
    update_time: datetime
    
    class Config:
        from_attributes = True


class ApiListFilter(BaseModel):
    """接口列表筛选"""
    project_id: int
    catalog_id: Optional[int] = None
    keyword: Optional[str] = None
    method: Optional[str] = None


# ============ 导入导出相关 ============

class SwaggerInfo(BaseModel):
    """Swagger 信息"""
    title: str
    version: str
    description: Optional[str] = None


class SwaggerPath(BaseModel):
    """Swagger 路径"""
    summary: Optional[str] = None
    description: Optional[str] = None
    operationId: Optional[str] = None
    parameters: Optional[List[Dict]] = None
    requestBody: Optional[Dict] = None
    responses: Optional[Dict] = None


class SwaggerDoc(BaseModel):
    """Swagger 文档"""
    openapi: str
    info: SwaggerInfo
    paths: Dict[str, Dict[str, SwaggerPath]]
    components: Optional[Dict] = None


class ApiImportResult(BaseModel):
    """导入结果"""
    total: int = Field(..., description="总数")
    success: int = Field(..., description="成功数")
    failed: int = Field(..., description="失败数")
    errors: List[str] = Field(default=[], description="错误信息")
    apis: List[ApiDefinitionOut] = Field(default=[], description="导入的接口")


# ============ Curl 导入相关 ============

class CurlImportRequest(BaseModel):
    """Curl 导入请求"""
    curl_command: str = Field(..., description="curl 命令字符串")
    project_id: int = Field(..., description="项目ID")
    catalog_id: Optional[int] = Field(None, description="目录ID")


class CurlImportResponse(BaseModel):
    """Curl 导入响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="提示信息")
    api: Optional[ApiDefinitionOut] = Field(None, description="导入的接口")


class CurlParseRequest(BaseModel):
    """Curl 解析请求"""
    curl_command: str = Field(..., description="curl 命令字符串")
    project_id: int = Field(..., description="项目ID")
    catalog_id: Optional[int] = Field(None, description="目录ID")


class CurlParseResponse(BaseModel):
    """Curl 解析响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="提示信息")
    api: Optional[Dict[str, Any]] = Field(None, description="解析的接口数据")


# ============ 调试相关 ============

class ApiBodyField(BaseModel):
    """接口请求体字段"""
    name: str = Field(..., description="字段名")
    value: Optional[str] = Field(default=None, description="字段值")
    field_type: str = Field(default="text", description="字段类型 text/file")
    file_name: Optional[str] = Field(default=None, description="文件名")
    mime_type: Optional[str] = Field(default=None, description="MIME类型")
    file_key: Optional[str] = Field(default=None, description="MinIO 对象键")
    file_bucket: Optional[str] = Field(default=None, description="MinIO bucket")
    description: Optional[str] = Field(None, description="字段描述")


class ApiBodyFileUploadResponse(BaseModel):
    """接口请求体文件上传响应"""
    success: bool = Field(..., description="是否成功")
    file_bucket: str = Field(..., description="MinIO bucket")
    file_key: str = Field(..., description="MinIO 对象键")
    file_name: str = Field(..., description="文件名")
    mime_type: str = Field(..., description="MIME类型")
    size: int = Field(..., description="文件大小")


class ApiDebugRequest(BaseModel):
    """接口调试请求"""
    method: str = Field(..., description="请求方法")
    url: str = Field(..., description="完整URL")
    headers: List[Dict[str, Any]] = Field(default=[], description="请求头")
    global_header_policy: Optional[Dict[str, Any]] = Field(default_factory=dict, description="全局Header使用策略")
    params: List[Dict[str, Any]] = Field(default=[], description="查询参数")
    body: Any = Field(default=None, description="请求体")
    body_type: str = Field(default="json", description="请求体类型")
    body_fields: List[ApiBodyField] = Field(default=[], description="form-data 字段")
    timeout: int = Field(default=30, description="超时时间")
    env_id: Optional[int] = Field(None, description="环境ID")
    project_id: Optional[int] = Field(None, description="项目ID（未选环境时用于加载项目变量）")
    variables: Optional[Dict[str, Any]] = Field(default={}, description="变量")
    worker_id: Optional[int] = Field(
        None,
        description="经在线压测执行机代发时指定 Worker ID；不传则由平台本机发送",
    )


class ApiDebugResponse(BaseModel):
    """接口调试响应"""
    status_code: int = Field(..., description="状态码")
    headers: Dict[str, str] = Field(default={}, description="响应头")
    body: Any = Field(..., description="响应体")
    time: float = Field(..., description="响应时间(ms)")
    size: int = Field(..., description="响应大小(bytes)")
    request: ApiDebugRequest = Field(..., description="请求信息")


class WsDebugRequest(BaseModel):
    """WebSocket 调试请求"""
    url: str = Field(..., description="WebSocket URL 或路径")
    headers: List[Dict[str, Any]] = Field(default=[], description="连接 Headers")
    steps: List[Dict[str, Any]] = Field(default=[], description="步骤：send/receive/wait/close")
    assertions: List[Dict[str, Any]] = Field(default=[], description="断言规则")
    timeout: int = Field(default=30, description="超时(秒)")
    env_id: Optional[int] = Field(None, description="环境ID")
    project_id: Optional[int] = Field(None, description="项目ID")
    variables: Optional[Dict[str, Any]] = Field(default={}, description="变量")


class WsDebugResponse(BaseModel):
    """WebSocket 调试响应"""
    success: bool = Field(..., description="是否成功")
    messages: List[Dict[str, Any]] = Field(default=[], description="消息流")
    assertions: List[Dict[str, Any]] = Field(default=[], description="断言结果")
    response_body: Dict[str, Any] = Field(default={}, description="聚合响应体")
    elapsed_ms: float = Field(default=0, description="耗时(ms)")
    error: Optional[str] = Field(None, description="错误信息")


# ============ 分页相关 ============

class ApiListResponse(BaseModel):
    """接口列表响应"""
    data: List[ApiDefinitionOut]
    total: int
    page: int
    size: int


# ============ 断言相关 ============

class ApiAssertion(BaseModel):
    """断言规则"""
    type: str = Field(..., description="断言类型: status_code/json_path/header/contains/ws_contains/ws_json_path/ws_message_count")
    target: Optional[str] = Field(None, description="目标字段/路径")
    operator: str = Field(..., description="操作符: equals/not_equals/contains/gt/lt")
    expected: Any = Field(..., description="期望值")
    description: Optional[str] = Field(None, description="断言描述")


class ApiExtractor(BaseModel):
    """变量提取规则"""
    name: str = Field(..., description="变量名")
    source: str = Field(default="json", description="来源: json/header")
    path: str = Field(..., description="提取路径")
    description: Optional[str] = Field(None, description="描述")


# ============ 测试用例相关 ============

class ApiTestCaseBase(BaseModel):
    """测试用例基础模型"""
    name: str = Field(..., max_length=100, description="用例名称")
    request_headers: Dict[str, str] = Field(default={}, description="请求头覆盖")
    global_header_policy: Dict[str, Any] = Field(default_factory=dict, description="全局Header使用策略")
    request_params: List[ApiParam] = Field(default=[], description="请求参数覆盖")
    request_body: Optional[Any] = Field(default=None, description="请求体覆盖")
    request_body_type: str = Field(default="json", description="请求体类型")
    request_body_fields: List[Dict[str, Any]] = Field(default=[], description="form-data 字段覆盖")
    ws_steps: List[Dict[str, Any]] = Field(default=[], description="WebSocket 步骤序列")
    assertions: List[ApiAssertion] = Field(default=[], description="断言规则")
    assertion_groups: List[Dict[str, Any]] = Field(default=[], description="条件分支断言组")
    extractors: List[ApiExtractor] = Field(default=[], description="变量提取规则")
    depends_on: List[int] = Field(default=[], description="依赖用例ID列表")
    timeout: int = Field(default=30, description="超时时间(秒)")
    retry_count: int = Field(default=0, description="重试次数")
    tags: List[str] = Field(default=[], description="标签")
    priority: str = Field(default="P2", description="优先级 P0/P1/P2/P3")
    # 前置/后置脚本
    pre_script: Optional[str] = Field(None, description="前置脚本（Python，请求前执行）")
    post_script: Optional[str] = Field(None, description="后置脚本（Python，请求后执行）")
    # 数据集（数据驱动）
    data_set: List[Dict[str, Any]] = Field(default=[], description="数据集，格式: [{col1:v1, col2:v2}, ...]")
    # 数据库断言
    db_assertions: List[Dict[str, Any]] = Field(default=[], description="数据库断言规则")

    @field_validator("global_header_policy", "request_headers", mode="before")
    @classmethod
    def coerce_json_dict(cls, v):
        return v if isinstance(v, dict) else {}

    @field_validator(
        "request_params",
        "request_body_fields",
        "ws_steps",
        "assertions",
        "assertion_groups",
        "extractors",
        "depends_on",
        "tags",
        "data_set",
        "db_assertions",
        mode="before",
    )
    @classmethod
    def coerce_json_list(cls, v):
        return v if isinstance(v, list) else []


class ApiTestCaseCreate(ApiTestCaseBase):
    """创建测试用例"""
    api_id: int = Field(..., description="关联接口ID")
    project_id: int = Field(..., description="所属项目ID")
    catalog_id: Optional[int] = Field(None, description="目录ID")


class ApiTestCaseUpdate(ApiTestCaseBase):
    """更新测试用例"""
    api_id: Optional[int] = Field(None, description="关联接口ID（传入则更换关联接口）")
    catalog_id: Optional[int] = Field(None, description="目录ID")


class ApiTestCaseOut(ApiTestCaseBase):
    """测试用例输出"""
    id: int
    api_id: int
    api_name: Optional[str] = None
    api_method: Optional[str] = None
    api_path: Optional[str] = None
    api_protocol: Optional[str] = Field(None, description="关联接口协议")
    project_id: int
    catalog_id: Optional[int] = None
    catalog_name: Optional[str] = None
    create_by: str
    update_by: Optional[str] = None
    create_time: datetime
    update_time: datetime
    
    class Config:
        from_attributes = True


class ApiTestCaseListResponse(BaseModel):
    """测试用例列表响应"""
    data: List[ApiTestCaseOut]
    total: int
    page: int
    size: int


# ============ 执行相关 ============

class ApiRunRequest(BaseModel):
    """执行请求"""
    env_id: int = Field(..., description="环境ID")
    variables: Optional[Dict[str, Any]] = Field(default={}, description="变量")
    auto_validate_schema: bool = Field(default=False, description="是否自动校验响应 Schema")
    propagate_extracted: bool = Field(default=True, description="数据驱动时行间传递提取变量")


class VariablePreviewRequest(BaseModel):
    """变量预览请求"""
    env_id: Optional[int] = Field(None, description="环境ID")
    project_id: Optional[int] = Field(None, description="项目ID")
    extra_variables: Optional[Dict[str, Any]] = Field(default={}, description="额外变量")
    samples: List[str] = Field(default=[], description="待预览替换的示例字符串")


class ApiAssertionResult(BaseModel):
    """断言结果"""
    type: str
    target: Optional[str]
    operator: str
    expected: Any
    actual: Any
    passed: bool
    group_name: Optional[str] = Field(None, description="条件分支组名")
    description: Optional[str] = Field(None, description="断言描述")


class ApiRunResult(BaseModel):
    """执行结果"""
    record_id: int
    status: str = Field(..., description="success/failed")
    response_status: Optional[int] = None
    response_time: Optional[float] = Field(
        default=None,
        description="用例执行总耗时(ms)：含重试等待、断言、变量提取、脚本等",
    )
    http_response_time: Optional[float] = Field(
        default=None,
        description="纯 HTTP 请求耗时(ms)：httpx 发起到收到响应",
    )
    assertions: List[ApiAssertionResult] = Field(default=[])
    extracted_vars: Dict[str, Any] = Field(default={})
    extractor_results: List[Dict[str, Any]] = Field(default=[], description="变量提取详情")
    error: Optional[str] = None
    request_detail: Optional[Dict[str, Any]] = Field(default=None, description="请求详情(原始值/最终值/变量替换)")
    response_detail: Optional[Dict[str, Any]] = Field(default=None, description="响应详情(状态码/响应头/响应体)")
    case_id: Optional[int] = Field(default=None, description="用例ID")
    case_name: Optional[str] = Field(default=None, description="用例名称")
    retry_info: Optional[Dict[str, Any]] = Field(default=None, description="重试信息")
    # 数据驱动字段
    data_run_index: Optional[int] = Field(default=None, description="数据驱动轮次（0-based）")
    data_row_label: Optional[str] = Field(default=None, description="本轮数据摘要")


class ApiDataDrivenRunResult(BaseModel):
    """数据驱动执行结果（多轮）"""
    total_rows: int = Field(..., description="总轮次")
    results: List[ApiRunResult] = Field(default=[], description="每轮结果")
    success: int = Field(default=0, description="成功轮次")
    failed: int = Field(default=0, description="失败轮次")


# ============ 测试套件相关 ============

class ApiSuiteBase(BaseModel):
    """测试套件基础模型"""
    name: str = Field(..., max_length=100, description="套件名称")
    catalog_id: Optional[int] = Field(None, description="所属目录ID")
    env_id: Optional[int] = Field(None, description="默认环境ID")
    timeout: int = Field(default=300, description="总超时时间(秒)")
    retry_count: int = Field(default=0, description="失败重试次数")
    stop_on_failure: bool = Field(default=False, description="失败时停止")
    parallel: bool = Field(default=False, description="并行执行")
    setup_sql_ids: List[int] = Field(default=[], description="前置 SQL 模板 ID 列表")
    teardown_sql_ids: List[int] = Field(default=[], description="后置 SQL 模板 ID 列表")
    db_assertions: List[Dict[str, Any]] = Field(default=[], description="套件级数据库断言")
    description: Optional[str] = Field(None, description="描述")


class ApiSuiteCreate(ApiSuiteBase):
    """创建测试套件"""
    project_id: int = Field(..., description="所属项目ID")
    case_ids: List[int] = Field(default=[], description="用例ID列表")


class ApiSuiteUpdate(ApiSuiteBase):
    """更新测试套件"""
    case_ids: List[int] = Field(default=[], description="用例ID列表")


class ApiSuiteCaseOut(BaseModel):
    """套件用例输出"""
    id: int
    case_id: int
    case_name: str
    api_name: str
    api_method: str
    sort: int


class ApiSuiteOut(ApiSuiteBase):
    """测试套件输出"""
    id: int
    project_id: int
    catalog_name: Optional[str] = Field(None, description="所属目录名称")
    cases: List[ApiSuiteCaseOut] = Field(default=[])
    case_count: int = Field(default=0, description="用例数量")
    create_by: str
    update_by: Optional[str] = None
    create_time: datetime
    update_time: datetime
    
    class Config:
        from_attributes = True


class ApiSuiteListResponse(BaseModel):
    """测试套件列表响应"""
    data: List[ApiSuiteOut]
    total: int
    page: int
    size: int


# ============ 套件执行相关 ============

class ApiBatchRunRequest(BaseModel):
    """批量执行请求"""
    case_ids: List[int] = Field(..., description="用例ID列表")
    env_id: int = Field(..., description="环境ID")
    suite_id: Optional[int] = Field(None, description="所属套件ID")
    auto_validate_schema: bool = Field(default=False, description="是否自动校验响应 Schema")


class ApiSuiteRunRequest(BaseModel):
    """套件执行请求"""
    env_id: Optional[int] = Field(None, description="环境ID，不传则使用套件默认环境")
    auto_validate_schema: bool = Field(default=False, description="是否自动校验响应 Schema")
    trigger_type: str = Field(default="manual", description="触发方式: manual/cron/assistant 等")


class ApiBatchRunResult(BaseModel):
    """批量执行结果"""
    record_id: Optional[int] = None
    total: int
    success: int
    failed: int
    total_time: Optional[float] = Field(default=None, description="总耗时(秒)")
    results: List[ApiRunResult]


class ApiSuiteRunRecordOut(BaseModel):
    """套件执行记录输出"""
    id: int
    suite_id: int
    suite_name: str
    project_id: int
    status: str
    trigger_type: str
    total_cases: int
    success_cases: int
    failed_cases: int
    skipped_cases: int
    start_time: datetime
    end_time: Optional[datetime]
    duration: float
    env_id: Optional[int]
    env_name: Optional[str]
    run_by: str
    
    class Config:
        from_attributes = True


class ApiSuiteRunListResponse(BaseModel):
    """套件执行记录列表响应"""
    data: List[ApiSuiteRunRecordOut]
    total: int
    page: int
    size: int


# ============ 定时任务相关 ============

class ApiCronJobBase(BaseModel):
    """接口定时任务基础"""
    name: str = Field(..., max_length=100, description="任务名称")
    run_type: str = Field(..., description="类型: Interval/date/crontab")
    interval: int = Field(default=3600, description="间隔(秒)")
    run_date: Optional[str] = Field(None, description="固定执行时间(格式: 2026-01-01 12:00:00)")
    crontab: Dict[str, str] = Field(default={"minute": "0", "hour": "*", "day": "*", "month": "*", "day_of_week": "*"})
    env_id: int = Field(..., description="执行环境ID")
    state: bool = Field(default=False, description="是否启用")
    # 执行记录
    last_run_record_id: Optional[int] = Field(None, description="最后一次执行记录ID")
    last_run_time: Optional[datetime] = Field(None, description="最后一次执行时间")
    last_run_status: Optional[str] = Field(None, description="最后一次执行状态")


class ApiCronJobCreate(ApiCronJobBase):
    """创建接口定时任务"""
    project_id: int = Field(..., description="所属项目ID")
    suite_id: Optional[int] = Field(None, description="关联套件ID（与 plan_id 二选一）")
    plan_id: Optional[int] = Field(None, description="关联测试计划ID（与 suite_id 二选一）")


class ApiCronJobUpdate(ApiCronJobBase):
    """更新接口定时任务"""
    suite_id: Optional[int] = Field(None, description="关联套件ID（与 plan_id 二选一）")
    plan_id: Optional[int] = Field(None, description="关联测试计划ID（与 suite_id 二选一）")


class ApiCronJobOut(ApiCronJobBase):
    """接口定时任务输出"""
    id: str
    project_id: int
    suite_id: Optional[int] = None
    suite_name: Optional[str] = None
    plan_id: Optional[int] = None
    plan_name: Optional[str] = None
    target_type: str = "suite"   # suite / plan
    create_by: str
    update_by: Optional[str] = None
    create_time: datetime
    update_time: datetime

    class Config:
        from_attributes = True


class ApiCronJobListResponse(BaseModel):
    """接口定时任务列表响应"""
    data: List[ApiCronJobOut]
    total: int


# ============ 测试计划相关 ============

class ApiPlanBase(BaseModel):
    """测试计划基础"""
    name: str = Field(..., max_length=100, description="计划名称")
    description: Optional[str] = Field(None, description="计划描述")
    env_id: Optional[int] = Field(None, description="默认执行环境ID")
    variables: Dict[str, Any] = Field(default={}, description="计划级全局变量")
    parallel: bool = Field(default=False, description="是否并行执行各 Item")
    is_template: bool = Field(default=False, description="是否为计划模板")
    catalog_id: Optional[int] = Field(None, description="所属目录ID")


class ApiPlanCreate(ApiPlanBase):
    """创建测试计划"""
    project_id: int = Field(..., description="所属项目ID")


class ApiPlanUpdate(ApiPlanBase):
    """更新测试计划"""
    pass


class ApiPlanOut(ApiPlanBase):
    """测试计划输出"""
    id: int
    project_id: int
    is_template: bool = False
    catalog_id: Optional[int] = None
    catalog_name: Optional[str] = Field(None, description="所属目录名称")
    item_count: int = 0
    suite_item_count: int = Field(0, description="套件条目数")
    case_item_count: int = Field(0, description="用例条目数")
    run_count: int = Field(0, description="累计执行次数")
    last_run_status: Optional[str] = Field(None, description="最近执行状态")
    last_run_time: Optional[datetime] = Field(None, description="最近执行时间")
    cron_job_count: int = Field(0, description="关联定时任务数")
    cron_enabled_count: int = Field(0, description="已启用定时任务数")
    create_by: str
    update_by: Optional[str] = None
    create_time: datetime
    update_time: datetime

    class Config:
        from_attributes = True


class ApiPlanListSummary(BaseModel):
    """计划列表页汇总（随目录/关键字筛选变化）"""
    plan_count: int = 0
    total_items: int = 0
    suite_items: int = 0
    case_items: int = 0
    parallel_plans: int = 0
    serial_plans: int = 0
    uncataloged_plans: int = 0
    total_runs: int = 0
    runs_7d: int = 0
    run_success_count: int = 0
    run_finished_count: int = 0
    run_success_rate: Optional[float] = Field(None, description="已完成执行的成功率(%)")
    cron_job_count: int = 0
    cron_enabled_count: int = 0


class ApiPlanListResponse(BaseModel):
    """测试计划列表响应"""
    data: List[ApiPlanOut]
    total: int
    page: int
    size: int
    summary: Optional[ApiPlanListSummary] = None


class ApiLinkedCaseBrief(BaseModel):
    """接口关联用例摘要"""
    id: int
    name: str
    priority: str = "P2"
    create_by: Optional[str] = None
    update_time: Optional[datetime] = None


class ApiPlanItemIn(BaseModel):
    """计划内容项输入"""
    item_type: str = Field(..., description="类型: suite/case")
    suite_id: Optional[int] = Field(None, description="关联套件ID")
    case_id: Optional[int] = Field(None, description="关联用例ID")
    sort: int = Field(default=0, description="排序")
    depends_on: List[int] = Field(
        default=[],
        description="依赖项 sort 序号列表（0-based，对应该次 items 数组位置；保存后持久化为 item ID）",
    )


class ApiPlanItemOut(BaseModel):
    """计划内容项输出"""
    id: int
    item_type: str
    suite_id: Optional[int] = None
    suite_name: Optional[str] = None
    case_id: Optional[int] = None
    case_name: Optional[str] = None
    api_name: Optional[str] = None
    api_method: Optional[str] = None
    sort: int
    depends_on: List[int] = []

    class Config:
        from_attributes = True


class ApiPlanItemsUpdateRequest(BaseModel):
    """全量更新计划内容请求"""
    items: List[ApiPlanItemIn]


class ApiPlanDetailOut(ApiPlanOut):
    """测试计划详情输出（含 items）"""
    items: List[ApiPlanItemOut] = []


class ApiPlanAddSuiteRequest(BaseModel):
    """追加套件请求"""
    suite_id: int = Field(..., description="套件ID")
    sort: Optional[int] = Field(None, description="排序，不传则追加到末尾")


class ApiPlanAddCasesRequest(BaseModel):
    """批量追加用例请求"""
    case_ids: List[int] = Field(..., description="用例ID列表")
    sort_start: Optional[int] = Field(None, description="起始排序值，不传则追加到末尾")


class ApiPlanSaveAsTemplateRequest(BaseModel):
    """另存为计划模板"""
    name: str = Field(..., max_length=100, description="模板名称")


class ApiPlanFromTemplateRequest(BaseModel):
    """从模板创建计划"""
    name: str = Field(..., max_length=100, description="计划名称")
    project_id: int = Field(..., description="所属项目ID")
    catalog_id: Optional[int] = Field(None, description="所属目录ID")
    env_id: Optional[int] = Field(None, description="默认环境ID")


class ApiPlanRunRequest(BaseModel):
    """执行测试计划请求"""
    env_id: Optional[int] = Field(None, description="执行环境ID，不传则使用计划默认环境")
    variables: Optional[Dict[str, Any]] = Field(default=None, description="额外变量，优先级高于计划级变量")
    stop_on_failure: bool = Field(default=False, description="遇到失败是否停止")
    auto_validate_schema: bool = Field(default=False, description="是否自动校验响应 Schema")
    trigger_type: str = Field(default="manual", description="触发方式: manual/cron/assistant 等")


class ApiPlanItemRunResult(BaseModel):
    """计划单个 Item 执行结果"""
    item_id: int
    item_type: str  # suite / case
    name: str
    status: str     # success / failed / skipped
    total: int = 0
    success: int = 0
    failed: int = 0
    duration: float = 0.0
    case_results: List[Any] = []
    error: Optional[str] = None


class ApiPlanRunResult(BaseModel):
    """执行测试计划返回结果"""
    plan_id: int
    plan_name: str
    env_id: int
    env_name: str
    status: str     # success / failed
    total: int
    success: int
    failed: int
    duration: float
    item_results: List[ApiPlanItemRunResult] = []
    run_by: str = "admin"
    record_id: Optional[int] = None   # 持久化后的记录ID


class ApiPlanRunRecordOut(BaseModel):
    """测试计划执行记录输出"""
    id: int
    plan_id: int
    project_id: int
    status: str
    trigger_type: str
    total_cases: int
    success_cases: int
    failed_cases: int
    env_id: Optional[int] = None
    env_name: Optional[str] = None
    duration: Optional[float] = None
    http_duration: Optional[float] = Field(None, description="接口总耗时(ms)")
    run_by: str
    start_time: datetime
    end_time: Optional[datetime] = None

    class Config:
        from_attributes = True


class ApiPlanRunRecordDetail(ApiPlanRunRecordOut):
    """测试计划执行记录详情（含 item_results）"""
    plan_name: Optional[str] = None
    item_results: List[Any] = []


class ApiPlanRunRecordListResponse(BaseModel):
    """测试计划执行记录列表"""
    data: List[ApiPlanRunRecordOut]
    total: int
    page: int
    size: int


class ApiPlanAsyncRunResponse(BaseModel):
    """计划异步执行响应"""
    record_id: int
    message: str = "计划已开始后台执行"


# ============ 用例导入/导出 ============

class ApiCaseBatchExportRequest(BaseModel):
    """批量导出用例请求"""
    case_ids: List[int] = Field(..., description="要导出的用例ID列表")


class ApiCaseBatchUpdateCatalogRequest(BaseModel):
    """批量修改用例目录"""
    case_ids: List[int] = Field(..., description="用例ID列表")
    catalog_id: Optional[int] = Field(None, description="目标目录ID，null 表示移出目录")


class ApiCaseImportResult(BaseModel):
    """批量导入用例结果"""
    success: int = Field(default=0, description="成功创建数")
    failed: int = Field(default=0, description="失败数")
    warnings: List[str] = Field(default=[], description="警告信息（接口未匹配等）")
    errors: List[str] = Field(default=[], description="错误信息")
    created_names: List[str] = Field(default=[], description="已创建的用例名列表")


# ============ Mock 接口 ============

class MockApiBase(BaseModel):
    name: str = Field(..., max_length=100, description="Mock名称")
    method: str = Field(..., max_length=10, description="请求方法 GET/POST/PUT/DELETE/PATCH")
    path: str = Field(..., max_length=500, description="匹配路径，如 /api/users")
    match_rules: Dict[str, Any] = Field(default={}, description="高级匹配规则")
    response_status: int = Field(default=200, description="响应状态码")
    response_headers: Dict[str, Any] = Field(default={}, description="响应头")
    response_body: Any = Field(default={}, description="响应体（支持 dict/list/str）")
    response_delay: int = Field(default=0, ge=0, description="延迟响应毫秒数")
    is_enabled: bool = Field(default=True, description="是否启用")


class MockApiCreate(MockApiBase):
    project_id: int = Field(..., description="所属项目ID")


class MockApiUpdate(MockApiBase):
    pass


class MockApiOut(MockApiBase):
    id: int
    project_id: int
    call_count: int = 0
    last_call_time: Optional[datetime] = None
    create_time: datetime
    update_time: datetime

    class Config:
        from_attributes = True


class MockApiListResponse(BaseModel):
    data: List[MockApiOut]
    total: int
    page: int
    size: int

