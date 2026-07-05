"""App 自动化 Pydantic Schemas"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class AppCaseSchemas(BaseModel):
    id: int
    name: str
    project_id: int
    catalog_id: Optional[int] = None
    steps: list = Field(default_factory=list)
    level: str = "P2"
    platform_scope: str = "android"
    driver_mode: str = "hybrid"
    description: Optional[str] = None
    username: str
    update_by: Optional[str] = None
    create_time: datetime
    update_time: datetime
    is_del: bool = False

    class Config:
        from_attributes = True


class AddAppCaseForm(BaseModel):
    name: str
    project_id: int
    steps: list = Field(default_factory=list)
    level: str = "P2"
    platform_scope: str = "android"
    driver_mode: str = "hybrid"
    description: Optional[str] = None
    username: str
    catalog_id: Optional[int] = None


class UpdateAppCaseForm(BaseModel):
    name: Optional[str] = None
    steps: Optional[list] = None
    level: Optional[str] = None
    platform_scope: Optional[str] = None
    driver_mode: Optional[str] = None
    description: Optional[str] = None
    catalog_id: Optional[int] = None
    is_del: bool = False


class AppSuiteSchemas(BaseModel):
    id: int
    name: str
    project_id: int
    catalog_id: Optional[int] = None
    pre_actions: list = Field(default_factory=list)
    setup_sql_ids: list = Field(default_factory=list)
    teardown_sql_ids: list = Field(default_factory=list)
    db_assertions: list = Field(default_factory=list)
    suite_type: str = "1"
    stop_on_failure: bool = False
    propagate_variables: bool = False
    username: str
    update_by: Optional[str] = None
    create_time: datetime
    update_time: datetime
    is_del: bool = False

    class Config:
        from_attributes = True


class AddAppSuiteForm(BaseModel):
    name: str
    project_id: int
    username: str
    catalog_id: Optional[int] = None
    pre_actions: list = Field(default_factory=list)
    setup_sql_ids: list = Field(default_factory=list)
    teardown_sql_ids: list = Field(default_factory=list)
    db_assertions: list = Field(default_factory=list)
    suite_type: str = "1"
    stop_on_failure: bool = False
    propagate_variables: bool = False


class UpdateAppSuiteForm(BaseModel):
    name: Optional[str] = None
    catalog_id: Optional[int] = None
    pre_actions: Optional[list] = None
    setup_sql_ids: Optional[list] = None
    teardown_sql_ids: Optional[list] = None
    db_assertions: Optional[list] = None
    suite_type: Optional[str] = None
    stop_on_failure: Optional[bool] = None
    propagate_variables: Optional[bool] = None
    is_del: bool = False


class AddAppSuiteStepForm(BaseModel):
    case_id: int
    sort: int = 0
    skip: bool = False


class AppPlanSchemas(BaseModel):
    id: int
    name: str
    project_id: int
    catalog_id: Optional[int] = None
    parallel: bool = False
    record_video: bool = True
    username: str
    update_by: Optional[str] = None
    create_time: datetime
    update_time: datetime
    is_del: bool = False

    class Config:
        from_attributes = True


class AddAppPlanForm(BaseModel):
    name: str
    project_id: int
    username: str
    catalog_id: Optional[int] = None
    parallel: bool = False
    record_video: bool = True


class UpdateAppPlanForm(BaseModel):
    name: Optional[str] = None
    catalog_id: Optional[int] = None
    parallel: Optional[bool] = None
    record_video: Optional[bool] = None
    is_del: bool = False


class UpdateAppPlanSuitesForm(BaseModel):
    suite_ids: List[int] = Field(default_factory=list)


class AppDeviceItem(BaseModel):
    device_id: str
    weight: int = Field(default=1, ge=1, le=100)
    concurrency: int = Field(default=1, ge=1, le=1)


class AppRunForm(BaseModel):
    env_id: int
    device_id: str = ""
    devices: Optional[List[AppDeviceItem]] = None
    concurrency: int = Field(default=1, ge=1, le=1)
    username: str = ""
    app_udid: str = Field(default="", description="adb 设备序列号，空则使用设备登记值")
    app_id: str = Field(default="", description="默认启动包名")
    implicit_wait: int = 10
    auto_grant_permissions: bool = True
    no_reset: bool = True
    record_video: Optional[bool] = Field(default=None, description="是否录制用例视频，空则使用计划默认值")
    ai_heal_enabled: Optional[bool] = Field(
        default=None,
        description="本次执行是否启用 AI 定位器自愈；不传则使用项目默认",
    )
    trigger_source: Optional[str] = None


class AppCaseDebugForm(AppRunForm):
    """App 用例步骤级调试：执行 steps[0:through_index+1] 后停止"""
    steps: list = Field(description="当前编辑器步骤（可未保存）")
    through_index: int = Field(ge=0, description="调试到此步（含该步，0-based）")
    driver_mode: str = Field(default="hybrid", description="用例驱动模式（与编辑器一致）")


class AppFragmentCreate(BaseModel):
    project_id: int
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    steps: list = Field(default_factory=list)
    tags: Optional[str] = Field(None, max_length=200)


class AppFragmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    steps: Optional[list] = None
    tags: Optional[str] = Field(None, max_length=200)


class AppFragmentExpandRequest(BaseModel):
    project_id: int
    steps: list = Field(default_factory=list)
    variables: dict = Field(default_factory=dict)


class AppCronJobCreate(BaseModel):
    name: str
    project_id: int
    suite_id: Optional[int] = None
    plan_id: Optional[int] = None
    env_id: int
    run_type: str
    interval: int = 3600
    run_date: Optional[str] = None
    crontab: dict = Field(default_factory=dict)
    device_id: Optional[str] = None
    app_udid: str = ""
    app_id: str = ""
    state: bool = False


class AppCronJobUpdate(AppCronJobCreate):
    pass


class AppCronJobOut(BaseModel):
    id: str
    name: str
    project_id: int
    suite_id: Optional[int] = None
    suite_name: Optional[str] = None
    plan_id: Optional[int] = None
    plan_name: Optional[str] = None
    target_type: str
    env_id: int
    device_id: Optional[str] = None
    app_udid: str = ""
    app_id: str = ""
    run_type: str
    interval: int
    run_date: Optional[str] = None
    crontab: dict = Field(default_factory=dict)
    state: bool
    last_run_record_id: Optional[int] = None
    last_run_time: Optional[datetime] = None
    last_run_status: Optional[str] = None
    create_by: str
    update_by: Optional[str] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None


class AppElementSchemas(BaseModel):
    id: int
    name: str
    project_id: int
    element_type: str = "control"
    locator: dict = Field(default_factory=dict)
    platform_map: dict = Field(default_factory=dict)
    remark: str = ""
    username: str
    update_by: Optional[str] = None
    create_time: datetime
    update_time: datetime
    is_del: bool = False

    class Config:
        from_attributes = True


class AddAppElementForm(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    project_id: int
    element_type: str = Field(default="control", description="control|image")
    locator: dict = Field(default_factory=dict)
    platform_map: dict = Field(default_factory=dict)
    remark: str = ""
    username: str = ""


class UpdateAppElementForm(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    element_type: Optional[str] = None
    locator: Optional[dict] = None
    platform_map: Optional[dict] = None
    remark: Optional[str] = None
    is_del: bool = False


class AppTemplatePresignForm(BaseModel):
    object_keys: List[str] = Field(default_factory=list)


class AppInspectorSessionForm(BaseModel):
    project_id: int
    device_id: str
    app_udid: str = ""


class AppInspectorCallbackForm(BaseModel):
    success: bool
    hierarchy: Optional[dict] = None
    screenshot_url: Optional[str] = None
    package: str = ""
    activity: str = ""
    error: Optional[str] = None
    webview_nodes: Optional[list] = None
    webview_contexts: Optional[list] = None
    webview_hint: Optional[str] = None
    dom: Optional[dict] = None
    selected_page: Optional[dict] = None
    contexts: Optional[list] = None


class AppInspectorWebviewProbeForm(BaseModel):
    page_index: int = Field(default=0, ge=0, description="H5 页面索引")
    package: str = Field(default="", description="限定 App 包名（WebView 时有效）")
    devtools_source: str = Field(
        default="webview",
        description="webview=App 内 WebView，chrome=手机 Chrome 浏览器",
    )


class AppInspectorExploreForm(BaseModel):
    action: str = Field(..., description="tap|input|swipe|back|home|press")
    x: Optional[int] = Field(default=None, description="tap/swipe 起点 X")
    y: Optional[int] = Field(default=None, description="tap/swipe 起点 Y")
    x2: Optional[int] = Field(default=None, description="swipe 终点 X")
    y2: Optional[int] = Field(default=None, description="swipe 终点 Y")
    text: str = Field(default="", description="input 文本")
    key: str = Field(default="", description="press 按键名，如 enter")
    duration: float = Field(default=0.3, ge=0.05, le=3.0, description="swipe 时长秒")
    refresh_tree: bool = Field(default=True, description="操作后是否刷新控件树")
