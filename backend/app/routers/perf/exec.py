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

from app.models.perf import PerfScene, PerfRecord
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
)
from app.core.variable_resolver import VariableResolver
from app.routers.perf.report_utils import build_rt_histogram

router = APIRouter(prefix="/exec", tags=["性能测试执行"])

# 全局运行中任务管理: {record_id: asyncio.Event}
_running_records: Dict[int, asyncio.Event] = {}
# 全局进度跟踪: {record_id: {"mode": "fixed", "current": 30, "total": 60, "percentage": 50.0}}
_running_progress: Dict[int, Dict] = {}

# CSV 参数化行指针（按 record_id）
_csv_row_pointers: Dict[int, int] = {}


def _replace_csv_vars(data, csv_row: dict):
    """递归替换 {{csv.column_name}} 为 CSV 值"""
    if not csv_row:
        return data
    if isinstance(data, dict):
        return {k: _replace_csv_vars(v, csv_row) for k, v in data.items()}
    if isinstance(data, list):
        return [_replace_csv_vars(item, csv_row) for item in data]
    if isinstance(data, str):
        import re
        def replacer(m):
            key = m.group(1).strip()
            return str(csv_row.get(key, m.group(0)))
        return re.sub(r'\{\{\s*csv\.([\w_]+)\s*\}\}', replacer, data)
    return data


def get_next_csv_row(record_id: int, csv_data: list, strategy: str, worker_index: int = 0) -> Optional[dict]:
    """获取下一行 CSV 数据"""
    if not csv_data:
        return None
    row_count = len(csv_data)

    if strategy == "round_robin":
        ptr = _csv_row_pointers.get(record_id, 0)
        row = csv_data[ptr % row_count]
        _csv_row_pointers[record_id] = ptr + 1
        return row

    elif strategy == "unique":
        # 单机模式下所有请求共享一个全局指针，unique 策略退化为"顺序取行，不循环到已用过的行"
        ptr = _csv_row_pointers.get(record_id, 0)
        if ptr >= row_count:
            ptr = 0
        row = csv_data[ptr]
        _csv_row_pointers[record_id] = ptr + 1
        return row

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

async def build_perf_request(case: ApiTestCase, env: Environment, target_host: Optional[str] = None, csv_row: Optional[dict] = None):
    """
    构建性能测试请求参数（复用现有逻辑，不写数据库）
    返回: (method, url, headers, params, body, timeout, body_type)
    """
    api = case.api
    if not api:
        raise ValueError(f"用例 {case.id} 关联接口不存在")

    project_obj = await Project.get_or_none(id=case.project_id, is_del=False)
    project_global_vars = (project_obj.global_vars or {}) if project_obj else {}
    env_vars = env.global_vars or {}
    all_variables = {**project_global_vars, **env_vars}

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
    csv_row: Optional[dict] = None
):
    """
    执行单个请求，返回结果字典
    返回: {case_id, case_name, status_code, response_time, success, error_msg, response_size}
    当传入 client 时复用连接池，否则每次新建 client（兼容其他调用方）
    """
    try:
        method, url, headers, params, body, timeout, body_type = await build_perf_request(case, env, target_host, csv_row)
    except Exception as e:
        return {
            "case_id": case.id,
            "case_name": case.name,
            "status_code": 0,
            "response_time": 0,
            "success": False,
            "error_msg": f"请求构建失败: {str(e)}",
            "response_size": 0,
            "request_size": 0
        }

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

        return {
            "case_id": case.id,
            "case_name": case.name,
            "status_code": response.status_code,
            "response_time": response_time,
            "success": success,
            "error_msg": error_msg,
            "response_size": response_size,
            "request_size": request_size
        }

    try:
        if client is not None:
            return await _do_request(client)
        else:
            async with httpx.AsyncClient(follow_redirects=True) as temp_client:
                return await _do_request(temp_client)
    except httpx.TimeoutException:
        return {
            "case_id": case.id,
            "case_name": case.name,
            "status_code": 0,
            "response_time": (time.time() - start_time) * 1000,
            "success": False,
            "error_msg": "timeout",
            "response_size": 0,
            "request_size": request_size
        }
    except Exception as e:
        return {
            "case_id": case.id,
            "case_name": case.name,
            "status_code": 0,
            "response_time": (time.time() - start_time) * 1000,
            "success": False,
            "error_msg": str(e),
            "response_size": 0,
            "request_size": request_size
        }


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
    record_id: int = None
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

            # CSV 参数化
            csv_row = get_next_csv_row(record_id, csv_data, csv_strategy, worker_id) if csv_data else None
            result = await execute_single_request(case, env, target_host, client=client, csv_row=csv_row)
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
    record_id: int = None
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

            # CSV 参数化
            csv_row = get_next_csv_row(record_id, csv_data, csv_strategy, worker_id) if csv_data else None
            result = await execute_single_request(case, env, target_host, client=client, csv_row=csv_row)
            result_queue.append(result)

            # 更新进度计数
            if progress_ref is not None:
                progress_ref["current"] = progress_ref.get("current", 0) + 1

            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000)


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
    stop_reason: list = None
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
    mode = config.get("mode", "fixed")
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

    while time.time() < expected_end_time + 2:
        if stop_event.is_set() and not result_queue:
            break

        await asyncio.sleep(1)

        second_results = []
        while result_queue:
            r = result_queue.popleft()
            second_results.append(r)
            streaming_stats.add(r["response_time"])
            total_bytes_received[0] += r.get("response_size", 0)
            total_bytes_sent[0] += r.get("request_size", 0)
            _update_case_stats(case_stats, r)
            _update_error_stats(error_stats, r)
            # 收集失败请求采样（内存中，不存数据库）
            if not r.get("success") and len(failed_samples) < max_samples:
                failed_samples.append({
                    "case_id": r.get("case_id"),
                    "case_name": r.get("case_name", "未知"),
                    "status_code": r.get("status_code", 0),
                    "response_time": round(r.get("response_time", 0), 2),
                    "error_msg": (r.get("error_msg") or "")[:500]
                })

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
            else:  # stepping
                steps = config.get("steps", [])
                total_d = sum(s.get("duration", 30) for s in steps) or 60
                pct = min(100, round(elapsed / total_d * 100, 1))
                _running_progress[record_id] = {
                    "mode": "stepping",
                    "current": round(elapsed, 1),
                    "total": total_d,
                    "percentage": pct
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


def _update_case_stats(case_stats: Dict[int, dict], result: dict, max_case_samples: int = 5000):
    """更新单用例统计（带蓄水池采样控制每个用例的rts上限）"""
    cid = result["case_id"]
    if cid not in case_stats:
        case_stats[cid] = {
            "name": result["case_name"],
            "total": 0, "success": 0, "fail": 0, "rts": [],
            "rt_count": 0  # 用于蓄水池采样的计数器
        }
    case_stats[cid]["total"] += 1
    if result["success"]:
        case_stats[cid]["success"] += 1
    else:
        case_stats[cid]["fail"] += 1
    if result["response_time"] > 0:
        rt = result["response_time"]
        rts = case_stats[cid]["rts"]
        case_stats[cid]["rt_count"] = case_stats[cid].get("rt_count", 0) + 1
        count = case_stats[cid]["rt_count"]
        if len(rts) < max_case_samples:
            rts.append(rt)
        else:
            j = random.randint(0, count - 1)
            if j < max_case_samples:
                rts[j] = rt


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
    result = {}
    for cid, stats in case_stats.items():
        rts = stats["rts"]
        result[str(cid)] = {
            "name": stats["name"],
            "total": stats["total"],
            "success": stats["success"],
            "fail": stats["fail"],
            "error_rate": round(stats["fail"] / stats["total"] * 100, 2) if stats["total"] > 0 else 0,
            "avg_rt": round(sum(rts) / len(rts), 2) if rts else 0,
            "min_rt": round(min(rts), 2) if rts else 0,
            "max_rt": round(max(rts), 2) if rts else 0,
            "median_rt": round(float(np.median(rts)), 2) if rts else 0,
            "p90_rt": round(float(np.percentile(rts, 90)), 2) if rts else 0,
            "p95_rt": round(float(np.percentile(rts, 95)), 2) if rts else 0,
            "p99_rt": round(float(np.percentile(rts, 99)), 2) if rts else 0,
            "std_dev": round(float(np.std(rts)), 2) if rts else 0,
        }
    return result


# ========== 最终聚合计算 ==========

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
    stop_reason: list = None
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
    # 根据停止原因设置状态
    if stop_reason and stop_reason[0] == "error_rate_threshold":
        record.status = "stopped"
        if isinstance(record.error_breakdown, dict):
            record.error_breakdown["stop_reason"] = "错误率连续3秒超过阈值，已自动停止"
    else:
        record.status = "success" if fail == 0 else "failed"
    record.case_aggregations = _build_case_aggregations(case_stats)
    record.error_breakdown = error_stats
    
    # 失败请求采样（存入 JSON 字段，最多50条）
    if failed_samples:
        # 如果 error_breakdown 中没有 failed_samples，添加进去
        if isinstance(record.error_breakdown, dict):
            record.error_breakdown["failed_samples"] = failed_samples

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


# ========== 三种模式执行入口 ==========

async def _run_fixed_mode(record, scene_items, case_map, env, config, stop_event, csv_data=None, csv_strategy="round_robin", record_id=None):
    """固定模式执行"""
    concurrent_users = config.get("concurrent_users", 1)
    ramp_up_seconds = config.get("ramp_up_seconds", 0)
    duration_seconds = config.get("duration_seconds", 60)
    target_host = config.get("target_host")
    distribution_mode = config.get("distribution_mode", "weighted_random")
    error_rate_threshold = config.get("error_rate_threshold", 0)
    stop_reason = [None]

    sem = asyncio.Semaphore(concurrent_users)
    result_queue = deque()
    streaming_stats = StreamingStats(max_samples=10000)
    case_stats = {}
    total_bytes_received = [0]
    total_bytes_sent = [0]
    error_stats = {"by_status_code": {}, "by_type": {}, "status_code_distribution": {}}
    failed_samples = []

    case_cycle = _build_case_cycle(scene_items) if distribution_mode == "fixed_ratio" else None

    start_time = time.time()
    expected_end = start_time + duration_seconds

    # 复用 httpx client（连接池）
    async with httpx.AsyncClient(follow_redirects=True) as client:
        aggregator_task = asyncio.create_task(
            _aggregator(record, result_queue, stop_event, expected_end, streaming_stats, case_stats,
                        total_bytes_received, total_bytes_sent, error_stats, failed_samples,
                        error_rate_threshold=error_rate_threshold, stop_reason=stop_reason)
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
                                       case_cycle, client, csv_data, csv_strategy, record_id)
                )
                worker_tasks.append(task)
        else:
            for i in range(concurrent_users):
                task = asyncio.create_task(
                    _perf_worker_fixed(i, scene_items, case_map, env, target_host,
                                       duration_seconds, stop_event, result_queue, sem, start_time,
                                       case_cycle, client, csv_data, csv_strategy, record_id)
                )
                worker_tasks.append(task)

        if worker_tasks:
            await asyncio.gather(*worker_tasks, return_exceptions=True)

        await asyncio.sleep(2)
        stop_event.set()
        await aggregator_task

    actual_duration = time.time() - start_time
    _finalize_record(record, streaming_stats, case_stats, total_bytes_received, total_bytes_sent,
                     error_stats, actual_duration, start_time, failed_samples, stop_reason=stop_reason)


async def _run_loop_mode(record, scene_items, case_map, env, config, stop_event, csv_data=None, csv_strategy="round_robin", record_id=None):
    """循环模式执行"""
    concurrent_users = config.get("concurrent_users", 1)
    ramp_up_seconds = config.get("ramp_up_seconds", 0)
    loop_count = config.get("loop_count", 100)
    target_host = config.get("target_host")
    distribution_mode = config.get("distribution_mode", "weighted_random")
    error_rate_threshold = config.get("error_rate_threshold", 0)
    stop_reason = [None]

    sem = asyncio.Semaphore(concurrent_users)
    result_queue = deque()
    streaming_stats = StreamingStats(max_samples=10000)
    case_stats = {}
    total_bytes_received = [0]
    total_bytes_sent = [0]
    error_stats = {"by_status_code": {}, "by_type": {}, "status_code_distribution": {}}
    failed_samples = []

    case_cycle = _build_case_cycle(scene_items) if distribution_mode == "fixed_ratio" else None

    start_time = time.time()
    # 预估最大持续时间（用于聚合器）
    expected_max_duration = max(loop_count * 0.5, 60)  # 更合理的预估
    expected_end = start_time + expected_max_duration

    # 复用 httpx client（连接池）
    async with httpx.AsyncClient(follow_redirects=True) as client:
        aggregator_task = asyncio.create_task(
            _aggregator(record, result_queue, stop_event, expected_end, streaming_stats, case_stats,
                        total_bytes_received, total_bytes_sent, error_stats, failed_samples,
                        error_rate_threshold=error_rate_threshold, stop_reason=stop_reason)
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
                                      csv_data=csv_data, csv_strategy=csv_strategy, record_id=record_id)
                )
                worker_tasks.append(task)
        else:
            for i in range(concurrent_users):
                task = asyncio.create_task(
                    _perf_worker_loop(i, scene_items, case_map, env, target_host,
                                      loop_count, stop_event, result_queue, sem, case_cycle, client,
                                      csv_data=csv_data, csv_strategy=csv_strategy, record_id=record_id)
                )
                worker_tasks.append(task)

        if worker_tasks:
            await asyncio.gather(*worker_tasks, return_exceptions=True)

        await asyncio.sleep(2)
        stop_event.set()
        await aggregator_task

    actual_duration = time.time() - start_time
    _finalize_record(record, streaming_stats, case_stats, total_bytes_received, total_bytes_sent,
                     error_stats, actual_duration, start_time, failed_samples, stop_reason=stop_reason)


async def _run_stepping_mode(record, scene_items, case_map, env, config, stop_event, csv_data=None, csv_strategy="round_robin", record_id=None):
    """梯度模式执行"""
    steps = config.get("steps", [])
    target_host = config.get("target_host")
    distribution_mode = config.get("distribution_mode", "weighted_random")
    error_rate_threshold = config.get("error_rate_threshold", 0)
    stop_reason = [None]

    if not steps:
        record.status = "failed"
        await record.save()
        return

    # 创建足够大的 Semaphore（最大并发数）
    max_users = max(s.get("users", 1) for s in steps)
    sem = asyncio.Semaphore(max_users)

    result_queue = deque()
    streaming_stats = StreamingStats(max_samples=10000)
    case_stats = {}
    total_bytes_received = [0]
    total_bytes_sent = [0]
    error_stats = {"by_status_code": {}, "by_type": {}, "status_code_distribution": {}}
    failed_samples = []

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
                        error_rate_threshold=error_rate_threshold, stop_reason=stop_reason)
        )

        # 动态调整 Semaphore：创建一个可动态调整的信号量包装
        active_workers = {}  # {worker_id: task}
        worker_counter = [0]

        # 预计算随机权重
        _weights = [item.get("weight", 1) for item in scene_items] if not case_cycle else None

        # 为每个 worker 创建启动事件，用事件通知替代轮询 sleep
        worker_events = {}  # {worker_id: asyncio.Event}

        async def stepping_worker(wid, case_pool, c_map, e, th, stop_evt, rq, s, cycle=None, csv_data=None, csv_strategy="round_robin", rec_id=None):
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
                if wid >= current_limit[0]:
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

                # CSV 参数化
                csv_row = get_next_csv_row(rec_id, csv_data, csv_strategy, wid) if csv_data else None
                result = await execute_single_request(case, e, th, client=client, csv_row=csv_row)
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
                               csv_data=csv_data, csv_strategy=csv_strategy, rec_id=record_id)
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
    _finalize_record(record, streaming_stats, case_stats, total_bytes_received, total_bytes_sent,
                     error_stats, actual_duration, start_time, failed_samples, stop_reason=stop_reason)


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

    env_id = config.get("env_id")
    env = await Environment.get_or_none(id=env_id, is_del=False) if env_id else None
    if not env:
        record.status = "failed"
        await record.save()
        return

    project = await Project.get_or_none(id=scene.project_id, is_del=False)
    project_global_vars = (project.global_vars or {}) if project else {}

    # 预加载用例（含关联接口，避免每次请求查DB）
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
    csv_data = scene.csv_data if scene else None
    csv_config = scene.csv_config if scene else {}
    csv_strategy = csv_config.get("strategy", "round_robin") if csv_config.get("enabled") else "round_robin"

    # 构建带断言和 api 信息的 scene_items（供 Worker 使用，不修改快照）
    from app.core.header_merge import merge_request_headers

    scene_items_for_worker = []
    for item in scene_items:
        case = case_map.get(item["case_id"])
        enriched = dict(item)
        if case:
            enriched["name"] = case.name or ""
            enriched["assertions"] = case.assertions or []
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
                        "csv_strategy": csv_strategy
                    },
                    "assigned_concurrent": assigned,
                    "worker_index": workers.index(worker),
                    "total_workers": len(workers),
                    "env_host": env.host,
                    "target_host": target_host,
                    "project_global_vars": project_global_vars,
                    "env_global_vars": env.global_vars or {},
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
                # 等待 Worker 执行完成（通过轮询或超时）
                max_duration = 3600  # 最大等待1小时
                waited = 0
                while waited < max_duration:
                    await asyncio.sleep(5)
                    waited += 5
                    # 检查是否所有 Worker 都已完成
                    busy_workers = await get_active_workers()
                    busy_workers = [w for w in busy_workers if w.current_record_id == record_id]
                    if not busy_workers:
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

    mode = config.get("mode", "fixed")

    try:
        if mode == "loop":
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
        await record.save()
    finally:
        _running_records.pop(record_id, None)
        _running_progress.pop(record_id, None)
        _csv_row_pointers.pop(record_id, None)
        await NotificationService.maybe_auto_push_perf_report(record_id)


# ========== HTTP APIs ==========

@router.post("/{scene_id}", summary="启动性能测试",
             dependencies=[Depends(require_permissions(PERF_SCENE_EXECUTE))])
async def start_perf(scene_id: int, env_id: int, background_tasks: BackgroundTasks,
                     use_workers: bool = False, username: str = Depends(get_current_username)):
    """启动性能测试"""
    scene = await PerfScene.get_or_none(id=scene_id, is_del=False)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")

    env = await Environment.get_or_none(id=env_id, is_del=False)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")

    config = scene.config or {}
    config["env_id"] = env_id

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
        record.status = "stopped"
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
