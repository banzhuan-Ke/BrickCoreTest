"""Runner 设备管控（强制停止等）"""
from __future__ import annotations

import logging

from app.core.runner.runner_middleware import revoke_device_middleware
from app.modules.ui.ui_execution_stop import stop_executions_for_device
from app.modules.app.app_execution_stop import stop_executions_for_device as stop_app_executions_for_device
from app.models.sys import Device

logger = logging.getLogger(__name__)

STOPPED_STATUS = "已停止"


async def force_stop_runner_device(device: Device) -> None:
    """
    管理员强制停止 Runner：标记已停止、吊销会话与中间件凭证。
    客户端须重新「上线」后才能接收任务与上报画面。
    """
    mq_user = getattr(device, "runner_mq_username", None) or ""
    redis_user = getattr(device, "runner_redis_username", None) or ""

    await Device.filter(id=device.id).update(
        status=STOPPED_STATUS,
        runner_session_jti="",
        runner_bound_user_id=None,
        runner_mq_username="",
        runner_mq_password="",
        runner_redis_username="",
        runner_redis_password="",
    )

    try:
        await stop_executions_for_device(device.id)
    except Exception as exc:
        logger.warning("停止设备 %s 时联动停止 UI 执行失败: %s", device.id, exc)

    try:
        await stop_app_executions_for_device(device.id)
    except Exception as exc:
        logger.warning("停止设备 %s 时联动停止 App 执行失败: %s", device.id, exc)

    try:
        from app.modules.ui.ui_debug_session_lifecycle import close_debug_sessions_for_device
        from app.modules.ai.record_session_lifecycle import fail_active_recordings_for_device

        await close_debug_sessions_for_device(
            device.id,
            reason="admin_force_stop",
            notify_runner=False,
        )
        await fail_active_recordings_for_device(
            device.id,
            error="管理员已强制停止执行器，录制已自动结束",
        )
    except Exception as exc:
        logger.warning("停止设备 %s 时关闭调试/录制失败: %s", device.id, exc)

    try:
        await revoke_device_middleware(
            device.id,
            mq_username=mq_user,
            redis_username=redis_user,
        )
    except Exception as exc:
        logger.warning("停止设备 %s 时吊销中间件凭证失败: %s", device.id, exc)
