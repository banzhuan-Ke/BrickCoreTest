"""用户站内信 API"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.platform.auth import (
    create_inbox_stream_token,
    is_authenticated,
    is_authenticated_inbox_stream,
)
from app.modules.test_management import assignment_notify_service as svc
from app.modules.test_management.premium_gateway import (
    raise_tm_premium_required,
    tm_premium_ready,
)
from app.modules.test_management.tm_premium_defaults import DEFAULT_USER_NOTIFY_PREFS
from app.schemas.test_management import StandardResponse

router = APIRouter(prefix="/inbox", tags=["站内信"])


class NotifyPreferencesBody(BaseModel):
    inbox_enabled: Optional[bool] = None
    external_enabled: Optional[bool] = None
    im_at_enabled: Optional[bool] = None
    muted_events: Optional[List[str]] = None
    dnd_enabled: Optional[bool] = None
    dnd_start: Optional[str] = Field(None, description="HH:MM")
    dnd_end: Optional[str] = Field(None, description="HH:MM")
    dnd_mute_inbox: Optional[bool] = None
    dnd_timezone: Optional[str] = Field(None, description="IANA 时区，如 Asia/Shanghai、UTC")


def _user_id(user_info: dict) -> int:
    uid = user_info.get("id")
    if uid is None:
        raise HTTPException(status_code=401, detail="无法识别当前用户")
    return int(uid)


@router.get("", response_model=StandardResponse, status_code=status.HTTP_200_OK)
async def list_inbox(
    project_id: Optional[int] = Query(None),
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user_info: dict = Depends(is_authenticated),
):
    if not tm_premium_ready():
        return StandardResponse(
            data={
                "total": 0,
                "page": page,
                "size": size,
                "data": [],
                "premium_required": True,
            }
        )
    data = await svc.list_inbox(
        user_id=_user_id(user_info),
        project_id=project_id,
        unread_only=unread_only,
        page=page,
        size=size,
    )
    return StandardResponse(data=data)


@router.get("/preferences", response_model=StandardResponse, status_code=status.HTTP_200_OK)
async def get_notify_preferences(
    user_info: dict = Depends(is_authenticated),
):
    if not tm_premium_ready():
        return StandardResponse(data={**DEFAULT_USER_NOTIFY_PREFS, "premium_required": True})
    from app.modules.test_management.user_notify_prefs import load_user_notify_prefs

    data = await load_user_notify_prefs(_user_id(user_info))
    return StandardResponse(data=data)


@router.put("/preferences", response_model=StandardResponse, status_code=status.HTTP_200_OK)
async def update_notify_preferences(
    body: NotifyPreferencesBody,
    user_info: dict = Depends(is_authenticated),
):
    if not tm_premium_ready():
        raise_tm_premium_required()
    from app.modules.test_management.user_notify_prefs import save_user_notify_prefs

    data = await save_user_notify_prefs(
        _user_id(user_info),
        body.model_dump(exclude_unset=True),
    )
    return StandardResponse(data=data, message="通知偏好已保存")


@router.get("/unread-count", response_model=StandardResponse, status_code=status.HTTP_200_OK)
async def get_unread_count(
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    if not tm_premium_ready():
        return StandardResponse(data={"count": 0, "premium_required": True})
    count = await svc.unread_count(user_id=_user_id(user_info), project_id=project_id)
    return StandardResponse(data={"count": count})


@router.get("/stream-token", response_model=StandardResponse, status_code=status.HTTP_200_OK)
async def inbox_stream_token(
    user_info: dict = Depends(is_authenticated),
):
    """签发 SSE 专用短效 token（勿用主会话 JWT 连接 /stream）。"""
    if not tm_premium_ready():
        raise_tm_premium_required()
    uid = _user_id(user_info)
    token = create_inbox_stream_token(uid)
    return StandardResponse(data={"token": token, "expires_in": 900})


@router.get("/stream")
async def inbox_stream(
    request: Request,
    user_info: dict = Depends(is_authenticated_inbox_stream),
):
    """SSE：新站内信实时推送（query 仅接受 /stream-token 签发的短效 token）。"""
    if not tm_premium_ready():
        raise_tm_premium_required()
    from app.modules.test_management.inbox_sse import (
        acquire_inbox_stream_slot,
        iter_inbox_sse,
        release_inbox_stream_slot,
    )

    uid = _user_id(user_info)
    initial_unread = await svc.unread_count(user_id=uid)

    async def event_gen():
        svc.schedule_flush_pending_for_user(uid)
        acquired = await acquire_inbox_stream_slot(uid)
        if not acquired:
            yield 'event: error\ndata: {"detail":"站内信实时连接数已达上限"}\n\n'
            return
        try:
            async for chunk in iter_inbox_sse(uid, initial_unread_count=initial_unread):
                if await request.is_disconnected():
                    break
                yield chunk
        finally:
            await release_inbox_stream_slot(uid)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{notification_id}/read", response_model=StandardResponse, status_code=status.HTTP_200_OK)
async def mark_notification_read(
    notification_id: int,
    user_info: dict = Depends(is_authenticated),
):
    if not tm_premium_ready():
        raise_tm_premium_required()
    ok = await svc.mark_read(notification_id=notification_id, user_id=_user_id(user_info))
    if not ok:
        raise HTTPException(status_code=404, detail="通知不存在")
    return StandardResponse(data={"ok": True})


@router.post("/read-all", response_model=StandardResponse, status_code=status.HTTP_200_OK)
async def mark_all_read(
    project_id: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    if not tm_premium_ready():
        raise_tm_premium_required()
    updated = await svc.mark_all_read(user_id=_user_id(user_info), project_id=project_id)
    return StandardResponse(data={"updated": updated})
