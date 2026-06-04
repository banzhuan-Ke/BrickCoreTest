"""Runner 设备日志上报（经 Backend 转发到 Redis，供 WebSocket 实时展示）"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.core.auth import verify_runner_token
from app.core.device_log_publisher import publish_device_log_line, publish_device_screen
from app.schemas.runner import (
    RunnerDeviceLogBatchRequest,
    RunnerDeviceLogRequest,
    RunnerDeviceScreenRequest,
)

router = APIRouter(prefix="/runner", tags=["Runner 客户端"])


@router.post(
    "/device-log",
    summary="上报单条设备执行日志",
    status_code=status.HTTP_200_OK,
)
async def runner_device_log(
    item: RunnerDeviceLogRequest,
    ctx: dict = Depends(verify_runner_token),
):
    device_id = item.device_id or ctx.get("device_id") or ""
    await publish_device_log_line(device_id, item.message)
    return {"ok": True}


@router.post(
    "/device-log/batch",
    summary="批量上报设备执行日志",
    status_code=status.HTTP_200_OK,
)
async def runner_device_log_batch(
    item: RunnerDeviceLogBatchRequest,
    ctx: dict = Depends(verify_runner_token),
):
    device_id = item.device_id or ctx.get("device_id") or ""
    for msg in item.messages:
        if msg:
            await publish_device_log_line(device_id, msg)
    return {"ok": True, "count": len(item.messages)}


@router.post(
    "/device-screen",
    summary="上报设备屏幕截图",
    status_code=status.HTTP_200_OK,
)
async def runner_device_screen(
    item: RunnerDeviceScreenRequest,
    ctx: dict = Depends(verify_runner_token),
):
    device_id = item.device_id or ctx.get("device_id") or ""
    fmt = (item.format or "jpeg").lower().strip()
    if fmt not in ("jpeg", "jpg", "webp", "png"):
        fmt = "jpeg"
    await publish_device_screen(device_id, item.image_base64, cache=item.cache)
    return {"ok": True, "format": fmt}
