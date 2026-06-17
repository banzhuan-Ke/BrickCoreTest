"""性能测试执行引擎 API"""
import asyncio
import itertools
import random
import time
from collections import deque, defaultdict
from datetime import datetime
from typing import Dict, Optional, List

import httpx
import numpy as np
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks

from app.models.perf import PerfScene, PerfRecord, PerfWorker
from app.models.http import ApiTestCase
from app.models.sys import Environment, Project
from app.core.auth import require_permissions, get_current_username
from app.core.permissions import PERF_SCENE_EXECUTE
from app.core.notification import NotificationService
from app.routers.http.utils import (
    replace_variables_with_detail,
    evaluate_assertion,
    build_api_url,
    prepare_httpx_headers,
    extract_variables,
)
from app.core.variable_resolver import VariableResolver
from app.routers.perf.report_utils import build_rt_histogram
from app.routers.perf.perf_state import _running_records, _running_progress
from app.routers.perf.progress_utils import normalize_distribution_mode
from app.core.stream_phase.engine import is_stream_queue_result
from app.core.stream_phase import (
    aggregate_phase_metrics,
    execute_stream_request,
    stream_result_to_perf_queue_item,
    extract_stream_detail,
    normalize_perf_mode,
    is_stream_burst_mode,
    use_stream_execution,
    normalize_stream_profile,
    has_stream_profile_config,
    STREAM_BURST_MODE,
)
from app.core.perf_journey import (
    JOURNEY_FIXED_MODE,
    JOURNEY_LOOP_MODE,
    is_journey_mode,
    normalize_journey_config,
    collect_journey_case_ids,
    journey_to_scene_items,
    journey_has_sync_barrier,
    PhaseSyncCoordinator,
    JourneyStatsCollector,
    run_one_journey,
)
from app.core.perf_trace import (
    attach_trace_meta,
    build_trace_meta,
    collect_result_diagnostics,
    normalize_detail_level,
    append_request_detail,
)

router = APIRouter(prefix="/exec", tags=["性能测试执行"])

ERROR_RATE_AUTO_STOP_MSG = "错误率连续3秒超过阈值，已自动停止"

# 全局运行中任务管理: {record_id: asyncio.Event}（见 perf_state.py）

# CSV 参数化行指针（round_robin 用 record_id，unique 用 record_id_u{worker_index}）
_csv_row_pointers: Dict[int | str, int] = {}


def _clear_csv_row_pointers(record_id: int) -> None:
    prefix = f"{record_id}"
    for key in list(_csv_row_pointers.keys()):
        key_str = str(key)
        if key_str == prefix or key_str.startswith(f"{prefix}_"):
            _csv_row_pointers.pop(key, None)


def _replace_csv_vars(data, csv_row: dict):
    """递归替换 ${{csv.column_name}} / {{csv.column_name}} 为 CSV 值"""
    if not csv_row:
        return data
    if isinstance(data, dict):
        return {k: _replace_csv_vars(v, csv_row) for k, v in data.items()}
    if isinstance(data, list):
        return [_replace_csv_vars(item, csv_row) for item in data]
    if isinstance(data, str):
        import re
        def replacer(m):
            key = (m.group(1) or m.group(2) or "").strip()
            return str(csv_row.get(key, m.group(0)))
        return re.sub(
            r'\$\{\{\s*csv\.([^}]+)\s*\}\}|\{\{\s*csv\.([^}]+)\s*\}\}',
            replacer,
            data,
        )
    return data


def get_next_csv_row(
    record_id: int,
    csv_data: list,
    strategy: str,
    worker_index: int = 0,
    total_workers: int = 1,
) -> Optional[dict]:
    """获取下一行 CSV 数据。

    round_robin: 全局顺序取行；分布式下按 worker_index 条带分配，避免各节点重复同一行。
    random: 每次请求随机取一行。
    unique: 按 worker_index 分区取行（分布式下每节点独占一段，不与其他 Worker 重复）。
    """
    if not csv_data:
        return None
    row_count = len(csv_data)
    tw = max(1, int(total_workers or 1))

    if strategy == "round_robin":
        ptr = _csv_row_pointers.get(record_id, 0)
        if tw > 1:
            global_idx = worker_index + ptr * tw
            row = csv_data[global_idx % row_count]
        else:
            row = csv_data[ptr % row_count]
        _csv_row_pointers[record_id] = ptr + 1
        return row

    elif strategy == "unique":
        ptr_key = f"{record_id}_u{worker_index}"
        ptr = _csv_row_pointers.get(ptr_key, 0)
        if tw > 1:
            segment_size = max(1, row_count // tw)
            start = worker_index * segment_size
            row_idx = min(start + (ptr % segment_size), row_count - 1)
        else:
            row_idx = ptr % row_count
        _csv_row_pointers[ptr_key] = ptr + 1
        return csv_data[row_idx]

    elif strategy == "random":
        return random.choice(csv_data)

    return None


class StreamingStats:
    """流式统计：Welford算法维护均值/方差/最值，Reservoir Sampling维护百分位样本"""

    def __init__(self, max_samples: int = 10000):
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0  # 用于方差计算
        self.min_val = float('inf')
        self.max_val = float('-inf')
        self.samples = []
        self.max_samples = max_samples

    def add(self, value: float):
        """添加一个响应时间样本"""
        if value <= 0:
            return
        self.count += 1
        # Welford's online algorithm
        delta = value - self.mean
        self.mean += delta / self.count
        delta2 = value - self.mean
        self.m2 += delta * delta2
        # Min/Max
        if value < self.min_val:
            self.min_val = value
        if value > self.max_val:
            self.max_val = value
        # Reservoir Sampling
        if len(self.samples) < self.max_samples:
            self.samples.append(value)
        else:
            j = random.randint(0, self.count - 1)
            if j < self.max_samples:
                self.samples[j] = value

    def get_mean(self) -> float:
        return self.mean if self.count > 0 else 0.0

    def get_variance(self) -> float:
        return self.m2 / self.count if self.count > 1 else 0.0

    def get_std_dev(self) -> float:
        import math
        return math.sqrt(self.get_variance()) if self.count > 1 else 0.0

    def get_min(self) -> float:
        return self.min_val if self.count > 0 else 0.0

    def get_max(self) -> float:
        return self.max_val if self.count > 0 else 0.0

    def get_percentile(self, p: float) -> float:
        if not self.samples:
            return 0.0
        return float(np.percentile(self.samples, p))

    def is_empty(self) -> bool:
        return self.count == 0


# ========== 请求构建与执行 ==========

async def build_perf_request(
    case: ApiTestCase,
    env: Environment,
    target_host: Optional[str] = None,
    csv_row: Optional[dict] = None,
    session_variables: Optional[dict] = None,
):
    """
    构建性能测试请求参数（复用现有逻辑，不写数据库）
    返回: (method, url, headers, params, body, timeout, body_type)
    """
    api = case.api
    if not api:
        raise ValueError(f"用例 {case.id} 关联接口不存在")

    from app.core.data_tools.tag_service import merge_execution_variables
    from app.core.data_tools.inline_tools import ensure_dt_cache

    all_variables = ensure_dt_cache(await merge_execution_variables(case.project_id, env.id))
    if session_variables:
        from app.core.global_vars_validate import flatten_global_vars
        all_variables = {**all_variables, **flatten_global_vars(session_variables)}

    from app.core.header_merge import merge_request_headers

    headers = merge_request_headers(
        api_headers=api.headers,
        case_headers=case.request_headers,
    )
    
    api_params = api.params or []
    if isinstance(api_params, dict):
        api_params = [{"name": k, "value": v} for k, v in api_params.items()]
    
    case_params = case.request_params or []
    if isinstance(case_params, dict):
        case_params = [{"name": k, "value": v} for k, v in case_params.items()]
    
    base_url = headers.pop("base_url", None) if isinstance(headers, dict) else None
    if not base_url and isinstance(case.request_headers, dict):
        base_url = case.request_headers.get("base_url")
    base_url = target_host or base_url or api.base_url or env.host
    try:
        url = build_api_url(base_url, api.path)
    except ValueError as e:
        raise ValueError(f"请求构建失败: {str(e)}")
    
    headers = headers if isinstance(headers, dict) else {}
    params = {p.get("name", ""): p.get("value", "") for p in api_params if p.get("name")}
    for p in case_params:
        if p.get("name"):
            params[p["name"]] = p.get("value", "")
    
    body = case.request_body if case.request_body else (api.body or {})
    
    # 环境变量替换
    var_resolver = VariableResolver(all_variables)
    url, _ = replace_variables_with_detail(url, all_variables, "url", resolver=var_resolver)
    headers, _ = replace_variables_with_detail(headers, all_variables, "headers", resolver=var_resolver)
    params, _ = replace_variables_with_detail(params, all_variables, "params", resolver=var_resolver)
    body, _ = replace_variables_with_detail(body, all_variables, "body", resolver=var_resolver)
    
    # CSV 变量替换
    if csv_row:
        url = _replace_csv_vars(url, csv_row)
        headers = _replace_csv_vars(headers, csv_row)
        params = _replace_csv_vars(params, csv_row)
        body = _replace_csv_vars(body, csv_row)
    
    safe_headers = headers if isinstance(headers, dict) else {}
    
    return api.method.upper(), url, safe_headers, params, body, case.timeout, api.body_type


async def execute_single_request(
    case: ApiTestCase,
    env: Environment,
    target_host: Optional[str] = None,
    client: httpx.AsyncClient = None,
    csv_row: Optional[dict] = None,
    worker_id: Optional[int] = None,
):
    """
    执行单个请求，返回结果字典
    返回: {case_id, case_name, status_code, response_time, success, error_msg, response_size}
    当传入 client 时复用连接池，否则每次新建 client（兼容其他调用方）
    """
    try:
        method, url, headers, params, body, timeout, body_type = await build_perf_request(case, env, target_host, csv_row)
    except Exception as e:
        return attach_trace_meta({
            "case_id": case.id,
            "case_name": case.name,
            "status_code": 0,
            "response_time": 0,
            "success": False,
            "error_msg": f"请求构建失败: {str(e)}",
            "response_size": 0,
            "request_size": 0
        }, worker_id=worker_id)

    start_time = time.time()
    response_size = 0
    request_size = 0

    async def _do_request(req_client: httpx.AsyncClient):
        kwargs = {"headers": prepare_httpx_headers(headers), "params": params, "timeout": timeout}

        if method in ["POST", "PUT", "PATCH"] and body:
            if body_type == "json":
                kwargs["json"] = body
            else:
                kwargs["data"] = body

        nonlocal request_size
        # 估算请求体大小
        try:
            request_size = len(str(body).encode('utf-8')) if body else 0
        except:
            request_size = 0

        response = await req_client.request(method, url, **kwargs)
        response_size = len(response.content)

        try:
            response_body = response.json()
        except:
            response_body = response.text

        response_time = (time.time() - start_time) * 1000

        # 执行断言
        assertions_passed = True
        failed_assertion_detail = None
        for assertion in case.assertions or []:
            passed, actual_value = evaluate_assertion(response, response_body, assertion)
            if not passed:
                assertions_passed = False
                failed_assertion_detail = {
                    "type": assertion.get("type", ""),
                    "target": assertion.get("target", ""),
                    "operator": assertion.get("operator", ""),
                    "expected": str(assertion.get("expected", "")),
                    "actual": str(actual_value)[:500] if actual_value is not None else "None"
                }
                break

        success = response.status_code < 500 and assertions_passed

        error_msg = None
        if not success:
            if failed_assertion_detail:
                error_msg = f"断言失败: [{failed_assertion_detail['type']}] {failed_assertion_detail['target']} {failed_assertion_detail['operator']} '{failed_assertion_detail['expected']}', 实际值: '{failed_assertion_detail['actual']}'"
            elif response.status_code >= 500:
                error_msg = f"服务端错误: HTTP {response.status_code}"
            elif response.status_code >= 400:
                error_msg = f"客户端错误: HTTP {response.status_code}"

        return attach_trace_meta({
            "case_id": case.id,
            "case_name": case.name,
            "status_code": response.status_code,
            "response_time": response_time,
            "success": success,
            "error_msg": error_msg,
            "response_size": response_size,
            "request_size": request_size
        }, method=method, url=url, body=body, headers=headers, params=params,
           response_body=response_body, csv_row=csv_row, worker_id=worker_id)

    try:
        if client is not None:
            return await _do_request(client)
        else:
            async with httpx.AsyncClient(follow_redirects=True) as temp_client:
                return await _do_request(temp_client)
    except httpx.TimeoutException:
        return attach_trace_meta({
            "case_id": case.id,
            "case_name": case.name,
            "status_code": 0,
            "response_time": (time.time() - start_time) * 1000,
            "success": False,
            "error_msg": "timeout",
            "response_size": 0,
            "request_size": request_size
        }, method=method, url=url, body=body, headers=headers, params=params,
           csv_row=csv_row, worker_id=worker_id)
    except Exception as e:
        return attach_trace_meta({
            "case_id": case.id,
            "case_name": case.name,
            "status_code": 0,
            "response_time": (time.time() - start_time) * 1000,
            "success": False,
            "error_msg": str(e),
            "response_size": 0,
            "request_size": request_size
        }, method=method, url=url, body=body, headers=headers, params=params,
           csv_row=csv_row, worker_id=worker_id)


async def execute_stream_burst_request(
    case: ApiTestCase,
    env: Environment,
    stream_profile: dict,
    target_host: Optional[str] = None,
    client: httpx.AsyncClient = None,
    csv_row: Optional[dict] = None,
    user_id: str = "",
    session_variables: Optional[dict] = None,
):
    """执行流式阶段压测单次请求。"""
    try:
        method, url, headers, params, body, timeout, body_type = await build_perf_request(
            case, env, target_host, csv_row, session_variables=session_variables,
        )
    except Exception as e:
        item = attach_trace_meta({
            "case_id": case.id, "case_name": case.name, "status_code": 0,
            "response_time": 0, "success": False, "error_msg": f"请求构建失败: {str(e)}",
            "response_size": 0, "request_size": 0,
        }, user_id=user_id)
        item["_stream_detail"] = extract_stream_detail(item)
        return item

    question = body.get("question", "") if isinstance(body, dict) else ""
    profile = normalize_stream_profile({"stream_profile": stream_profile})
    detail = await execute_stream_request(
        method, url, headers, params, body, body_type, timeout, profile,
        client=client, user_id=user_id, question=question,
        case_id=case.id, case_name=case.name,
    )
    item = stream_result_to_perf_queue_item(detail)
    item["_trace_meta"] = build_trace_meta(
        method=method, url=url, body=body, headers=headers, params=params,
        response_body=(detail.get("extras") or {}).get("answer_preview"),
        csv_row=csv_row, user_id=user_id,
    )
    return item


async def _execute_perf_case_request(
    case: ApiTestCase,
    env: Environment,
    target_host: Optional[str],
    client: httpx.AsyncClient,
    csv_row: Optional[dict],
    worker_id: int,
    stream_profile: Optional[dict] = None,
):
    """普通 HTTP 或流式问答单次请求（fixed/loop/stepping 共用）。"""
    if stream_profile:
        user_id = f"User_{worker_id:03d}"
        return await execute_stream_burst_request(
            case, env, stream_profile, target_host, client=client, csv_row=csv_row, user_id=user_id,
        )
    return await execute_single_request(case, env, target_host, client=client, csv_row=csv_row, worker_id=worker_id)


async def execute_perf_step(
    case: ApiTestCase,
    env: Environment,
    target_host: Optional[str],
    client: httpx.AsyncClient,
    csv_row: Optional[dict],
    worker_id: int,
    session_variables: Optional[dict] = None,
    stream_profile: Optional[dict] = None,
) -> tuple[dict, dict]:
    """Journey 单步执行：HTTP/流式 + 断言 + 变量提取。"""
    if stream_profile:
        user_id = f"User_{worker_id:03d}"
        result = await execute_stream_burst_request(
            case, env, stream_profile, target_host, client=client,
            csv_row=csv_row, user_id=user_id, session_variables=session_variables,
        )
        return result, {}

    try:
        method, url, headers, params, body, timeout, body_type = await build_perf_request(
            case, env, target_host, csv_row, session_variables=session_variables,
        )
    except Exception as e:
        return attach_trace_meta({
            "case_id": case.id,
            "case_name": case.name,
            "status_code": 0,
            "response_time": 0,
            "success": False,
            "error_msg": f"请求构建失败: {str(e)}",
            "response_size": 0,
            "request_size": 0,
        }, worker_id=worker_id), {}

    start_time = time.time()
    request_size = 0
    try:
        kwargs = {"headers": prepare_httpx_headers(headers), "params": params, "timeout": timeout}
        if method in ["POST", "PUT", "PATCH"] and body:
            if body_type == "json":
                kwargs["json"] = body
            else:
                kwargs["data"] = body
        try:
            request_size = len(str(body).encode("utf-8")) if body else 0
        except Exception:
            request_size = 0

        response = await client.request(method, url, **kwargs)
        response_size = len(response.content)
        try:
            response_body = response.json()
        except Exception:
            response_body = response.text

        response_time = (time.time() - start_time) * 1000
        assertions_passed = True
        failed_assertion_detail = None
        for assertion in case.assertions or []:
            passed, actual_value = evaluate_assertion(response, response_body, assertion)
            if not passed:
                assertions_passed = False
                failed_assertion_detail = {
                    "type": assertion.get("type", ""),
                    "target": assertion.get("target", ""),
                    "operator": assertion.get("operator", ""),
                    "expected": str(assertion.get("expected", "")),
                    "actual": str(actual_value)[:500] if actual_value is not None else "None",
                }
                break

        success = response.status_code < 500 and assertions_passed
        error_msg = None
        if not success:
            if failed_assertion_detail:
                error_msg = (
                    f"断言失败: [{failed_assertion_detail['type']}] {failed_assertion_detail['target']} "
                    f"{failed_assertion_detail['operator']} '{failed_assertion_detail['expected']}', "
                    f"实际值: '{failed_assertion_detail['actual']}'"
                )
            elif response.status_code >= 500:
                error_msg = f"服务端错误: HTTP {response.status_code}"
            elif response.status_code >= 400:
                error_msg = f"客户端错误: HTTP {response.status_code}"

        extracted, _ = extract_variables(response_body, case.extractors or [], headers=response.headers)
        return attach_trace_meta({
            "case_id": case.id,
            "case_name": case.name,
            "status_code": response.status_code,
            "response_time": response_time,
            "success": success,
            "error_msg": error_msg,
            "response_size": response_size,
            "request_size": request_size,
        }, method=method, url=url, body=body, headers=headers, params=params,
           response_body=response_body, csv_row=csv_row, worker_id=worker_id), extracted
    except httpx.TimeoutException:
        return attach_trace_meta({
            "case_id": case.id,
            "case_name": case.name,
            "status_code": 0,
            "response_time": (time.time() - start_time) * 1000,
            "success": False,
            "error_msg": "timeout",
            "response_size": 0,
            "request_size": request_size,
        }, method=method, url=url, body=body, headers=headers, params=params,
           csv_row=csv_row, worker_id=worker_id), {}
    except Exception as e:
        return attach_trace_meta({
            "case_id": case.id,
            "case_name": case.name,
            "status_code": 0,
            "response_time": (time.time() - start_time) * 1000,
            "success": False,
            "error_msg": str(e),
            "response_size": 0,
            "request_size": request_size,
        }, method=method, url=url, body=body, headers=headers, params=params,
           csv_row=csv_row, worker_id=worker_id), {}


# ========== 压测 Worker ==========

def _build_case_cycle(case_pool: List[dict]):
    """构建固定比例分配的请求序列循环器"""
    sequence = []
    for item in case_pool:
        for _ in range(item.get("weight", 1)):
            sequence.append(item)
    return itertools.cycle(sequence) if sequence else None


async def _perf_worker_fixed(
    worker_id: int,
    case_pool: List[dict],
    case_map: Dict[int, ApiTestCase],
    env: Environment,
    target_host: Optional[str],
    duration_seconds: int,
    stop_event: asyncio.Event,
    result_queue: deque,
    sem: asyncio.Semaphore,
    start_time: float,
    case_cycle=None,
    client: httpx.AsyncClient = None,
    csv_data: List[dict] = None,
    csv_strategy: str = "round_robin",
    record_id: int = None,
    stream_profile: Optional[dict] = None,
    total_workers: int = 1,
):
    """固定模式 worker：持续执行直到超时"""
    end_time = start_time + duration_seconds
    # 预计算随机权重（避免每次循环重建列表）
    _weights = [item.get("weight", 1) for item in case_pool] if not case_cycle else None

    while time.time() < end_time:
        if stop_event.is_set():
            break

        async with sem:
            if stop_event.is_set():
                break

            if case_cycle:
                chosen = next(case_cycle)
            else:
                chosen = random.choices(case_pool, weights=_weights, k=1)[0]
            case_id = chosen["case_id"]
            delay_ms = chosen.get("delay_ms", 0)

            case = case_map.get(case_id)
            if not case:
                result_queue.append({
                    "case_id": case_id, "case_name": "未知", "status_code": 0,
                    "response_time": 0, "success": False, "error_msg": "用例不存在",
                    "response_size": 0, "request_size": 0
                })
                continue

            csv_row = get_next_csv_row(
                record_id, csv_data, csv_strategy, worker_id, total_workers=total_workers,
            ) if csv_data else None
            result = await _execute_perf_case_request(
                case, env, target_host, client, csv_row, worker_id, stream_profile,
            )
            result_queue.append(result)

            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000)


async def _perf_worker_loop(
    worker_id: int,
    case_pool: List[dict],
    case_map: Dict[int, ApiTestCase],
    env: Environment,
    target_host: Optional[str],
    loop_count: int,
    stop_event: asyncio.Event,
    result_queue: deque,
    sem: asyncio.Semaphore,
    case_cycle=None,
    client: httpx.AsyncClient = None,
    progress_ref: dict = None,
    csv_data: List[dict] = None,
    csv_strategy: str = "round_robin",
    record_id: int = None,
    stream_profile: Optional[dict] = None,
    total_workers: int = 1,
):
    """循环模式 worker：执行指定次数"""
    # 预计算随机权重（避免每次循环重建列表）
    _weights = [item.get("weight", 1) for item in case_pool] if not case_cycle else None

    for _ in range(loop_count):
        if stop_event.is_set():
            break

        async with sem:
            if stop_event.is_set():
                break

            if case_cycle:
                chosen = next(case_cycle)
            else:
                chosen = random.choices(case_pool, weights=_weights, k=1)[0]
            case_id = chosen["case_id"]
            delay_ms = chosen.get("delay_ms", 0)

            case = case_map.get(case_id)
            if not case:
                result_queue.append({
                    "case_id": case_id, "case_name": "未知", "status_code": 0,
                    "response_time": 0, "success": False, "error_msg": "用例不存在",
                    "response_size": 0, "request_size": 0
                })
                continue

            csv_row = get_next_csv_row(
                record_id, csv_data, csv_strategy, worker_id, total_workers=total_workers,
            ) if csv_data else None
            result = await _execute_perf_case_request(
                case, env, target_host, client, csv_row, worker_id, stream_profile,
            )
            result_queue.append(result)

            if progress_ref is not None:
                progress_ref["current"] = progress_ref.get("current", 0) + 1

            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000)


async def _perf_worker_stream_burst(
    worker_id: int,
    case_pool: List[dict],
    case_map: Dict[int, ApiTestCase],
    env: Environment,
    target_host: Optional[str],
    stream_profile: dict,
    stop_event: asyncio.Event,
    result_queue: deque,
    sem: asyncio.Semaphore,
    case_cycle=None,
    csv_data: List[dict] = None,
    csv_strategy: str = "round_robin",
    record_id: int = None,
    total_workers: int = 1,
):
    """流式并发单次：每个虚拟用户只发 1 次请求。"""
    async with sem:
        if stop_event.is_set():
            return

        _weights = [item.get("weight", 1) for item in case_pool] if not case_cycle else None
        if case_cycle:
            chosen = next(case_cycle)
        else:
            chosen = random.choices(case_pool, weights=_weights, k=1)[0]
        case_id = chosen["case_id"]
        case = case_map.get(case_id)
        if not case:
            result_queue.append({
                "case_id": case_id, "case_name": "未知", "status_code": 0,
                "response_time": 0, "success": False, "error_msg": "用例不存在",
                "response_size": 0, "request_size": 0, "has_answer": False,
            })
            return

        csv_row = get_next_csv_row(
            record_id, csv_data, csv_strategy, worker_id, total_workers=total_workers,
        ) if csv_data else None
        user_id = f"User_{worker_id:03d}"
        result = await execute_stream_burst_request(
            case, env, stream_profile, target_host, csv_row=csv_row, user_id=user_id,
        )
        result_queue.append(result)


# ========== 秒级聚合器 ==========

async def _aggregator(
    record: PerfRecord,
    result_queue: deque,
    stop_event: asyncio.Event,
    expected_end_time: float,
    streaming_stats: StreamingStats,
    case_stats: dict,
    total_bytes_received: list,
    total_bytes_sent: list,
    error_stats: dict,
    failed_samples: list,
    max_samples: int = 50,
    current_limit: list = None,
    error_rate_threshold: float = 0,
    stop_reason: list = None,
    request_details: list = None,
    request_traces: list = None,
    journey_progress_ref: dict = None,
):
    """秒级聚合定时器"""
    time_series = []
    last_db_save = time.time()
    total_req = 0
    total_success = 0
    total_fail = 0
    start_time = time.time()

    # 错误率阈值自动停止：连续超阈值的秒数计数器
    consecutive_error_seconds = 0

    # 获取基准时长用于计算 timestamp（兼容三种模式）
    config = record.config_snapshot or {}
    mode = normalize_perf_mode(config.get("mode", "fixed"))
    if mode == "fixed":
        base_duration = config.get("duration_seconds", 60) or 60
    elif mode == "loop":
        # loop 模式用预估的单次请求时间作为基准
        base_duration = 5
    else:  # stepping
        steps = config.get("steps", [])
        base_duration = sum(s.get("duration", 30) for s in steps) or 60

    # 进度信息引用（循环模式由 worker 更新，固定/梯度由聚合器计算）
    record_id = record.id
    detail_level = normalize_detail_level((record.config_snapshot or {}).get("request_detail_level"))

    while time.time() < expected_end_time + 2:
        if stop_event.is_set() and not result_queue:
            break

        await asyncio.sleep(1)

        second_results = []
        while result_queue:
            r = result_queue.popleft()
            second_results.append(r)
            if request_details is not None and is_stream_queue_result(r):
                append_request_detail(request_details, extract_stream_detail(r))
            streaming_stats.add(r["response_time"])
            total_bytes_received[0] += r.get("response_size", 0)
            total_bytes_sent[0] += r.get("request_size", 0)
            _update_case_stats(case_stats, r)
            _update_error_stats(error_stats, r)
            collect_result_diagnostics(r, failed_samples, request_traces, detail_level)

        if not second_results and stop_event.is_set():
            break

        sec_total = len(second_results)
        sec_success = sum(1 for r in second_results if r["success"])
        sec_fail = sec_total - sec_success
        sec_rts = [r["response_time"] for r in second_results if r["response_time"] > 0]
        sec_avg_rt = sum(sec_rts) / len(sec_rts) if sec_rts else 0
        sec_p95_rt = round(float(np.percentile(sec_rts, 95)), 2) if len(sec_rts) >= 2 else round(sec_avg_rt, 2)
        sec_error_rate = round(sec_fail / sec_total * 100, 2) if sec_total > 0 else 0

        total_req += sec_total
        total_success += sec_success
        total_fail += sec_fail

        # 错误率阈值检查：连续 3 秒超阈值则自动停止
        if error_rate_threshold > 0 and sec_total > 0:
            if sec_error_rate >= error_rate_threshold:
                consecutive_error_seconds += 1
                if consecutive_error_seconds >= 3:
                    stop_event.set()
                    if stop_reason is not None:
                        stop_reason[0] = "error_rate_threshold"
            else:
                consecutive_error_seconds = 0

        elapsed = time.time() - start_time
        # active_users 根据模式计算
        if mode == "stepping" and current_limit is not None:
            active_users = current_limit[0]
        else:
            active_users = config.get("concurrent_users", 1)

        point = {
            "timestamp": int(elapsed),
            "qps": round(sec_total, 2),
            "avg_rt": round(sec_avg_rt, 2),
            "p95_rt": sec_p95_rt,
            "error_rate": sec_error_rate,
            "active_users": active_users,
            "total_req": total_req,
            "success": total_success,
            "fail": total_fail
        }
        time_series.append(point)

        # 计算并更新进度
        if record_id:
            if mode == "loop":
                # 循环模式：从 progress_ref 读取 worker 计数
                loop_total = config.get("loop_count", 100) * config.get("concurrent_users", 1)
                _running_progress[record_id] = {
                    "mode": "loop",
                    "current": total_req,
                    "total": loop_total,
                    "percentage": round(min(100, total_req / loop_total * 100), 1) if loop_total > 0 else 0
                }
            elif mode == "fixed":
                duration = config.get("duration_seconds", 60) or 60
                pct = min(100, round(elapsed / duration * 100, 1))
                _running_progress[record_id] = {
                    "mode": "fixed",
                    "current": round(elapsed, 1),
                    "total": duration,
                    "percentage": pct
                }
            elif mode == "stepping":
                steps = config.get("steps", [])
                total_d = sum(s.get("duration", 30) for s in steps) or 60
                pct = min(100, round(elapsed / total_d * 100, 1))
                _running_progress[record_id] = {
                    "mode": "stepping",
                    "current": round(elapsed, 1),
                    "total": total_d,
                    "percentage": pct
                }
            elif mode in (JOURNEY_FIXED_MODE, JOURNEY_LOOP_MODE):
                if mode == JOURNEY_LOOP_MODE:
                    loop_total = config.get("loop_count", 100) * config.get("concurrent_users", 1)
                    journey_current = (journey_progress_ref or {}).get("current", 0)
                    _running_progress[record_id] = {
                        "mode": mode,
                        "current": journey_current,
                        "total": loop_total,
                        "percentage": round(min(100, journey_current / loop_total * 100), 1) if loop_total > 0 else 0,
                    }
                else:
                    duration = config.get("duration_seconds", 60) or 60
                    pct = min(100, round(elapsed / duration * 100, 1))
                    _running_progress[record_id] = {
                        "mode": mode,
                        "current": round(elapsed, 1),
                        "total": duration,
                        "percentage": pct,
                    }
            elif mode == STREAM_BURST_MODE:
                burst_total = config.get("concurrent_users", 1)
                _running_progress[record_id] = {
                    "mode": STREAM_BURST_MODE,
                    "current": total_req,
                    "total": burst_total,
                    "percentage": round(min(100, total_req / burst_total * 100), 1) if burst_total > 0 else 0,
                }

        if time.time() - last_db_save >= 3:
            record.time_series_data = time_series
            record.total_requests = total_req
            record.success_count = total_success
            record.fail_count = total_fail
            await record.save()
            last_db_save = time.time()

    record.time_series_data = time_series
    record.total_requests = total_req
    record.success_count = total_success
    record.fail_count = total_fail
    await record.save()

    return time_series


def _update_case_stats(case_stats: Dict[int, dict], result: dict, max_case_samples: int = None):
    """更新单用例统计（带蓄水池采样控制每个用例的rts上限）"""
    from app.routers.perf.case_agg_utils import MAX_CASE_RT_SAMPLES, append_rt_reservoir

    if max_case_samples is None:
        max_case_samples = MAX_CASE_RT_SAMPLES
    cid = result["case_id"]
    if cid not in case_stats:
        case_stats[cid] = {
            "name": result["case_name"],
            "total": 0, "success": 0, "fail": 0, "rts": [],
            "rt_count": 0,
        }
    case_stats[cid]["total"] += 1
    if result["success"]:
        case_stats[cid]["success"] += 1
    else:
        case_stats[cid]["fail"] += 1
    if result["response_time"] > 0:
        rts = case_stats[cid]["rts"]
        case_stats[cid]["rt_count"] = case_stats[cid].get("rt_count", 0) + 1
        append_rt_reservoir(
            rts,
            result["response_time"],
            case_stats[cid]["rt_count"],
            max_samples=max_case_samples,
        )


def _record_status_code_distribution(error_stats: dict, result: dict):
    """记录全部请求的 HTTP 状态码分布"""
    sc_key = str(result.get("status_code", 0))
    dist = error_stats.setdefault("status_code_distribution", {})
    dist[sc_key] = dist.get(sc_key, 0) + 1


def _update_error_stats(error_stats: dict, result: dict):
    """更新错误分类统计"""
    _record_status_code_distribution(error_stats, result)
    if result["success"]:
        return

    status_code = result.get("status_code", 0)
    error_msg = result.get("error_msg", "")
    
    # 按状态码统计
    sc_key = str(status_code)
    error_stats["by_status_code"][sc_key] = error_stats["by_status_code"].get(sc_key, 0) + 1
    
    # 按错误类型统计
    error_type = "unknown"
    if status_code == 0:
        if "timeout" in str(error_msg).lower():
            error_type = "timeout"
        elif "connection" in str(error_msg).lower() or "refused" in str(error_msg).lower():
            error_type = "connection_error"
        else:
            error_type = "network_error"
    elif status_code >= 500:
        error_type = "server_error"
    elif status_code >= 400:
        error_type = "client_error"
    else:
        # 状态码正常但断言失败
        error_type = "assertion_failed"
    
    error_stats["by_type"][error_type] = error_stats["by_type"].get(error_type, 0) + 1


def _build_case_aggregations(case_stats: Dict[int, dict]) -> dict:
    """构建接口维度聚合数据"""
    from app.routers.perf.case_agg_utils import metrics_from_rts

    result = {}
    for cid, stats in case_stats.items():
        result[str(cid)] = metrics_from_rts(stats.get("rts") or [], stats)
    return result


# ========== 最终聚合计算 ==========

async def _load_preserved_status(record: PerfRecord) -> Optional[str]:
    """若用户已手动停止，保留 stopped 状态（stop_perf 写入 DB，内存 record 可能仍为 running）。"""
    fresh = await PerfRecord.get_or_none(id=record.id)
    if fresh and fresh.status == "stopped":
        if isinstance(fresh.error_breakdown, dict) and fresh.error_breakdown.get("stop_reason"):
            bd = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
            bd.setdefault("stop_reason", fresh.error_breakdown["stop_reason"])
            record.error_breakdown = bd
        return "stopped"
    return None


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


def _finalize_record(
    record: PerfRecord,
    streaming_stats: StreamingStats,
    case_stats: dict,
    total_bytes_received: list,
    total_bytes_sent: list,
    error_stats: dict,
    actual_duration: float,
    start_time: float,
    failed_samples: list = None,
    stop_reason: list = None,
    request_traces: list = None,
    preserved_status: Optional[str] = None,
):
    """计算最终聚合指标（从 StreamingStats 读取）"""
    total = record.total_requests
    success = record.success_count
    fail = record.fail_count

    # 防御性处理：即使 streaming_stats 为空，也尝试从 case_stats 恢复
    if streaming_stats.is_empty() and case_stats:
        for stats in case_stats.values():
            for rt in stats.get("rts", []):
                streaming_stats.add(rt)

    if not streaming_stats.is_empty():
        record.avg_response_time = round(streaming_stats.get_mean(), 2)
        record.min_response_time = round(streaming_stats.get_min(), 2)
        record.max_response_time = round(streaming_stats.get_max(), 2)
        record.median_response_time = round(streaming_stats.get_percentile(50), 2)
        record.p90_response_time = round(streaming_stats.get_percentile(90), 2)
        record.p95_response_time = round(streaming_stats.get_percentile(95), 2)
        record.p99_response_time = round(streaming_stats.get_percentile(99), 2)
        record.std_dev_response_time = round(streaming_stats.get_std_dev(), 2)
    else:
        # 没有任何响应时间数据，全部设为 0
        record.avg_response_time = 0
        record.min_response_time = 0
        record.max_response_time = 0
        record.median_response_time = 0
        record.p90_response_time = 0
        record.p95_response_time = 0
        record.p99_response_time = 0
        record.std_dev_response_time = 0
    
    record.qps = round(total / actual_duration, 2) if actual_duration > 0 else 0
    record.error_rate = round(fail / total * 100, 2) if total > 0 else 0
    record.duration = round(actual_duration, 2)
    record.ended_at = datetime.now()
    auto_stop_msg = None
    preserved_stop_reason = None
    if isinstance(record.error_breakdown, dict):
        preserved_stop_reason = record.error_breakdown.get("stop_reason")
    if preserved_status == "stopped":
        record.status = "stopped"
    elif stop_reason and stop_reason[0] == "error_rate_threshold":
        record.status = "stopped"
        auto_stop_msg = ERROR_RATE_AUTO_STOP_MSG
    elif total == 0:
        record.status = "failed"
        if not preserved_stop_reason:
            preserved_stop_reason = "未产生任何请求"
    else:
        record.status = "success" if fail == 0 else "failed"
    record.case_aggregations = _build_case_aggregations(case_stats)
    record.error_breakdown = error_stats
    if auto_stop_msg and isinstance(record.error_breakdown, dict):
        record.error_breakdown["stop_reason"] = auto_stop_msg
    elif preserved_stop_reason and isinstance(record.error_breakdown, dict):
        record.error_breakdown["stop_reason"] = preserved_stop_reason
    
    # 失败请求采样（存入 JSON 字段，最多50条）
    if failed_samples:
        # 如果 error_breakdown 中没有 failed_samples，添加进去
        if isinstance(record.error_breakdown, dict):
            record.error_breakdown["failed_samples"] = failed_samples

    if request_traces and isinstance(record.error_breakdown, dict):
        record.error_breakdown["request_traces"] = request_traces[:500]

    # 响应时间直方图
    histogram = build_rt_histogram(streaming_stats.samples)
    if isinstance(record.error_breakdown, dict):
        record.error_breakdown["rt_histogram"] = histogram
    else:
        record.error_breakdown = {"rt_histogram": histogram}
    
    # KB/s 计算
    if actual_duration > 0:
        record.received_kb_per_sec = round(total_bytes_received[0] / 1024 / actual_duration, 2)
        record.sent_kb_per_sec = round(total_bytes_sent[0] / 1024 / actual_duration, 2)
    else:
        record.received_kb_per_sec = 0
        record.sent_kb_per_sec = 0


def _apply_phase_metrics(record: PerfRecord, request_details: list):
    """写入流式阶段压测明细与聚合指标。"""
    if not request_details:
        record.phase_metrics = {}
        record.request_details = []
        return
    normalized = [extract_stream_detail(d) for d in request_details]
    record.request_details = normalized
    profile = normalize_stream_profile(record.config_snapshot or {})
    record.phase_metrics = aggregate_phase_metrics(
        normalized,
        parser_id=profile.get("parser_id", ""),
        phase_schema=normalized[0].get("phase_schema") if normalized else [],
    )


# ========== 三种模式执行入口 ==========


async def _run_stream_burst_mode(
    record,
    scene_items,
    case_map,
    env,
    config,
    stop_event,
    csv_data=None,
    csv_strategy="round_robin",
    record_id=None,
):
    """流式阶段并发单次：N 用户各发 1 次流式请求。"""
    stream_profile = normalize_stream_profile(config)
    concurrent_users = config.get("concurrent_users", 1)
    ramp_up_seconds = config.get("ramp_up_seconds", 0)
    target_host = config.get("target_host")
    distribution_mode = normalize_distribution_mode(config.get("distribution_mode"))
    error_rate_threshold = config.get("error_rate_threshold", 0)
    stop_reason = [None]

    sem = asyncio.Semaphore(concurrent_users)
    result_queue = deque()
    request_details = []
    streaming_stats = StreamingStats(max_samples=10000)
    case_stats = {}
    total_bytes_received = [0]
    total_bytes_sent = [0]
    error_stats = {"by_status_code": {}, "by_type": {}, "status_code_distribution": {}}
    failed_samples = []
    request_traces = []

    case_cycle = _build_case_cycle(scene_items) if distribution_mode == "fixed_ratio" else None
    start_time = time.time()
    expected_max_duration = max(600, concurrent_users * 30)
    expected_end = start_time + expected_max_duration

    aggregator_task = asyncio.create_task(
        _aggregator(record, result_queue, stop_event, expected_end, streaming_stats, case_stats,
                    total_bytes_received, total_bytes_sent, error_stats, failed_samples,
                    error_rate_threshold=error_rate_threshold, stop_reason=stop_reason,
                    request_details=request_details, request_traces=request_traces)
    )

    worker_tasks = []
    if ramp_up_seconds > 0 and concurrent_users > 1:
        interval = ramp_up_seconds / concurrent_users
        for i in range(concurrent_users):
            if stop_event.is_set():
                break
            await asyncio.sleep(interval)
            worker_tasks.append(asyncio.create_task(
                _perf_worker_stream_burst(
                    i, scene_items, case_map, env, target_host, stream_profile, stop_event, result_queue, sem,
                    case_cycle, csv_data, csv_strategy, record_id, total_workers=concurrent_users
                )
            ))
    else:
        for i in range(concurrent_users):
            worker_tasks.append(asyncio.create_task(
                _perf_worker_stream_burst(
                    i, scene_items, case_map, env, target_host, stream_profile, stop_event, result_queue, sem,
                    case_cycle, csv_data, csv_strategy, record_id, total_workers=concurrent_users
                )
            ))

    if worker_tasks:
        await asyncio.gather(*worker_tasks, return_exceptions=True)

    await asyncio.sleep(2)
    stop_event.set()
    await aggregator_task

    actual_duration = time.time() - start_time
    preserved_status = await _load_preserved_status(record)
    _finalize_record(record, streaming_stats, case_stats, total_bytes_received, total_bytes_sent,
                     error_stats, actual_duration, start_time, failed_samples, stop_reason=stop_reason,
                     request_traces=request_traces, preserved_status=preserved_status)
    _apply_phase_metrics(record, request_details)

    if record_id:
        _running_progress[record_id] = {
            "mode": STREAM_BURST_MODE,
            "current": len(request_details),
            "total": concurrent_users,
            "percentage": round(min(100, len(request_details) / concurrent_users * 100), 1) if concurrent_users else 100,
        }


async def _run_fixed_mode(record, scene_items, case_map, env, config, stop_event, csv_data=None, csv_strategy="round_robin", record_id=None):
    """固定模式执行"""
    concurrent_users = config.get("concurrent_users", 1)
    ramp_up_seconds = config.get("ramp_up_seconds", 0)
    duration_seconds = config.get("duration_seconds", 60)
    target_host = config.get("target_host")
    distribution_mode = normalize_distribution_mode(config.get("distribution_mode"))
    error_rate_threshold = config.get("error_rate_threshold", 0)
    stop_reason = [None]
    stream_profile = normalize_stream_profile(config) if use_stream_execution(config) else None
    request_details = [] if stream_profile else None

    sem = asyncio.Semaphore(concurrent_users)
    result_queue = deque()
    streaming_stats = StreamingStats(max_samples=10000)
    case_stats = {}
    total_bytes_received = [0]
    total_bytes_sent = [0]
    error_stats = {"by_status_code": {}, "by_type": {}, "status_code_distribution": {}}
    failed_samples = []
    request_traces = []

    case_cycle = _build_case_cycle(scene_items) if distribution_mode == "fixed_ratio" else None

    start_time = time.time()
    expected_end = start_time + duration_seconds

    async with httpx.AsyncClient(follow_redirects=True) as client:
        aggregator_task = asyncio.create_task(
            _aggregator(record, result_queue, stop_event, expected_end, streaming_stats, case_stats,
                        total_bytes_received, total_bytes_sent, error_stats, failed_samples,
                        error_rate_threshold=error_rate_threshold, stop_reason=stop_reason,
                        request_details=request_details, request_traces=request_traces)
        )

        worker_tasks = []
        if ramp_up_seconds > 0 and concurrent_users > 1:
            interval = ramp_up_seconds / concurrent_users
            for i in range(concurrent_users):
                if stop_event.is_set():
                    break
                await asyncio.sleep(interval)
                task = asyncio.create_task(
                    _perf_worker_fixed(i, scene_items, case_map, env, target_host,
                                       duration_seconds, stop_event, result_queue, sem, start_time,
                                       case_cycle, client, csv_data, csv_strategy, record_id,
                                       stream_profile=stream_profile, total_workers=concurrent_users)
                )
                worker_tasks.append(task)
        else:
            for i in range(concurrent_users):
                task = asyncio.create_task(
                    _perf_worker_fixed(i, scene_items, case_map, env, target_host,
                                       duration_seconds, stop_event, result_queue, sem, start_time,
                                       case_cycle, client, csv_data, csv_strategy, record_id,
                                       stream_profile=stream_profile, total_workers=concurrent_users)
                )
                worker_tasks.append(task)

        if worker_tasks:
            await asyncio.gather(*worker_tasks, return_exceptions=True)

        await asyncio.sleep(2)
        stop_event.set()
        await aggregator_task

    actual_duration = time.time() - start_time
    preserved_status = await _load_preserved_status(record)
    _finalize_record(record, streaming_stats, case_stats, total_bytes_received, total_bytes_sent,
                     error_stats, actual_duration, start_time, failed_samples, stop_reason=stop_reason,
                     request_traces=request_traces, preserved_status=preserved_status)
    if request_details is not None:
        _apply_phase_metrics(record, request_details)


async def _run_loop_mode(record, scene_items, case_map, env, config, stop_event, csv_data=None, csv_strategy="round_robin", record_id=None):
    """循环模式执行"""
    concurrent_users = config.get("concurrent_users", 1)
    ramp_up_seconds = config.get("ramp_up_seconds", 0)
    loop_count = config.get("loop_count", 100)
    target_host = config.get("target_host")
    distribution_mode = normalize_distribution_mode(config.get("distribution_mode"))
    error_rate_threshold = config.get("error_rate_threshold", 0)
    stop_reason = [None]
    stream_profile = normalize_stream_profile(config) if use_stream_execution(config) else None
    request_details = [] if stream_profile else None

    sem = asyncio.Semaphore(concurrent_users)
    result_queue = deque()
    streaming_stats = StreamingStats(max_samples=10000)
    case_stats = {}
    total_bytes_received = [0]
    total_bytes_sent = [0]
    error_stats = {"by_status_code": {}, "by_type": {}, "status_code_distribution": {}}
    failed_samples = []
    request_traces = []

    case_cycle = _build_case_cycle(scene_items) if distribution_mode == "fixed_ratio" else None

    start_time = time.time()
    # loop 由 worker 次数驱动；聚合器须等 worker 结束后由 stop_event 收尾，不能用短超时
    expected_end = start_time + 86400 * 7

    async with httpx.AsyncClient(follow_redirects=True) as client:
        aggregator_task = asyncio.create_task(
            _aggregator(record, result_queue, stop_event, expected_end, streaming_stats, case_stats,
                        total_bytes_received, total_bytes_sent, error_stats, failed_samples,
                        error_rate_threshold=error_rate_threshold, stop_reason=stop_reason,
                        request_details=request_details, request_traces=request_traces)
        )

        worker_tasks = []
        if ramp_up_seconds > 0 and concurrent_users > 1:
            interval = ramp_up_seconds / concurrent_users
            for i in range(concurrent_users):
                if stop_event.is_set():
                    break
                await asyncio.sleep(interval)
                task = asyncio.create_task(
                    _perf_worker_loop(i, scene_items, case_map, env, target_host,
                                      loop_count, stop_event, result_queue, sem, case_cycle, client,
                                      csv_data=csv_data, csv_strategy=csv_strategy, record_id=record_id,
                                      stream_profile=stream_profile, total_workers=concurrent_users)
                )
                worker_tasks.append(task)
        else:
            for i in range(concurrent_users):
                task = asyncio.create_task(
                    _perf_worker_loop(i, scene_items, case_map, env, target_host,
                                      loop_count, stop_event, result_queue, sem, case_cycle, client,
                                      csv_data=csv_data, csv_strategy=csv_strategy, record_id=record_id,
                                      stream_profile=stream_profile, total_workers=concurrent_users)
                )
                worker_tasks.append(task)

        if worker_tasks:
            await asyncio.gather(*worker_tasks, return_exceptions=True)

        await asyncio.sleep(2)
        stop_event.set()
        await aggregator_task

    actual_duration = time.time() - start_time
    preserved_status = await _load_preserved_status(record)
    _finalize_record(record, streaming_stats, case_stats, total_bytes_received, total_bytes_sent,
                     error_stats, actual_duration, start_time, failed_samples, stop_reason=stop_reason,
                     request_traces=request_traces, preserved_status=preserved_status)
    if request_details is not None:
        _apply_phase_metrics(record, request_details)


async def _run_stepping_mode(record, scene_items, case_map, env, config, stop_event, csv_data=None, csv_strategy="round_robin", record_id=None):
    """梯度模式执行"""
    steps = config.get("steps", [])
    target_host = config.get("target_host")
    distribution_mode = normalize_distribution_mode(config.get("distribution_mode"))
    error_rate_threshold = config.get("error_rate_threshold", 0)
    stop_reason = [None]
    stream_profile = normalize_stream_profile(config) if use_stream_execution(config) else None
    request_details = [] if stream_profile else None

    if not steps:
        record.status = "failed"
        await record.save()
        return

    max_users = max(s.get("users", 1) for s in steps)
    sem = asyncio.Semaphore(max_users)

    result_queue = deque()
    streaming_stats = StreamingStats(max_samples=10000)
    case_stats = {}
    total_bytes_received = [0]
    total_bytes_sent = [0]
    error_stats = {"by_status_code": {}, "by_type": {}, "status_code_distribution": {}}
    failed_samples = []
    request_traces = []

    case_cycle = _build_case_cycle(scene_items) if distribution_mode == "fixed_ratio" else None

    start_time = time.time()
    total_duration = sum(s.get("duration", 0) for s in steps)
    expected_end = start_time + total_duration + len(steps) * 2

    # 动态调整并发数，用于聚合器读取当前阶段并发
    current_limit = [0]

    # 复用 httpx client（连接池）
    async with httpx.AsyncClient(follow_redirects=True) as client:
        aggregator_task = asyncio.create_task(
            _aggregator(record, result_queue, stop_event, expected_end, streaming_stats, case_stats,
                        total_bytes_received, total_bytes_sent, error_stats, failed_samples,
                        current_limit=current_limit,
                        error_rate_threshold=error_rate_threshold, stop_reason=stop_reason,
                        request_details=request_details, request_traces=request_traces)
        )

        # 动态调整 Semaphore：创建一个可动态调整的信号量包装
        active_workers = {}  # {worker_id: task}
        worker_counter = [0]

        # 预计算随机权重
        _weights = [item.get("weight", 1) for item in scene_items] if not case_cycle else None

        # 为每个 worker 创建启动事件，用事件通知替代轮询 sleep
        worker_events = {}  # {worker_id: asyncio.Event}

        async def stepping_worker(wid, case_pool, c_map, e, th, stop_evt, rq, s, cycle=None, csv_data=None, csv_strategy="round_robin", rec_id=None, tw=1):
            """梯度模式的 worker，通过事件通知启动，避免轮询空转"""
            event = worker_events.get(wid)
            while not stop_evt.is_set():
                # 等待被允许运行：事件触发或 stop
                if event and not event.is_set():
                    try:
                        await asyncio.wait_for(event.wait(), timeout=0.5)
                    except asyncio.TimeoutError:
                        pass
                # 再次检查限制和停止状态
                if stop_evt.is_set():
                    break
                if wid > current_limit[0]:
                    if event:
                        event.clear()
                    continue

                if cycle:
                    chosen = next(cycle)
                else:
                    chosen = random.choices(case_pool, weights=_weights, k=1)[0]
                case_id = chosen["case_id"]
                delay_ms = chosen.get("delay_ms", 0)

                case = c_map.get(case_id)
                if not case:
                    rq.append({
                        "case_id": case_id, "case_name": "未知", "status_code": 0,
                        "response_time": 0, "success": False, "error_msg": "用例不存在",
                        "response_size": 0, "request_size": 0
                    })
                    continue

                csv_row = get_next_csv_row(rec_id, csv_data, csv_strategy, wid, total_workers=tw) if csv_data else None
                result = await _execute_perf_case_request(
                    case, e, th, client, csv_row, wid, stream_profile,
                )
                rq.append(result)

                if delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000)

        # 预先创建所有 worker
        for i in range(max_users):
            worker_counter[0] += 1
            wid = worker_counter[0]
            worker_events[wid] = asyncio.Event()
            task = asyncio.create_task(
                stepping_worker(wid, scene_items, case_map, env, target_host,
                               stop_event, result_queue, sem, case_cycle,
                               csv_data=csv_data, csv_strategy=csv_strategy, rec_id=record_id,
                               tw=max_users)
            )
            active_workers[wid] = task

        # 分阶段调整并发：设置 current_limit 并触发对应 worker 的事件
        for step in steps:
            if stop_event.is_set():
                break
            new_limit = step.get("users", 1)
            current_limit[0] = new_limit
            # 触发新加入的 worker 事件
            for wid in range(1, new_limit + 1):
                evt = worker_events.get(wid)
                if evt and not evt.is_set():
                    evt.set()
            # 等待该阶段持续时间
            await asyncio.sleep(step.get("duration", 30))

        # 停止所有 worker
        stop_event.set()
        for evt in worker_events.values():
            evt.set()
        for task in active_workers.values():
            if not task.done():
                task.cancel()

        await asyncio.sleep(2)
        await aggregator_task

    actual_duration = time.time() - start_time
    preserved_status = await _load_preserved_status(record)
    _finalize_record(record, streaming_stats, case_stats, total_bytes_received, total_bytes_sent,
                     error_stats, actual_duration, start_time, failed_samples, stop_reason=stop_reason,
                     request_traces=request_traces, preserved_status=preserved_status)
    if request_details is not None:
        _apply_phase_metrics(record, request_details)


async def _perf_worker_journey(
    worker_id: int,
    case_map: Dict[int, ApiTestCase],
    env: Environment,
    target_host: Optional[str],
    journey: dict,
    mode: str,
    duration_seconds: Optional[int],
    loop_count: Optional[int],
    stop_event: asyncio.Event,
    result_queue: deque,
    sem: asyncio.Semaphore,
    sync: PhaseSyncCoordinator,
    journey_stats: JourneyStatsCollector,
    active_users: int,
    client: httpx.AsyncClient,
    csv_data: List[dict] = None,
    csv_strategy: str = "round_robin",
    record_id: int = None,
    stream_profile_global: Optional[dict] = None,
    start_time: float = 0,
    journey_progress_ref: dict = None,
):
    """Journey 模式 worker：每个虚拟用户反复执行完整业务链路。"""
    journey_index = 0
    end_time = start_time + duration_seconds if duration_seconds else None
    iterations = loop_count if mode == JOURNEY_LOOP_MODE else None
    sem_held = True

    def _release_sem_slot():
        nonlocal sem_held
        if sem_held:
            sem.release()
            sem_held = False

    async def _acquire_sem_slot():
        nonlocal sem_held
        if not sem_held:
            await sem.acquire()
            sem_held = True

    async def execute_step(phase_idx, step_idx, step_cfg, session_vars, csv_row=None):
        case = case_map.get(step_cfg["case_id"])
        if not case:
            return {
                "case_id": step_cfg["case_id"], "case_name": "未知", "status_code": 0,
                "response_time": 0, "success": False, "error_msg": "用例不存在",
                "response_size": 0, "request_size": 0,
            }, {}
        return await execute_perf_step(
            case, env, target_host, client, csv_row, worker_id,
            session_variables=session_vars,
            stream_profile=step_cfg.get("_stream_profile"),
        )

    while not stop_event.is_set():
        if iterations is not None and journey_index >= iterations:
            break
        if end_time is not None and time.time() >= end_time:
            break

        if stop_event.is_set():
            break
        await sem.acquire()
        sem_held = True
        try:
            if stop_event.is_set():
                break
            session_vars = {}
            csv_row = get_next_csv_row(
                record_id, csv_data, csv_strategy, worker_id, total_workers=active_users,
            ) if csv_data else None
            if csv_row:
                session_vars.update(csv_row)

            local_queue: list = []

            async def execute_step_bound(phase_idx, step_idx, step_cfg, session_vars):
                return await execute_step(phase_idx, step_idx, step_cfg, session_vars, csv_row)

            chain_ok, chain_duration, phase_summaries = await run_one_journey(
                journey=journey,
                worker_id=worker_id,
                journey_index=journey_index,
                session_vars=session_vars,
                sync=sync,
                active_users=active_users,
                execute_step=execute_step_bound,
                result_queue=local_queue,
                stream_profile_global=stream_profile_global,
                slot_release=_release_sem_slot,
                slot_acquire=_acquire_sem_slot,
                stop_event=stop_event,
            )
            for r in local_queue:
                result_queue.append(r)
            await journey_stats.record_journey(chain_ok, chain_duration, phase_summaries)
            journey_index += 1
            if journey_progress_ref is not None:
                journey_progress_ref["current"] = journey_progress_ref.get("current", 0) + 1

            delay_ms = journey.get("delay_between_journeys_ms", 0)
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000)
        finally:
            if sem_held:
                sem.release()
                sem_held = False


async def _run_journey_mode(
    record,
    case_map,
    env,
    config,
    stop_event,
    csv_data=None,
    csv_strategy="round_robin",
    record_id=None,
):
    """Journey 固定/循环模式执行。"""
    mode = normalize_perf_mode(config.get("mode", JOURNEY_FIXED_MODE))
    journey = normalize_journey_config(config)
    concurrent_users = config.get("concurrent_users", 1)
    ramp_up_seconds = config.get("ramp_up_seconds", 0)
    target_host = config.get("target_host")
    error_rate_threshold = config.get("error_rate_threshold", 0)
    stop_reason = [None]
    duration_seconds = config.get("duration_seconds", 60) if mode == JOURNEY_FIXED_MODE else None
    loop_count = config.get("loop_count", 100) if mode == JOURNEY_LOOP_MODE else None
    stream_profile_global = normalize_stream_profile(config) if has_stream_profile_config(config) else None
    has_stream_steps = any(
        s.get("use_stream") for p in journey.get("phases", []) for s in p.get("steps", [])
    )
    request_details = [] if (stream_profile_global or has_stream_steps) else None

    sem = asyncio.Semaphore(concurrent_users)
    result_queue = deque()
    streaming_stats = StreamingStats(max_samples=10000)
    case_stats = {}
    total_bytes_received = [0]
    total_bytes_sent = [0]
    error_stats = {"by_status_code": {}, "by_type": {}, "status_code_distribution": {}}
    failed_samples = []
    request_traces = []
    journey_stats = JourneyStatsCollector()
    sync = PhaseSyncCoordinator()
    journey_progress_ref = {"current": 0} if mode == JOURNEY_LOOP_MODE else None

    start_time = time.time()
    if mode == JOURNEY_FIXED_MODE:
        expected_end = start_time + (duration_seconds or 60)
    else:
        # journey_loop 同 loop：由 worker 次数驱动，聚合器等待 stop_event
        expected_end = start_time + 86400 * 7

    async with httpx.AsyncClient(follow_redirects=True) as client:
        aggregator_task = asyncio.create_task(
            _aggregator(record, result_queue, stop_event, expected_end, streaming_stats, case_stats,
                        total_bytes_received, total_bytes_sent, error_stats, failed_samples,
                        error_rate_threshold=error_rate_threshold, stop_reason=stop_reason,
                        request_details=request_details, request_traces=request_traces,
                        journey_progress_ref=journey_progress_ref)
        )

        worker_tasks = []
        spawn = lambda i: asyncio.create_task(
            _perf_worker_journey(
                i, case_map, env, target_host, journey, mode,
                duration_seconds, loop_count, stop_event, result_queue, sem,
                sync, journey_stats, concurrent_users, client,
                csv_data, csv_strategy, record_id, stream_profile_global, start_time,
                journey_progress_ref=journey_progress_ref,
            )
        )
        if ramp_up_seconds > 0 and concurrent_users > 1:
            interval = ramp_up_seconds / concurrent_users
            for i in range(concurrent_users):
                if stop_event.is_set():
                    break
                await asyncio.sleep(interval)
                worker_tasks.append(spawn(i))
        else:
            for i in range(concurrent_users):
                worker_tasks.append(spawn(i))

        if worker_tasks:
            await asyncio.gather(*worker_tasks, return_exceptions=True)

        await asyncio.sleep(2)
        stop_event.set()
        await aggregator_task

    actual_duration = time.time() - start_time
    preserved_status = await _load_preserved_status(record)
    _finalize_record(record, streaming_stats, case_stats, total_bytes_received, total_bytes_sent,
                     error_stats, actual_duration, start_time, failed_samples, stop_reason=stop_reason,
                     request_traces=request_traces, preserved_status=preserved_status)
    if request_details is not None:
        _apply_phase_metrics(record, request_details)

    journey_agg = journey_stats.to_aggregations()
    if isinstance(record.error_breakdown, dict):
        record.error_breakdown["journey_aggregations"] = journey_agg
    else:
        record.error_breakdown = {"journey_aggregations": journey_agg}

    if record_id:
        if mode == JOURNEY_LOOP_MODE:
            total = (loop_count or 0) * concurrent_users
            _running_progress[record_id] = {
                "mode": mode,
                "current": journey_agg.get("total_journeys", 0),
                "total": total,
                "percentage": round(min(100, journey_agg.get("total_journeys", 0) / total * 100), 1) if total else 0,
            }
        else:
            dur = duration_seconds or 60
            pct = min(100, round(actual_duration / dur * 100, 1))
            _running_progress[record_id] = {
                "mode": mode,
                "current": round(actual_duration, 1),
                "total": dur,
                "percentage": pct,
            }


async def run_perf_scene(record_id: int, use_workers: bool = False):
    """压测执行主函数（模式分发）
    use_workers: 是否尝试使用分布式 Worker 节点
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

    from app.core.data_tools.tag_service import merge_execution_variables
    from app.core.data_tools.inline_tools import ensure_dt_cache

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
    from app.core.header_merge import merge_request_headers

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

    # 分布式执行：有活跃 Worker 且用户选择使用
    if use_workers:
        if is_journey_mode(mode) and journey_has_sync_barrier(config):
            record.status = "failed"
            record.ended_at = datetime.now()
            record.error_breakdown = {
                "stop_reason": "分布式压测不支持 journey 阶段 sync_before 屏障，请关闭阶段同步或使用单机执行",
            }
            await record.save()
            return

        workers = await get_active_workers(scene.project_id)
        if len(workers) >= 1:
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

            if distribution_info["workers"]:
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
                return

    # 本地执行
    stop_event = asyncio.Event()
    _running_records[record_id] = stop_event

    record.status = "running"
    record.started_at = datetime.now()
    await record.save()

    mode = normalize_perf_mode(config.get("mode", "fixed"))

    try:
        if is_journey_mode(mode):
            await _run_journey_mode(record, case_map, env, config, stop_event, csv_data, csv_strategy, record_id)
        elif is_stream_burst_mode(mode):
            await _run_stream_burst_mode(record, scene_items, case_map, env, config, stop_event, csv_data, csv_strategy, record_id)
        elif mode == "loop":
            await _run_loop_mode(record, scene_items, case_map, env, config, stop_event, csv_data, csv_strategy, record_id)
        elif mode == "stepping":
            await _run_stepping_mode(record, scene_items, case_map, env, config, stop_event, csv_data, csv_strategy, record_id)
        else:
            await _run_fixed_mode(record, scene_items, case_map, env, config, stop_event, csv_data, csv_strategy, record_id)

        await record.save()
    except Exception as e:
        import traceback
        traceback.print_exc()
        record.status = "failed"
        record.ended_at = datetime.now()
        bd = record.error_breakdown if isinstance(record.error_breakdown, dict) else {}
        bd["stop_reason"] = f"执行异常: {e}"
        record.error_breakdown = bd
        await record.save()
    finally:
        _running_records.pop(record_id, None)
        _running_progress.pop(record_id, None)
        _clear_csv_row_pointers(record_id)
        await NotificationService.maybe_auto_push_perf_report(record_id)


# ========== HTTP APIs ==========

@router.post("/{scene_id}", summary="启动性能测试",
             dependencies=[Depends(require_permissions(PERF_SCENE_EXECUTE))])
async def start_perf(scene_id: int, env_id: int, background_tasks: BackgroundTasks,
                     use_workers: bool = False,
                     request_detail_level: str = "brief",
                     username: str = Depends(get_current_username)):
    """启动性能测试"""
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")

    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")

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

    background_tasks.add_task(run_perf_scene, record.id, use_workers)

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
