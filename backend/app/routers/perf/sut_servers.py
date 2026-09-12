"""被测服务器控制台 API（JWT + 项目权限）。"""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.core.platform.auth import get_current_username, is_authenticated, require_permissions
from app.core.platform.datetime_utils import now_app, now_epoch_ms
from app.core.platform.permissions import PERF_SCENE_EDIT, PERF_SCENE_VIEW
from app.core.platform.project_access import PROJECT_ROLE_MEMBER, PROJECT_ROLE_VIEWER, assert_project_access
from app.models.perf import SutMetricChunk, SutServer
from app.models.sys import Project
from app.modules.perf.sut_metrics_store import (
    MAX_SERIES_POINTS,
    flatten_chunks_to_points,
    flatten_chunks_to_series,
    platform_sut_metrics_retain_days,
    summarize_series,
)
from app.modules.perf.sut_agent_settings import agent_settings_from_row, validate_agent_settings
from app.modules.perf.sut_schedule import is_monitoring_allowed
from app.modules.perf.sut_schedule_validate import validate_schedule
from app.modules.perf.sut_force import get_force_until_ms_from_row
from app.modules.perf.sut_token import generate_sut_token, hash_sut_token

router = APIRouter(
    prefix="/sut-servers",
    tags=["被测服务器监控"],
    dependencies=[Depends(is_authenticated), Depends(require_permissions(PERF_SCENE_VIEW))],
)

HEARTBEAT_ONLINE_SEC = 90
MAX_METRICS_RANGE_MS = 24 * 3600 * 1000


def _server_status(row: SutServer) -> str:
    if not row.last_heartbeat_at:
        return "offline"
    hb = row.last_heartbeat_at
    if hb.tzinfo is not None:
        hb = hb.replace(tzinfo=None)
    now = now_app()
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    age = (now - hb).total_seconds()
    return "online" if age <= HEARTBEAT_ONLINE_SEC else "offline"


def _config_rev(row: SutServer) -> int:
    return int(getattr(row, "config_rev", None) or 1)


def _serialize_server(
    row: SutServer,
    *,
    include_token: Optional[str] = None,
    include_host_info: bool = True,
    include_agent_uid: bool = True,
) -> dict[str, Any]:
    data = {
        "id": row.id,
        "project_id": row.project_id,
        "name": row.name,
        "hostname": row.hostname or "",
        "role": row.role or "",
        "monitoring_enabled": bool(row.monitoring_enabled),
        "schedule": row.schedule_json,
        "agent_settings": agent_settings_from_row(row),
        "config_rev": _config_rev(row),
        "last_heartbeat_at": row.last_heartbeat_at.isoformat() if row.last_heartbeat_at else None,
        "last_metrics_at": row.last_metrics_at.isoformat() if getattr(row, "last_metrics_at", None) else None,
        "status": _server_status(row),
        "sample_allowed": is_monitoring_allowed(
            monitoring_enabled=bool(row.monitoring_enabled),
            schedule=row.schedule_json if isinstance(row.schedule_json, dict) else None,
            force_until_ms=get_force_until_ms_from_row(row),
        ),
        "create_time": row.create_time.isoformat() if row.create_time else None,
        "update_time": row.update_time.isoformat() if row.update_time else None,
        "create_by": row.create_by or "",
    }
    if include_agent_uid:
        data["agent_uid"] = row.agent_uid
    if include_host_info:
        data["host_info"] = row.host_info or {}
    if include_token:
        data["token"] = include_token
        data["token_once"] = True
    return data


class SutServerCreate(BaseModel):
    project_id: int
    name: str = Field(..., min_length=1, max_length=100)
    role: Optional[str] = Field(None, max_length=64)
    monitoring_enabled: bool = True
    schedule: Optional[dict[str, Any]] = None
    agent_settings: Optional[dict[str, Any]] = None


class SutServerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    role: Optional[str] = Field(None, max_length=64)
    monitoring_enabled: Optional[bool] = None
    schedule: Optional[dict[str, Any]] = None
    # 显式传 null 清除平台覆盖；省略字段则不改
    agent_settings: Optional[dict[str, Any]] = None


class RotateTokenBody(BaseModel):
    clear_agent_uid: bool = False


async def _get_server_or_404(server_id: int) -> SutServer:
    row = await SutServer.get_or_none(id=server_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="被测服务器不存在")
    return row


def _platform_base_from_request(request: Request) -> str:
    origin = (request.headers.get("origin") or "").strip().rstrip("/")
    if origin.startswith("http://") or origin.startswith("https://"):
        return origin
    referer = (request.headers.get("referer") or "").strip()
    if referer:
        try:
            u = urlparse(referer)
            if u.scheme in ("http", "https") and u.netloc:
                return f"{u.scheme}://{u.netloc}"
        except Exception:
            pass
    return str(request.base_url).rstrip("/")


@router.get("", summary="被测服务器列表")
async def list_sut_servers(
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_VIEWER)
    rows = await SutServer.filter(project_id=project_id, is_del=False).order_by("-id")
    return {
        "data": [
            _serialize_server(r, include_host_info=False, include_agent_uid=False) for r in rows
        ],
        "total": len(rows),
    }


@router.get("/overview", summary="多机监控总览")
async def sut_servers_overview(
    project_id: int = Query(...),
    user_info: dict = Depends(is_authenticated),
):
    """各机 online 状态 + 近 15 分钟 CPU/内存摘要。"""
    await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_VIEWER)
    rows = await SutServer.filter(project_id=project_id, is_del=False).order_by("id")
    now_ms = now_epoch_ms()
    from_ms = now_ms - 15 * 60 * 1000
    server_ids = [r.id for r in rows]
    chunks_by_server: dict[int, list] = {sid: [] for sid in server_ids}
    if server_ids:
        chunks = await SutMetricChunk.filter(
            server_id__in=server_ids,
            start_ms__lte=now_ms,
            end_ms__gte=from_ms,
        ).order_by("start_ms")
        for ch in chunks:
            chunks_by_server.setdefault(ch.server_id, []).append(ch)

    items = []
    for r in rows:
        raw = flatten_chunks_to_points(
            chunks_by_server.get(r.id, []), from_ms=from_ms, to_ms=now_ms
        )
        summary = summarize_series(raw)
        last_point = raw[-1] if raw else None
        items.append(
            {
                **_serialize_server(r, include_host_info=False, include_agent_uid=False),
                "summary_15m": summary,
                "latest": {
                    "ts_ms": last_point.get("ts_ms") if last_point else None,
                    "cpu_pct": last_point.get("cpu_pct") if last_point else None,
                    "mem_pct": last_point.get("mem_pct") if last_point else None,
                    "disk_pct": last_point.get("disk_pct") if last_point else None,
                    "net_rx_kbps": last_point.get("net_rx_kbps") if last_point else None,
                    "net_tx_kbps": last_point.get("net_tx_kbps") if last_point else None,
                },
            }
        )
    online = sum(1 for i in items if i.get("status") == "online")
    return {
        "data": items,
        "total": len(items),
        "online_count": online,
        "from_ms": from_ms,
        "to_ms": now_ms,
    }


@router.post(
    "",
    summary="创建被测服务器",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def create_sut_server(
    body: SutServerCreate,
    username: str = Depends(get_current_username),
    user_info: dict = Depends(is_authenticated),
):
    await assert_project_access(user_info, body.project_id, min_role=PROJECT_ROLE_MEMBER)
    project = await Project.get_or_none(id=body.project_id, is_del=False)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="名称不能为空")
    plain = generate_sut_token()
    try:
        schedule = validate_schedule(body.schedule)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    try:
        agent_settings = validate_agent_settings(body.agent_settings)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    row = await SutServer.create(
        project_id=body.project_id,
        name=name,
        role=(body.role or "").strip(),
        token_hash=hash_sut_token(plain),
        monitoring_enabled=bool(body.monitoring_enabled),
        schedule_json=schedule,
        agent_settings_json=agent_settings,
        config_rev=1,
        host_info={},
        create_by=username or "",
    )
    return _serialize_server(row, include_token=plain)


@router.get("/{server_id}", summary="被测服务器详情")
async def get_sut_server(
    server_id: int,
    user_info: dict = Depends(is_authenticated),
):
    row = await _get_server_or_404(server_id)
    await assert_project_access(user_info, row.project_id, min_role=PROJECT_ROLE_VIEWER)
    return _serialize_server(row)


@router.patch(
    "/{server_id}",
    summary="更新被测服务器",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def update_sut_server(
    server_id: int,
    body: SutServerUpdate,
    user_info: dict = Depends(is_authenticated),
):
    row = await _get_server_or_404(server_id)
    await assert_project_access(user_info, row.project_id, min_role=PROJECT_ROLE_MEMBER)
    fields: list[str] = []
    bump_rev = False
    patch = body.model_dump(exclude_unset=True)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="名称不能为空")
        row.name = name
        fields.append("name")
    if body.role is not None:
        row.role = body.role.strip()
        fields.append("role")
    if body.monitoring_enabled is not None:
        row.monitoring_enabled = bool(body.monitoring_enabled)
        fields.append("monitoring_enabled")
        bump_rev = True
    if body.schedule is not None:
        try:
            row.schedule_json = validate_schedule(body.schedule)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        fields.append("schedule_json")
        bump_rev = True
    if "agent_settings" in patch:
        try:
            row.agent_settings_json = validate_agent_settings(patch.get("agent_settings"))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        fields.append("agent_settings_json")
        bump_rev = True
    if bump_rev:
        row.config_rev = _config_rev(row) + 1
        fields.append("config_rev")
    if fields:
        await row.save(update_fields=fields)
    return _serialize_server(row)


@router.post(
    "/{server_id}/rotate-token",
    summary="轮换 Token",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def rotate_sut_token(
    server_id: int,
    body: Optional[RotateTokenBody] = None,
    user_info: dict = Depends(is_authenticated),
):
    row = await _get_server_or_404(server_id)
    await assert_project_access(user_info, row.project_id, min_role=PROJECT_ROLE_MEMBER)
    plain = generate_sut_token()
    row.token_hash = hash_sut_token(plain)
    fields = ["token_hash"]
    if body and body.clear_agent_uid:
        row.agent_uid = None
        fields.append("agent_uid")
    row.config_rev = _config_rev(row) + 1
    fields.append("config_rev")
    await row.save(update_fields=fields)
    return _serialize_server(row, include_token=plain)


@router.post(
    "/{server_id}/reset-agent",
    summary="重置采集器绑定",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def reset_agent_binding(
    server_id: int,
    user_info: dict = Depends(is_authenticated),
):
    """清空 agent_uid，允许新采集器用现有 Token 重新激活（数据目录丢失时）。"""
    row = await _get_server_or_404(server_id)
    await assert_project_access(user_info, row.project_id, min_role=PROJECT_ROLE_MEMBER)
    row.agent_uid = None
    row.config_rev = _config_rev(row) + 1
    await row.save(update_fields=["agent_uid", "config_rev"])
    return _serialize_server(row)


@router.delete(
    "/{server_id}",
    summary="删除被测服务器",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def delete_sut_server(
    server_id: int,
    user_info: dict = Depends(is_authenticated),
):
    row = await _get_server_or_404(server_id)
    await assert_project_access(user_info, row.project_id, min_role=PROJECT_ROLE_MEMBER)
    row.is_del = True
    row.agent_uid = None
    await row.save(update_fields=["is_del", "agent_uid"])
    return {"ok": True}


@router.get("/{server_id}/metrics", summary="查询监控曲线")
async def get_sut_metrics(
    server_id: int,
    from_ms: Optional[int] = Query(None),
    to_ms: Optional[int] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    row = await _get_server_or_404(server_id)
    await assert_project_access(user_info, row.project_id, min_role=PROJECT_ROLE_VIEWER)

    now_ms = now_epoch_ms()
    if to_ms is None:
        to_ms = now_ms
    if from_ms is None:
        from_ms = to_ms - 3600 * 1000
    if from_ms > to_ms:
        raise HTTPException(status_code=422, detail="from_ms 不能大于 to_ms")
    if to_ms - from_ms > MAX_METRICS_RANGE_MS:
        raise HTTPException(status_code=422, detail="查询时间窗不能超过 24 小时")

    chunks = await SutMetricChunk.filter(
        server_id=server_id,
        start_ms__lte=to_ms,
        end_ms__gte=from_ms,
    ).order_by("start_ms")
    raw = flatten_chunks_to_points(list(chunks), from_ms=from_ms, to_ms=to_ms)
    series = flatten_chunks_to_series(list(chunks), from_ms=from_ms, to_ms=to_ms)
    return {
        "server_id": server_id,
        "from_ms": from_ms,
        "to_ms": to_ms,
        "series": series,
        "summary": summarize_series(raw),
        "raw_point_count": len(raw),
        "source": "agent",
        "downsampled": len(raw) > MAX_SERIES_POINTS,
    }


@router.get("/{server_id}/install-snippet", summary="被测监控采集器安装配置片段")
async def install_snippet(
    server_id: int,
    request: Request,
    user_info: dict = Depends(is_authenticated),
):
    """不含明文 token（创建/轮换时已返回）；platform 尽量用浏览器 Origin。"""
    row = await _get_server_or_404(server_id)
    await assert_project_access(user_info, row.project_id, min_role=PROJECT_ROLE_VIEWER)
    platform = _platform_base_from_request(request)
    settings = agent_settings_from_row(row) or {
        "interval_sec": 5,
        "upload_every_sec": 15,
        "buffer_hours": 48,
    }
    return {
        "server_id": row.id,
        "name": row.name,
        "hint": (
            "将创建/轮换 Token 时返回的 token 写入 agent_config.json，勿放 URL Query。"
            "明文 Token 关闭后无法再看，丢失需轮换。采样间隔/缓冲也可在控制台「采集参数」修改，"
            "约 30 秒内心跳热更新。推荐 venv 安装依赖后运行；HTTP 平台须 allow_insecure_http=true。"
        ),
        "config_example": {
            "platform": platform,
            "token": "<粘贴一次性 Token>",
            "interval_sec": settings["interval_sec"],
            "upload_every_sec": settings["upload_every_sec"],
            "buffer_hours": settings["buffer_hours"],
            "data_dir": "./data",
            "allow_insecure_http": str(platform).startswith("http://"),
        },
    }
