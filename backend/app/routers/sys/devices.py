import asyncio
import logging
from fastapi import APIRouter, HTTPException, status, Depends
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState
from app.core.auth import is_authenticated, require_permissions
from app.core.permissions import DEVICE_VIEW, DEVICE_EDIT
from app.schemas.sys import DeviceSchemas
from app.models.sys import Device
from app.core import config as settings
from redis.asyncio import Redis
import json
from app.core.mq_producer import MQProducer
from app.core.runner_device_control import STOPPED_STATUS, force_stop_runner_device
from app.core.runner_middleware import revoke_device_middleware

# 创建路由对象
router = APIRouter(prefix="/devices", tags=["设备管理"])


# 注册设备
@router.post("", summary="注册设备", status_code=status.HTTP_201_CREATED)
async def register_device(item: DeviceSchemas):
    # 检查设备是否存在且未被删除
    device = await Device.get_or_none(id=item.id, is_del=False)
    if device and device.status == STOPPED_STATUS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="设备已被管理员停止，请在 Runner 客户端重新上线",
        )
    if device:
        # 同步更新所有字段（name/ip/hostname/version 等可能已变更）
        update_data = item.model_dump(exclude_none=True, exclude={"id", "create_time"})
        update_data["status"] = "在线"
        await device.update_from_dict(update_data)
        await device.save()
        return device
    try:
        # 创建新设备（排除 None 值，避免 auto_now_add 字段被显式传入 null）
        device = await Device.create(**item.model_dump(exclude_none=True))
        return device
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


# 获取设备列表（只返回未删除的设备）
@router.get("", summary="设备列表", status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(DEVICE_VIEW))])
async def get_device_list(status: str = None, user_info: dict = Depends(is_authenticated)):
    # 过滤未删除的设备
    query = Device.filter(is_del=False)
    # 支持根据状态查询设备
    if status:
        query = query.filter(status=status)
    device = await query.order_by("-id")
    return device


# 获取设备详情（只返回未删除的设备）
@router.get("/{device_id}", summary="设备详情", response_model=DeviceSchemas, status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permissions(DEVICE_VIEW))])
async def get_device_detail(device_id: str, user_info: dict = Depends(is_authenticated)):
    # 只查询未删除的设备
    device = await Device.get_or_none(id=device_id, is_del=False)
    if not device:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="设备不存在或已被删除")
    return device


# 删除设备（逻辑删除）
@router.delete("/{device_id}", summary="删除设备", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permissions(DEVICE_EDIT))])
async def delete_device(device_id: str, user_info: dict = Depends(is_authenticated)):
    # 只删除未删除的设备
    device = await Device.get_or_none(id=device_id, is_del=False)
    if not device:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="设备不存在或已被删除")
    # 创建MQ生产者实例
    mq = MQProducer()
    try:
        # 删除消息队列device_id
        mq.channel.queue_delete(device_id)
        logging.info(f"成功删除消息队列: {device_id}")
    except Exception as e:
        logging.error(f"删除消息队列失败: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="设备队列清理失败！")
    finally:
        # 关闭MQ生产者实例
        mq.close()
    try:
        await revoke_device_middleware(
            device_id,
            mq_username=device.runner_mq_username,
            redis_username=device.runner_redis_username,
        )
    except Exception as e:
        logging.warning(f"吊销设备中间件凭证失败: {e}")
    # 逻辑删除：设置is_del=True
    device.is_del = True
    await device.save()


@router.post(
    "/{device_id}/stop",
    summary="停止 Runner 设备",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permissions(DEVICE_EDIT))],
)
async def stop_runner_device(device_id: str, user_info: dict = Depends(is_authenticated)):
    """
    强制停止在线 Runner：吊销会话与 MQ/Redis 凭证，停止画面/日志上报。
    执行器端须重新「上线」后才能继续使用。
    """
    device = await Device.get_or_none(id=device_id, is_del=False)
    if not device:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="设备不存在或已被删除")
    if device.status == STOPPED_STATUS:
        return {"ok": True, "device_id": device_id, "status": STOPPED_STATUS, "message": "设备已处于停止状态"}
    if device.status not in ("在线", "执行中"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="仅可停止在线或执行中的设备")

    await force_stop_runner_device(device)
    logging.info("管理员 %s 已停止 Runner 设备 %s", user_info.get("username"), device_id)
    return {
        "ok": True,
        "device_id": device_id,
        "status": STOPPED_STATUS,
        "message": "设备已停止，Runner 需重新上线后方可使用",
    }


# websocket接口（只允许未删除的设备连接）
@router.websocket("/ws/{device_id}")
async def websocket_subscribe(websocket: WebSocket, device_id: str):
    # 校验设备是否存在且未被删除
    device = await Device.get_or_none(id=device_id, is_del=False)
    if not device:
        try:
            await websocket.close(code=1008, reason="设备不存在或已被删除")
        except Exception:
            pass
        return

    await websocket.accept()
    logging.info(f"WebSocket连接已接受: {device_id}")
    redis_cli = Redis(host=settings.REDIS_CONFIG['host'],
                      port=settings.REDIS_CONFIG['port'],
                      db=settings.REDIS_CONFIG['db'],
                      password=settings.REDIS_CONFIG['password'],
                      decode_responses=True
                      )
    # 初始化一个订阅器
    pubsub = redis_cli.pubsub()
    try:
        # 订阅事件频道
        await pubsub.subscribe(f"{device_id}:log", f"{device_id}:screen")
        logging.info(f"已订阅频道：{device_id}:log 和 {device_id}:screen")
        # 发送历史日志
        history_logs = await redis_cli.lrange(f"{device_id}:history_logs", 0, -1)
        for log in history_logs:
            if websocket.client_state != WebSocketState.CONNECTED:
                break
            message = {
                "type": "log",
                "data": log
            }
            await websocket.send_text(json.dumps(message))
            logging.info(f"发送历史日志到客户端：{log}")
        # 发送缓存画面（勿用 type=log，否则前端无法渲染截图）
        cached_screen = await redis_cli.get(f"{device_id}:cached_image")
        if cached_screen:
            await websocket.send_text(json.dumps({
                "type": "screen",
                "format": "jpeg",
                "data": cached_screen,
            }))
        # 循环接收订阅的消息
        async for message in pubsub.listen():
            # 连接断开时立即退出循环
            if websocket.client_state != WebSocketState.CONNECTED:
                break
            if message['type'] == 'message':
                try:
                    if message['channel'] == f"{device_id}:log":
                        msg_data = {
                            "type": "log",
                            "data": message['data']
                        }
                    elif message['channel'] == f"{device_id}:screen":
                        msg_data = {
                            "type": "screen",
                            "format": "jpeg",
                            "data": message['data'],
                        }
                    # 发送前最终状态确认
                    if websocket.client_state == WebSocketState.CONNECTED:
                        await websocket.send_text(json.dumps(msg_data))
                        logging.info(f"发送数据到客户端: {msg_data['type']} ({len(message['data'])} 字节)")
                except RuntimeError as e:
                    if "WebSocket is not connected" in str(e):
                        break
                    logging.error(f"发送失败: {str(e)}")
                except Exception as e:
                    logging.error(f"处理消息时出错: {str(e)}")
                    break
            await asyncio.sleep(0.01)
    except WebSocketDisconnect:
        logging.info(f"客户端正常断开: {device_id}")
    except Exception as e:
        logging.error(f"WebSocket处理过程中出错: {str(e)}")
    finally:
        try:
            # 连接关闭检查
            if pubsub and pubsub.subscribed:
                # 取消订阅
                await pubsub.unsubscribe()
                # 等待取消订阅完成
                await asyncio.sleep(0.1)
                logging.info(f"已取消订阅频道: {device_id}:log 和 {device_id}:screen")
        except Exception as e:
            logging.error(f"取消订阅时出错: {e}")
        if redis_cli:
            await redis_cli.close()
        if not websocket.client_state == WebSocketState.DISCONNECTED:
            try:
                await websocket.close()
            except RuntimeError:
                pass
        logging.info(f"---------WebSocket连接已关闭------")