"""Runner 设备管控（强制停止等）"""
from __future__ import annotations

import logging

from app.core.runner_middleware import revoke_device_middleware
from app.core.ui_execution_stop import stop_executions_for_device
from app.models.sys import Device

logger = logging.getLogger(__name__)

STOPPED_STATUS = "已停止"


async def force_stop_runner_device(device: Device) -> None:
    """
    管理员强制停止 Runner：标记已停止、吊销会话与中间件凭证。
    客户端须重新「上线」后才能接收任务与上报画面。
    """
    mq_user = device.runner_mq_username
    redis_user = device.runner_redis_username

    device.status = STOPPED_STATUS
    device.runner_session_jti = ""
    device.runner_bound_user_id = None
    device.runner_mq_username = ""
    device.runner_mq_password = ""
    device.runner_redis_username = ""
    device.runner_redis_password = ""
    await device.save()

    try:
        await stop_executions_for_device(device.id)
    except Exception as exc:
        logger.warning("停止设备 %s 时联动停止 UI 执行失败: %s", device.id, exc)

    try:
        await revoke_device_middleware(
            device.id,
            mq_username=mq_user,
            redis_username=redis_user,
        )
    except Exception as exc:
        logger.warning("停止设备 %s 时吊销中间件凭证失败: %s", device.id, exc)
