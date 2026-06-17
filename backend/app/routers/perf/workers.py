"""性能测试 Worker 节点管理"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from tortoise.transactions import in_transaction

from app.models.perf import PerfWorker, PerfRecord
from app.core.perf_trace import append_request_detail
from app.routers.perf.perf_state import _running_progress
from app.routers.perf.progress_utils import compute_running_progress
from app.routers.perf.case_agg_utils import (
    merge_case_aggregation,
    finalize_case_aggregation,
    strip_rt_samples_from_case_aggregations,
)

ERROR_RATE_AUTO_STOP_MSG = "错误率连续3秒超过阈值，已自动停止"

# 前端用 router（继承 perf_router 的认证依赖）
router = APIRouter(prefix="/workers", tags=["性能测试Worker节点"])

# Worker 脚本用 public_router（无认证依赖，独立注册）
public_router = APIRouter(prefix="/workers", tags=["性能测试Worker节点"])


# ========== 请求模型 ==========

class WorkerRegisterRequest(BaseModel):
    name: str
    host: str
    port: Optional[int] = 0
    max_concurrent: int = 100
    token: str


class WorkerHeartbeatRequest(BaseModel):
    worker_id: int
    token: str
    status: Optional[str] = None  # idle / busy
    current_record_id: Optional[int] = None


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


# ========== 内存中的分布式聚合数据 ==========
# {record_id: {worker_id: [秒级数据点列表]}}
_worker_reports: dict = {}

# 任务队列: {worker_id: task_dict}
_task_queue: dict = {}
# 任务事件: {worker_id: asyncio.Event}
_task_events: dict = {}

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


def _get_worker_reports(record_id: int):
    if record_id not in _worker_reports:
        _worker_reports[record_id] = {}
    return _worker_reports[record_id]


def _clear_worker_reports(record_id: int):
    _worker_reports.pop(record_id, None)


def _assign_task(worker_id: int, task: dict):
    """向 Worker 分配任务"""
    _task_queue[worker_id] = task
    evt = _task_events.get(worker_id)
    if evt:
        evt.set()


def _get_task(worker_id: int) -> Optional[dict]:
    """获取并移除 Worker 的任务"""
    return _task_queue.pop(worker_id, None)


# ========== Worker 管理接口 ==========

@public_router.post("/register", summary="Worker 注册")
async def register_worker(req: WorkerRegisterRequest, project_id: int = Query(...)):
    """Worker 节点启动时调用，注册到 Backend（同项目+token+主机名复用已有记录，避免重复计数）"""
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
async def unregister_worker(req: WorkerUnregisterRequest, project_id: int = Query(...)):
    """客户端下线时调用，立即将节点标记为离线（不再等待心跳超时）。"""
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
    project_id: Optional[int] = Query(None, description="项目ID，传入则只返回该项目 Worker"),
    status: Optional[str] = Query(None)
):
    """获取 Worker 节点列表"""
    query = PerfWorker.filter()
    if project_id is not None:
        query = query.filter(project_id=project_id)
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
    for w, last_hb in deduped.values():
        if last_hb:
            is_offline = (now - last_hb) > timedelta(minutes=2)
        else:
            # 刚注册、尚未心跳：用创建时间兜底
            ct = w.create_time.replace(tzinfo=None) if w.create_time and w.create_time.tzinfo else w.create_time
            is_offline = not ct or (now - ct) > timedelta(minutes=2)
        dynamic_status = "offline" if is_offline else "online"
        if status and dynamic_status != status:
            continue
        result.append({
            "id": w.id,
            "name": w.name,
            "host": w.host,
            "max_concurrent": w.max_concurrent,
            "status": dynamic_status,
            "last_heartbeat": w.last_heartbeat.strftime("%Y-%m-%d %H:%M:%S") if w.last_heartbeat else "-",
            "current_record_id": w.current_record_id,
            "create_time": w.create_time.strftime("%Y-%m-%d %H:%M:%S")
        })
    result.sort(key=lambda x: x["id"], reverse=True)
    return result


@router.delete("/{worker_id}", summary="删除 Worker")
async def delete_worker(worker_id: int):
    """删除 Worker 节点"""
    worker = await PerfWorker.get_or_none(id=worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker 不存在")
    await worker.delete()
    return {"message": "删除成功"}


# ========== 任务分发与结果上报 ==========

def _normalize_heartbeat(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


async def get_active_workers(project_id: Optional[int] = None) -> List[PerfWorker]:
    """获取活跃的 Worker 节点（2分钟内有心跳，按项目+token+主机去重）"""
    cutoff = datetime.now() - timedelta(minutes=2)
    query = PerfWorker.filter()
    if project_id is not None:
        query = query.filter(project_id=project_id)
    workers = await query.all()

    deduped: dict = {}
    for w in workers:
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


async def send_task_to_worker(worker: PerfWorker, task: dict):
    """向 Worker 分配压测任务（通过内存队列）"""
    _assign_task(worker.id, task)
    return True


@public_router.get("/{worker_id}/task", summary="Worker 获取任务（长轮询）")
async def get_worker_task(worker_id: int, token: str = Query(...), timeout: int = Query(30)):
    """Worker 长轮询获取任务，最多等待 timeout 秒"""
    worker = await PerfWorker.get_or_none(id=worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker 不存在")
    if worker.token != token:
        raise HTTPException(status_code=403, detail="Token 无效")

    # 检查是否有立即的任务
    task = _get_task(worker_id)
    if task:
        worker.status = "busy"
        await worker.save()
        return {"has_task": True, "task": task}

    # 创建等待事件
    evt = asyncio.Event()
    _task_events[worker_id] = evt

    try:
        await asyncio.wait_for(evt.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        _task_events.pop(worker_id, None)

    task = _get_task(worker_id)
    if task:
        worker.status = "busy"
        await worker.save()
        return {"has_task": True, "task": task}

    return {"has_task": False}


def distribute_concurrent(total: int, workers: List[PerfWorker]) -> List[int]:
    """将总并发数拆分到各 Worker
    策略: 按比例分配，每个 Worker 不超过其 max_concurrent
    """
    if not workers:
        return []

    total_capacity = sum(w.max_concurrent for w in workers)
    if total_capacity <= 0:
        return [0] * len(workers)

    assignments = []
    remaining = total

    for w in workers:
        # 按比例分配
        ratio = w.max_concurrent / total_capacity
        assigned = int(total * ratio)
        # 不超过 Worker 上限
        assigned = min(assigned, w.max_concurrent)
        # 至少分配 1 如果还有剩余
        if remaining > 0 and assigned == 0:
            assigned = 1
        assigned = min(assigned, remaining)
        assignments.append(assigned)
        remaining -= assigned

    # 如果还有剩余，按顺序加到还有余量的 Worker
    idx = 0
    while remaining > 0:
        w = workers[idx % len(workers)]
        if assignments[idx % len(workers)] < w.max_concurrent:
            assignments[idx % len(workers)] += 1
            remaining -= 1
        idx += 1
        if idx > len(workers) * 10:  # 防止死循环
            break

    return assignments


@public_router.post("/{record_id}/report", summary="接收 Worker 秒级上报")
async def receive_worker_report(record_id: int, data: WorkerReportData):
    """Worker 每秒上报一次聚合数据"""
    worker = await PerfWorker.get_or_none(id=data.worker_id)
    if not worker or worker.token != data.token:
        raise HTTPException(status_code=403, detail="Token 无效")
    record = await PerfRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    await _assert_worker_assigned(worker, record)
    reports = _get_worker_reports(record_id)
    if data.worker_id not in reports:
        reports[data.worker_id] = []
    reports[data.worker_id].append(data.dict())

    # 分布式压测期间将合并时序写入 DB，供前端轮询实时图表
    if record.status == "running":
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
        hist_map = {h["label"]: h for h in merged_hist}
        for h in new_hist:
            if h["label"] in hist_map:
                hist_map[h["label"]]["count"] += h.get("count", 0)
            else:
                hist_map[h["label"]] = dict(h)
        existing_errors["rt_histogram"] = list(hist_map.values())

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
        from app.core.stream_phase import aggregate_phase_metrics, extract_stream_detail, normalize_stream_profile
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

    async with _get_final_merge_lock(record_id):
        async with in_transaction():
            record = await PerfRecord.select_for_update().get_or_none(id=record_id)
            if not record:
                raise HTTPException(status_code=404, detail="记录不存在")
            await _assert_worker_assigned(worker, record)

            bd = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
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
    return {"message": "最终报告接收成功"}


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
    """从 Worker 最终报告累加的 RT 统计回填 record 顶栏延迟指标"""
    bd = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
    rt_stats = bd.get("_worker_rt_stats") or []
    if not rt_stats:
        return
    total_weight = sum(s["total"] for s in rt_stats)
    if total_weight <= 0:
        return
    record.avg_response_time = round(sum(s["avg"] * s["total"] for s in rt_stats) / total_weight, 2)
    record.min_response_time = round(min(s["min"] for s in rt_stats), 2)
    record.max_response_time = round(max(s["max"] for s in rt_stats), 2)
    record.median_response_time = round(sum(s["median"] * s["total"] for s in rt_stats) / total_weight, 2)
    record.p90_response_time = round(sum(s["p90"] * s["total"] for s in rt_stats) / total_weight, 2)
    record.p95_response_time = round(sum(s["p95"] * s["total"] for s in rt_stats) / total_weight, 2)
    record.p99_response_time = round(sum(s["p99"] * s["total"] for s in rt_stats) / total_weight, 2)
    record.std_dev_response_time = round(sum(s["std_dev"] * s["total"] for s in rt_stats) / total_weight, 2)
    if pop_temp:
        bd.pop("_worker_rt_stats", None)
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
    """合并所有 Worker 的秒级上报数据为统一时序"""
    reports = _get_worker_reports(record_id)
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
                    "_p95_weight": 0,
                }
            m = merged[ts]
            # 以每秒请求数为准（qps 字段即该秒请求量），避免累计 total_req 参与合并
            sec_req = int(dp.get("qps") or 0)
            m["qps"] += sec_req
            m["total_req"] += sec_req
            m["success"] += int(dp.get("success") or 0)
            m["fail"] += int(dp.get("fail") or 0)
            m["active_users"] += dp.get("active_users", 0)
            if sec_req > 0:
                m["avg_rt"] = (
                    m["avg_rt"] * m["_rt_weight"] + dp.get("avg_rt", 0) * sec_req
                ) / (m["_rt_weight"] + sec_req)
                p95_val = dp.get("p95_rt")
                if p95_val is not None:
                    m["p95_rt"] = (
                        m["p95_rt"] * m["_p95_weight"] + p95_val * sec_req
                    ) / (m["_p95_weight"] + sec_req)
                    m["_p95_weight"] += sec_req
                m["_rt_weight"] += sec_req

    # 计算错误率
    for m in merged.values():
        total = m["total_req"]
        m["error_rate"] = round(m["fail"] / total * 100, 2) if total > 0 else 0
        if m.get("_p95_weight", 0) <= 0 and m.get("avg_rt"):
            m["p95_rt"] = m["avg_rt"]
        m.pop("_rt_weight", None)
        m.pop("_p95_weight", None)

    # 按时间戳排序
    return sorted(merged.values(), key=lambda x: x["timestamp"])


def merge_time_series_lists(series_list: list) -> list:
    """合并多个 Worker 最终报告中的时序点（秒级上报缺失时的兜底）。"""
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
                    "_p95_weight": 0,
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
                p95_val = dp.get("p95_rt")
                if p95_val is not None:
                    m["p95_rt"] = (
                        m["p95_rt"] * m["_p95_weight"] + p95_val * sec_req
                    ) / (m["_p95_weight"] + sec_req)
                    m["_p95_weight"] += sec_req
                m["_rt_weight"] += sec_req

    for m in merged.values():
        total = m["total_req"]
        m["error_rate"] = round(m["fail"] / total * 100, 2) if total > 0 else 0
        if m.get("_p95_weight", 0) <= 0 and m.get("avg_rt"):
            m["p95_rt"] = m["avg_rt"]
        m.pop("_rt_weight", None)
        m.pop("_p95_weight", None)

    return sorted(merged.values(), key=lambda x: x["timestamp"])


async def finalize_distributed_record(record_id: int):
    """分布式执行完成后，汇总所有 Worker 数据生成最终报告"""
    record = await PerfRecord.get_or_none(id=record_id)
    if not record:
        return

    # 合并时序数据
    merged_ts = await merge_worker_time_series(record_id)

    bd = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
    final_ts_lists = bd.pop("_worker_final_time_series", None)
    if not merged_ts and final_ts_lists:
        merged_ts = merge_time_series_lists(final_ts_lists)

    # 如果秒级上报为空，回退到最终报告中已合并的 time_series_data
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
    record.error_breakdown = bd

    record.ended_at = datetime.now()
    await record.save()

    # 清理内存数据
    _clear_worker_reports(record_id)
    _final_merge_locks.pop(record_id, None)
    _running_progress.pop(record_id, None)

    # 更新 Worker 状态为 idle
    workers = await PerfWorker.filter(current_record_id=record_id).all()
    for w in workers:
        w.status = "idle"
        w.current_record_id = None
        await w.save()
