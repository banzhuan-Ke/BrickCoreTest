"""性能测试 Worker 节点管理"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.models.perf import PerfWorker, PerfRecord

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


class WorkerReportData(BaseModel):
    worker_id: int
    token: str
    timestamp: int  # 秒级时间戳
    qps: float = 0
    avg_rt: float = 0
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


# ========== 内存中的分布式聚合数据 ==========
# {record_id: {worker_id: [秒级数据点列表]}}
_worker_reports: dict = {}

# 任务队列: {worker_id: task_dict}
_task_queue: dict = {}
# 任务事件: {worker_id: asyncio.Event}
_task_events: dict = {}


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
        existing.name = req.name
        existing.port = req.port or 0
        existing.max_concurrent = req.max_concurrent
        existing.status = "idle"
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
    reports = _get_worker_reports(record_id)
    if data.worker_id not in reports:
        reports[data.worker_id] = []
    reports[data.worker_id].append(data.dict())
    return {"message": "上报成功"}


@public_router.post("/{record_id}/final", summary="接收 Worker 最终报告")
async def receive_worker_final_report(record_id: int, data: WorkerFinalReport):
    """Worker 执行完成后上报最终报告"""
    worker = await PerfWorker.get_or_none(id=data.worker_id)
    if not worker or worker.token != data.token:
        raise HTTPException(status_code=403, detail="Token 无效")
    record = await PerfRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    if not isinstance(record.error_breakdown, dict):
        record.error_breakdown = {}

    # 累加到已有数据（支持多 Worker 累加）
    record.total_requests += data.total_requests
    record.success_count += data.success_count
    record.fail_count += data.fail_count

    # 记录最大执行时长（QPS 在 finalize 时按 total_requests/duration 统一计算）
    record.duration = max(record.duration or 0, data.duration)

    if record.total_requests > 0:
        record.error_rate = round(record.fail_count / record.total_requests * 100, 2)

    # 累加流量字节（finalize 时统一换算 KB/s）
    if isinstance(record.error_breakdown, dict):
        record.error_breakdown["_total_bytes_received"] = (
            record.error_breakdown.get("_total_bytes_received", 0) + data.total_bytes_received
        )
        record.error_breakdown["_total_bytes_sent"] = (
            record.error_breakdown.get("_total_bytes_sent", 0) + data.total_bytes_sent
        )

    # 保存 Worker RT 统计用于最终聚合（从真实样本计算，比秒级反推准确）
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
        "std_dev": data.std_dev_response_time
    })

    # 合并错误分类（兼容新的统一格式）
    existing_errors = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
    new_errors = data.error_breakdown or {}

    # 合并全量状态码分布
    for key, val in (new_errors.get("status_code_distribution") or {}).items():
        existing_errors.setdefault("status_code_distribution", {})[key] = (
            existing_errors.get("status_code_distribution", {}).get(key, 0) + val
        )

    # 合并直方图
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

    # by_status_code
    for key, val in (new_errors.get("by_status_code") or {}).items():
        existing_errors.setdefault("by_status_code", {})[key] = existing_errors.get("by_status_code", {}).get(key, 0) + val
    # by_type
    for key, val in (new_errors.get("by_type") or {}).items():
        existing_errors.setdefault("by_type", {})[key] = existing_errors.get("by_type", {}).get(key, 0) + val
    # failed_samples
    new_samples = (new_errors.get("failed_samples") or [])
    if new_samples:
        existing_samples = existing_errors.get("failed_samples", [])
        existing_samples.extend(new_samples)
        existing_errors["failed_samples"] = existing_samples[:50]
    # 兼容旧版扁平格式（直接累加）
    for key, val in new_errors.items():
        if key in (
            "by_status_code", "by_type", "failed_samples",
            "status_code_distribution", "rt_histogram",
        ):
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

    # 合并接口维度聚合
    import numpy as np
    existing_cases = record.case_aggregations or {}
    new_cases = data.case_aggregations or {}
    for case_id, new_agg in new_cases.items():
        if case_id not in existing_cases:
            existing_cases[case_id] = new_agg
        else:
            old = existing_cases[case_id]
            old["total"] = old.get("total", 0) + new_agg.get("total", 0)
            old["success"] = old.get("success", 0) + new_agg.get("success", 0)
            old["fail"] = old.get("fail", 0) + new_agg.get("fail", 0)
            # 合并 RT 数据并重新计算聚合指标
            old_rts = []
            # 尝试从 old 的各百分位字段反推近似样本（兜底）
            if "rts" in old:
                old_rts = old.pop("rts")
            elif old.get("avg_rt"):
                old_rts = [old.get("avg_rt", 0)] * old.get("total", 0)
            new_rts = new_agg.get("rts", [])
            if not new_rts and new_agg.get("avg_rt"):
                new_rts = [new_agg.get("avg_rt", 0)] * new_agg.get("total", 0)
            merged_rts = old_rts + new_rts
            if merged_rts:
                old["avg_rt"] = round(sum(merged_rts) / len(merged_rts), 2)
                old["min_rt"] = round(min(merged_rts), 2)
                old["max_rt"] = round(max(merged_rts), 2)
                old["median_rt"] = round(float(np.median(merged_rts)), 2)
                old["p90_rt"] = round(float(np.percentile(merged_rts, 90)), 2)
                old["p95_rt"] = round(float(np.percentile(merged_rts, 95)), 2)
                old["p99_rt"] = round(float(np.percentile(merged_rts, 99)), 2)
                old["std_dev"] = round(float(np.std(merged_rts)), 2)
            old["error_rate"] = round(old["fail"] / old["total"] * 100, 2) if old["total"] > 0 else 0
    record.case_aggregations = existing_cases

    # 时序以秒级上报内存聚合为准；仅在没有秒级上报时用最终报告中的时序兜底
    if data.time_series_data and not _get_worker_reports(record_id):
        record.time_series_data = data.time_series_data

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
        if t <= 0 or not agg.get("avg_rt"):
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
                    "_error_count": 0
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
            m["_error_count"] += int(dp.get("error_rate", 0) * sec_req / 100) if sec_req > 0 else 0

    # 计算错误率
    for m in merged.values():
        total = m["total_req"]
        m["error_rate"] = round(m["_error_count"] / total * 100, 2) if total > 0 else 0
        if m.get("_p95_weight", 0) <= 0 and m.get("avg_rt"):
            m["p95_rt"] = m["avg_rt"]
        m.pop("_rt_weight", None)
        m.pop("_p95_weight", None)
        m.pop("_error_count", None)

    # 按时间戳排序
    return sorted(merged.values(), key=lambda x: x["timestamp"])


async def finalize_distributed_record(record_id: int):
    """分布式执行完成后，汇总所有 Worker 数据生成最终报告"""
    record = await PerfRecord.get_or_none(id=record_id)
    if not record:
        return

    # 合并时序数据
    merged_ts = await merge_worker_time_series(record_id)

    # 如果秒级上报为空，回退到最终报告中已合并的 time_series_data
    if not merged_ts and record.time_series_data:
        merged_ts = record.time_series_data

    record.time_series_data = merged_ts

    # 从 Worker 累加的 RT 统计计算最终整体指标（比秒级反推准确）
    rt_stats = (record.error_breakdown or {}).get("_worker_rt_stats", [])
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
        # 清理临时数据
        if isinstance(record.error_breakdown, dict):
            record.error_breakdown.pop("_worker_rt_stats", None)

    # 请求数以 Worker 最终报告为准；仅未收到最终报告时用秒级时序回填
    if merged_ts and (record.total_requests or 0) == 0:
        record.total_requests = sum(ts["total_req"] for ts in merged_ts)
        record.success_count = sum(ts["success"] for ts in merged_ts)
        record.fail_count = sum(ts["fail"] for ts in merged_ts)

    if not record.duration and merged_ts:
        record.duration = max(ts["timestamp"] for ts in merged_ts) + 1

    _reconcile_request_counts(record)

    dur = record.duration or 0
    total_req = record.total_requests or 0
    if dur > 0 and total_req > 0:
        record.qps = round(total_req / dur, 2)

    if not (record.avg_response_time or 0):
        _recompute_rt_from_case_aggregations(record)

    # 状态判定：有失败即 failed（和本地执行保持一致）
    if record.error_rate and record.error_rate > 0:
        record.status = "failed"
    else:
        record.status = "success"

    # 流量：按累计字节与总时长计算 KB/s
    bd = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
    total_recv = bd.pop("_total_bytes_received", 0)
    total_sent = bd.pop("_total_bytes_sent", 0)
    dur = record.duration or 0
    if dur > 0:
        record.received_kb_per_sec = round(total_recv / 1024 / dur, 2)
        record.sent_kb_per_sec = round(total_sent / 1024 / dur, 2)
    record.error_breakdown = bd

    record.ended_at = datetime.now()
    await record.save()

    # 清理内存数据
    _clear_worker_reports(record_id)

    # 更新 Worker 状态为 idle
    workers = await PerfWorker.filter(current_record_id=record_id).all()
    for w in workers:
        w.status = "idle"
        w.current_record_id = None
        await w.save()
