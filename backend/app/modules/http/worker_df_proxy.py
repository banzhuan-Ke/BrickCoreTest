"""数据工厂经 PerfWorker 代发（task_type=df_datasource_probe）。

编排/写确认/变量替换在平台；Worker 只在本机连库/ES。选定 Worker 后禁止静默回退本机。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException

from app.core.db.db_drivers import _decrypt_password, enrich_execute_result
from app.core.runner.runner_version import compare_version
from app.modules.http.worker_http_proxy import (
    MIN_DF_PROXY_ENGINE,
    NO_LOCAL_FALLBACK,
    WorkerProxyError,
    require_api_proxy_worker,
    to_http_exception,
)

logger = logging.getLogger(__name__)

TASK_TYPE = "df_datasource_probe"


def _with_no_fallback(message: str) -> str:
    text = str(message or "").strip().rstrip("。，,")
    if "未回退" in text or "勿回退" in text:
        return text
    return f"{text}，{NO_LOCAL_FALLBACK}"


async def require_df_proxy_worker(project_id: int, worker_id: int):
    """校验 Worker 可用且引擎 ≥ MIN_DF_PROXY_ENGINE。"""
    worker = await require_api_proxy_worker(project_id, worker_id)
    engine_ver = (getattr(worker, "engine_version", None) or "").strip()
    if not engine_ver or compare_version(engine_ver, MIN_DF_PROXY_ENGINE) < 0:
        raise WorkerProxyError(
            f"数据工厂经执行机连接需要引擎 ≥ {MIN_DF_PROXY_ENGINE}"
            f"（当前 {engine_ver or '未知'}），请升级 BrickCorePerf / Runner 压测包",
            400,
        )
    return worker


async def require_df_proxy_worker_http(project_id: int, worker_id: int):
    try:
        return await require_df_proxy_worker(project_id, worker_id)
    except WorkerProxyError as exc:
        raise to_http_exception(exc) from exc


def _plain_password(ds: Any, password_override: Optional[str] = None) -> str:
    if password_override is not None:
        return str(password_override)
    try:
        return _decrypt_password(ds) or ""
    except Exception:
        return ""


def _dsn_task_fields(ds: Any, *, password: str) -> dict[str, Any]:
    return {
        "db_type": (getattr(ds, "db_type", None) or "mysql"),
        "host": getattr(ds, "host", None) or "",
        "port": int(getattr(ds, "port", None) or 3306),
        "database_name": getattr(ds, "database_name", None) or "",
        "username": getattr(ds, "username", None) or "",
        "password": password or "",
        "timeout_seconds": int(getattr(ds, "timeout_seconds", None) or 10),
        "allow_write": bool(getattr(ds, "allow_write", False)),
        "max_rows": int(getattr(ds, "max_rows", None) or 100),
    }


async def send_df_probe_via_worker(
    *,
    worker=None,
    project_id: Optional[int] = None,
    worker_id: Optional[int] = None,
    ds: Any,
    mode: str = "ping",
    statement: str = "",
    allow_write: bool = False,
    for_assertion: bool = False,
    max_rows: Optional[int] = None,
    password_override: Optional[str] = None,
) -> dict[str, Any]:
    """经 Worker 测连或执行语句。失败抛 WorkerProxyError / 返回结构化失败，绝不本机连库。"""
    from app.routers.perf import df_datasource_bridge
    from app.routers.perf.workers import send_task_to_worker
    from app.modules.http.worker_http_proxy import _cleanup_worker_task

    if worker is None:
        worker = await require_df_proxy_worker(int(project_id or 0), int(worker_id or 0))

    mode_n = (mode or "ping").strip().lower()
    if mode_n not in ("ping", "execute"):
        mode_n = "ping"

    timeout_sec = max(1, int(getattr(ds, "timeout_seconds", None) or 10))
    wait_timeout = float(timeout_sec + 20)
    limit = int(max_rows) if max_rows is not None else int(getattr(ds, "max_rows", None) or 100)
    limit = max(1, min(limit, 1000))

    password = _plain_password(ds, password_override)
    request_id = df_datasource_bridge.new_request_id()
    await df_datasource_bridge.register_wait(request_id)

    task = {
        "task_type": TASK_TYPE,
        "request_id": request_id,
        "mode": mode_n,
        "statement": statement or "",
        "allow_write": bool(allow_write),
        "for_assertion": bool(for_assertion),
        "max_rows": limit,
        **_dsn_task_fields(ds, password=password),
    }
    # 勿把密码打进日志
    logger.info(
        "df_datasource_probe 下发 worker_id=%s mode=%s db_type=%s host=%s port=%s",
        worker.id,
        mode_n,
        task.get("db_type"),
        task.get("host"),
        task.get("port"),
    )

    ok = await send_task_to_worker(worker, task)
    if not ok:
        await df_datasource_bridge.cancel(request_id)
        busy = False
        try:
            from app.routers.perf import worker_queue

            busy = await worker_queue.has_pending_task(worker.id)
        except Exception:
            busy = False
        if busy:
            raise WorkerProxyError(
                "下发任务失败（执行机任务队列占用），请稍后重试或换一台空闲执行机",
                503,
            )
        raise WorkerProxyError(
            "下发任务失败（写入执行机队列失败，可能是 Redis 不可用），请稍后重试",
            503,
        )

    result = await df_datasource_bridge.wait_result(request_id, timeout=wait_timeout)
    await _cleanup_worker_task(worker, request_id)

    if result is None:
        raise WorkerProxyError(
            "等待执行机数据源结果超时，请确认执行机在线且版本支持数据工厂代发",
            408,
        )

    # Worker 可能把业务失败放在 error + success=false，不抛 HTTP，与直连一致
    out = enrich_execute_result(result if isinstance(result, dict) else {})
    if "worker_id" not in out:
        out["worker_id"] = worker.id
        out["worker_name"] = (getattr(worker, "name", None) or "")[:100]
    out["via_worker"] = True
    return out


def raise_as_http(exc: WorkerProxyError) -> None:
    raise to_http_exception(exc)


def map_proxy_error_to_result(exc: WorkerProxyError) -> dict[str, Any]:
    """测连等希望 200+data 时，把代发失败收成 success=false。"""
    return enrich_execute_result(
        {
            "success": False,
            "error": _with_no_fallback(str(exc)),
            "rows": [],
            "row_count": 0,
            "via_worker": True,
        }
    )
