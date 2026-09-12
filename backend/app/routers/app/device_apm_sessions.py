"""独立设备性能监控会话：启停、秒级点、终态落库。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.infra.mq_producer import MQProducer
from app.core.platform.auth import (
    get_current_username,
    is_authenticated,
    require_any_permissions,
    verify_runner_or_internal,
)
from app.core.platform.permissions import APP_CASE_EXECUTE, APP_CASE_VIEW, APP_ELEMENT_VIEW
from app.core.platform.platform_settings_service import (
    delete_app_device_apm_session,
    get_ui_case_record_delete_mode,
)
from app.models.app import AppCaseExecution, AppDeviceApmSession, AppPlanExecution, AppSuiteExecution
from app.models.sys import Device
from app.modules.app.app_device_lock import (
    acquire_device_lock,
    get_device_lock,
    refresh_device_lock,
    release_device_lock,
    release_device_lock_by_holder,
    release_device_lock_by_udid,
)
from app.modules.app import device_apm_session_service as apm_sess
from app.modules.app.device_apm import (
    ALLOWED_METRICS,
    DEFAULT_METRICS,
    compare_device_apm_payloads,
    downsample_series,
    normalize_thresholds,
    validate_device_apm_for_dispatch,
)
from app.modules.app.device_apm_session_service import session_ttl_seconds, starting_lock_ttl_seconds
from app.modules.ui.ui_project_guard import assert_user_project_member, assert_user_project_viewer
from app.routers.perf.report_utils import apply_display_nicknames
from app.schemas.app import (
    AppDeviceApmCompareForm,
    AppDeviceApmFinalForm,
    AppDeviceApmPointsForm,
    AppDeviceApmSessionForm,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/device-apm", tags=["设备性能监控"])

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
    registered = (device.app_udid or "").strip()
    override = (app_udid or "").strip()
    if override and registered and override != registered:
        raise HTTPException(
            status_code=422,
            detail="app_udid 必须与已登记设备一致，不允许监控未登记手机",
        )
    if override and not registered:
        raise HTTPException(
            status_code=422,
            detail="设备未登记 app_udid，请连接手机后重新上线 Runner，不允许手填未登记 UDID",
        )
    udid = override or registered
    if not udid:
        raise HTTPException(status_code=422, detail="设备未登记 app_udid，请连接手机后重新上线 Runner")
    return device, udid


def _clean_metrics(raw: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    for m in raw or DEFAULT_METRICS:
        key = str(m or "").strip().lower()
        if key in ALLOWED_METRICS and key not in cleaned:
            cleaned.append(key)
    return cleaned or list(DEFAULT_METRICS)


@router.post("/sessions", summary="开始独立设备性能监控", dependencies=[Depends(is_authenticated)])
async def start_device_apm_session(
    body: AppDeviceApmSessionForm,
    request: Request,
    user_info: dict = Depends(require_any_permissions(APP_CASE_EXECUTE)),
    username: str = Depends(get_current_username),
):
    await assert_user_project_member(user_info, body.project_id)
    device, udid = await _resolve_app_device(body.device_id, body.app_udid)
    pkg = (body.pkg_name or "").strip()
    metrics = _clean_metrics(body.metrics)
    thresholds = normalize_thresholds(body.thresholds)
    cfg = {
        "enabled": True,
        "pkg_name": pkg,
        "interval_ms": body.interval_ms,
        "metrics": metrics,
        "thresholds": thresholds,
    }
    err = validate_device_apm_for_dispatch(
        cfg,
        udid=udid,
        platform=device.app_platform or "android",
    )
    if err:
        raise HTTPException(status_code=422, detail=err)

    # 同设备已有活跃会话：同项目直接恢复，避免「已被设备性能监控占用」死锁
    existing = await apm_sess.prepare_udid_for_new_session(
        udid, project_id=body.project_id, username=username or ""
    )
    if existing and existing.get("_conflict"):
        other = existing.get("session") or {}
        raise HTTPException(
            status_code=409,
            detail=(
                f"设备 {udid} 正被「设备性能监控」占用"
                f"（会话 {other.get('session_id') or ''}，用户 {other.get('username') or '未知'}），"
                "请先在原会话停止或等待结束后再试"
            ),
        )
    if existing and str(existing.get("status") or "") in ("starting", "running", "stopping"):
        return {
            "code": 0,
            "data": {
                **apm_sess.public_session_view(existing),
                "resumed": True,
            },
            "message": "resumed",
        }

    try:
        session = await apm_sess.create_session(
            project_id=body.project_id,
            device_id=device.id,
            app_udid=udid,
            pkg_name=pkg,
            username=username or "",
            interval_ms=body.interval_ms,
            metrics=metrics,
            thresholds=thresholds,
            duration_sec=body.duration_sec,
        )
    except ValueError as bind_exc:
        raise HTTPException(status_code=409, detail=str(bind_exc)) from bind_exc
    session_id = session["session_id"]
    # 启动阶段用短锁；首批 points 上报后再按 duration 续满
    lock_ttl = starting_lock_ttl_seconds(body.duration_sec)
    try:
        await acquire_device_lock(
            udid,
            holder_type="apm",
            holder_id=session_id,
            username=username or "",
            ttl_seconds=lock_ttl,
        )
    except HTTPException as lock_exc:
        # 仅清理「孤儿」apm 锁：锁 holder 在 Redis 无活跃会话时才释放，禁止抢走仍在跑的会话
        try:
            lock = await get_device_lock(udid)
            if not (lock and lock.get("holder_type") == "apm"):
                await apm_sess.close_session(session_id)
                raise lock_exc
            holder_id = str(lock.get("holder_id") or "")
            indexed = await apm_sess.get_session_id_by_udid(udid)
            holder_sess = await apm_sess.get_session(holder_id) if holder_id else None
            holder_status = str((holder_sess or {}).get("status") or "")
            orphan = (
                not holder_id
                or not holder_sess
                or holder_status in ("finished", "failed")
                or (indexed and str(indexed) != holder_id and not holder_sess)
            )
            if not orphan:
                await apm_sess.close_session(session_id)
                raise lock_exc
            await release_device_lock_by_udid(udid)
            await acquire_device_lock(
                udid,
                holder_type="apm",
                holder_id=session_id,
                username=username or "",
                ttl_seconds=lock_ttl,
            )
        except HTTPException:
            await apm_sess.close_session(session_id)
            raise
        except Exception:
            await apm_sess.close_session(session_id)
            raise lock_exc

    base = _request_base_url(request)
    points_url = f"{base}/app-module/device-apm/sessions/{session_id}/points"
    final_url = f"{base}/app-module/device-apm/sessions/{session_id}/final"
    status_url = f"{base}/app-module/device-apm/sessions/{session_id}/runner-status"

    try:
        mq = _get_mq()
        # 消息过期略长于会话 TTL，避免执行器离线很久后仍消费到「会话已没」的僵尸 APM 任务
        ttl_sec = int(session_ttl_seconds(float(body.duration_sec or 0)))
        expire_ms = max(60_000, (ttl_sec + 300) * 1000)
        mq.send_test_task(
            env_config={
                "engine_type": "app",
                "platform": device.app_platform or "android",
                "device_udid": udid,
                "project_id": body.project_id,
            },
            run_case={
                "task_type": "app_device_metrics",
                "mode": "standalone",
                "apm_session_id": session_id,
                "device_udid": udid,
                "pkg_name": pkg,
                "interval_ms": body.interval_ms,
                "metrics": metrics,
                "thresholds": thresholds,
                "duration_sec": body.duration_sec,
                "points_url": points_url,
                "final_url": final_url,
                "status_url": status_url,
            },
            device_id=device.id,
            expiration_ms=expire_ms,
        )
    except Exception as exc:
        await release_device_lock(udid, holder_type="apm", holder_id=session_id)
        await apm_sess.close_session(session_id)
        logger.exception("派发独立 APM 失败")
        raise HTTPException(status_code=500, detail=f"派发监控任务失败: {exc}") from exc

    # 保持 starting，等首批 points 再 mark_running，避免 MQ 丢失后长期占锁
    session = await apm_sess.get_session(session_id) or session
    return {"code": 0, "data": apm_sess.public_session_view(session), "message": "ok"}


@router.get("/sessions", summary="监控记录列表", dependencies=[Depends(is_authenticated)])
async def list_device_apm_sessions(
    project_id: int = Query(...),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user_info: dict = Depends(require_any_permissions(APP_CASE_VIEW, APP_CASE_EXECUTE, APP_ELEMENT_VIEW)),
):
    await assert_user_project_viewer(user_info, project_id)
    qs = AppDeviceApmSession.filter(project_id=project_id, is_del=False)
    total = await qs.count()
    rows = await qs.order_by("-create_time").offset((page - 1) * size).limit(size)
    delete_mode = await get_ui_case_record_delete_mode()
    items = [
        {
            "session_id": r.id,
            "project_id": r.project_id,
            "device_id": r.device_id,
            "app_udid": r.app_udid,
            "pkg_name": r.pkg_name,
            "status": r.status,
            "interval_ms": r.interval_ms,
            "metrics": r.metrics or [],
            "error": r.error,
            "username": r.username,
            "sample_count": (r.summary or {}).get("sample_count") if isinstance(r.summary, dict) else None,
            "cpu_pct_max": (r.summary or {}).get("cpu_pct_max") if isinstance(r.summary, dict) else None,
            "mem_pss_mb_max": (r.summary or {}).get("mem_pss_mb_max") if isinstance(r.summary, dict) else None,
            "create_time": r.create_time.isoformat() if r.create_time else None,
            "update_time": r.update_time.isoformat() if r.update_time else None,
        }
        for r in rows
    ]
    await apply_display_nicknames(items)
    return {
        "code": 0,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "delete_mode": delete_mode,
        },
        "message": "ok",
    }


@router.delete(
    "/history/{session_id}",
    summary="删除监控记录（遵循平台运行记录删除模式）",
    dependencies=[Depends(is_authenticated)],
)
async def delete_device_apm_history(
    session_id: str,
    permanent: bool = Query(default=False),
    user_info: dict = Depends(require_any_permissions(APP_CASE_EXECUTE)),
):
    """删除已落库的监控历史。进行中的会话请先用 DELETE /sessions/{id} 停止。"""
    row = await AppDeviceApmSession.get_or_none(id=session_id, is_del=False)
    if not row:
        raise HTTPException(status_code=404, detail="监控记录不存在")
    await assert_user_project_member(user_info, row.project_id)
    # 若 Redis 仍在跑，禁止删库记录以免状态错乱
    live = await apm_sess.get_session(session_id)
    if live and str(live.get("status") or "") in ("starting", "running", "stopping"):
        raise HTTPException(status_code=409, detail="该会话仍在监控中，请先停止后再删除记录")
    result = await delete_app_device_apm_session(row, permanent=permanent)
    # 同步清 Redis 终态，避免删除后仍可通过 session API 读到
    try:
        await apm_sess.close_session(session_id)
    except Exception:
        pass
    return {"code": 0, "data": {"session_id": session_id, "result": result}, "message": "ok"}


@router.post("/sessions/{session_id}/persist", summary="保存监控记录到历史", dependencies=[Depends(is_authenticated)])
async def persist_device_apm_session(
    session_id: str,
    user_info: dict = Depends(require_any_permissions(APP_CASE_EXECUTE)),
):
    """将 Redis 终态或已有汇总写入 DB（停止后可手动保存/补写）。"""
    session = await apm_sess.get_session(session_id)
    summary = None
    series = None
    thresholds = None
    status = "finished"
    error = None
    project_id = 0
    device_id = ""
    udid = ""
    pkg = ""
    interval_ms = 1000
    metrics: list = []
    username = ""
    if session:
        project_id = int(session.get("project_id") or 0)
        await assert_user_project_member(user_info, project_id)
        status = str(session.get("status") or "finished")
        if status not in ("finished", "failed"):
            raise HTTPException(status_code=409, detail="请先停止监控后再保存记录")
        summary = session.get("summary") if isinstance(session.get("summary"), dict) else {}
        series = session.get("series") if isinstance(session.get("series"), list) else []
        if not series:
            series = await apm_sess.get_points(session_id, limit=0)
        series = downsample_series(series or [])
        thresholds = session.get("thresholds")
        # 采集 error 与落库 persist_error 分离，勿把落库失败写入 error 字段
        error = session.get("error")
        device_id = str(session.get("device_id") or "")
        udid = str(session.get("app_udid") or "")
        pkg = str(session.get("pkg_name") or "")
        interval_ms = int(session.get("interval_ms") or 1000)
        metrics = session.get("metrics") or []
        username = str(session.get("username") or "")
    else:
        row = await AppDeviceApmSession.get_or_none(id=session_id, is_del=False)
        if not row:
            raise HTTPException(status_code=404, detail="会话不存在或已过期")
        await assert_user_project_member(user_info, row.project_id)
        return {
            "code": 0,
            "data": {"session_id": row.id, "status": row.status, "already_saved": True},
            "message": "ok",
        }

    payload = {
        "session_id": session_id,
        "project_id": project_id,
        "device_id": device_id,
        "app_udid": udid,
        "pkg_name": pkg,
        "status": status,
        "interval_ms": interval_ms,
        "metrics": metrics,
        "thresholds": thresholds,
        "summary": summary,
        "series": series,
        "error": error,
        "username": username,
    }
    result = await apm_sess.persist_session_to_db(payload)
    if result.startswith("error:"):
        raise HTTPException(status_code=500, detail=f"保存失败: {result[6:]}")
    return {"code": 0, "data": {"session_id": session_id, "status": status, "already_saved": False}, "message": "ok"}

@router.get("/sessions/{session_id}", summary="查询监控会话（含增量点）", dependencies=[Depends(is_authenticated)])
async def get_device_apm_session(
    session_id: str,
    after_ts_ms: int | None = Query(default=None),
    user_info: dict = Depends(require_any_permissions(APP_CASE_VIEW, APP_CASE_EXECUTE, APP_ELEMENT_VIEW)),
):
    session = await apm_sess.get_session(session_id)
    if not session:
        row = await AppDeviceApmSession.get_or_none(id=session_id, is_del=False)
        if not row:
            raise HTTPException(status_code=404, detail="监控会话不存在或已过期")
        await assert_user_project_viewer(user_info, row.project_id)
        return {
            "code": 0,
            "data": {
                "session_id": row.id,
                "project_id": row.project_id,
                "device_id": row.device_id,
                "app_udid": row.app_udid,
                "pkg_name": row.pkg_name,
                "interval_ms": row.interval_ms,
                "metrics": row.metrics or [],
                "thresholds": row.thresholds or {},
                "status": row.status,
                "error": row.error,
                "summary": row.summary,
                "series": row.series or [],
                "points": [],
            },
            "message": "ok",
        }
    pid = int(session.get("project_id") or 0)
    if pid <= 0:
        raise HTTPException(status_code=404, detail="监控会话项目无效")
    await assert_user_project_viewer(user_info, pid)
    # 鉴权后再做 stale 清理，避免跨项目误释锁
    stale = await apm_sess.fail_if_stale(session_id)
    if stale and str(stale.get("status") or "") in ("failed", "finished"):
        udid = str(stale.get("app_udid") or "")
        try:
            await release_device_lock(udid, holder_type="apm", holder_id=session_id)
        except Exception:
            await release_device_lock_by_holder("apm", session_id)
        try:
            await apm_sess.persist_session_to_db(stale)
        except Exception:
            logger.exception("APM get-stale persist failed session=%s", session_id)
        session = stale
    points = await apm_sess.get_points(session_id, after_ts_ms=after_ts_ms)
    return {"code": 0, "data": apm_sess.public_session_view(session, points=points), "message": "ok"}


@router.delete("/sessions/{session_id}", summary="停止监控", dependencies=[Depends(is_authenticated)])
async def stop_device_apm_session(
    session_id: str,
    user_info: dict = Depends(require_any_permissions(APP_CASE_EXECUTE)),
):
    session = await apm_sess.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="监控会话不存在或已结束")
    await assert_user_project_member(user_info, int(session.get("project_id") or 0))
    status = str(session.get("status") or "")
    if status in ("finished", "failed"):
        udid = str(session.get("app_udid") or "")
        await release_device_lock(udid, holder_type="apm", holder_id=session_id)
        return {"code": 0, "data": apm_sess.public_session_view(session), "message": "already stopped"}
    # 仅标记 stopping，等 Runner final 再释锁；同时检查是否已 stale
    await apm_sess.mark_stopping(session_id)
    stale = await apm_sess.fail_if_stale(session_id)
    if stale and str(stale.get("status") or "") in ("failed", "finished"):
        udid = str(stale.get("app_udid") or "")
        try:
            await release_device_lock(udid, holder_type="apm", holder_id=session_id)
        except Exception:
            await release_device_lock_by_holder("apm", session_id)
        try:
            await apm_sess.persist_session_to_db(stale)
        except Exception:
            logger.exception("APM stop-stale persist failed session=%s", session_id)
        return {"code": 0, "data": apm_sess.public_session_view(stale), "message": "stopped stale"}
    session = await apm_sess.get_session(session_id) or session
    return {"code": 0, "data": apm_sess.public_session_view(session), "message": "stopping"}


@router.post("/sessions/{session_id}/points", summary="Runner 上报采样点（内部）")
async def post_device_apm_points(
    session_id: str,
    body: AppDeviceApmPointsForm,
    _ctx: dict = Depends(verify_runner_or_internal),
):
    session = await apm_sess.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session gone")
    status = str(session.get("status") or "")
    if status not in ("starting", "running", "stopping"):
        raise HTTPException(status_code=409, detail=f"session status={status}")
    n = await apm_sess.append_points(
        session_id,
        body.points or [],
        batch_id=getattr(body, "batch_id", None),
    )
    if status == "starting":
        await apm_sess.mark_running(session_id)
    udid = str(session.get("app_udid") or "")
    await refresh_device_lock(
        udid,
        holder_type="apm",
        holder_id=session_id,
        ttl_seconds=session_ttl_seconds(float(session.get("duration_sec") or 0)),
    )
    return {"code": 0, "data": {"accepted": n}, "message": "ok"}


@router.post("/sessions/{session_id}/final", summary="Runner 上报终态（内部）")
async def post_device_apm_final(
    session_id: str,
    body: AppDeviceApmFinalForm,
    _ctx: dict = Depends(verify_runner_or_internal),
):
    session = await apm_sess.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session gone")
    err = body.error
    if err is None and isinstance(body.summary, dict):
        err = body.summary.get("error")
    if isinstance(err, str) and len(err) > 500:
        err = err[:500]
    updated = await apm_sess.apply_final(
        session_id,
        summary=body.summary,
        series=body.series,
        thresholds=body.thresholds,
        error=err,
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="final conflict, please retry")
    if str(updated.get("status") or "") not in ("finished", "failed"):
        raise HTTPException(status_code=409, detail="session not terminal after final")

    udid = str(session.get("app_udid") or "")
    try:
        await release_device_lock(udid, holder_type="apm", holder_id=session_id)
    except Exception:
        await release_device_lock_by_holder("apm", session_id)

    persist_result = await apm_sess.persist_session_to_db(updated)
    view = apm_sess.public_session_view(updated)
    if persist_result.startswith("error:"):
        raise HTTPException(
            status_code=500,
            detail=f"会话终态已接收但落库失败: {persist_result[6:]}",
        )
    return {"code": 0, "data": view, "message": "ok"}


@router.get("/sessions/{session_id}/runner-status", summary="Runner 校验会话（内部）")
async def runner_device_apm_status(
    session_id: str,
    _ctx: dict = Depends(verify_runner_or_internal),
):
    session = await apm_sess.get_session(session_id)
    if not session:
        return {"code": 0, "data": {"status": "gone"}, "message": "ok"}
    return {
        "code": 0,
        "data": {"status": session.get("status"), "pkg_name": session.get("pkg_name")},
        "message": "ok",
    }


async def _load_apm_side(kind: str, sid: str) -> tuple[dict, int]:
    kind = (kind or "").strip().lower()
    sid = str(sid or "").strip()
    if not sid:
        raise HTTPException(status_code=422, detail="缺少对比 ID")
    if kind == "session":
        session = await apm_sess.get_session(sid)
        if session:
            pid = int(session.get("project_id") or 0)
            if pid <= 0:
                raise HTTPException(status_code=404, detail=f"独立会话项目无效: {sid}")
            return (
                {"summary": session.get("summary") or {}, "series": session.get("series") or []},
                pid,
            )
        row = await AppDeviceApmSession.get_or_none(id=sid, is_del=False)
        if not row:
            raise HTTPException(status_code=404, detail=f"独立会话不存在: {sid}")
        return (
            {"summary": row.summary or {}, "series": row.series or []},
            int(row.project_id),
        )

    def _parse_int_id(raw: str) -> int:
        if not raw.isdigit():
            raise HTTPException(status_code=422, detail=f"非法执行记录 ID: {raw}")
        return int(raw)

    if kind == "case":
        row = await AppCaseExecution.get_or_none(id=_parse_int_id(sid), is_del=False)
        if not row:
            raise HTTPException(status_code=404, detail=f"用例执行记录不存在: {sid}")
        project_id = 0
        try:
            case = await row.case
            project_id = int(getattr(case, "project_id", 0) or 0)
        except Exception:
            project_id = 0
        if project_id <= 0:
            raise HTTPException(status_code=404, detail=f"用例执行记录项目无效: {sid}")
        return (
            {"summary": row.device_apm_summary or {}, "series": row.device_apm_series or []},
            project_id,
        )
    if kind == "suite":
        row = await AppSuiteExecution.get_or_none(id=_parse_int_id(sid), is_del=False)
        if not row:
            raise HTTPException(status_code=404, detail=f"套件执行记录不存在: {sid}")
        project_id = 0
        try:
            suite = await row.suite
            project_id = int(getattr(suite, "project_id", 0) or 0)
        except Exception:
            project_id = 0
        if project_id <= 0:
            raise HTTPException(status_code=404, detail=f"套件执行记录项目无效: {sid}")
        return (
            {"summary": row.device_apm_summary or {}, "series": row.device_apm_series or []},
            project_id,
        )
    if kind == "plan":
        row = await AppPlanExecution.get_or_none(id=_parse_int_id(sid), is_del=False)
        if not row:
            raise HTTPException(status_code=404, detail=f"计划执行记录不存在: {sid}")
        project_id = 0
        try:
            plan = await row.plan
            project_id = int(getattr(plan, "project_id", 0) or 0)
        except Exception:
            project_id = 0
        if project_id <= 0:
            raise HTTPException(status_code=404, detail=f"计划执行记录项目无效: {sid}")
        return (
            {"summary": row.device_apm_summary or {}, "series": row.device_apm_series or []},
            project_id,
        )
    raise HTTPException(status_code=422, detail=f"不支持的对比类型: {kind}")


@router.post(
    "/compare",
    summary="设备性能双记录对比",
    dependencies=[Depends(is_authenticated)],
)
async def compare_device_apm(
    body: AppDeviceApmCompareForm,
    user_info: dict = Depends(require_any_permissions(APP_CASE_VIEW, APP_ELEMENT_VIEW)),
):
    left, left_pid = await _load_apm_side(body.left_type, body.left_id)
    right, right_pid = await _load_apm_side(body.right_type, body.right_id)
    if left_pid:
        await assert_user_project_viewer(user_info, left_pid)
    if right_pid and right_pid != left_pid:
        await assert_user_project_viewer(user_info, right_pid)
    data = compare_device_apm_payloads(
        left,
        right,
        left_label=body.left_label or "A",
        right_label=body.right_label or "B",
    )
    return {"code": 0, "data": data, "message": "ok"}
