"""
系统管理相关模型
"""
from tortoise import models, fields


class User(models.Model):
    """用户模型"""
    id = fields.IntField(pk=True, auto_increment=True, description="用户id")
    username = fields.CharField(max_length=50, description="用户名")
    password = fields.CharField(max_length=255, description="密码")
    nickname = fields.CharField(max_length=50, description="用户昵称")
    email = fields.CharField(max_length=50, description="邮箱", default="")
    mobile = fields.CharField(max_length=11, description="手机号", default="")
    avatar = fields.CharField(max_length=255, description="头像URL", default="")
    is_active = fields.BooleanField(default=True, description="是否激活")
    is_superuser = fields.BooleanField(default=False, description="是否超级管理员")
    created_at = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    roles = fields.ManyToManyField("models.Role", related_name="users", description="用户角色")
    default_project = fields.ForeignKeyField(
        "models.Project",
        related_name="default_for_users",
        null=True,
        on_delete=fields.SET_NULL,
        description="登录后默认进入的项目",
    )
    is_del = fields.BooleanField(description="是否删除", default=False)

    def __str__(self):
        return self.nickname

    class Meta:
        table = "user"
        table_description = "用户列表"


class Role(models.Model):
    """角色模型"""
    id = fields.IntField(pk=True, auto_increment=True, description="角色ID")
    code = fields.CharField(max_length=50, description="角色唯一标识", null=True, unique=True)
    name = fields.CharField(max_length=50, description="角色名称")
    description = fields.CharField(max_length=255, description="角色描述", default="")
    permissions = fields.JSONField(description="权限列表", default=list)
    is_system = fields.BooleanField(default=False, description="是否系统预置角色")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    is_del = fields.BooleanField(description="是否删除", default=False)

    def __str__(self):
        return self.name

    class Meta:
        table = "role"
        table_description = "角色列表"


class InviteCode(models.Model):
    """注册邀请码"""
    id = fields.IntField(pk=True, auto_increment=True, description="邀请码ID")
    code = fields.CharField(max_length=32, unique=True, description="邀请码")
    role_ids = fields.JSONField(default=list, description="注册后绑定的角色ID列表")
    max_uses = fields.IntField(default=1, description="最大可用次数")
    used_count = fields.IntField(default=0, description="已使用次数")
    expires_at = fields.DatetimeField(null=True, description="过期时间")
    note = fields.CharField(max_length=255, default="", description="备注")
    created_by_id = fields.IntField(null=True, description="创建人ID")
    created_by_username = fields.CharField(max_length=50, default="", description="创建人用户名")
    is_active = fields.BooleanField(default=True, description="是否启用")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    is_del = fields.BooleanField(default=False, description="是否删除")

    class Meta:
        table = "invite_code"
        table_description = "注册邀请码"


class Project(models.Model):
    """项目表模型"""
    id = fields.IntField(pk=True, description="项目id", auto_increment=True)
    name = fields.CharField(max_length=255, description="项目名称")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    user = fields.ForeignKeyField("models.User", related_name="projects", description="项目创建人")
    username = fields.CharField(max_length=50, description="创建人")
    global_vars = fields.JSONField(description="项目全局变量", default=dict)
    default_headers = fields.JSONField(description="项目级默认请求头", default=list)
    is_del = fields.BooleanField(description="是否删除", default=False)

    def __str__(self):
        return self.name

    class Meta:
        table = "project"
        table_description = "测试项目"


class ProjectMember(models.Model):
    """项目成员"""
    id = fields.IntField(pk=True, auto_increment=True, description="成员记录ID")
    project = fields.ForeignKeyField("models.Project", related_name="members", description="所属项目")
    user = fields.ForeignKeyField("models.User", related_name="project_memberships", description="用户")
    role = fields.CharField(max_length=20, description="项目角色 owner/manager/member/viewer", default="member")
    invited_by = fields.ForeignKeyField(
        "models.User",
        related_name="invited_project_members",
        null=True,
        description="邀请人",
    )
    create_time = fields.DatetimeField(auto_now_add=True, description="加入时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    is_del = fields.BooleanField(default=False, description="是否删除")

    class Meta:
        table = "project_member"
        table_description = "项目成员"
        unique_together = (("project", "user"),)


class Environment(models.Model):
    """环境的模型类"""
    id = fields.IntField(pk=True, description="环境id")
    name = fields.CharField(max_length=255, description="环境名称")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    project = fields.ForeignKeyField("models.Project", related_name="environments", description="所属项目")
    host = fields.CharField(max_length=255, description="环境地址")
    global_vars = fields.JSONField(description="全局变量", default=dict)
    default_headers = fields.JSONField(description="环境级默认请求头", default=list)
    username = fields.CharField(max_length=50, description="创建人")
    is_del = fields.BooleanField(description="是否删除", default=False)

    def __str__(self):
        return self.name

    class Meta:
        table = "environment"
        table_description = "测试环境"


class Device(models.Model):
    """设备模型"""
    id = fields.CharField(max_length=50, pk=True, description="设备id")
    ip = fields.CharField(max_length=50, description="设备ip")
    name = fields.CharField(max_length=50, description="设备名称")
    system = fields.CharField(max_length=50, description="操作系统")
    status = fields.CharField(max_length=20, description="设备状态", default="离线")
    username = fields.CharField(max_length=50, description="创建人")
    version = fields.CharField(max_length=50, description="设备版本", default="")
    hostname = fields.CharField(max_length=50, description="设备主机名", default="")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    is_del = fields.BooleanField(description="是否删除", default=False)
    runner_session_jti = fields.CharField(max_length=64, default="", description="Runner 会话 jti")
    runner_bound_user_id = fields.IntField(null=True, description="Runner 绑定用户 ID")
    runner_client_version = fields.CharField(max_length=50, default="", description="Runner 客户端版本")
    runner_last_heartbeat = fields.DatetimeField(null=True, description="Runner 最后心跳")
    runner_mq_username = fields.CharField(max_length=128, default="", description="Runner 隔离 MQ 用户名")
    runner_mq_password = fields.CharField(max_length=256, default="", description="Runner 隔离 MQ 密码（服务端）")
    runner_redis_username = fields.CharField(max_length=128, default="", description="Runner 隔离 Redis 用户名")
    runner_redis_password = fields.CharField(max_length=256, default="", description="Runner 隔离 Redis 密码（服务端）")
    runner_engine_types = fields.JSONField(
        default=list, description="Runner 引擎能力 web|app|perf"
    )
    app_platform = fields.CharField(max_length=20, default="", description="App 平台 android|ios|harmony")
    app_udid = fields.CharField(max_length=128, default="", description="adb/hdc 设备序列号")
    app_connection = fields.CharField(max_length=20, default="", description="usb|wifi")
    toolchain_status = fields.JSONField(default=dict, description="工具链状态 adb/hdc/xcode 等")

    class Meta:
        table = "device"
        table_description = "设备表"


class TestCatalog(models.Model):
    """统一测试目录（原 Module / ApiCategory / ApiTestCaseCategory）"""
    id = fields.IntField(pk=True, description="目录id", auto_increment=True)
    name = fields.CharField(max_length=255, description="目录名称")
    project = fields.ForeignKeyField("models.Project", related_name="test_catalogs", description="所属项目")
    parent = fields.ForeignKeyField(
        "models.TestCatalog", related_name="children", null=True, description="父目录"
    )
    sort = fields.IntField(default=0, description="排序")
    description = fields.TextField(null=True, description="目录描述")
    username = fields.CharField(max_length=50, description="创建人")
    is_del = fields.BooleanField(description="是否删除", default=False)
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")

    def __str__(self):
        return self.name

    class Meta:
        table = "test_catalog"
        table_description = "统一测试目录"


class OperationLog(models.Model):
    """操作日志"""
    id = fields.IntField(pk=True, auto_increment=True, description="日志id")
    user_id = fields.IntField(description="操作人ID")
    username = fields.CharField(max_length=50, description="操作人用户名")
    action = fields.CharField(max_length=100, description="操作行为")
    module = fields.CharField(max_length=50, description="所属模块")
    method = fields.CharField(max_length=10, description="请求方法")
    path = fields.CharField(max_length=255, description="请求路径")
    path_name = fields.CharField(max_length=100, description="路径中文名称", default="")
    params = fields.JSONField(default=dict, description="请求参数")
    ip = fields.CharField(max_length=50, description="客户端IP", default="")
    status_code = fields.IntField(description="响应状态码", default=200)
    create_time = fields.DatetimeField(auto_now_add=True, description="操作时间")

    class Meta:
        table = "operation_log"
        table_description = "操作日志"


class NotificationConfig(models.Model):
    """项目通知配置"""
    id = fields.IntField(pk=True, auto_increment=True, description="配置ID")
    project = fields.ForeignKeyField("models.Project", related_name="notifications", description="所属项目")
    channel_type = fields.CharField(max_length=20, description="通知渠道: email/dingtalk/wechat/feishu")
    enabled = fields.BooleanField(default=True, description="是否启用")
    config = fields.JSONField(default=dict, description="渠道参数")
    auto_push_report = fields.BooleanField(default=False, description="是否自动推送报告(兼容旧字段)")
    api_auto_push_report = fields.BooleanField(default=False, description="API套件执行成功后自动推送报告")
    ui_auto_push_report = fields.BooleanField(default=False, description="UI计划执行成功后自动推送报告")
    perf_auto_push_report = fields.BooleanField(default=False, description="性能测试执行完成后自动推送报告")
    app_auto_push_report = fields.BooleanField(default=False, description="App计划/套件执行完成后自动推送报告")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "notification_config"
        table_description = "项目通知配置"


class NotificationLog(models.Model):
    """通知推送记录"""
    id = fields.IntField(pk=True, auto_increment=True, description="记录ID")
    project = fields.ForeignKeyField("models.Project", related_name="notification_logs", description="所属项目", null=True)
    channel_type = fields.CharField(max_length=20, description="通知渠道: email/dingtalk/wechat/feishu")
    notify_type = fields.CharField(max_length=20, description="通知类型: alert/report")
    title = fields.CharField(max_length=255, description="消息标题")
    content_summary = fields.JSONField(default=dict, description="内容摘要")
    recipients = fields.JSONField(default=list, description="接收人列表")
    status = fields.CharField(max_length=20, description="推送状态: success/failed")
    error_msg = fields.TextField(description="失败原因", default="")
    related_id = fields.IntField(description="关联记录ID", null=True)
    related_type = fields.CharField(max_length=50, description="关联类型", default="")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")

    class Meta:
        table = "notification_log"
        table_description = "通知推送记录"


class SystemSmtpConfig(models.Model):
    """全局 SMTP 配置"""
    id = fields.IntField(pk=True, auto_increment=True, description="配置ID")
    host = fields.CharField(max_length=255, description="SMTP服务器")
    port = fields.IntField(description="端口")
    username = fields.CharField(max_length=255, description="发件账号")
    password = fields.CharField(max_length=255, description="密码/授权码")
    use_tls = fields.BooleanField(default=True, description="是否启用TLS/SSL")
    sender = fields.CharField(max_length=255, description="发件人显示名称")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "system_smtp_config"
        table_description = "全局SMTP配置"


class SystemMcpConfig(models.Model):
    """全局 MCP Server 配置（平台内可改，无需重建镜像）"""
    id = fields.IntField(pk=True, auto_increment=True, description="配置ID")
    enabled = fields.BooleanField(default=True, description="是否启用 MCP Server")
    base_url = fields.CharField(max_length=500, default="", description="平台对外访问地址")
    api_key = fields.CharField(max_length=500, default="", description="MCP API Key（加密存储）")
    update_by = fields.CharField(max_length=50, default="", description="最后修改人")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "system_mcp_config"
        table_description = "全局MCP配置"


class SystemLoginPageConfig(models.Model):
    """登录/注册页展示配置（背景、文案等）"""
    id = fields.IntField(pk=True, auto_increment=True, description="配置ID")
    pro_bg_key = fields.CharField(max_length=20, default="opt3", description="清新 Pro 背景方案")
    classic_bg_key = fields.CharField(max_length=20, default="classic1", description="经典风格背景方案")
    pro_bg_url = fields.CharField(max_length=500, default="", description="Pro 自定义背景 URL")
    classic_bg_url = fields.CharField(max_length=500, default="", description="经典自定义背景 URL")
    welcome_title = fields.CharField(max_length=200, default="欢迎登录 BrickCore", description="登录页标题")
    footer_text = fields.CharField(
        max_length=500, default="© 2025-2026 BrickCore. All Rights Reserved.", description="页脚文案"
    )
    show_register = fields.BooleanField(default=True, description="是否显示注册入口")
    bg_brick_count = fields.IntField(default=30, description="登录页漂浮积木数量")
    bg_star_count = fields.IntField(default=15, description="登录页四角星数量")
    bg_dot_count = fields.IntField(default=15, description="登录页半透明光点数量")
    bg_motion_enabled = fields.BooleanField(default=True, description="是否启用登录页漂浮动效")
    update_by = fields.CharField(max_length=50, default="", description="最后修改人")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "system_login_page_config"
        table_description = "登录页配置"


class SystemPlatformSettings(models.Model):
    """平台全局设置（数据保留策略等）"""
    id = fields.IntField(pk=True, auto_increment=True, description="配置ID")
    ui_case_record_delete_mode = fields.CharField(
        max_length=20,
        default="logical",
        description="UI用例运行记录删除模式：logical|physical|recycle_bin",
    )
    update_by = fields.CharField(max_length=50, default="", description="最后修改人")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "system_platform_settings"
        table_description = "平台全局设置"


class SystemStreamParserConfig(models.Model):
    """SSE 流式解析配置（问答评测 / 压测流式场景复用）"""
    id = fields.IntField(pk=True, auto_increment=True, description="配置ID")
    name = fields.CharField(max_length=200, description="配置名称")
    description = fields.TextField(null=True, description="说明文档（Markdown）")
    parser_id = fields.CharField(max_length=64, description="内置解析器 ID")
    parser_options = fields.JSONField(default=dict, description="解析器选项（如 rule_based 规则）")
    success_rule = fields.JSONField(default=dict, description="成功判定规则")
    is_builtin = fields.BooleanField(default=False, description="内置预置，不可删除")
    is_enabled = fields.BooleanField(default=True, description="是否启用")
    sort_order = fields.IntField(default=0, description="排序")
    create_by = fields.CharField(max_length=50, default="", description="创建人")
    update_by = fields.CharField(max_length=50, default="", description="最后修改人")
    is_del = fields.BooleanField(default=False)
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "system_stream_parser_config"
        table_description = "SSE流式解析配置"


class SystemRunnerReleaseConfig(models.Model):
    """执行器客户端安装包发布配置（网盘/OSS 外链，避免大文件占服务器磁盘）"""
    id = fields.IntField(pk=True, auto_increment=True, description="配置ID")
    external_download_url = fields.CharField(
        max_length=1000, default="", description="安装包外链（百度网盘/阿里云盘/OSS 等）"
    )
    external_download_label = fields.CharField(
        max_length=100, default="网盘下载", description="外链下载按钮文案"
    )
    update_by = fields.CharField(max_length=50, default="", description="最后修改人")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "system_runner_release_config"
        table_description = "执行器发布配置"


class PlatformDoc(models.Model):
    """平台文档中心 - 自定义文章/视频/附件（可扩展上传）"""
    id = fields.IntField(pk=True, description="文档ID")
    title = fields.CharField(max_length=200, description="标题")
    parent_id = fields.IntField(null=True, description="父级ID")
    builtin_id = fields.CharField(max_length=64, null=True, unique=True, description="内置文档/分组 ID 覆盖")
    doc_type = fields.CharField(max_length=20, default="markdown", description="markdown/video/file/link/group")
    content = fields.TextField(null=True, description="Markdown 正文")
    file_key = fields.CharField(max_length=500, null=True, description="MinIO 对象键或外链")
    link_url = fields.CharField(max_length=1000, null=True, description="外部链接")
    sort_order = fields.IntField(default=0, description="排序")
    is_published = fields.BooleanField(default=True, description="是否发布")
    is_hidden = fields.BooleanField(default=False, description="隐藏内置条目")
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    is_del = fields.BooleanField(default=False)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "platform_doc"
        table_description = "平台文档"


class AssetFavorite(models.Model):
    """用户收藏的接口 / Web 用例（按项目隔离）"""
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="asset_favorites", description="用户")
    project = fields.ForeignKeyField("models.Project", related_name="asset_favorites", description="项目")
    asset_type = fields.CharField(max_length=16, description="api|ui_case")
    asset_id = fields.IntField(description="资产 ID")
    sort_order = fields.IntField(default=0, description="排序")
    create_time = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "asset_favorite"
        table_description = "接口/Web用例收藏"
        unique_together = (("user_id", "project_id", "asset_type", "asset_id"),)
