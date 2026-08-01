"""性能测试 Worker 节点管理"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Optional, List

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from tortoise.transactions import in_transaction

from app.models.perf import PerfWorker, PerfRecord
from app.modules.perf.perf_trace import append_request_detail
from app.routers.perf.perf_state import _running_progress
from app.routers.perf.progress_utils import compute_running_progress
from app.routers.perf.case_agg_utils import (
    merge_case_aggregation,
    finalize_case_aggregation,
    strip_rt_samples_from_case_aggregations,
)
from app.routers.perf.report_utils import merge_rt_histograms
from app.routers.perf import worker_queue, worker_reports
from app.routers.perf.access import get_worker_for_member
from app.modules.perf.metrics_accuracy import merge_rt_samples, percentiles_from_samples
from app.core.platform.auth import (
    _authenticate_user_from_token,
    is_authenticated,
    oauth2_scheme_optional,
    require_permissions,
    verify_runner_token,
)
from app.core.platform.config import INTERNAL_API_KEY, RUNNER_ENGINE_VERSION
from app.core.platform.permissions import PERF_SCENE_EDIT, PERF_WORKER_VIEW
from app.core.platform.project_access import PROJECT_ROLE_MEMBER, PROJECT_ROLE_VIEWER, assert_project_access

logger = logging.getLogger(__name__)

ERROR_RATE_AUTO_STOP_MSG = "错误率连续3秒超过阈值，已自动停止"

# 前端用 router（继承 perf_router 的认证依赖）
router = APIRouter(
    prefix="/workers",
    tags=["性能测试Worker节点"],
    dependencies=[Depends(require_permissions(PERF_WORKER_VIEW))],
)

# Worker 脚本用 public_router：注册需 Runner/用户/内部密钥；心跳/领取任务仍靠 worker token
public_router = APIRouter(prefix="/workers", tags=["性能测试Worker节点"])


async def _require_worker_project_auth(
    project_id: int = Query(...),
    token: str | None = Depends(oauth2_scheme_optional),
    x_runner_token: str | None = Header(None, alias="X-Runner-Token"),
    x_internal_token: str | None = Header(None, alias="X-Internal-Token"),
) -> dict:
    """注册/下线：必须证明对 project_id 有成员权限，或持有平台内部密钥。"""
    if x_internal_token and x_internal_token == INTERNAL_API_KEY:
        return {"internal": True, "project_id": project_id}

    if x_runner_token:
        runner_ctx = await verify_runner_token(x_runner_token)
        user_id = runner_ctx.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Runner token 缺少用户信息")
        from app.models.sys import User

        user = await User.get_or_none(id=user_id, is_del=False)
        if not user or not user.is_active:
            raise HTTPException(status_code=403, detail="Runner 关联用户无效或已停用")
        user_info = {
            "id": user.id,
            "username": user.username,
            "is_superuser": bool(user.is_superuser),
        }
        await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_MEMBER)
        return {"runner": True, **user_info, "project_id": project_id}

    if token:
        user_info = await _authenticate_user_from_token(token)
        await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_MEMBER)
        return {**user_info, "project_id": project_id}

    raise HTTPException(
        status_code=401,
        detail="Worker 注册/下线需要 X-Runner-Token、登录 JWT 或有效的 X-Internal-Token",
    )


# ========== 请求模型 ==========

class WorkerRegisterRequest(BaseModel):
    name: str
    host: str
    port: Optional[int] = 0
    max_concurrent: int = 100
    token: str
    agent_kind: Optional[str] = ""
    engine_version: Optional[str] = ""


class WorkerHeartbeatRequest(BaseModel):
    worker_id: int
    token: str
    status: Optional[str] = None  # idle / busy
    current_record_id: Optional[int] = None
    agent_kind: Optional[str] = None
    engine_version: Optional[str] = None


class WorkerUnregisterRequest(BaseModel):
    token: str
    host: str


class WorkerReportData(BaseModel):
    worker_id: int
    token: str
    timestamp: int  # 秒级时间戳
    qps: float = 0
    avg_rt: float = 0
    p95_rt: float = 0
    error_rate: float = 0
    active_users: int = 0
    total_req: int = 0
    success: int = 0
    fail: int = 0


class WorkerFinalReport(BaseModel):
    worker_id: int
    token: str
    total_requests: int = 0
    success_count: int = 0
    fail_count: int = 0
    qps: float = 0
    duration: float = 0
    total_bytes_received: int = 0
    total_bytes_sent: int = 0
    avg_response_time: float = 0
    min_response_time: float = 0
    max_response_time: float = 0
    median_response_time: float = 0
    p90_response_time: float = 0
    p95_response_time: float = 0
    p99_response_time: float = 0
    std_dev_response_time: float = 0
    error_rate: float = 0
    received_kb_per_sec: float = 0
    sent_kb_per_sec: float = 0
    error_breakdown: dict = {}
    case_aggregations: dict = {}
    time_series_data: list = []
    phase_metrics: dict = {}
    request_details: list = []
    # 蓄水池样本：多 Worker 合并后算真分位（旧客户端可缺省）
    rt_samples: list = []
    success_avg_response_time: float = 0
    success_p95_response_time: float = 0
    success_rt_samples: list = []


# ========== 分布式聚合（秒级点列存 Redis，见 worker_reports；进程锁仅本机） ==========

_final_merge_locks: dict[int, asyncio.Lock] = {}


def _get_final_merge_lock(record_id: int) -> asyncio.Lock:
    if record_id not in _final_merge_locks:
        _final_merge_locks[record_id] = asyncio.Lock()
    return _final_merge_locks[record_id]


def _worker_assigned_to_record(worker: PerfWorker, record: PerfRecord) -> bool:
    if worker.current_record_id == record.id:
        return True
    dist = record.distribution_info if isinstance(record.distribution_info, dict) else {}
    for item in dist.get("workers") or []:
        if item.get("worker_id") == worker.id:
            return True
    return False


async def _assert_worker_assigned(worker: PerfWorker, record: PerfRecord) -> None:
    if not _worker_assigned_to_record(worker, record):
        raise HTTPException(status_code=403, detail="Worker 未参与该压测任务")


async def _clear_worker_reports(record_id: int):
    await worker_reports.clear_reports(record_id)


# ========== Worker 管理接口 ==========

@public_router.post("/register", summary="Worker 注册")
async def register_worker(
    req: WorkerRegisterRequest,
    project_id: int = Query(...),
    _auth: dict = Depends(_require_worker_project_auth),
):
    """Worker 节点启动时调用，注册到 Backend（同项目+token+主机名复用已有记录，避免重复计数）"""
    _ = _auth
    now = datetime.now()
    existing = await PerfWorker.filter(
        project_id=project_id,
        token=req.token,
        host=req.host,
    ).order_by("-id").first()

    if existing:
        was_executing = existing.status == "busy" or bool(existing.current_record_id)
        existing.name = req.name
        existing.port = req.port or 0
        existing.max_concurrent = req.max_concurrent
        existing.agent_kind = (req.agent_kind or existing.agent_kind or "").strip()[:32]
        existing.engine_version = (req.engine_version or existing.engine_version or "").strip()[:50]
        existing.status = "idle"
        # 执行中重连时不要清 current_record_id，否则平台会误判任务已结束并提前 finalize
        if not was_executing:
            existing.current_record_id = None
        existing.last_heartbeat = now
        await existing.save()
        # 清理历史重复注册（同机多次启动留下的脏数据）
        await PerfWorker.filter(
            project_id=project_id,
            token=req.token,
            host=req.host,
        ).exclude(id=existing.id).delete()
        return {"worker_id": existing.id, "message": "重新连接成功"}

    worker = await PerfWorker.create(
        name=req.name,
        host=req.host,
        port=req.port or 0,
        token=req.token,
        max_concurrent=req.max_concurrent,
        agent_kind=(req.agent_kind or "").strip()[:32],
        engine_version=(req.engine_version or "").strip()[:50],
        status="idle",
        project_id=project_id,
        last_heartbeat=now,
    )
    return {"worker_id": worker.id, "message": "注册成功"}


@public_router.post("/heartbeat", summary="Worker 心跳")
async def worker_heartbeat(req: WorkerHeartbeatRequest):
    """Worker 定期发送心跳，保持在线状态"""
    worker = await PerfWorker.get_or_none(id=req.worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker 不存在")
    if worker.token != req.token:
        raise HTTPException(status_code=403, detail="Token 无效")

    worker.last_heartbeat = datetime.now()
    if req.status:
        worker.status = req.status
    if req.current_record_id is not None:
        worker.current_record_id = req.current_record_id
    if req.agent_kind is not None and str(req.agent_kind).strip():
        worker.agent_kind = str(req.agent_kind).strip()[:32]
    if req.engine_version is not None and str(req.engine_version).strip():
        worker.engine_version = str(req.engine_version).strip()[:50]
    await worker.save()

    return {"message": "心跳成功"}


@public_router.get("/records/{record_id}/stop-check", summary="Worker 查询是否应停止压测")
async def worker_stop_check(
    record_id: int,
    worker_id: int = Query(...),
    token: str = Query(...),
):
    worker = await PerfWorker.get_or_none(id=worker_id)
    if not worker or worker.token != token:
        raise HTTPException(status_code=403, detail="Token 无效")
    record = await PerfRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    await _assert_worker_assigned(worker, record)
    should_stop = record.status in ("stopped", "failed", "success")
    return {"should_stop": should_stop, "status": record.status}


@public_router.post("/unregister", summary="Worker 主动下线")
async def unregister_worker(
    req: WorkerUnregisterRequest,
    project_id: int = Query(...),
    _auth: dict = Depends(_require_worker_project_auth),
):
    """客户端下线时调用，立即将节点标记为离线（不再等待心跳超时）。"""
    _ = _auth
    workers = await PerfWorker.filter(
        project_id=project_id,
        token=req.token,
        host=req.host,
    ).all()
    if not workers:
        return {"message": "未找到 Worker 记录", "count": 0}

    stale = datetime.now() - timedelta(days=1)
    for w in workers:
        w.status = "idle"
        w.current_record_id = None
        w.last_heartbeat = stale
        await w.save()
    return {"message": "已下线", "count": len(workers)}


@router.get("", summary="Worker 列表")
async def get_workers(
    project_id: int = Query(..., description="项目ID"),
    status: Optional[str] = Query(None),
    user_info: dict = Depends(is_authenticated),
):
    """获取 Worker 节点列表（必须指定项目，并校验成员权限）"""
    await assert_project_access(user_info, project_id, min_role=PROJECT_ROLE_VIEWER)
    await reclaim_stale_busy_workers(project_id)
    query = PerfWorker.filter(project_id=project_id)
    if status:
        query = query.filter(status=status)

    workers = await query.order_by("-id").all()
    now = datetime.now()

    # 同项目+token+主机仅保留一条（优先最近心跳）
    deduped: dict = {}
    for w in workers:
        key = (w.project_id, w.token, w.host)
        last_hb = w.last_heartbeat.replace(tzinfo=None) if w.last_heartbeat and w.last_heartbeat.tzinfo else w.last_heartbeat
        prev = deduped.get(key)
        if not prev:
            deduped[key] = (w, last_hb)
        elif last_hb and (not prev[1] or last_hb > prev[1]):
            deduped[key] = (w, last_hb)

    result = []
    expected_ver = (RUNNER_ENGINE_VERSION or "").strip()
    for w, last_hb in deduped.values():
        if last_hb:
            age_sec = max(0, int((now - last_hb).total_seconds()))
            is_offline = (now - last_hb) > timedelta(minutes=2)
            offline_reason = f"超过 2 分钟无心跳（已 {age_sec} 秒）" if is_offline else None
        else:
            ct = w.create_time.replace(tzinfo=None) if w.create_time and w.create_time.tzinfo else w.create_time
            if ct:
                age_sec = max(0, int((now - ct).total_seconds()))
                is_offline = (now - ct) > timedelta(minutes=2)
                offline_reason = (
                    "从未心跳，且注册已超过 2 分钟"
                    if is_offline
                    else None
                )
            else:
                age_sec = None
                is_offline = True
                offline_reason = "从未心跳"
        dynamic_status = "offline" if is_offline else "online"
        if status and dynamic_status != status:
            continue
        engine_ver = (getattr(w, "engine_version", "") or "").strip()
        if not engine_ver:
            version_ok = None
        elif expected_ver:
            version_ok = engine_ver == expected_ver
        else:
            version_ok = None
        result.append({
            "id": w.id,
            "name": w.name,
            "host": w.host,
            "max_concurrent": w.max_concurrent,
            "status": dynamic_status,
            "agent_kind": getattr(w, "agent_kind", "") or "",
            "engine_version": engine_ver,
            "expected_engine_version": expected_ver,
            "version_ok": version_ok,
            "offline_reason": offline_reason if is_offline else None,
            "heartbeat_age_seconds": age_sec,
            "last_heartbeat": w.last_heartbeat.strftime("%Y-%m-%d %H:%M:%S") if w.last_heartbeat else "-",
            "current_record_id": w.current_record_id,
            "create_time": w.create_time.strftime("%Y-%m-%d %H:%M:%S")
        })
    result.sort(key=lambda x: x["id"], reverse=True)
    return result


@router.delete(
    "/{worker_id}",
    summary="删除 Worker",
    dependencies=[Depends(require_permissions(PERF_SCENE_EDIT))],
)
async def delete_worker(worker: PerfWorker = Depends(get_worker_for_member)):
    """删除 Worker 节点"""
    await worker.delete()
    return {"message": "删除成功"}


# ========== 任务分发与结果上报 ==========

def _normalize_heartbeat(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _worker_is_busy(w: PerfWorker) -> bool:
    if w.current_record_id:
        return True
    return (w.status or "").lower() == "busy"


_HEARTBEAT_TIMEOUT = timedelta(minutes=2)


def _is_heartbeat_stale(w: PerfWorker, now: Optional[datetime] = None) -> bool:
    """超过心跳窗口视为僵死（与 get_active_workers 在线判定一致）。"""
    now = now or datetime.now()
    cutoff = now - _HEARTBEAT_TIMEOUT
    last_hb = _normalize_heartbeat(w.last_heartbeat)
    if last_hb:
        return last_hb <= cutoff
    ct = _normalize_heartbeat(w.create_time)
    if ct:
        return ct <= cutoff
    return True


async def reclaim_stale_busy_workers(project_id: Optional[int] = None) -> int:
    """心跳超时后强制清 current_record_id / busy，避免长期占槽。"""
    query = PerfWorker.filter()
    if project_id is not None:
        query = query.filter(project_id=project_id)
    workers = await query.all()
    now = datetime.now()
    reclaimed = 0
    for w in workers:
        if not _worker_is_busy(w):
            continue
        if not _is_heartbeat_stale(w, now=now):
            continue
        prev_record = w.current_record_id
        w.status = "idle"
        w.current_record_id = None
        await w.save()
        reclaimed += 1
        logger.info(
            "回收僵死 busy Worker id=%s host=%s prev_record_id=%s",
            w.id,
            w.host,
            prev_record,
        )
    return reclaimed


async def get_active_workers(
    project_id: Optional[int] = None,
    *,
    exclude_busy: bool = True,
) -> List[PerfWorker]:
    """获取活跃的 Worker 节点（2分钟内有心跳，按项目+token+主机去重）"""
    await reclaim_stale_busy_workers(project_id)
    cutoff = datetime.now() - _HEARTBEAT_TIMEOUT
    query = PerfWorker.filter()
    if project_id is not None:
        query = query.filter(project_id=project_id)
    workers = await query.all()

    deduped: dict = {}
    for w in workers:
        if exclude_busy and _worker_is_busy(w):
            continue
        last_hb = _normalize_heartbeat(w.last_heartbeat)
        if not last_hb:
            ct = _normalize_heartbeat(w.create_time)
            if ct and ct > cutoff:
                last_hb = ct
        if not last_hb or last_hb <= cutoff:
            continue
        key = (w.project_id, w.token, w.host)
        prev = deduped.get(key)
        if not prev:
            deduped[key] = w
            continue
        prev_hb = _normalize_heartbeat(prev.last_heartbeat)
        if prev_hb and last_hb > prev_hb:
            deduped[key] = w
    return list(deduped.values())


async def send_task_to_worker(worker: PerfWorker, task: dict) -> bool:
    """向 Worker 分配压测任务（Redis 优先；已有待领取任务则拒绝覆盖）"""
    if await worker_queue.has_pending_task(worker.id):
        return False
    return await worker_queue.assign_task(worker.id, task)


class WorkerApiDebugResult(BaseModel):
    worker_id: int
    token: str
    request_id: str
    status_code: Optional[int] = None
    headers: dict = {}
    body: Any = None
    time: float = 0
    size: int = 0
    error: Optional[str] = None


@public_router.post("/debug-result", summary="接收执行机接口调试结果")
async def receive_api_debug_result(data: WorkerApiDebugResult):
    """Worker 完成 task_type=api_debug 后回传；与压测 final 分离。"""
    from app.routers.perf import api_debug_bridge

    worker = await PerfWorker.get_or_none(id=data.worker_id)
    if not worker or worker.token != data.token:
        raise HTTPException(status_code=403, detail="Token 无效")

    payload = {
        "status_code": data.status_code,
        "headers": data.headers or {},
        "body": data.body,
        "time": data.time or 0,
        "size": data.size or 0,
        "error": data.error,
    }
    ok = await api_debug_bridge.complete(data.request_id, payload)
    # 短任务：立即标空闲，避免压测列表长时间 busy
    if not worker.current_record_id:
        worker.status = "idle"
        await worker.save()
    if not ok:
        raise HTTPException(status_code=404, detail="调试请求已过期或不存在")
    return {"message": "ok"}


@public_router.get("/{worker_id}/task", summary="Worker 获取任务（长轮询）")
async def get_worker_task(worker_id: int, token: str = Query(...), timeout: int = Query(30)):
    """Worker 长轮询获取任务，最多等待 timeout 秒"""
    worker = await PerfWorker.get_or_none(id=worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker 不存在")
    if worker.token != token:
        raise HTTPException(status_code=403, detail="Token 无效")

    task = await worker_queue.wait_for_task(worker_id, timeout=min(max(timeout, 1), 60))
    if task:
        worker.status = "busy"
        rid = task.get("record_id")
        if rid is not None:
            worker.current_record_id = rid
        await worker.save()
        return {"has_task": True, "task": task}

    return {"has_task": False}


def distribute_by_weights(
    total: int,
    capacities: List[int],
    weights: Optional[List[int]] = None,
) -> List[int]:
    """按权重将总并发拆到各槽位，每槽不超过 capacities[i]。

    weights 缺省或长度不匹配时，用 capacities 作权重（与历史按 max_concurrent 比例一致）。
    """
    n = len(capacities)
    if n == 0:
        return []
    caps = [max(0, int(c or 0)) for c in capacities]
    if sum(caps) <= 0:
        return [0] * n

    if weights is None or len(weights) != n:
        wts = [max(1, c) if c > 0 else 0 for c in caps]
    else:
        wts = [max(0, int(w or 0)) for w in weights]
        # 有容量但权重被写成 0 时，至少给 1，避免整槽饿死
        wts = [max(1, w) if caps[i] > 0 and w <= 0 else w for i, w in enumerate(wts)]

    total_weight = sum(wts)
    if total_weight <= 0:
        return [0] * n

    total = max(0, int(total or 0))
    assignments: List[int] = []
    remaining = total

    for i in range(n):
        if caps[i] <= 0 or wts[i] <= 0:
            assignments.append(0)
            continue
        ratio = wts[i] / total_weight
        assigned = int(total * ratio)
        assigned = min(assigned, caps[i])
        if remaining > 0 and assigned == 0:
            assigned = 1
        assigned = min(assigned, remaining, caps[i])
        assignments.append(assigned)
        remaining -= assigned

    idx = 0
    guard = 0
    while remaining > 0 and guard <= n * 10:
        i = idx % n
        if assignments[i] < caps[i]:
            assignments[i] += 1
            remaining -= 1
        idx += 1
        guard += 1

    return assignments


def distribute_concurrent(
    total: int,
    workers: List[PerfWorker],
    weights: Optional[List[int]] = None,
) -> List[int]:
    """将总并发数拆分到各 Worker。

    默认按 max_concurrent 比例；传入 weights（与 workers 等长正整数）时按权重比例，
    仍受各机 max_concurrent 上限约束。
    """
    if not workers:
        return []
    capacities = [int(w.max_concurrent or 0) for w in workers]
    return distribute_by_weights(total, capacities, weights)


def parse_worker_weights_json(raw: Optional[str]) -> dict[int, int]:
    """解析 worker_weights 查询参数（JSON 对象，key 为 worker id）。"""
    import json

    if raw is None or not str(raw).strip():
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ValueError("worker_weights 须为 JSON 对象，如 {\"12\":2,\"15\":1}")
    if not isinstance(data, dict):
        raise ValueError("worker_weights 须为 JSON 对象")
    out: dict[int, int] = {}
    for k, v in data.items():
        try:
            wid = int(k)
            wv = int(v)
        except (TypeError, ValueError):
            raise ValueError(f"worker_weights 非法项: {k!r}={v!r}")
        if wv < 1:
            raise ValueError(f"worker_weights[{wid}] 须为正整数")
        out[wid] = wv
    return out


def resolve_worker_selection(
    active: List[PerfWorker],
    worker_ids: Optional[List[int]] = None,
    weight_map: Optional[dict[int, int]] = None,
) -> tuple[List[PerfWorker], List[int]]:
    """从在线空闲列表解析用户勾选与权重。

    worker_ids 为 None：使用全部 active，权重默认 max_concurrent（可被 weight_map 覆盖）。
    worker_ids 非空：须全部落在 active 内，否则 ValueError。
    返回 (selected_workers, weights)，与 selected 等长。
    """
    if not active:
        return [], []

    active_by_id = {int(w.id): w for w in active}
    weight_map = weight_map or {}

    if worker_ids is None:
        selected = list(active)
    else:
        ids = [int(x) for x in worker_ids]
        if not ids:
            raise ValueError("请至少选择一个压测执行器")
        missing = [i for i in ids if i not in active_by_id]
        if missing:
            raise ValueError(
                f"所选执行器不可用或不在线空闲：{', '.join(str(i) for i in missing)}"
            )
        # 保持用户勾选顺序
        selected = [active_by_id[i] for i in ids]

    weights = [
        int(weight_map.get(int(w.id), w.max_concurrent or 1) or 1)
        for w in selected
    ]
    weights = [max(1, w) for w in weights]
    return selected, weights


class WorkerRequestStop(BaseModel):
    worker_id: int
    token: str
    reason: str = ERROR_RATE_AUTO_STOP_MSG


@public_router.post("/{record_id}/request-stop", summary="Worker 请求全局停止（错误率超限等）")
async def worker_request_stop(record_id: int, data: WorkerRequestStop):
    """任一 Worker 触发自动停止时，将整条记录标为 stopped，其他 Worker 经 stop-check 退出。"""
    worker = await PerfWorker.get_or_none(id=data.worker_id)
    if not worker or worker.token != data.token:
        raise HTTPException(status_code=403, detail="Token 无效")
    record = await PerfRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    await _assert_worker_assigned(worker, record)
    if record.status in ("stopped", "failed", "success"):
        return {"message": "记录已结束", "status": record.status}
    if not isinstance(record.error_breakdown, dict):
        record.error_breakdown = {}
    if not record.error_breakdown.get("stop_reason"):
        record.error_breakdown["stop_reason"] = data.reason or ERROR_RATE_AUTO_STOP_MSG
    record.status = "stopped"
    record.ended_at = datetime.now()
    record.error_breakdown = record.error_breakdown
    await record.save()
    return {"message": "已请求全局停止", "status": record.status}


@public_router.post("/{record_id}/report", summary="接收 Worker 秒级上报")
async def receive_worker_report(record_id: int, data: WorkerReportData):
    """Worker 每秒上报一次聚合数据（点列写入 Redis，供多副本合并）。"""
    worker = await PerfWorker.get_or_none(id=data.worker_id)
    if not worker or worker.token != data.token:
        raise HTTPException(status_code=403, detail="Token 无效")

    point = data.dict() if hasattr(data, "dict") else data.model_dump()
    ok = await worker_reports.append_report(record_id, data.worker_id, point)
    if not ok:
        raise HTTPException(
            status_code=503,
            detail="秒级上报存储不可用（需要 Redis；单机调试可设 PERF_ALLOW_INMEMORY_WORKER_REPORTS=1）",
        )

    async with in_transaction():
        record = await PerfRecord.select_for_update().get_or_none(id=record_id)
        if not record:
            raise HTTPException(status_code=404, detail="记录不存在")
        await _assert_worker_assigned(worker, record)

        bd = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
        # 已有 Worker 最终报告合并时，禁止秒级回写覆盖 total / 合并标记
        if bd.get("_merged_worker_ids"):
            return {"message": "上报成功（最终合并进行中，已忽略秒级汇总写库）"}

        if record.status != "running":
            return {"message": "上报成功"}

        merged_ts = await merge_worker_time_series(record_id)
        if merged_ts:
            record.time_series_data = merged_ts
            record.total_requests = sum(int(ts.get("qps") or 0) for ts in merged_ts)
            record.success_count = sum(int(ts.get("success") or 0) for ts in merged_ts)
            record.fail_count = sum(int(ts.get("fail") or 0) for ts in merged_ts)
            latest = merged_ts[-1]
            record.qps = latest.get("qps", 0)
            record.avg_response_time = latest.get("avg_rt", 0)
            record.error_rate = latest.get("error_rate", 0)
            progress = compute_running_progress(record.config_snapshot or {}, merged_ts)
            if progress:
                _running_progress[record_id] = progress
            await record.save()

    return {"message": "上报成功"}


def _merge_worker_final_into_record(record: PerfRecord, data: WorkerFinalReport) -> None:
    if not isinstance(record.error_breakdown, dict):
        record.error_breakdown = {}

    record.total_requests += data.total_requests
    record.success_count += data.success_count
    record.fail_count += data.fail_count
    record.error_breakdown["_worker_final_count"] = int(record.error_breakdown.get("_worker_final_count") or 0) + 1
    record.duration = max(record.duration or 0, data.duration)

    if record.total_requests > 0:
        record.error_rate = round(record.fail_count / record.total_requests * 100, 2)

    if isinstance(record.error_breakdown, dict):
        record.error_breakdown["_total_bytes_received"] = (
            record.error_breakdown.get("_total_bytes_received", 0) + data.total_bytes_received
        )
        record.error_breakdown["_total_bytes_sent"] = (
            record.error_breakdown.get("_total_bytes_sent", 0) + data.total_bytes_sent
        )

    existing_rt_stats = []
    if isinstance(record.error_breakdown, dict):
        existing_rt_stats = record.error_breakdown.pop("_worker_rt_stats", [])
    existing_rt_stats.append({
        "total": data.total_requests,
        "avg": data.avg_response_time,
        "min": data.min_response_time,
        "max": data.max_response_time,
        "median": data.median_response_time,
        "p90": data.p90_response_time,
        "p95": data.p95_response_time,
        "p99": data.p99_response_time,
        "std_dev": data.std_dev_response_time,
    })

    existing_errors = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
    new_errors = data.error_breakdown or {}

    for key, val in (new_errors.get("status_code_distribution") or {}).items():
        existing_errors.setdefault("status_code_distribution", {})[key] = (
            existing_errors.get("status_code_distribution", {}).get(key, 0) + val
        )

    new_hist = new_errors.get("rt_histogram") or []
    if new_hist:
        merged_hist = existing_errors.get("rt_histogram") or []
        existing_errors["rt_histogram"] = merge_rt_histograms(merged_hist, new_hist)

    for key, val in (new_errors.get("by_status_code") or {}).items():
        existing_errors.setdefault("by_status_code", {})[key] = existing_errors.get("by_status_code", {}).get(key, 0) + val
    for key, val in (new_errors.get("by_type") or {}).items():
        existing_errors.setdefault("by_type", {})[key] = existing_errors.get("by_type", {}).get(key, 0) + val

    new_samples = (new_errors.get("failed_samples") or [])
    if new_samples:
        existing_samples = existing_errors.get("failed_samples", [])
        existing_samples.extend(new_samples)
        existing_errors["failed_samples"] = existing_samples[:50]

    new_traces = (new_errors.get("request_traces") or [])
    if new_traces:
        existing_traces = existing_errors.get("request_traces", [])
        existing_traces.extend(new_traces)
        existing_errors["request_traces"] = existing_traces[:500]

    new_journey = new_errors.get("journey_aggregations") or {}
    if new_journey:
        old_j = existing_errors.get("journey_aggregations") or {}
        merged_j = {
            "total_journeys": old_j.get("total_journeys", 0) + new_journey.get("total_journeys", 0),
            "success_journeys": old_j.get("success_journeys", 0) + new_journey.get("success_journeys", 0),
            "fail_journeys": old_j.get("fail_journeys", 0) + new_journey.get("fail_journeys", 0),
            "phases": dict(old_j.get("phases") or {}),
        }
        tj = merged_j["total_journeys"]
        merged_j["journey_success_rate"] = round(merged_j["success_journeys"] / tj * 100, 2) if tj else 0
        for pk, pv in (new_journey.get("phases") or {}).items():
            if pk not in merged_j["phases"]:
                merged_j["phases"][pk] = dict(pv)
            else:
                op = merged_j["phases"][pk]
                op["total"] = op.get("total", 0) + pv.get("total", 0)
                op["success"] = op.get("success", 0) + pv.get("success", 0)
                op["fail"] = op.get("fail", 0) + pv.get("fail", 0)
                op["error_rate"] = round(op["fail"] / op["total"] * 100, 2) if op.get("total") else 0
        existing_errors["journey_aggregations"] = merged_j

    for key, val in new_errors.items():
        if key in (
            "by_status_code", "by_type", "failed_samples", "request_traces",
            "status_code_distribution", "rt_histogram", "journey_aggregations",
            "metrics_meta",
        ):
            continue
        if key == "stop_reason":
            if val and not existing_errors.get("stop_reason"):
                existing_errors["stop_reason"] = val
            continue
        if isinstance(val, int):
            existing_errors[key] = existing_errors.get(key, 0) + val
        elif isinstance(val, dict) and key in existing_errors:
            for sub_key, sub_val in val.items():
                existing_errors[key][sub_key] = existing_errors[key].get(sub_key, 0) + sub_val
        else:
            existing_errors[key] = val
    existing_errors["_worker_rt_stats"] = existing_rt_stats

    # 增量合并蓄水池，避免 list-of-lists 撑爆 error_breakdown JSON
    new_samples = list(getattr(data, "rt_samples", None) or [])
    if new_samples:
        prev = existing_errors.get("_worker_rt_samples") or []
        # 兼容：旧逻辑存 [[...],[...]]，新逻辑存扁平 list
        if prev and isinstance(prev[0], (list, tuple)):
            existing_errors["_worker_rt_samples"] = merge_rt_samples([*prev, new_samples])
        else:
            existing_errors["_worker_rt_samples"] = merge_rt_samples([prev, new_samples])

    # 成功请求延迟样本合并
    succ_samples = list(getattr(data, "success_rt_samples", None) or [])
    if succ_samples or (getattr(data, "success_avg_response_time", 0) or 0) > 0:
        succ_bucket = existing_errors.get("_worker_success_rt") or {
            "samples": [], "stats": [],
        }
        if succ_samples:
            prev_s = succ_bucket.get("samples") or []
            succ_bucket["samples"] = merge_rt_samples([prev_s, succ_samples])
        stats_list = succ_bucket.setdefault("stats", [])
        stats_list.append({
            "total": int(getattr(data, "success_count", 0) or 0),
            "avg": float(getattr(data, "success_avg_response_time", 0) or 0),
            "p95": float(getattr(data, "success_p95_response_time", 0) or 0),
        })
        existing_errors["_worker_success_rt"] = succ_bucket

    # 透传 metrics_meta（取首个非空，勿做数值累加）
    new_meta = (new_errors.get("metrics_meta") if isinstance(new_errors, dict) else None) or {}
    if new_meta and not existing_errors.get("metrics_meta"):
        existing_errors["metrics_meta"] = new_meta

    record.error_breakdown = existing_errors

    existing_cases = record.case_aggregations or {}
    new_cases = data.case_aggregations or {}
    for case_id, new_agg in new_cases.items():
        cid = str(case_id)
        merged_raw = merge_case_aggregation(existing_cases.get(cid), new_agg)
        existing_cases[cid] = finalize_case_aggregation(merged_raw, keep_samples=True)
    record.case_aggregations = existing_cases

    if data.request_details:
        existing_details = record.request_details or []
        for detail in data.request_details:
            append_request_detail(existing_details, detail)
        record.request_details = existing_details
    if data.phase_metrics or data.request_details:
        from app.modules.stream_phase import aggregate_phase_metrics, extract_stream_detail, normalize_stream_profile
        normalized = [extract_stream_detail(d) for d in (record.request_details or [])]
        record.request_details = normalized
        profile = normalize_stream_profile(record.config_snapshot or {})
        record.phase_metrics = aggregate_phase_metrics(
            normalized,
            parser_id=profile.get("parser_id", ""),
            phase_schema=normalized[0].get("phase_schema") if normalized else [],
        )

    if data.time_series_data:
        bd = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
        finals = bd.get("_worker_final_time_series") or []
        finals.append(list(data.time_series_data))
        bd["_worker_final_time_series"] = finals
        record.error_breakdown = bd


@public_router.post("/{record_id}/final", summary="接收 Worker 最终报告")
async def receive_worker_final_report(record_id: int, data: WorkerFinalReport):
    """Worker 执行完成后上报最终报告"""
    worker = await PerfWorker.get_or_none(id=data.worker_id)
    if not worker or worker.token != data.token:
        raise HTTPException(status_code=403, detail="Token 无效")

    should_finalize = False
    async with _get_final_merge_lock(record_id):
        async with in_transaction():
            record = await PerfRecord.select_for_update().get_or_none(id=record_id)
            if not record:
                raise HTTPException(status_code=404, detail="记录不存在")
            await _assert_worker_assigned(worker, record)

            bd = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
            if bd.get("_perf_finalized"):
                return {"message": "记录已收尾，忽略迟到最终报告"}
            merged_ids = bd.get("_merged_worker_ids") or []
            if data.worker_id in merged_ids:
                return {"message": "已处理"}
            merged_ids.append(data.worker_id)
            bd["_merged_worker_ids"] = merged_ids
            record.error_breakdown = bd

            # 秒级上报运行期间已把 total/success/fail 写入 record；
            # 最终报告按 Worker 累加，首个最终报告到达前需清零，避免与秒级汇总重复计数。
            if len(merged_ids) == 1:
                record.total_requests = 0
                record.success_count = 0
                record.fail_count = 0

            _merge_worker_final_into_record(record, data)
            _refresh_record_summary_metrics(record)
            worker_db = await PerfWorker.select_for_update().get(id=data.worker_id)
            worker_db.current_record_id = None
            worker_db.status = "idle"
            await worker_db.save()
            await record.save()

            expected = len((record.distribution_info or {}).get("workers") or []) or 1
            finals = int((record.error_breakdown or {}).get("_worker_final_count") or 0)
            # 收齐后直接收尾，避免仅依赖 BackgroundTasks 等待循环（进程重启会丢）
            if record.status == "running" and finals >= expected:
                should_finalize = True

    if should_finalize:
        await finalize_distributed_record(record_id)
        return {"message": "最终报告接收成功，已收尾", "finalized": True}
    return {"message": "最终报告接收成功"}


async def maybe_finalize_stuck_running_record(record: PerfRecord) -> bool:
    """若 running 且已收齐 Worker 最终报告，补做收尾（列表/状态轮询自愈）。"""
    if not record or record.status != "running":
        return False
    bd = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
    finals = int(bd.get("_worker_final_count") or 0)
    expected = len((record.distribution_info or {}).get("workers") or []) or 1
    if finals < expected:
        return False
    await finalize_distributed_record(record.id)
    return True


# ========== 分布式聚合辅助 ==========

def _reconcile_request_counts(record: PerfRecord) -> None:
    """保证 total / success / fail 一致，避免秒级汇总与最终报告不一致"""
    total = record.total_requests or 0
    if total <= 0:
        return
    success = record.success_count or 0
    fail = record.fail_count or 0
    if success + fail > total:
        record.fail_count = max(0, total - success)
        fail = record.fail_count
    elif success + fail < total:
        if fail == 0 and (record.error_rate or 0) == 0:
            record.success_count = total
        else:
            record.fail_count = total - success
    record.error_rate = round(record.fail_count / total * 100, 2) if total > 0 else 0


def _recompute_rt_from_case_aggregations(record: PerfRecord) -> None:
    """从接口维度聚合回填整体响应时间（Worker 汇总为 0 时的兜底）"""
    cases = record.case_aggregations or {}
    if not cases:
        return
    weighted = []
    mins, maxs = [], []
    p90s, p95s, p99s, medians, stds = [], [], [], [], []
    for agg in cases.values():
        t = agg.get("total", 0)
        avg_rt = agg.get("avg_rt")
        if t <= 0 or avg_rt is None:
            continue
        weighted.append((agg["avg_rt"], t))
        mins.append(agg.get("min_rt", 0))
        maxs.append(agg.get("max_rt", 0))
        medians.append(agg.get("median_rt", 0))
        p90s.append(agg.get("p90_rt", 0))
        p95s.append(agg.get("p95_rt", 0))
        p99s.append(agg.get("p99_rt", 0))
        stds.append(agg.get("std_dev", 0))
    if not weighted:
        return
    w = sum(t for _, t in weighted)
    record.avg_response_time = round(sum(rt * t for rt, t in weighted) / w, 2)
    record.min_response_time = round(min(mins), 2) if mins else 0
    record.max_response_time = round(max(maxs), 2) if maxs else 0
    record.median_response_time = round(sum(m * t for m, (_, t) in zip(medians, weighted)) / w, 2)
    record.p90_response_time = round(sum(p * t for p, (_, t) in zip(p90s, weighted)) / w, 2)
    record.p95_response_time = round(sum(p * t for p, (_, t) in zip(p95s, weighted)) / w, 2)
    record.p99_response_time = round(sum(p * t for p, (_, t) in zip(p99s, weighted)) / w, 2)
    record.std_dev_response_time = round(sum(s * t for s, (_, t) in zip(stds, weighted)) / w, 2)


def _apply_worker_rt_stats_to_record(record: PerfRecord, *, pop_temp: bool = False) -> None:
    """从 Worker 最终报告累加的 RT 统计回填 record 顶栏延迟指标。

    优先合并各 Worker ``rt_samples`` 计算真分位；无样本时回退「Pxx 加权平均」。
    """
    bd = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
    raw_samples = bd.get("_worker_rt_samples") or []
    # 兼容扁平 list 与旧版 list-of-lists
    if raw_samples and isinstance(raw_samples[0], (list, tuple)):
        merged = merge_rt_samples(raw_samples)
    elif raw_samples:
        merged = []
        for x in raw_samples:
            try:
                v = float(x)
            except (TypeError, ValueError):
                continue
            if v > 0:
                merged.append(v)
    else:
        merged = []

    if merged:
        pct = percentiles_from_samples(merged)
        record.median_response_time = pct["median_response_time"]
        record.p90_response_time = pct["p90_response_time"]
        record.p95_response_time = pct["p95_response_time"]
        record.p99_response_time = pct["p99_response_time"]
        # avg/min/max/std 仍用各 Worker 加权（全量计数更准）
        rt_stats = bd.get("_worker_rt_stats") or []
        if rt_stats:
            total_weight = sum(s["total"] for s in rt_stats)
            if total_weight > 0:
                record.avg_response_time = round(
                    sum(s["avg"] * s["total"] for s in rt_stats) / total_weight, 2
                )
                record.min_response_time = round(min(s["min"] for s in rt_stats), 2)
                record.max_response_time = round(max(s["max"] for s in rt_stats), 2)
                record.std_dev_response_time = round(
                    sum(s["std_dev"] * s["total"] for s in rt_stats) / total_weight, 2
                )
    else:
        rt_stats = bd.get("_worker_rt_stats") or []
        if rt_stats:
            total_weight = sum(s["total"] for s in rt_stats)
            if total_weight > 0:
                record.avg_response_time = round(sum(s["avg"] * s["total"] for s in rt_stats) / total_weight, 2)
                record.min_response_time = round(min(s["min"] for s in rt_stats), 2)
                record.max_response_time = round(max(s["max"] for s in rt_stats), 2)
                record.median_response_time = round(sum(s["median"] * s["total"] for s in rt_stats) / total_weight, 2)
                record.p90_response_time = round(sum(s["p90"] * s["total"] for s in rt_stats) / total_weight, 2)
                record.p95_response_time = round(sum(s["p95"] * s["total"] for s in rt_stats) / total_weight, 2)
                record.p99_response_time = round(sum(s["p99"] * s["total"] for s in rt_stats) / total_weight, 2)
                record.std_dev_response_time = round(sum(s["std_dev"] * s["total"] for s in rt_stats) / total_weight, 2)

    # 成功专用延迟写入 error_breakdown.success_latency（不占顶栏字段）
    succ = bd.get("_worker_success_rt") or {}
    succ_samples = succ.get("samples") or []
    succ_stats = succ.get("stats") or []
    success_latency = {}
    if succ_samples:
        sp = percentiles_from_samples(succ_samples)
        w = sum(int(s.get("total") or 0) for s in succ_stats) or len(succ_samples)
        avg = 0.0
        if succ_stats and w > 0:
            avg = sum(float(s.get("avg") or 0) * int(s.get("total") or 0) for s in succ_stats) / w
        elif succ_samples:
            avg = sum(succ_samples) / len(succ_samples)
        success_latency = {
            "avg_response_time": round(avg, 2),
            "p95_response_time": sp["p95_response_time"],
            "median_response_time": sp["median_response_time"],
            "sample_count": len(succ_samples),
        }
    elif succ_stats:
        w = sum(int(s.get("total") or 0) for s in succ_stats)
        if w > 0:
            success_latency = {
                "avg_response_time": round(
                    sum(float(s.get("avg") or 0) * int(s.get("total") or 0) for s in succ_stats) / w, 2
                ),
                "p95_response_time": round(
                    sum(float(s.get("p95") or 0) * int(s.get("total") or 0) for s in succ_stats) / w, 2
                ),
                "sample_count": w,
            }
    if success_latency:
        bd["success_latency"] = success_latency

    if pop_temp:
        bd.pop("_worker_rt_samples", None)
        bd.pop("_worker_rt_stats", None)
        bd.pop("_worker_success_rt", None)
    # JSONField 需重新赋值，确保 Tortoise 感知变更
    if success_latency or pop_temp:
        record.error_breakdown = bd


def _refresh_record_summary_metrics(record: PerfRecord, *, pop_rt_temp: bool = False) -> None:
    """回填 record 顶栏 QPS / 延迟（Worker 最终报告或 finalize 时调用）"""
    _apply_worker_rt_stats_to_record(record, pop_temp=pop_rt_temp)
    if record.avg_response_time is None or record.avg_response_time <= 0:
        _recompute_rt_from_case_aggregations(record)
    dur = record.duration or 0
    total_req = record.total_requests or 0
    if dur > 0 and total_req > 0:
        record.qps = round(total_req / dur, 2)


async def merge_worker_time_series(record_id: int) -> list:
    """合并所有 Worker 的秒级上报数据为统一时序。

    说明：各 Worker 的 P95 不能加权平均得到全局 P95。多 Worker 同秒合并时
    秒级 p95_rt 取各节点该秒 P95 的最大值作为保守上界（趋势参考），最终报告
    仍以 rt_samples 合并后的真分位为准。
    """
    reports = await worker_reports.load_all_reports(record_id)
    if not reports:
        return []

    # 按时间戳聚合所有 Worker 数据
    merged = {}
    for worker_id, data_points in reports.items():
        for dp in data_points:
            ts = dp.get("timestamp")
            if ts not in merged:
                merged[ts] = {
                    "timestamp": ts,
                    "qps": 0,
                    "avg_rt": 0,
                    "p95_rt": 0,
                    "error_rate": 0,
                    "active_users": 0,
                    "total_req": 0,
                    "success": 0,
                    "fail": 0,
                    "_rt_weight": 0,
                    "_p95_values": [],
                    "_worker_count": 0,
                }
            m = merged[ts]
            # 以每秒请求数为准（qps 字段即该秒请求量），避免累计 total_req 参与合并
            sec_req = int(dp.get("qps") or 0)
            m["qps"] += sec_req
            m["total_req"] += sec_req
            m["success"] += int(dp.get("success") or 0)
            m["fail"] += int(dp.get("fail") or 0)
            m["active_users"] += dp.get("active_users", 0)
            m["_worker_count"] += 1
            if sec_req > 0:
                m["avg_rt"] = (
                    m["avg_rt"] * m["_rt_weight"] + dp.get("avg_rt", 0) * sec_req
                ) / (m["_rt_weight"] + sec_req)
                m["_rt_weight"] += sec_req
            p95_val = dp.get("p95_rt")
            if p95_val is not None:
                try:
                    m["_p95_values"].append(float(p95_val))
                except (TypeError, ValueError):
                    pass

    # 计算错误率
    for m in merged.values():
        total = m["total_req"]
        m["error_rate"] = round(m["fail"] / total * 100, 2) if total > 0 else 0
        p95_vals = m.pop("_p95_values", [])
        if len(p95_vals) <= 1:
            m["p95_rt"] = round(p95_vals[0], 2) if p95_vals else (m.get("avg_rt") or 0)
            m["p95_approx"] = False
        else:
            # 多 Worker：取 max 作保守上界，并标记非严格全局 P95
            m["p95_rt"] = round(max(p95_vals), 2)
            m["p95_approx"] = True
        m.pop("_rt_weight", None)
        m.pop("_worker_count", None)

    # 按时间戳排序
    return sorted(merged.values(), key=lambda x: x["timestamp"])


def merge_time_series_lists(series_list: list) -> list:
    """合并多个 Worker 最终报告中的时序点（秒级上报缺失时的兜底）。

    多 Worker 同秒 P95 取 max 作保守上界，并标记 p95_approx（与 merge_worker_time_series 一致）。
    """
    if not series_list:
        return []
    merged = {}
    for series in series_list:
        if not series:
            continue
        for dp in series:
            ts = dp.get("timestamp")
            if ts is None:
                continue
            if ts not in merged:
                merged[ts] = {
                    "timestamp": ts,
                    "qps": 0,
                    "avg_rt": 0,
                    "p95_rt": 0,
                    "error_rate": 0,
                    "active_users": 0,
                    "total_req": 0,
                    "success": 0,
                    "fail": 0,
                    "_rt_weight": 0,
                    "_p95_values": [],
                }
            m = merged[ts]
            sec_req = int(dp.get("qps") or dp.get("total_req") or 0)
            m["qps"] += sec_req
            m["total_req"] += sec_req
            m["success"] += int(dp.get("success") or 0)
            m["fail"] += int(dp.get("fail") or 0)
            m["active_users"] += dp.get("active_users", 0)
            if sec_req > 0:
                m["avg_rt"] = (
                    m["avg_rt"] * m["_rt_weight"] + dp.get("avg_rt", 0) * sec_req
                ) / (m["_rt_weight"] + sec_req)
                m["_rt_weight"] += sec_req
            p95_val = dp.get("p95_rt")
            if p95_val is not None:
                try:
                    m["_p95_values"].append(float(p95_val))
                except (TypeError, ValueError):
                    pass

    for m in merged.values():
        total = m["total_req"]
        m["error_rate"] = round(m["fail"] / total * 100, 2) if total > 0 else 0
        p95_vals = m.pop("_p95_values", [])
        if len(p95_vals) <= 1:
            m["p95_rt"] = round(p95_vals[0], 2) if p95_vals else (m.get("avg_rt") or 0)
            m["p95_approx"] = False
        else:
            m["p95_rt"] = round(max(p95_vals), 2)
            m["p95_approx"] = True
        m.pop("_rt_weight", None)

    return sorted(merged.values(), key=lambda x: x["timestamp"])


async def finalize_distributed_record(record_id: int):
    """分布式执行完成后，汇总所有 Worker 数据生成最终报告"""
    async with _get_final_merge_lock(record_id):
        await _finalize_distributed_record_locked(record_id)
    _final_merge_locks.pop(record_id, None)


async def _finalize_distributed_record_locked(record_id: int):
    record = await PerfRecord.get_or_none(id=record_id)
    if not record:
        return
    bd = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
    if bd.get("_perf_finalized"):
        return

    final_ts_lists = bd.pop("_worker_final_time_series", None)

    # 优先使用各 Worker 最终报告中的完整时序（跨副本一致），秒级缓存仅作兜底
    merged_ts = []
    if final_ts_lists:
        merged_ts = merge_time_series_lists(final_ts_lists)
    if not merged_ts:
        merged_ts = await merge_worker_time_series(record_id)
    if not merged_ts and record.time_series_data:
        merged_ts = record.time_series_data

    record.error_breakdown = bd
    record.time_series_data = merged_ts

    # 请求数以 Worker 最终报告为准；仅未收到最终报告时用秒级时序回填
    if merged_ts and (record.total_requests or 0) == 0:
        record.total_requests = sum(int(ts.get("qps") or ts.get("total_req") or 0) for ts in merged_ts)
        record.success_count = sum(int(ts.get("success") or 0) for ts in merged_ts)
        record.fail_count = sum(int(ts.get("fail") or 0) for ts in merged_ts)

    if not record.duration and merged_ts:
        record.duration = max(ts["timestamp"] for ts in merged_ts) + 1

    _reconcile_request_counts(record)
    _refresh_record_summary_metrics(record, pop_rt_temp=True)

    if record.case_aggregations:
        record.case_aggregations = strip_rt_samples_from_case_aggregations(record.case_aggregations)

    # 状态判定：保留用户手动停止；有失败即 failed（和本地执行保持一致）
    bd = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
    if record.status == "stopped":
        pass
    elif bd.get("stop_reason") == ERROR_RATE_AUTO_STOP_MSG:
        record.status = "stopped"
    elif (record.total_requests or 0) == 0 and (record.distribution_info or {}).get("is_distributed"):
        record.status = "failed"
        if not bd.get("stop_reason"):
            bd["stop_reason"] = "未收到 Worker 最终报告或总请求数为 0"
        record.error_breakdown = bd
    elif record.error_rate and record.error_rate > 0:
        record.status = "failed"
    else:
        record.status = "success"

    # 流量：按累计字节与总时长计算 KB/s
    bd = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
    total_recv = bd.pop("_total_bytes_received", 0)
    total_sent = bd.pop("_total_bytes_sent", 0)
    bd.pop("_worker_final_count", None)
    bd.pop("_merged_worker_ids", None)
    dur = record.duration or 0
    if dur > 0:
        record.received_kb_per_sec = round(total_recv / 1024 / dur, 2)
        record.sent_kb_per_sec = round(total_sent / 1024 / dur, 2)
    bd["_perf_finalized"] = True
    record.error_breakdown = bd

    record.ended_at = record.ended_at or datetime.now()
    await record.save()

    # 清理共享上报缓存
    await _clear_worker_reports(record_id)
    _running_progress.pop(record_id, None)

    # 更新 Worker 状态为 idle
    workers = await PerfWorker.filter(current_record_id=record_id).all()
    for w in workers:
        w.status = "idle"
        w.current_record_id = None
        await w.save()

    try:
        from app.modules.perf.perf_ai_analyze import maybe_trigger_record_ai_after_finalize
        await maybe_trigger_record_ai_after_finalize(record)
    except Exception:
        logger.exception("触发压测 AI 分析失败 record_id=%s", record_id)