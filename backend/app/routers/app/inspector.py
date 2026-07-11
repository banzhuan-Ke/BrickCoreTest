"""App Inspector：控件树探测（MQ → Runner → 回调）"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.modules.app.app_device_lock import (
    acquire_device_lock,
    refresh_device_lock,
    release_device_lock,
    release_device_lock_by_holder,
)
from app.modules.app.app_inspector_service import (
    apply_dump_result,
    apply_explore_result,
    apply_screenshot_result,
    apply_webview_probe_result,
    close_session,
    create_session,
    get_session,
    load_session_screenshot_bytes,
    mark_dumping,
    mark_exploring,
    mark_screenshot_refreshing,
    mark_webview_probing,
    prepare_session_for_client,
)
from app.core.platform.auth import get_current_username, is_authenticated, require_any_permissions, require_permissions, verify_runner_or_internal
from app.core.infra.mq_producer import MQProducer
from app.core.platform.permissions import APP_CASE_EDIT, APP_ELEMENT_EDIT, APP_ELEMENT_VIEW
from app.modules.ui.ui_project_guard import assert_user_project_member, assert_user_project_viewer
from app.models.sys import Device
from app.schemas.app import (
    AppInspectorCallbackForm,
    AppInspectorExploreForm,
    AppInspectorSessionForm,
    AppInspectorWebviewProbeForm,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inspector", tags=["元素探查"])

INSPECTOR_WRITE_PERMS = (APP_ELEMENT_EDIT, APP_CASE_EDIT)

_mq_producer: MQProducer | None = None


def _get_mq() -> MQProducer:
    global _mq_producer
    if _mq_producer is None:
        _mq_producer = MQProducer()
    return _mq_producer


def _request_base_url(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-proto")
    host = request.headers.get("host") or request.url.netloc
    scheme = forwarded or request.url.scheme
    return f"{scheme}://{host}".rstrip("/")


async def _resolve_app_device(device_id: str, app_udid: str | None) -> tuple[Device, str]:
    device = await Device.get_or_none(id=device_id, status="在线", is_del=False)
    if not device:
        raise HTTPException(status_code=503, detail="执行设备不在线或不存在")
    types = device.runner_engine_types or ["web"]
    if "app" not in types:
        raise HTTPException(status_code=422, detail="所选设备不支持 App 自动化")
    udid = (app_udid or device.app_udid or "").strip()
    if not udid:
        raise HTTPException(status_code=422, detail="设备未登记 app_udid，请连接手机后重新上线 Runner")
    return device, udid


def _validate_explore_form(body: AppInspectorExploreForm) -> None:
    action = (body.action or "").strip().lower()
    if action not in ("tap", "input", "swipe", "back", "home", "press"):
        raise HTTPException(status_code=422, detail=f"不支持的探索操作: {body.action}")
    if action == "tap" and (body.x is None or body.y is None):
        raise HTTPException(status_code=422, detail="tap 需要 x、y 坐标")
    if action == "swipe" and None in (body.x, body.y, body.x2, body.y2):
        raise HTTPException(status_code=422, detail="swipe 需要 x、y、x2、y2 坐标")
    if action == "input" and not (body.text or "").strip():
        raise HTTPException(status_code=422, detail="input 需要 text 文本")
    if action == "press" and not (body.key or "").strip():
        raise HTTPException(status_code=422, detail="press 需要 key 按键名")


async def _dispatch_inspector_task(
    *,
    request: Request,
    session: dict,
    device: Device,
    run_case: dict,
) -> None:
    base_url = _request_base_url(request)
    callback_path = run_case.pop("callback_path")
    session_id = session["session_id"]
    callback_url = f"{base_url}/app-module/inspector/sessions/{session_id}/{callback_path}"
    run_case["callback_url"] = callback_url
    run_case.setdefault("device_udid", session["app_udid"])
    run_case.setdefault("inspector_session_id", session_id)
    mq = _get_mq()
    mq.send_test_task(
        env_config={
            "engine_type": "app",
            "platform": device.app_platform or "android",
            "device_udid": session["app_udid"],
            "project_id": session["project_id"],
        },
        run_case=run_case,
        device_id=device.id,
    )


@router.post("/sessions", summary="创建 Inspector 会话", dependencies=[Depends(is_authenticated)])
async def create_inspector_session(
    body: AppInspectorSessionForm,
    user_info: dict = Depends(require_permissions(APP_ELEMENT_VIEW)),
    username: str = Depends(get_current_username),
):
    await assert_user_project_member(user_info, body.project_id)
    device, udid = await _resolve_app_device(body.device_id, body.app_udid)
    session = await create_session(
        project_id=body.project_id,
        device_id=device.id,
        app_udid=udid,
        username=username,
    )
    try:
        await acquire_device_lock(
            udid,
            holder_type="inspector",
            holder_id=session["session_id"],
            username=username,
        )
    except HTTPException:
        await close_session(session["session_id"])
        raise
    return {"data": session}


@router.get("/sessions/{session_id}", summary="查询 Inspector 会话", dependencies=[Depends(is_authenticated)])
async def get_inspector_session(
    session_id: str,
    user_info: dict = Depends(require_permissions(APP_ELEMENT_VIEW)),
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    await assert_user_project_viewer(user_info, session["project_id"])
    return {"data": prepare_session_for_client(session)}


@router.get(
    "/sessions/{session_id}/screenshot",
    summary="获取 Inspector 截图（同源代理，供前端裁剪图像模板）",
    dependencies=[Depends(is_authenticated)],
)
async def get_inspector_screenshot(
    session_id: str,
    user_info: dict = Depends(require_permissions(APP_ELEMENT_VIEW)),
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    await assert_user_project_viewer(user_info, session["project_id"])
    try:
        data, media_type = await load_session_screenshot_bytes(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("读取 Inspector 截图失败 session=%s", session_id)
        raise HTTPException(status_code=500, detail=f"读取截图失败: {exc}") from exc
    return Response(content=data, media_type=media_type)


@router.post("/sessions/{session_id}/dump", summary="请求刷新控件树", dependencies=[Depends(is_authenticated)])
async def request_dump(
    session_id: str,
    request: Request,
    user_info: dict = Depends(require_any_permissions(*INSPECTOR_WRITE_PERMS)),
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    await assert_user_project_member(user_info, session["project_id"])
    if session.get("status") == "dumping":
        return {"data": prepare_session_for_client(session), "msg": "正在探测中"}

    device = await Device.get_or_none(id=session["device_id"], is_del=False)
    if not device or device.status != "在线":
        raise HTTPException(status_code=503, detail="Runner 设备已离线")

    await mark_dumping(session_id)
    await refresh_device_lock(
        session["app_udid"],
        holder_type="inspector",
        holder_id=session_id,
    )
    base_url = _request_base_url(request)
    callback_url = f"{base_url}/app-module/inspector/sessions/{session_id}/callback"

    try:
        mq = _get_mq()
        mq.send_test_task(
            env_config={
                "engine_type": "app",
                "platform": device.app_platform or "android",
                "device_udid": session["app_udid"],
                "project_id": session["project_id"],
            },
            run_case={
                "task_type": "app_inspector",
                "inspector_session_id": session_id,
                "callback_url": callback_url,
                "device_udid": session["app_udid"],
            },
            device_id=device.id,
        )
    except Exception as exc:
        logger.exception("下发 Inspector 任务失败")
        await apply_dump_result(session_id, {"success": False, "error": str(exc)})
        raise HTTPException(status_code=500, detail=f"下发探测任务失败: {exc}") from exc

    session = await get_session(session_id)
    return {"data": prepare_session_for_client(session), "msg": "已下发探测任务"}


@router.post("/sessions/{session_id}/callback", summary="Runner 回调（内部）")
async def inspector_callback(
    session_id: str,
    body: AppInspectorCallbackForm,
    _ctx: dict = Depends(verify_runner_or_internal),
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    updated = await apply_dump_result(session_id, body.model_dump())
    return {"data": updated}


@router.post(
    "/sessions/{session_id}/webview-probe",
    summary="探测 WebView 内 H5 DOM",
    dependencies=[Depends(is_authenticated)],
)
async def request_webview_probe(
    session_id: str,
    body: AppInspectorWebviewProbeForm,
    request: Request,
    user_info: dict = Depends(require_any_permissions(*INSPECTOR_WRITE_PERMS)),
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    await assert_user_project_member(user_info, session["project_id"])
    if session.get("webview_status") == "probing":
        return {"data": prepare_session_for_client(session), "msg": "H5 探测进行中"}

    device = await Device.get_or_none(id=session["device_id"], is_del=False)
    if not device or device.status != "在线":
        raise HTTPException(status_code=503, detail="Runner 设备已离线")

    devtools_source = (body.devtools_source or "webview").strip().lower()
    if devtools_source not in ("webview", "chrome"):
        devtools_source = "webview"
    package = (body.package or session.get("package") or "").strip()
    await mark_webview_probing(session_id, body.page_index, devtools_source=devtools_source)
    await refresh_device_lock(
        session["app_udid"],
        holder_type="inspector",
        holder_id=session_id,
    )
    base_url = _request_base_url(request)
    callback_url = f"{base_url}/app-module/inspector/sessions/{session_id}/webview-callback"

    try:
        mq = _get_mq()
        mq.send_test_task(
            env_config={
                "engine_type": "app",
                "platform": device.app_platform or "android",
                "device_udid": session["app_udid"],
                "project_id": session["project_id"],
            },
            run_case={
                "task_type": "app_inspector_webview",
                "inspector_session_id": session_id,
                "callback_url": callback_url,
                "device_udid": session["app_udid"],
                "page_index": body.page_index,
                "package": package,
                "devtools_source": devtools_source,
            },
            device_id=device.id,
        )
    except Exception as exc:
        logger.exception("下发 WebView 探测任务失败")
        await apply_webview_probe_result(session_id, {"success": False, "error": str(exc)})
        raise HTTPException(status_code=500, detail=f"下发 H5 探测任务失败: {exc}") from exc

    session = await get_session(session_id)
    return {"data": prepare_session_for_client(session), "msg": "已下发 H5 DOM 探测任务"}


@router.post(
    "/sessions/{session_id}/explore",
    summary="探索模式：试点击/输入/滑动等",
    dependencies=[Depends(is_authenticated)],
)
async def request_explore(
    session_id: str,
    body: AppInspectorExploreForm,
    request: Request,
    user_info: dict = Depends(require_any_permissions(*INSPECTOR_WRITE_PERMS)),
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    await assert_user_project_member(user_info, session["project_id"])
    _validate_explore_form(body)
    if session.get("explore_status") == "exploring":
        return {"data": prepare_session_for_client(session), "msg": "探索操作进行中"}
    if session.get("status") == "dumping":
        raise HTTPException(status_code=409, detail="控件树刷新中，请稍后再试")

    device = await Device.get_or_none(id=session["device_id"], is_del=False)
    if not device or device.status != "在线":
        raise HTTPException(status_code=503, detail="Runner 设备已离线")

    await mark_exploring(session_id)
    await refresh_device_lock(session["app_udid"], holder_type="inspector", holder_id=session_id)

    action = (body.action or "").strip().lower()
    try:
        await _dispatch_inspector_task(
            request=request,
            session=session,
            device=device,
            run_case={
                "task_type": "app_inspector_explore",
                "callback_path": "explore-callback",
                "action": action,
                "x": body.x,
                "y": body.y,
                "x2": body.x2,
                "y2": body.y2,
                "text": body.text,
                "key": body.key,
                "duration": body.duration,
                "refresh_tree": body.refresh_tree,
            },
        )
    except Exception as exc:
        logger.exception("下发探索任务失败")
        await apply_explore_result(session_id, {"success": False, "error": str(exc)})
        raise HTTPException(status_code=500, detail=f"下发探索任务失败: {exc}") from exc

    session = await get_session(session_id)
    return {"data": prepare_session_for_client(session), "msg": "已下发探索操作"}


@router.post("/sessions/{session_id}/explore-callback", summary="探索操作回调（内部）")
async def inspector_explore_callback(
    session_id: str,
    body: AppInspectorCallbackForm,
    _ctx: dict = Depends(verify_runner_or_internal),
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    updated = await apply_explore_result(session_id, body.model_dump())
    return {"data": updated}


@router.post(
    "/sessions/{session_id}/screenshot-refresh",
    summary="刷新投屏截图（轻量，不刷新控件树）",
    dependencies=[Depends(is_authenticated)],
)
async def request_screenshot_refresh(
    session_id: str,
    request: Request,
    user_info: dict = Depends(require_permissions(APP_ELEMENT_VIEW)),
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    await assert_user_project_viewer(user_info, session["project_id"])
    if session.get("screenshot_status") == "refreshing":
        return {"data": prepare_session_for_client(session), "msg": "截图刷新中"}

    device = await Device.get_or_none(id=session["device_id"], is_del=False)
    if not device or device.status != "在线":
        raise HTTPException(status_code=503, detail="Runner 设备已离线")

    await mark_screenshot_refreshing(session_id)
    await refresh_device_lock(session["app_udid"], holder_type="inspector", holder_id=session_id)

    try:
        await _dispatch_inspector_task(
            request=request,
            session=session,
            device=device,
            run_case={
                "task_type": "app_inspector_screenshot",
                "callback_path": "screenshot-callback",
            },
        )
    except Exception as exc:
        logger.exception("下发截图刷新任务失败")
        await apply_screenshot_result(session_id, {"success": False, "error": str(exc)})
        raise HTTPException(status_code=500, detail=f"下发截图刷新失败: {exc}") from exc

    session = await get_session(session_id)
    return {"data": prepare_session_for_client(session), "msg": "已下发截图刷新"}


@router.post("/sessions/{session_id}/screenshot-callback", summary="截图刷新回调（内部）")
async def inspector_screenshot_callback(
    session_id: str,
    body: AppInspectorCallbackForm,
    _ctx: dict = Depends(verify_runner_or_internal),
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    updated = await apply_screenshot_result(session_id, body.model_dump())
    return {"data": updated}


@router.post("/sessions/{session_id}/webview-callback", summary="WebView 探测回调（内部）")
async def inspector_webview_callback(
    session_id: str,
    body: AppInspectorCallbackForm,
    _ctx: dict = Depends(verify_runner_or_internal),
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    updated = await apply_webview_probe_result(session_id, body.model_dump())
    return {"data": updated}


@router.get("/sessions/{session_id}/runner-status", summary="Runner 校验会话（内部）")
async def inspector_runner_status(
    session_id: str,
    _ctx: dict = Depends(verify_runner_or_internal),
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "data": {
            "session_id": session_id,
            "status": session.get("status"),
            "webview_status": session.get("webview_status"),
            "explore_status": session.get("explore_status"),
            "screenshot_status": session.get("screenshot_status"),
        }
    }


@router.delete("/sessions/{session_id}", summary="关闭 Inspector 会话", dependencies=[Depends(is_authenticated)])
async def delete_inspector_session(
    session_id: str,
    user_info: dict = Depends(require_permissions(APP_ELEMENT_VIEW)),
):
    session = await get_session(session_id)
    if session:
        await assert_user_project_viewer(user_info, session["project_id"])
    await release_device_lock_by_holder("inspector", session_id)
    await close_session(session_id)
    return {"msg": "已关闭"}
