"""性能测试执行编排 API（施压仅在闭源 Runner Worker）。

本模块只负责：创建记录、校验 Worker、下发任务、等待汇总与停止/状态查询。
施压循环、流式读包、并发调度等实现见 runner/perf_worker.py，不得再写回 Backend。
"""
import asyncio
import time
from datetime import datetime
from typing import Optional, List, Any

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query, Body
from pydantic import BaseModel, Field

from app.models.perf import PerfScene, PerfRecord, PerfWorker
from app.models.http import ApiTestCase
from app.models.sys import Environment, Project
from app.core.platform.auth import require_permissions, get_current_username
from app.core.platform.permissions import PERF_SCENE_EXECUTE
from app.core.ops.notification import NotificationService
from app.routers.perf.perf_state import _running_records, _running_progress
from app.routers.perf.progress_utils import normalize_distribution_mode
from app.routers.perf.access import assert_env_in_project, get_record_for_member, get_record_for_viewer, get_scene_for_member
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
from app.modules.perf.perf_target_eval import normalize_perf_targets

router = APIRouter(prefix="/exec", tags=["性能测试执行"])


class StartPerfOptions(BaseModel):
    """启动可选 Body：覆盖场景性能验收目标。"""
    perf_targets: Optional[dict[str, Any]] = Field(
        None, description="本次覆盖的 perf_targets；缺省则用场景 config 快照"
    )


async def snapshot_scene_items_with_case_meta(scene_items: Optional[List[dict]]) -> List[dict]:
    """执行快照：附带 case_name / case_update_time，供报告用例漂移提示。"""
    items = list(scene_items or [])
    if not items:
        return []
    case_ids = []
    for it in items:
        if isinstance(it, dict) and it.get("case_id") is not None:
            try:
                case_ids.append(int(it["case_id"]))
            except (TypeError, ValueError):
                pass
    case_map = {}
    if case_ids:
        cases = await ApiTestCase.filter(id__in=list(set(case_ids))).all()
        case_map = {c.id: c for c in cases}
    out = []
    for it in items:
        row = dict(it) if isinstance(it, dict) else {"case_id": it}
        cid = row.get("case_id")
        try:
            cid_int = int(cid) if cid is not None else None
        except (TypeError, ValueError):
            cid_int = None
        case = case_map.get(cid_int) if cid_int is not None else None
        if case:
            row["case_name"] = case.name
            row["case_update_time"] = (
                case.update_time.strftime("%Y-%m-%d %H:%M:%S") if case.update_time else None
            )
        out.append(row)
    return out


def _estimate_distributed_max_wait(config: dict) -> int:
    """根据场景配置估算分布式压测最长等待时间（秒）。"""
    mode = normalize_perf_mode(config.get("mode", "fixed"))
    concurrent = int(config.get("concurrent_users") or 1)
    ramp_up = int(config.get("ramp_up_seconds") or 0)
    buffer = 600
    stream_timeout = 0
    if use_stream_execution(config):
        stream_timeout = int(normalize_stream_profile(config).get("timeout_seconds") or 600)

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
        # 阶段墙钟 + Ramp + 收尾 grace（流式按单请求超时，默认 600）+ 缓冲
        stage_sum = sum(int(s.get("duration") or 30) for s in steps)
        drain = max(stream_timeout, 120) if stream_timeout else 120
        return stage_sum + ramp_up + drain + buffer
    if is_stream_burst_mode(mode):
        timeout = int(normalize_stream_profile(config).get("timeout_seconds") or 600)
        return timeout + concurrent * 30 + ramp_up + buffer
    if mode == JOURNEY_FIXED_MODE:
        return int(config.get("duration_seconds") or 60) + ramp_up + buffer
    duration = int(config.get("duration_seconds") or 60)
    stream_extra = stream_timeout
    return max(duration, stream_extra) + ramp_up + buffer


async def run_perf_scene(record_id: int, use_workers: bool = True):
    """压测执行主函数：施压一律派发 Runner Worker（不再本机直跑）。
    use_workers 保留签名兼容，实际始终为 True。
    """
    from app.routers.perf.workers import (
        get_active_workers,
        distribute_concurrent,
        send_task_to_worker,
        finalize_distributed_record,
        resolve_worker_selection,
    )
    from app.routers.perf import worker_queue

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

    # 目标 Host 连通性由执行机在施压时验证；平台侧不做 HEAD 预检，
    # 避免「仅执行机能访问 SUT、平台打不到」时误拦启动。

    # CSV 参数化数据
    csv_config = scene.csv_config if scene else {}
    csv_enabled = bool((csv_config or {}).get("enabled"))
    csv_data = scene.csv_data if (scene and csv_enabled) else None
    csv_strategy = csv_config.get("strategy", "round_robin") if csv_enabled else "round_robin"

    config = dict(config)
    config["distribution_mode"] = normalize_distribution_mode(config.get("distribution_mode"))

    # 构建带断言和 api 信息的 scene_items（供 Worker 使用，不修改快照）
    # 每次执行均从 DB 重读用例；须把用例覆盖字段完整下发，避免回落到接口定义旧值
    from app.core.shared.header_merge import merge_request_headers
    from app.modules.http.http_utils import resolve_body_fields

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
                    "body_type": api.body_type,
                    "body_fields": api.body_fields or [],
                }
                merged_headers = merge_request_headers(
                    api_headers=api.headers,
                    case_headers=case.request_headers,
                )
                enriched["merged_headers"] = merged_headers
            # 用例级覆盖：始终下发（含空），由 Worker 按套件同款规则解析
            enriched["request_headers"] = case.request_headers or {}
            enriched["request_params"] = case.request_params or []
            enriched["request_body"] = case.request_body if case.request_body is not None else {}
            enriched["request_body_type"] = (
                case.request_body_type or (api.body_type if api else None) or "json"
            )
            enriched["request_body_fields"] = resolve_body_fields(
                case.request_body_fields,
                (api.body_fields if api else None),
            )
            # 供 Worker 判断：用例是否显式配置了覆盖
            # params：非空列表/字典才整表覆盖；body：只要 DB 非 null（含 {}）即覆盖接口
            enriched["case_params_override"] = bool(case.request_params)
            enriched["case_body_override"] = case.request_body is not None
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

    active_workers = await get_active_workers(scene.project_id, exclude_busy=True)
    if len(active_workers) < 1:
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

    selection = (config.get("_worker_selection") or {}) if isinstance(config, dict) else {}
    sel_ids = selection.get("ids") if isinstance(selection, dict) else None
    sel_weights = selection.get("weights") if isinstance(selection, dict) else None
    weight_map = None
    if isinstance(sel_weights, dict):
        try:
            weight_map = {int(k): int(v) for k, v in sel_weights.items()}
        except (TypeError, ValueError):
            weight_map = None
    try:
        workers, worker_weights = resolve_worker_selection(
            active_workers,
            worker_ids=[int(x) for x in sel_ids] if isinstance(sel_ids, list) and sel_ids else None,
            weight_map=weight_map,
        )
    except ValueError as e:
        record.status = "failed"
        record.ended_at = datetime.now()
        record.error_breakdown = {"stop_reason": str(e)}
        await record.save()
        return

    if len(workers) < 1:
        record.status = "failed"
        record.ended_at = datetime.now()
        record.error_breakdown = {
            "stop_reason": "无可用压测 Worker（所选执行器均不可用）",
        }
        await record.save()
        return

    total_concurrent = config.get("concurrent_users", 1)
    steps = config.get("steps", []) if config.get("mode") == "stepping" else []
    if config.get("mode") == "stepping":
        total_concurrent = max(s.get("users", 1) for s in steps) if steps else 1

    total_capacity = sum(w.max_concurrent for w in workers)
    if total_capacity < total_concurrent:
        record.status = "failed"
        record.ended_at = datetime.now()
        record.error_breakdown = {
            "stop_reason": (
                f"Worker 总容量不足：需要并发 {total_concurrent}，"
                f"当前选中空闲 Worker 总容量 {total_capacity}，请上线更多执行器或降低并发"
            ),
        }
        await record.save()
        return

    assignments = distribute_concurrent(total_concurrent, workers, worker_weights)
    # 给各 Worker 领取与启动留同步窗口，避免派发延迟混入 elapsed/QPS
    sync_start_epoch = time.time() + 3.0
    # 梯度：每个阶段单独按比例分摊，避免各机都跑全局阶段并发
    step_assignments: List[List[int]] = []
    if steps:
        for step in steps:
            step_users = int(step.get("users", 1) or 1)
            step_assignments.append(distribute_concurrent(step_users, workers, worker_weights))

    distribution_info = {
        "is_distributed": True,
        "sync_start_epoch": sync_start_epoch,
        "requested_concurrent": total_concurrent,
        "effective_concurrent": 0,
        "workers": []
    }

    for idx, (worker, assigned) in enumerate(zip(workers, assignments)):
        if assigned <= 0:
            continue
        task_config = dict(config)
        # 内部选择字段不下发到 Worker
        task_config.pop("_worker_selection", None)
        task_config["concurrent_users"] = assigned
        if steps and step_assignments:
            scaled_steps = []
            for si, step in enumerate(steps):
                scaled = dict(step) if isinstance(step, dict) else {"users": 1, "duration": 30}
                scaled["users"] = step_assignments[si][idx] if idx < len(step_assignments[si]) else 0
                scaled_steps.append(scaled)
            task_config["steps"] = scaled_steps
        task = {
            "record_id": record_id,
            "sync_start_epoch": sync_start_epoch,
            "scene_snapshot": {
                "scene_items": scene_items_for_worker,
                "config": task_config,
                "csv_data": csv_data,
                "csv_strategy": csv_strategy,
                "journey": normalize_journey_config(config) if is_journey_mode(mode) else None,
            },
            "assigned_concurrent": assigned,
            "worker_index": idx,
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
                "host": worker.host,
                "weight": worker_weights[idx] if idx < len(worker_weights) else None,
            })
            distribution_info["effective_concurrent"] += assigned

    if not distribution_info["workers"]:
        record.status = "failed"
        record.ended_at = datetime.now()
        record.error_breakdown = {
            "stop_reason": "下发压测任务到 Worker 失败（无空闲 Worker 或任务队列占用），请检查执行器在线状态后重试",
        }
        await record.save()
        return

    # 部分下发成功但未达到请求并发：回滚已派发任务，避免低负载误跑并污染基线对比
    if distribution_info["effective_concurrent"] < total_concurrent:
        for item in distribution_info["workers"]:
            wid = item.get("worker_id")
            if wid is None:
                continue
            await worker_queue.clear_task(wid)
            w = await PerfWorker.get_or_none(id=wid)
            if w:
                w.status = "idle"
                w.current_record_id = None
                await w.save()
        record.status = "failed"
        record.ended_at = datetime.now()
        record.distribution_info = distribution_info
        record.error_breakdown = {
            "stop_reason": (
                f"Worker 任务下发不完整：请求并发 {total_concurrent}，"
                f"实际仅下发 {distribution_info['effective_concurrent']}，已取消本次执行"
            ),
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
    stop_seen_at: Optional[int] = None
    # 手动/错误率停止后，再等一段时间收齐各 Worker 最终报告，避免过早 finalize
    stop_grace_seconds = 90
    while waited < max_duration:
        await asyncio.sleep(1)
        waited += 1
        fresh = await PerfRecord.get_or_none(id=record_id)
        bd = fresh.error_breakdown if fresh and isinstance(fresh.error_breakdown, dict) else {}
        finals = int(bd.get("_worker_final_count") or 0)
        if finals >= expected_final_reports:
            break
        if fresh and fresh.status == "stopped":
            if stop_seen_at is None:
                stop_seen_at = waited
            if waited - stop_seen_at >= stop_grace_seconds:
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
                     ai_analyze: Optional[bool] = Query(None, description="执行完成后是否 AI 分析"),
                     worker_ids: Optional[List[int]] = Query(
                         None, description="选用的压测执行器 ID 列表；缺省为全部空闲在线"
                     ),
                     worker_weights: Optional[str] = Query(
                         None,
                         description='分压权重 JSON，如 {"12":2,"15":1}；缺省按各机 max_concurrent',
                     ),
                     options: Optional[StartPerfOptions] = Body(None),
                     scene: PerfScene = Depends(get_scene_for_member),
                     username: str = Depends(get_current_username)):
    """启动性能测试（施压一律派发 Runner Worker；use_workers 查询参数已忽略）。"""
    _ = use_workers
    _ = scene_id
    env = await assert_env_in_project(env_id, scene.project_id)

    from app.routers.perf.workers import (
        get_active_workers,
        parse_worker_weights_json,
        resolve_worker_selection,
    )
    from app.modules.ai.ai_project_settings import resolve_perf_ai_for_run

    active = await get_active_workers(scene.project_id, exclude_busy=True)
    if not active:
        raise HTTPException(
            status_code=503,
            detail="无可用压测 Worker，请安装并上线执行器后再启动压测（后端不再本机直跑施压）",
        )

    try:
        weight_map = parse_worker_weights_json(worker_weights)
        selected, weights = resolve_worker_selection(
            active,
            worker_ids=worker_ids,
            weight_map=weight_map or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    config = scene.config or {}
    needed = int(config.get("concurrent_users", 1) or 1)
    if config.get("mode") == "stepping":
        steps = config.get("steps") or []
        needed = max((int(s.get("users", 1) or 1) for s in steps), default=1)
    capacity = sum(w.max_concurrent for w in selected)
    if capacity < needed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Worker 总容量不足：场景需要并发 {needed}，"
                f"当前选中空闲 Worker 总容量 {capacity}。请勾选更多执行器或降低并发后再启动。"
            ),
        )

    config = dict(config)
    config["env_id"] = env_id
    config["request_detail_level"] = (
        "full" if request_detail_level == "full" else "brief"
    )
    config["ai_analyze_on_complete"] = await resolve_perf_ai_for_run(
        scene.project_id, user_override=ai_analyze
    )
    # 手工启动：落库勾选与权重，供后台 run_perf_scene 过滤；定时任务不写则仍用全部空闲
    if worker_ids is not None:
        config["_worker_selection"] = {
            "ids": [int(w.id) for w in selected],
            "weights": {str(int(w.id)): int(weights[i]) for i, w in enumerate(selected)},
        }

    # 性能验收目标：Body 覆盖 > 场景 config；写入快照后报告只读 snapshot
    if options is not None and options.perf_targets is not None:
        config["perf_targets"] = normalize_perf_targets(options.perf_targets)
    elif config.get("perf_targets") is not None:
        config["perf_targets"] = normalize_perf_targets(config.get("perf_targets"))

    record = await PerfRecord.create(
        scene_id=scene.id,
        project_id=scene.project_id,
        status="pending",
        trigger_type="manual",
        config_snapshot=config,
        scene_items_snapshot=await snapshot_scene_items_with_case_meta(scene.scene_items or []),
        run_by=username
    )

    # use_workers 参数保留兼容，实际始终走 Worker
    background_tasks.add_task(run_perf_scene, record.id, True)

    return {
        "record_id": record.id,
        "status": "pending",
        "message": "性能测试已启动",
        "capacity": capacity,
        "requested_concurrent": needed,
        "selected_workers": len(selected),
    }


@router.post(
    "/{record_id}/stop",
    summary="停止性能测试",
    dependencies=[Depends(require_permissions(PERF_SCENE_EXECUTE))],
)
async def stop_perf(record: PerfRecord = Depends(get_record_for_member)):
    """停止性能测试"""
    if record.status != "running":
        raise HTTPException(status_code=400, detail="当前任务未在执行中")

    stop_event = _running_records.get(record.id)
    if stop_event:
        stop_event.set()

    if not isinstance(record.error_breakdown, dict):
        record.error_breakdown = {}
    record.error_breakdown["stop_reason"] = "用户手动停止"
    record.status = "stopped"
    record.ended_at = datetime.now()
    await record.save()

    # BackgroundTasks 等待丢失时，停止仍尽量汇总已有最终报告/秒级数据
    try:
        from app.routers.perf.workers import finalize_distributed_record
        await finalize_distributed_record(record.id)
    except Exception:
        pass

    return {"message": "停止信号已发送"}


@router.get("/{record_id}/status", summary="查询执行状态")
async def get_status(record: PerfRecord = Depends(get_record_for_viewer)):
    """查询性能测试执行状态（用于前端轮询）"""
    if record.status == "running":
        from app.routers.perf.workers import maybe_finalize_stuck_running_record
        try:
            healed = await maybe_finalize_stuck_running_record(record)
            if healed:
                record = await PerfRecord.get(id=record.id)
        except Exception:
            pass

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
        "progress": _running_progress.get(record.id)
    }


