"""
通知配置相关 API
"""
import asyncio
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field

from app.core.platform.auth import is_authenticated, require_permissions, verify_runner_or_internal
from app.core.platform.permissions import (
    NOTIFICATION_CONFIG_VIEW, NOTIFICATION_CONFIG_EDIT,
    SMTP_CONFIG_VIEW, SMTP_CONFIG_EDIT,
    NOTIFICATION_LOG_VIEW, NOTIFICATION_LOG_EDIT
)
from app.core.ops.notification import NotificationService
from app.models.sys import NotificationConfig, SystemSmtpConfig, Project, NotificationLog

router = APIRouter(prefix="/notifications", tags=["通知配置"], dependencies=[Depends(is_authenticated)])

# 独立的内部接口 router，不需要 JWT，仅用于 Runner 等内部服务调用
internal_router = APIRouter(prefix="/notifications", tags=["通知配置-内部接口"])


# ============ Schemas ============

class NotificationConfigItem(BaseModel):
    channel_type: str = Field(..., description="email/dingtalk/wechat/feishu")
    enabled: bool = True
    api_alert_on_failure: bool = True
    ui_alert_on_failure: bool = True
    perf_alert_on_failure: bool = True
    app_alert_on_failure: bool = True
    config: dict = Field(default_factory=dict)
    api_auto_push_report: bool = False
    ui_auto_push_report: bool = False
    perf_auto_push_report: bool = False
    app_auto_push_report: bool = False


class NotificationConfigOut(BaseModel):
    id: int
    project_id: int
    channel_type: str
    enabled: bool
    api_alert_on_failure: bool = True
    ui_alert_on_failure: bool = True
    perf_alert_on_failure: bool = True
    app_alert_on_failure: bool = True
    config: dict
    api_auto_push_report: bool
    ui_auto_push_report: bool
    perf_auto_push_report: bool = False
    app_auto_push_report: bool = False

    class Config:
        from_attributes = True


def _config_out(cfg: NotificationConfig) -> NotificationConfigOut:
    return NotificationConfigOut(
        id=cfg.id,
        project_id=cfg.project_id,
        channel_type=cfg.channel_type,
        enabled=cfg.enabled,
        api_alert_on_failure=getattr(cfg, "api_alert_on_failure", True),
        ui_alert_on_failure=getattr(cfg, "ui_alert_on_failure", True),
        perf_alert_on_failure=getattr(cfg, "perf_alert_on_failure", True),
        app_alert_on_failure=getattr(cfg, "app_alert_on_failure", True),
        config=cfg.config,
        api_auto_push_report=cfg.api_auto_push_report,
        ui_auto_push_report=cfg.ui_auto_push_report,
        perf_auto_push_report=getattr(cfg, "perf_auto_push_report", False),
        app_auto_push_report=getattr(cfg, "app_auto_push_report", False),
    )


class SmtpConfigForm(BaseModel):
    host: str
    port: int
    username: str
    password: str
    use_tls: bool = True
    sender: str


class SmtpConfigOut(BaseModel):
    id: int
    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    sender: str

    class Config:
        from_attributes = True


class SmtpTestRequest(BaseModel):
    """用当前表单参数测试 SMTP（可不先保存）"""
    host: str
    port: int
    username: str
    password: str = ""
    use_tls: bool = True
    sender: str = ""
    to: Optional[str] = None


class SendUiReportPayload(BaseModel):
    plan_execution_id: int


# ============ 项目通知配置 ============

class NotificationSendTargetOut(BaseModel):
    id: int
    channel_type: str
    enabled: bool
    config: dict = Field(default_factory=dict)


@router.get(
    "/config/send-targets",
    summary="获取可用于发送报告的通知渠道（项目成员）",
    response_model=List[NotificationSendTargetOut],
    status_code=status.HTTP_200_OK,
)
async def list_report_send_targets(
    project_id: int,
    user_info: dict = Depends(is_authenticated),
):
    """发送报告弹窗用：仅返回已启用配置；不要求「通知配置」管理权限。"""
    from app.core.platform.project_access import PROJECT_ROLE_VIEWER, assert_project_access

    await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_VIEWER)
    configs = await NotificationConfig.filter(project_id=project_id, enabled=True).all()
    result = []
    for cfg in configs:
        raw = cfg.config or {}
        # 脱敏：Webhook 只回传截断预览，完整 URL 发送时仍用库内配置
        safe = {}
        if cfg.channel_type == "email":
            safe["recipients"] = raw.get("recipients") or []
        else:
            url = (raw.get("webhook_url") or "").strip()
            safe["webhook_url"] = (url[:48] + "…") if len(url) > 48 else url
        result.append(
            NotificationSendTargetOut(
                id=cfg.id,
                channel_type=cfg.channel_type,
                enabled=True,
                config=safe,
            )
        )
    return result


@router.get(
    "/config",
    summary="获取项目通知配置列表",
    response_model=List[NotificationConfigOut],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permissions(NOTIFICATION_CONFIG_VIEW))],
)
async def get_notification_configs(project_id: int):
    """按项目查询所有通知配置"""
    configs = await NotificationConfig.filter(project_id=project_id).all()
    return [_config_out(cfg) for cfg in configs]


@router.post(
    "/config",
    summary="创建通知配置",
    response_model=NotificationConfigOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(NOTIFICATION_CONFIG_EDIT))],
)
async def create_notification_config(item: NotificationConfigItem, project_id: int):
    """为项目创建通知配置"""
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    cfg = await NotificationConfig.create(
        project_id=project_id,
        channel_type=item.channel_type,
        enabled=item.enabled,
        api_alert_on_failure=item.api_alert_on_failure,
        ui_alert_on_failure=item.ui_alert_on_failure,
        perf_alert_on_failure=item.perf_alert_on_failure,
        app_alert_on_failure=item.app_alert_on_failure,
        config=item.config,
        api_auto_push_report=item.api_auto_push_report,
        ui_auto_push_report=item.ui_auto_push_report,
        perf_auto_push_report=item.perf_auto_push_report,
        app_auto_push_report=item.app_auto_push_report,
    )
    return _config_out(cfg)


@router.put(
    "/config/{config_id}",
    summary="更新通知配置",
    response_model=NotificationConfigOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permissions(NOTIFICATION_CONFIG_EDIT))],
)
async def update_notification_config(config_id: int, item: NotificationConfigItem):
    """更新通知配置"""
    cfg = await NotificationConfig.get_or_none(id=config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")

    cfg.channel_type = item.channel_type
    cfg.enabled = item.enabled
    cfg.api_alert_on_failure = item.api_alert_on_failure
    cfg.ui_alert_on_failure = item.ui_alert_on_failure
    cfg.perf_alert_on_failure = item.perf_alert_on_failure
    cfg.app_alert_on_failure = item.app_alert_on_failure
    cfg.config = item.config
    cfg.api_auto_push_report = item.api_auto_push_report
    cfg.ui_auto_push_report = item.ui_auto_push_report
    cfg.perf_auto_push_report = item.perf_auto_push_report
    cfg.app_auto_push_report = item.app_auto_push_report
    await cfg.save()

    return _config_out(cfg)


@router.delete(
    "/config/{config_id}",
    summary="删除通知配置",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions(NOTIFICATION_CONFIG_EDIT))],
)
async def delete_notification_config(config_id: int):
    """删除通知配置"""
    cfg = await NotificationConfig.get_or_none(id=config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")
    await cfg.delete()


@router.post(
    "/config/{config_id}/test",
    summary="测试通知配置",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permissions(NOTIFICATION_CONFIG_EDIT))],
)
async def test_notification_config(config_id: int):
    """按配置发送一条测试消息"""
    cfg = await NotificationConfig.get_or_none(id=config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")

    project = await Project.get_or_none(id=cfg.project_id)
    project_name = project.name if project else "未知项目"

    content = {
        "execution_type": "测试消息",
        "name": f"项目 [{project_name}] 的通知配置测试",
        "status": "测试",
        "total": 10,
        "success": 10,
        "failed": 0,
        "pass_rate": 100.0,
        "duration": 0,
        "run_by": "系统",
        "link": ""
    }

    # 对于测试消息，三种渠道统一走发送接口；邮件改为发送一条纯测试邮件
    try:
        if cfg.channel_type == "email":
            recipients = cfg.config.get("recipients", [])
            if not recipients:
                raise HTTPException(status_code=400, detail="未配置收件人")
            await NotificationService._send_email(
                to=recipients,
                subject="[测试] BrickCore 通知配置测试",
                body_html=f"<h3>测试成功</h3><p>项目 [{project_name}] 的邮件通知配置已生效。</p>"
            )
        elif cfg.channel_type == "dingtalk":
            await NotificationService._send_dingtalk_alert(cfg, "[测试] 通知配置测试", content)
        elif cfg.channel_type == "wechat":
            await NotificationService._send_wechat_alert(cfg, "[测试] 通知配置测试", content)
        elif cfg.channel_type == "feishu":
            await NotificationService._send_feishu_alert(cfg, "[测试] 通知配置测试", content)
        else:
            raise HTTPException(status_code=400, detail=f"不支持的通知渠道: {cfg.channel_type}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发送失败: {e}")

    return {"detail": "测试消息已发送"}


# ============ 发送 Web 报告（供 Runner 调用） ============

@internal_router.post("/send-ui-report", summary="发送 UI 测试报告邮件", status_code=status.HTTP_200_OK,
                      dependencies=[Depends(verify_runner_or_internal)])
async def send_ui_report_endpoint(payload: SendUiReportPayload):
    """Runner 调用：为指定 UI 计划执行记录生成并发送报告邮件（仅自动推开关打开的配置）"""
    try:
        await NotificationService.send_ui_report(
            plan_execution_id=payload.plan_execution_id,
            auto_push_only=True,
        )
        return {"detail": "报告邮件已发送"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发送失败: {e}")


# ============ 全局 SMTP 配置 ============

@router.get("/smtp", summary="获取全局 SMTP 配置", response_model=Optional[SmtpConfigOut], status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(SMTP_CONFIG_VIEW))])
async def get_smtp_config():
    """获取全局 SMTP 配置"""
    cfg = await SystemSmtpConfig.first()
    if not cfg:
        return None
    return SmtpConfigOut(
        id=cfg.id,
        host=cfg.host,
        port=cfg.port,
        username=cfg.username,
        password=cfg.password,
        use_tls=cfg.use_tls,
        sender=cfg.sender
    )


@router.put("/smtp", summary="更新全局 SMTP 配置", response_model=SmtpConfigOut, status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(SMTP_CONFIG_EDIT))])
async def update_smtp_config(item: SmtpConfigForm):
    """更新全局 SMTP 配置，无记录则创建"""
    cfg = await SystemSmtpConfig.first()
    if cfg:
        cfg.host = item.host
        cfg.port = item.port
        cfg.username = item.username
        cfg.password = item.password
        cfg.use_tls = item.use_tls
        cfg.sender = item.sender
        await cfg.save()
    else:
        cfg = await SystemSmtpConfig.create(
            host=item.host,
            port=item.port,
            username=item.username,
            password=item.password,
            use_tls=item.use_tls,
            sender=item.sender
        )

    return SmtpConfigOut(
        id=cfg.id,
        host=cfg.host,
        port=cfg.port,
        username=cfg.username,
        password=cfg.password,
        use_tls=cfg.use_tls,
        sender=cfg.sender
    )


@router.post("/smtp/test", summary="测试 SMTP 连通性", status_code=status.HTTP_200_OK,
             dependencies=[Depends(require_permissions(SMTP_CONFIG_EDIT))])
async def test_smtp_config(item: SmtpTestRequest):
    """使用当前表单参数连接 SMTP 并发送一封测试邮件（无需先保存）。

    若密码留空，则回退使用已保存的授权码。
    """
    password = item.password
    if not (password or "").strip():
        saved = await SystemSmtpConfig.first()
        if saved and saved.password:
            password = saved.password
    try:
        result = await asyncio.to_thread(
            NotificationService.test_smtp_connection,
            host=item.host,
            port=item.port,
            username=item.username,
            password=password,
            use_tls=item.use_tls,
            sender=item.sender,
            to=item.to,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SMTP 测试失败: {e}")
    return {"detail": f"测试邮件已发送至 {result['to']}", "data": result}


# ============ 推送记录 ============

@router.get("/logs", summary="推送记录列表", status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(NOTIFICATION_LOG_VIEW))])
async def get_notification_logs(
    project_id: int = None,
    channel_type: str = None,
    notify_type: str = None,
    status: str = None,
    page: int = 1,
    size: int = 10
):
    """查询推送记录，支持筛选和分页"""
    query = NotificationLog.all().order_by("-id")
    if project_id:
        query = query.filter(project_id=project_id)
    if channel_type:
        query = query.filter(channel_type=channel_type)
    if notify_type:
        query = query.filter(notify_type=notify_type)
    if status:
        query = query.filter(status=status)

    total = await query.count()
    data = await query.offset((page - 1) * size).limit(size).prefetch_related("project")

    result = []
    for item in data:
        result.append({
            "id": item.id,
            "project_id": item.project_id,
            "project_name": item.project.name if item.project else None,
            "channel_type": item.channel_type,
            "notify_type": item.notify_type,
            "title": item.title,
            "content_summary": item.content_summary,
            "recipients": item.recipients,
            "status": item.status,
            "error_msg": item.error_msg,
            "related_id": item.related_id,
            "related_type": item.related_type,
            "create_time": item.create_time
        })

    return {"total": total, "page": page, "size": size, "data": result}


@router.delete("/logs", summary="批量删除推送记录", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(NOTIFICATION_LOG_EDIT))])
async def delete_notification_logs(ids: List[int]):
    """批量删除推送记录"""
    if not ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    await NotificationLog.filter(id__in=ids).delete()
    return None
