"""Runner 客户端连接 API"""
from __future__ import annotations

import uuid
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.platform import config as app_config
from app.core.platform.auth import (
    create_runner_token,
    require_permissions,
    verify_runner_token,
)
from app.core.platform.permissions import DEVICE_EDIT
from app.core.runner.runner_connect import build_runner_connect_bundle, resolve_public_base_url
from app.core.runner.runner_middleware import provision_device_middleware, revoke_device_middleware
from app.core.runner.runner_version import ensure_client_version, get_version_info
from app.models.sys import Device
from app.schemas.runner import (
    RunnerConnectRequest,
    RunnerConnectResponse,
    RunnerDisconnectRequest,
    RunnerHeartbeatRequest,
    RunnerMqConfig,
    RunnerRedisConfig,
    RunnerVersionResponse,
)

router = APIRouter(prefix="/runner", tags=["Runner 客户端"])


def _request_base_url(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-proto")
    host = request.headers.get("host") or request.url.netloc
    scheme = forwarded or request.url.scheme
    return f"{scheme}://{host}"


@router.post(
    "/connect",
    summary="Runner 客户端上线",
    response_model=RunnerConnectResponse,
    status_code=status.HTTP_200_OK,
)
async def runner_connect(
    item: RunnerConnectRequest,
    request: Request,
    user_info: dict = Depends(require_permissions(DEVICE_EDIT)),
):
    username = user_info.get("username") or ""
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="无法识别登录用户")

    ensure_client_version(item.client_version)

    jti = uuid.uuid4().hex
    device = await Device.get_or_none(id=item.id)
    if device and device.is_del:
        device.is_del = False

    payload = item.model_dump(exclude={"client_version"})
    payload["status"] = "在线"
    payload["username"] = username
    payload["runner_session_jti"] = jti
    payload["runner_bound_user_id"] = user_id
    payload["runner_client_version"] = item.client_version
    payload["runner_last_heartbeat"] = datetime.now()
    if not item.runner_engine_types:
        payload["runner_engine_types"] = ["web"]
    if item.toolchain_status:
        payload["toolchain_status"] = item.toolchain_status

    if device:
        await device.update_from_dict(payload)
        await device.save()
    else:
        device = await Device.create(**payload)

    runner_token = create_runner_token(device_id=item.id, user_id=user_id, jti=jti)
    expires_at = datetime.fromtimestamp(time.time() + app_config.RUNNER_TOKEN_TIMEOUT)

    base_url = resolve_public_base_url(_request_base_url(request))
    try:
        creds = await provision_device_middleware(item.id)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"中间件凭证初始化失败，请确认 RabbitMQ Management 与 Redis ACL 可用: {exc}",
        ) from exc

    device.runner_mq_username = creds["mq_username"]
    device.runner_mq_password = creds["mq_password"]
    device.runner_redis_username = creds["redis_username"]
    device.runner_redis_password = creds["redis_password"]
    await device.save()

    bundle = build_runner_connect_bundle(
        device_id=item.id,
        base_url=base_url,
        mq_username=creds["mq_username"],
        mq_password=creds["mq_password"],
        redis_username=creds["redis_username"],
        redis_password=creds["redis_password"],
    )

    return RunnerConnectResponse(
        device_id=item.id,
        runner_token=runner_token,
        runner_token_expires_at=expires_at,
        base_url=bundle["base_url"],
        engine_version=bundle["engine_version"],
        client_version_min=bundle["client_version_min"],
        client_version_latest=bundle["client_version_latest"],
        storage_type=bundle["storage_type"],
        upload_mode=bundle["upload_mode"],
        internal_api_key=app_config.INTERNAL_API_KEY,
        mq=RunnerMqConfig(**bundle["mq"]),
        redis=RunnerRedisConfig(**bundle["redis"]),
        database=None,
    )


@router.post(
    "/disconnect",
    summary="Runner 客户端下线",
    status_code=status.HTTP_200_OK,
)
async def runner_disconnect(
    item: RunnerDisconnectRequest,
    runner_ctx: dict = Depends(verify_runner_token),
):
    device_id = item.device_id or runner_ctx.get("device_id")
    device = await Device.get_or_none(id=device_id, is_del=False)
    if not device:
        return {"ok": True, "message": "设备不存在或已删除"}

    device.status = "离线"
    device.runner_session_jti = ""
    device.runner_bound_user_id = None
    mq_user = device.runner_mq_username
    redis_user = device.runner_redis_username
    device.runner_mq_username = ""
    device.runner_mq_password = ""
    device.runner_redis_username = ""
    device.runner_redis_password = ""
    await device.save()

    try:
        await revoke_device_middleware(
            device_id,
            mq_username=mq_user,
            redis_username=redis_user,
        )
    except Exception:
        pass

    from app.modules.app.app_execution_stale import close_inflight_executions_for_udid

    udid = (device.app_udid or "").strip()
    if udid:
        try:
            await close_inflight_executions_for_udid(udid)
        except Exception:
            pass

    return {"ok": True, "device_id": device_id}


def _merge_runner_capabilities(device: Device, item: RunnerHeartbeatRequest) -> None:
    if item.runner_engine_types is not None:
        device.runner_engine_types = item.runner_engine_types
        device.app_udid = item.app_udid or ""
        device.app_connection = item.app_connection or ""
        if item.app_platform is not None:
            device.app_platform = item.app_platform or ""
    elif item.app_udid is not None or item.app_connection is not None:
        device.app_udid = item.app_udid or ""
        device.app_connection = item.app_connection or ""
    if item.app_platform and item.runner_engine_types is None:
        device.app_platform = item.app_platform
    if item.toolchain_status is not None:
        device.toolchain_status = item.toolchain_status
    if isinstance(item.app_capabilities, dict) and item.app_capabilities:
        status = dict(device.toolchain_status or {})
        status["app_capabilities"] = item.app_capabilities
        device.toolchain_status = status


@router.post(
    "/heartbeat",
    summary="Runner 客户端心跳",
    status_code=status.HTTP_200_OK,
)
async def runner_heartbeat(
    item: RunnerHeartbeatRequest,
    runner_ctx: dict = Depends(verify_runner_token),
):
    device_id = item.device_id or runner_ctx.get("device_id")
    device = await Device.get_or_none(id=device_id, is_del=False)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    device.runner_last_heartbeat = datetime.now()
    device.status = "在线"
    if item.client_version:
        device.runner_client_version = item.client_version
    _merge_runner_capabilities(device, item)
    await device.save()
    return {"ok": True, "device_id": device_id}


@router.get(
    "/version",
    summary="Runner 版本信息",
    response_model=RunnerVersionResponse,
    status_code=status.HTTP_200_OK,
)
async def runner_version(request: Request):
    base = _request_base_url(request)
    return RunnerVersionResponse(**await get_version_info(base))


@router.get("/health", summary="Runner 服务健康检查", status_code=status.HTTP_200_OK)
async def runner_health():
    return {"ok": True, "service": "runner-api"}
