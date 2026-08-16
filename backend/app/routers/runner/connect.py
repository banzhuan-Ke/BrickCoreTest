"""Runner 客户端连接 API"""
from __future__ import annotations

import asyncio
import logging
import uuid
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from tortoise.exceptions import OperationalError

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
logger = logging.getLogger(__name__)


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

    mq_user = device.runner_mq_username
    redis_user = device.runner_redis_username
    udid = (device.app_udid or "").strip()
    persisted = await _update_device_with_retry(
        device_id,
        {
            "status": "离线",
            "runner_session_jti": "",
            "runner_bound_user_id": None,
            "runner_mq_username": "",
            "runner_mq_password": "",
            "runner_redis_username": "",
            "runner_redis_password": "",
        },
        purpose="设备下线写库",
    )

    try:
        await revoke_device_middleware(
            device_id,
            mq_username=mq_user,
            redis_username=redis_user,
        )
    except Exception:
        pass

    from app.modules.runner.runner_offline_cleanup import on_runner_device_offline

    cleanup = {}
    try:
        cleanup = await on_runner_device_offline(device_id, udid=udid)
    except Exception as exc:
        logger.warning("Runner 下线联动收尾失败 device=%s: %s", device_id, exc)

    return {
        "ok": True,
        "device_id": device_id,
        "disconnect_persisted": persisted,
        "cleanup": cleanup,
    }


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


def _heartbeat_update_fields(device: Device, item: RunnerHeartbeatRequest) -> dict:
    _merge_runner_capabilities(device, item)
    fields: dict = {
        "runner_last_heartbeat": datetime.now(),
        "status": "在线",
        "runner_client_version": device.runner_client_version,
        "runner_engine_types": device.runner_engine_types,
        "app_platform": device.app_platform,
        "app_udid": device.app_udid,
        "app_connection": device.app_connection,
        "toolchain_status": device.toolchain_status,
    }
    return fields


async def _update_device_with_retry(
    device_id: str,
    fields: dict,
    *,
    attempts: int = 4,
    purpose: str = "设备写库",
) -> bool:
    """设备行更新；遇 InnoDB 行锁超时则退避重试，最终仍失败则软降级，避免拖垮连接池。"""
    for attempt in range(attempts):
        try:
            await Device.filter(id=device_id, is_del=False).update(**fields)
            return True
        except OperationalError as ex:
            msg = str(ex)
            if "1205" not in msg and "Lock wait" not in msg.lower():
                raise
            if attempt >= attempts - 1:
                logger.warning(
                    "%s锁等待超时 device_id=%s attempts=%s: %s",
                    purpose,
                    device_id,
                    attempts,
                    ex,
                )
                return False
            await asyncio.sleep(0.25 * (2 ** attempt))
    return False


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

    if item.client_version:
        device.runner_client_version = item.client_version
    fields = _heartbeat_update_fields(device, item)
    persisted = await _update_device_with_retry(device_id, fields, purpose="设备心跳写库")
    return {"ok": True, "device_id": device_id, "heartbeat_persisted": persisted}


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


@router.get(
    "/active-recording",
    summary="查询本 Runner 设备进行中的 Web 录制",
    status_code=status.HTTP_200_OK,
)
async def runner_active_recording(runner_ctx: dict = Depends(verify_runner_token)):
    """Runner 桌面客户端轮询：返回当前设备 recording 会话快照，无则 data 为 null。"""
    from app.modules.ai.record_session_lifecycle import (
        get_active_recording_on_device,
        serialize_active_recording,
    )
    from app.routers.ai.recorder import get_record_runtime_state

    device_id = str(runner_ctx.get("device_id") or "")
    record = await get_active_recording_on_device(device_id)
    if not record:
        return {"data": None}
    runtime = get_record_runtime_state(record.id)
    return {"data": serialize_active_recording(record, runtime)}
