"""性能测试执行编排 API（施压仅在闭源 Runner Worker）。

本模块只负责：创建记录、校验 Worker、下发任务、等待汇总与停止/状态查询。
施压循环、流式读包、并发调度等实现见 Runner 压测 Worker，不得再写回 Backend。
"""
import asyncio
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks

from app.models.perf import PerfScene, PerfRecord
from app.models.http import ApiTestCase
from app.models.sys import Environment, Project
from app.core.platform.auth import require_permissions, get_current_username
from app.core.platform.permissions import PERF_SCENE_EXECUTE
from app.core.ops.notification import NotificationService
from app.routers.perf.perf_state import _running_records, _running_progress
from app.routers.perf.progress_utils import normalize_distribution_mode
from app.modules.stream_phase import (
    normalize_perf_mode,
    is_stream_burst_mode,
    use_stream_execution,
    normalize_stream_profile,
)
from app.modules.perf.perf_journey import (
    JOURNEY_FIXED_MODE,
    JOURNEY_LOOP_MODE,
    is_journey_mode,
    normalize_journey_config,
    collect_journey_case_ids,
    journey_to_scene_items,
    journey_has_sync_barrier,
)

router = APIRouter(prefix="/exec", tags=["性能测试执行"])


def _estimate_distributed_max_wait(config: dict) -> int:
    """根据场景配置估算分布式压测最长等待时间（秒）。"""
    mode = normalize_perf_mode(config.get("mode", "fixed"))
    concurrent = int(config.get("concurrent_users") or 1)
    ramp_up = int(config.get("ramp_up_seconds") or 0)
    buffer = 600

    if mode in ("loop", JOURNEY_LOOP_MODE):
        loop_count = int(config.get("loop_count") or 100)
        per_iter = 10
        if use_stream_execution(config):
            per_iter = max(
                per_iter,
                int(normalize_stream_profile(config).get("timeout_seconds") or 600),
            )
        if mode == JOURNEY_LOOP_MODE:
            journey = normalize_journey_config(config)
            step_count = sum(len(p.get("steps") or []) for p in journey.get("phases") or [])
            per_iter = max(per_iter, step_count * 30)
        return min(86400, max(3600, loop_count * per_iter + ramp_up + buffer))
    if mode == "stepping":
        steps = config.get("steps") or []
        return sum(int(s.get("duration") or 30) for s in steps) + ramp_up + buffer
    if is_stream_burst_mode(mode):
        timeout = int(normalize_stream_profile(config).get("timeout_seconds") or 600)
        return timeout + concurrent * 30 + ramp_up + buffer
    if mode == JOURNEY_FIXED_MODE:
        return int(config.get("duration_seconds") or 60) + ramp_up + buffer
    duration = int(config.get("duration_seconds") or 60)
    stream_extra = 0
    if use_stream_execution(config):
        stream_extra = int(normalize_stream_profile(config).get("timeout_seconds") or 600)
    return max(duration, stream_extra) + ramp_up + buffer


async def run_perf_scene(record_id: int, use_workers: bool = True):
    """压测执行主函数：施压一律派发 Runner Worker（不再本机直跑）。
    use_workers 保留签名兼容，实际始终为 True。
    """
    from app.routers.perf.workers import get_active_workers, distribute_concurrent, send_task_to_worker, finalize_distributed_record

    record = await PerfRecord.get_or_none(id=record_id)
    if not record:
        return

    scene = await record.scene
    if not scene:
        record.status = "failed"
        await record.save()
        return

    config = record.config_snapshot
    scene_items = record.scene_items_snapshot
    mode = normalize_perf_mode(config.get("mode", "fixed"))

    if is_journey_mode(mode):
        scene_items = scene_items or journey_to_scene_items(config)

    env_id = config.get("env_id")
    env = await Environment.get_or_none(id=env_id, is_del=False) if env_id else None
    if not env:
        record.status = "failed"
        await record.save()
        return

    from app.modules.data_tools.tag_service import merge_execution_variables
    from app.modules.data_tools.inline_tools import ensure_dt_cache

    project = await Project.get_or_none(id=scene.project_id, is_del=False)
    project_global_vars = (project.global_vars or {}) if project else {}
    merged_variables = ensure_dt_cache(await merge_execution_variables(scene.project_id, env.id))

    # 预加载用例（含关联接口，避免每次请求查DB）
    if is_journey_mode(mode):
        case_ids = collect_journey_case_ids(config)
    else:
        case_ids = [item["case_id"] for item in scene_items]
    cases = await ApiTestCase.filter(id__in=case_ids, is_del=False).prefetch_related("api").all()
    case_map = {c.id: c for c in cases}

    missing = set(case_ids) - set(case_map.keys())
    if missing:
        scene_items = [item for item in scene_items if item["case_id"] in case_map]

    if not scene_items:
        record.status = "failed"
        await record.save()
        return

    target_host = config.get("target_host")

    # 压测前目标 Host 连通性检查
    check_url = target_host or env.host
    if check_url:
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=True) as check_client:
                await check_client.head(check_url)
        except httpx.ConnectError:
            record.status = "failed"
            record.ended_at = datetime.now()
            record.error_breakdown = {"stop_reason": f"目标Host不可达: {check_url}"}
            await record.save()
            return
        except httpx.TimeoutException:
            record.status = "failed"
            record.ended_at = datetime.now()
            record.error_breakdown = {"stop_reason": f"目标Host连接超时: {check_url}"}
            await record.save()
            return
        except Exception:
            # 其他异常（如 HEAD 不被支持）不阻断，继续执行
            pass

    # CSV 参数化数据
    csv_config = scene.csv_config if scene else {}
    csv_enabled = bool((csv_config or {}).get("enabled"))
    csv_data = scene.csv_data if (scene and csv_enabled) else None
    csv_strategy = csv_config.get("strategy", "round_robin") if csv_enabled else "round_robin"

    config = dict(config)
    config["distribution_mode"] = normalize_distribution_mode(config.get("distribution_mode"))

    # 构建带断言和 api 信息的 scene_items（供 Worker 使用，不修改快照）
    from app.core.shared.header_merge import merge_request_headers

    scene_items_for_worker = []
    for item in scene_items:
        case = case_map.get(item["case_id"])
        enriched = dict(item)
        if case:
            enriched["name"] = case.name or ""
            enriched["assertions"] = case.assertions or []
            enriched["extractors"] = case.extractors or []
            enriched["timeout"] = case.timeout or 30
            api = case.api
            if api:
                enriched["api"] = {
                    "id": api.id,
                    "name": api.name,
                    "method": api.method,
                    "path": api.path,
                    "base_url": api.base_url,
                    "headers": api.headers,
                    "params": api.params,
                    "body": api.body,
                    "body_type": api.body_type
                }
                merged_headers = merge_request_headers(
                    api_headers=api.headers,
                    case_headers=case.request_headers,
                )
                enriched["merged_headers"] = merged_headers
            # 用例级别覆盖
            if case.request_headers:
                enriched["request_headers"] = case.request_headers
            if case.request_params:
                enriched["request_params"] = case.request_params
            if case.request_body:
                enriched["request_body"] = case.request_body
        scene_items_for_worker.append(enriched)

    # 施压一律走 Runner Worker（Backend 不再本机直跑施压引擎）
    use_workers = True
    if is_journey_mode(mode) and journey_has_sync_barrier(config):
        record.status = "failed"
        record.ended_at = datetime.now()
        record.error_breakdown = {
            "stop_reason": "压测 Worker 不支持 journey 阶段 sync_before 屏障，请关闭阶段同步后重试",
        }
        await record.save()
        return

    workers = await get_active_workers(scene.project_id)
    if len(workers) < 1:
        record.status = "failed"
        record.ended_at = datetime.now()
        record.error_breakdown = {
            "stop_reason": (
                "无可用压测 Worker：请安装并上线 BrickCoreRunner / 压测执行器后重试。"
                "后端已不再支持本机直跑施压。"
            ),
        }
        await record.save()
        return

    total_concurrent = config.get("concurrent_users", 1)
    if config.get("mode") == "stepping":
        steps = config.get("steps", [])
        total_concurrent = max(s.get("users", 1) for s in steps) if steps else 1

    assignments = distribute_concurrent(total_concurrent, workers)
    distribution_info = {
        "is_distributed": True,
        "workers": []
    }

    for worker, assigned in zip(workers, assignments):
        if assigned <= 0:
            continue
        task_config = dict(config)
        task_config["concurrent_users"] = assigned
        task = {
            "record_id": record_id,
            "scene_snapshot": {
                "scene_items": scene_items_for_worker,
                "config": task_config,
                "csv_data": csv_data,
                "csv_strategy": csv_strategy,
                "journey": normalize_journey_config(config) if is_journey_mode(mode) else None,
            },
            "assigned_concurrent": assigned,
            "worker_index": workers.index(worker),
            "total_workers": len(workers),
            "env_host": env.host,
            "target_host": target_host,
            "project_global_vars": project_global_vars,
            "env_global_vars": env.global_vars or {},
            "merged_variables": merged_variables,
        }
        success = await send_task_to_worker(worker, task)
        if success:
            worker.status = "busy"
            worker.current_record_id = record_id
            await worker.save()
            distribution_info["workers"].append({
                "worker_id": worker.id,
                "assigned_concurrent": assigned,
                "host": worker.host
            })

    if not distribution_info["workers"]:
        record.status = "failed"
        record.ended_at = datetime.now()
        record.error_breakdown = {
            "stop_reason": "下发压测任务到 Worker 失败，请检查执行器在线状态后重试",
        }
        await record.save()
        return

    record.distribution_info = distribution_info
    record.status = "running"
    record.started_at = datetime.now()
    await record.save()
    # 等待 Worker 执行完成：以收到最终报告为准，不能仅看 current_record_id（重连注册会误清）
    expected_final_reports = len(distribution_info["workers"])
    max_duration = _estimate_distributed_max_wait(config)
    waited = 0
    while waited < max_duration:
        await asyncio.sleep(1)
        waited += 1
        fresh = await PerfRecord.get_or_none(id=record_id)
        bd = fresh.error_breakdown if fresh and isinstance(fresh.error_breakdown, dict) else {}
        finals = int(bd.get("_worker_final_count") or 0)
        if finals >= expected_final_reports:
            break
        if fresh and fresh.status == "stopped":
            break
    await finalize_distributed_record(record_id)
    _running_records.pop(record_id, None)
    _running_progress.pop(record_id, None)
    await NotificationService.maybe_auto_push_perf_report(record_id)


@router.post("/{scene_id}", summary="启动性能测试",
             dependencies=[Depends(require_permissions(PERF_SCENE_EXECUTE))])
async def start_perf(scene_id: int, env_id: int, background_tasks: BackgroundTasks,
                     use_workers: bool = True,
                     request_detail_level: str = "brief",
                     username: str = Depends(get_current_username)):
    """启动性能测试（施压一律派发 Runner Worker；use_workers 查询参数已忽略）。"""
    _ = use_workers
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")

    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")

    from app.routers.perf.workers import get_active_workers

    active = await get_active_workers(scene.project_id)
    if not active:
        raise HTTPException(
            status_code=503,
            detail="无可用压测 Worker，请安装并上线执行器后再启动压测（后端不再本机直跑施压）",
        )

    config = scene.config or {}
    config["env_id"] = env_id
    config["request_detail_level"] = (
        "full" if request_detail_level == "full" else "brief"
    )

    record = await PerfRecord.create(
        scene_id=scene_id,
        project_id=scene.project_id,
        status="pending",
        trigger_type="manual",
        config_snapshot=config,
        scene_items_snapshot=scene.scene_items or [],
        run_by=username
    )

    # use_workers 参数保留兼容，实际始终走 Worker
    background_tasks.add_task(run_perf_scene, record.id, True)

    return {
        "record_id": record.id,
        "status": "pending",
        "message": "性能测试已启动"
    }


@router.post("/{record_id}/stop", summary="停止性能测试")
async def stop_perf(record_id: int):
    """停止性能测试"""
    record = await PerfRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    if record.status != "running":
        raise HTTPException(status_code=400, detail="当前任务未在执行中")

    stop_event = _running_records.get(record_id)
    if stop_event:
        stop_event.set()

    if not isinstance(record.error_breakdown, dict):
        record.error_breakdown = {}
    record.error_breakdown["stop_reason"] = "用户手动停止"
    record.status = "stopped"
    record.ended_at = datetime.now()
    await record.save()

    return {"message": "停止信号已发送"}


@router.get("/{record_id}/status", summary="查询执行状态")
async def get_status(record_id: int):
    """查询性能测试执行状态（用于前端轮询）"""
    record = await PerfRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    time_series = record.time_series_data or []
    config = record.config_snapshot or {}
    error_breakdown = record.error_breakdown or {}

    return {
        "record_id": record.id,
        "status": record.status,
        "total_requests": record.total_requests,
        "success_count": record.success_count,
        "fail_count": record.fail_count,
        "qps": record.qps,
        "avg_response_time": record.avg_response_time,
        "error_rate": record.error_rate,
        "duration": record.duration,
        "time_series": time_series,
        "latest_point": time_series[-1] if time_series else None,
        "error_rate_threshold": config.get("error_rate_threshold", 0),
        "stop_reason": error_breakdown.get("stop_reason") if isinstance(error_breakdown, dict) else None,
        "progress": _running_progress.get(record_id)
    }
