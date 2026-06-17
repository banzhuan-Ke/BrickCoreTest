"""Runner 结果回传 API"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import verify_internal_token, verify_runner_token
from app.core.runner_results import save_runner_results
from app.models.sys import Device
from app.schemas.runner import RunnerEngineReadyRequest, RunnerResultsPayload

router = APIRouter(prefix="/runner", tags=["Runner 客户端"])


@router.post(
    "/results",
    summary="Runner 回传 UI 执行结果",
    status_code=status.HTTP_200_OK,
)
async def runner_save_results(
    item: RunnerResultsPayload,
    _ctx: dict = Depends(verify_runner_token),
):
    await save_runner_results(item.run_suite, item.result)
    return {"ok": True}


@router.post(
    "/results/internal",
    summary="Runner 回传结果（内部密钥，过渡期）",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def runner_save_results_internal(
    item: RunnerResultsPayload,
    _ctx: dict = Depends(verify_internal_token),
):
    await save_runner_results(item.run_suite, item.result)
    return {"ok": True}


@router.post(
    "/engine-ready",
    summary="Runner 引擎就绪（子进程启动确认）",
    status_code=status.HTTP_200_OK,
)
async def runner_engine_ready(
    item: RunnerEngineReadyRequest,
    runner_ctx: dict = Depends(verify_runner_token),
):
    device_id = item.id or runner_ctx.get("device_id")
    device = await Device.get_or_none(id=device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在，请先通过客户端 connect")

    update = item.model_dump(exclude_none=True, exclude={"client_version"})
    update["status"] = "在线"
    update["is_del"] = False
    update["runner_last_heartbeat"] = datetime.now()
    # engine-ready 上报的是 RUNNER_ENGINE_VERSION，勿覆盖桌面客户端 runner_client_version
    await device.update_from_dict(update)
    await device.save()
    return {"ok": True, "device_id": device_id}
