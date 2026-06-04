"""
系统管理相关 Pydantic Schemas
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
from datetime import datetime


# ========== 用户相关 ==========
class UserRoleSchema(BaseModel):
    """用户角色Schema"""
    id: int
    name: str
    
    class Config:
        from_attributes = True


class UserBase(BaseModel):
    """用户基础Schema"""
    username: str
    nickname: str
    email: str = ""
    mobile: str = ""
    avatar: str = ""
    is_active: bool = True
    is_superuser: bool = False


class UserSchemas(UserBase):
    """用户详情Schema"""
    id: int
    created_at: Optional[datetime] = None
    update_time: Optional[datetime] = None
    is_del: bool = False
    roles: List[UserRoleSchema] = []
    permissions: List[str] = []
    default_project_id: Optional[int] = None
    
    class Config:
        from_attributes = True


class UserListSchemas(BaseModel):
    """用户列表Schema"""
    total: int
    data: List[UserSchemas]


class RegisterForm(BaseModel):
    """注册表单"""
    username: str
    password: str
    password_confirm: str
    nickname: str
    email: str
    mobile: str
    roles: List[int] = []
    admin_username: str = ""
    admin_password: str = ""


class RegisterSchemas(UserSchemas):
    """注册返回Schema"""
    pass


class LoginForm(BaseModel):
    """登录表单"""
    username: str
    password: str


class LoginSchemas(BaseModel):
    """登录返回Schema"""
    token: str
    user: UserSchemas


class TokenForm(BaseModel):
    """Token表单"""
    token: str


class Token(BaseModel):
    """Token Schema"""
    access_token: str
    token_type: str = "bearer"


class UserUpdateForm(BaseModel):
    """用户更新表单"""
    username: str
    nickname: str
    email: str
    mobile: str
    avatar: str = ""
    is_active: bool
    is_superuser: bool
    is_del: Optional[bool] = None
    roles: Optional[List[int]] = None


class ProfileUpdateForm(BaseModel):
    """个人资料更新表单（当前登录用户自用）"""
    nickname: str
    email: str
    mobile: str
    avatar: str = ""


class PasswordChangeForm(BaseModel):
    """修改密码表单"""
    old_password: str
    new_password: str
    new_password_confirm: str


# ========== 角色相关 ==========
class RoleSchemas(BaseModel):
    """角色Schema"""
    id: int
    name: str
    description: str = ""
    permissions: List[str] = []
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    is_del: bool = False
    
    class Config:
        from_attributes = True


class RoleListSchemas(BaseModel):
    """角色列表Schema"""
    total: int
    data: List[RoleSchemas]


class AddRoleForm(BaseModel):
    """添加角色表单"""
    name: str
    description: str = ""
    permissions: List[str] = []


class UpdateRoleForm(BaseModel):
    """更新角色表单"""
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[str]] = None
    is_del: Optional[bool] = None


# ========== 项目相关 ==========
class ProjectSchemas(BaseModel):
    """项目Schema"""
    id: int
    name: str
    global_vars: Optional[dict] = {}
    default_headers: List[Dict[str, Any]] = Field(default=[], description="项目级默认请求头")
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    user_id: int
    username: str
    is_del: bool = False
    is_user_default: bool = False

    @field_validator("default_headers", mode="before")
    @classmethod
    def coerce_default_headers(cls, v):
        return v if isinstance(v, list) else []

    @field_validator("global_vars", mode="before")
    @classmethod
    def coerce_global_vars(cls, v):
        return v if isinstance(v, dict) else {}

    class Config:
        from_attributes = True


class ProjectListSchemas(BaseModel):
    """项目列表Schema"""
    total: int
    data: List[ProjectSchemas]


class AddProjectForm(BaseModel):
    """添加项目表单"""
    name: str
    user: int
    username: str


class UpdateProjectForm(BaseModel):
    """更新项目表单"""
    name: Optional[str] = None
    global_vars: Optional[dict] = None
    default_headers: Optional[List[Dict[str, Any]]] = None
    is_del: Optional[bool] = None


# ========== 环境相关 ==========
class EnvironmentSchemas(BaseModel):
    """环境Schema"""
    id: int
    name: str
    host: str
    global_vars: dict = {}
    default_headers: List[Dict[str, Any]] = Field(default=[], description="环境级默认请求头")
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    project_id: int
    username: str
    is_del: bool = False

    @field_validator("default_headers", mode="before")
    @classmethod
    def coerce_default_headers(cls, v):
        return v if isinstance(v, list) else []

    @field_validator("global_vars", mode="before")
    @classmethod
    def coerce_global_vars(cls, v):
        return v if isinstance(v, dict) else {}

    class Config:
        from_attributes = True


class EnvironmentListSchemas(BaseModel):
    """环境列表Schema"""
    total: int
    data: List[EnvironmentSchemas]


class AddEnvironmentForm(BaseModel):
    """添加环境表单"""
    name: str
    host: str
    global_vars: dict = {}
    default_headers: List[Dict[str, Any]] = Field(default=[], description="环境级默认请求头")
    project_id: int
    username: Optional[str] = None


class UpdateEnvironmentForm(BaseModel):
    """更新环境表单"""
    name: Optional[str] = None
    host: Optional[str] = None
    global_vars: Optional[dict] = None
    default_headers: Optional[List[Dict[str, Any]]] = None
    project_id: Optional[int] = None
    is_del: Optional[bool] = None


# ========== 设备相关 ==========
class DeviceSchemas(BaseModel):
    """设备Schema"""
    id: str
    ip: str
    name: str
    system: str
    status: str = "离线"
    username: str
    version: str = ""
    hostname: str = ""
    runner_client_version: str = ""
    runner_last_heartbeat: Optional[datetime] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    is_del: bool = False
    
    class Config:
        from_attributes = True


class DeviceListSchemas(BaseModel):
    """设备列表Schema"""
    total: int
    data: List[DeviceSchemas]


class AddDeviceForm(BaseModel):
    """添加设备表单"""
    ip: str
    name: str
    system: str
    status: str = "离线"
    version: str = ""
    hostname: str = ""


class UpdateDeviceForm(BaseModel):
    """更新设备表单"""
    ip: Optional[str] = None
    name: Optional[str] = None
    system: Optional[str] = None
    status: Optional[str] = None
    version: Optional[str] = None
    hostname: Optional[str] = None
    is_del: Optional[bool] = None


# ========== 测试目录相关 ==========
class TestCatalogOut(BaseModel):
    """测试目录 Schema"""
    id: int
    name: str
    project_id: int
    parent_id: Optional[int] = None
    sort: int = 0
    description: Optional[str] = None
    username: str
    is_del: bool = False
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

    class Config:
        from_attributes = True


class TestCatalogTreeNode(TestCatalogOut):
    """测试目录树节点"""
    children: List["TestCatalogTreeNode"] = []
    ui_cases_count: Optional[int] = None
    ui_suites_count: Optional[int] = None
    api_defs_count: Optional[int] = None
    api_cases_count: Optional[int] = None
    api_suites_count: Optional[int] = None
    ui_tasks_count: Optional[int] = None
    api_plans_count: Optional[int] = None


class TestCatalogCreate(BaseModel):
    """创建测试目录"""
    name: str
    project_id: int
    parent_id: Optional[int] = None
    sort: int = 0
    description: Optional[str] = None


class TestCatalogUpdate(BaseModel):
    """更新测试目录"""
    name: Optional[str] = None
    parent_id: Optional[int] = None
    sort: Optional[int] = None
    description: Optional[str] = None
    is_del: Optional[bool] = None


# 兼容旧模块表单别名
AddModuleForm = TestCatalogCreate
UpdateModuleForm = TestCatalogUpdate
ModuleSchemas = TestCatalogOut


class TestCatalogListSchemas(BaseModel):
    """测试目录列表 Schema"""
    total: int
    data: List[TestCatalogOut]


ModuleListSchemas = TestCatalogListSchemas


TestCatalogTreeNode.model_rebuild()


# ========== 操作日志相关 ==========
class OperationLogSchemas(BaseModel):
    """操作日志Schema"""
    id: int
    user_id: int
    username: str
    action: str
    module: str
    method: str
    path: str
    path_name: str = ""
    params: dict = {}
    ip: str = ""
    status_code: int = 200
    create_time: Optional[datetime] = None

    class Config:
        from_attributes = True


class OperationLogListSchemas(BaseModel):
    """操作日志列表Schema"""
    total: int
    data: List[OperationLogSchemas]
