"""套件整包经执行机：步骤组装、下发、收齐后断言落库。

契约见 docs/设计文档/api-suite-via-worker-plan.md。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from app.models.http import ApiRunRecord, ApiSuiteRunRecord, ApiTestCase
from app.models.sys import Environment, Project
from app.modules.http.worker_http_proxy import (
    MAX_WORKER_TASK_JSON_BYTES,
    MIN_API_SUITE_ENGINE,
    WorkerProxyError,
    form_data_has_file,
    prepare_body_fields_for_worker,
    require_api_proxy_worker,
    serialize_body_fields,
    strip_multipart_content_type,
    headers_to_plain_dict,
    append_query_params,
)
from app.core.runner.runner_version import compare_version
from app.schemas.http import ApiAssertionResult, ApiRunResult

SUITE_FAIL_HINT = (
    "可取消勾选「经执行机发送」后改由平台本机重跑，或升级执行机引擎后再试"
)
BATCH_SIZE_DEFAULT = 10


def require_api_suite_engine(worker) -> None:
    engine_ver = (getattr(worker, "engine_version", None) or "").strip()
    if not engine_ver or compare_version(engine_ver, MIN_API_SUITE_ENGINE) < 0:
        raise WorkerProxyError(
            f"套件整包经执行机需要引擎 ≥ {MIN_API_SUITE_ENGINE}"
            f"（当前 {engine_ver or '未知'}），请更新 BrickCorePerf / Runner。"
            f"{SUITE_FAIL_HINT}",
            400,
        )


def estimate_suite_task_bytes(task: dict) -> int:
    """整包体积：覆盖所有 step 的 url/headers/body/body_fields（含 b64）。"""
    size = 8192
    for step in task.get("steps") or []:
        if not isinstance(step, dict):
            continue
        size += len(str(step.get("url") or "").encode("utf-8"))
        try:
            size += len(json.dumps(step.get("headers") or {}, ensure_ascii=False, default=str).encode("utf-8"))
        except Exception:
            size += 1024
        try:
            size += len(json.dumps(step.get("params") or {}, ensure_ascii=False, default=str).encode("utf-8"))
        except Exception:
            size += 512
        body = step.get("body")
        if isinstance(body, (bytes, bytearray)):
            size += len(body)
        elif body not in (None, ""):
            try:
                size += len(json.dumps(body, ensure_ascii=False, default=str).encode("utf-8"))
            except Exception:
                size += len(str(body).encode("utf-8"))
        for item in step.get("body_fields") or []:
            if not isinstance(item, dict):
                continue
            b64 = item.get("file_content_b64")
            if b64:
                size += len(b64)
            else:
                size += len(str(item.get("value") or "").encode("utf-8"))
        try:
            size += len(json.dumps(step.get("extractors") or [], ensure_ascii=False, default=str).encode("utf-8"))
        except Exception:
            size += 256
    try:
        size += len(json.dumps(task.get("variables") or {}, ensure_ascii=False, default=str).encode("utf-8"))
    except Exception:
        size += 2048
    return size


def build_wire_http_fields(
    *,
    method: str,
    url: str,
    headers: dict,
    params: Optional[dict],
    body: Any,
    body_type: str,
    body_fields: list,
) -> dict[str, Any]:
    """与 api_debug 共用的发送层字段归一化（拼装完成后调用）。"""
    final_url = append_query_params(url, params)
    header_dict = headers_to_plain_dict(headers)
    bt = (body_type or "json").strip().lower()
    if bt == "form-data":
        header_dict = strip_multipart_content_type(header_dict)
    return {
        "method": (method or "GET").upper(),
        "url": final_url,
        "headers": header_dict,
        "body": body,
        "body_type": body_type or "json",
        "body_fields": body_fields or [],
    }


async def _build_case_step_skeleton(
    *,
    case: ApiTestCase,
    env: Environment,
    index: int,
    data_run_index: Optional[int] = None,
    data_row_label: Optional[str] = None,
    row_vars: Optional[dict] = None,
) -> dict[str, Any]:
    """组装步骤模板（保留 {{var}}；文件字段嵌入 b64）。GraphQL 在平台包成 JSON POST。"""
    from app.core.shared.header_merge import merge_request_headers
    from app.modules.http.http_utils import build_api_url, resolve_body_fields
    from app.modules.http.graphql_executor import merge_graphql_body

    api = await case.api
    if not api:
        return {
            "index": index,
            "case_id": case.id,
            "case_name": case.name,
            "protocol": "http",
            "unsupported": True,
            "error": "关联接口不存在",
            "data_run_index": data_run_index,
            "data_row_label": data_row_label,
        }

    protocol = (getattr(api, "protocol", None) or "http").strip().lower()
    if protocol in ("websocket", "grpc"):
        return {
            "index": index,
            "case_id": case.id,
            "case_name": case.name,
            "protocol": protocol,
            "unsupported": True,
            "error": f"经执行机整包暂不支持 {protocol} 用例",
            "data_run_index": data_run_index,
            "data_row_label": data_row_label,
            "assertions": case.assertions or [],
            "assertion_groups": case.assertion_groups or [],
        }

    headers = merge_request_headers(
        api_headers=api.headers,
        case_headers=case.request_headers,
    )
    from app.modules.stability.request_id import ensure_request_id

    headers, request_id = ensure_request_id(headers if isinstance(headers, dict) else {})
    api_params = api.params or []
    if isinstance(api_params, dict):
        api_params = [{"name": k, "value": v} for k, v in api_params.items()]
    case_params = case.request_params or []
    if isinstance(case_params, dict):
        case_params = [{"name": k, "value": v} for k, v in case_params.items()]

    base_url = headers.pop("base_url", None) if isinstance(headers, dict) else None
    if not base_url and isinstance(case.request_headers, dict):
        base_url = case.request_headers.get("base_url")
    base_url = base_url or api.base_url or env.host
    try:
        url = build_api_url(base_url, api.path, protocol=protocol if protocol != "graphql" else "http")
    except ValueError as e:
        return {
            "index": index,
            "case_id": case.id,
            "case_name": case.name,
            "protocol": protocol,
            "unsupported": True,
            "error": str(e),
            "data_run_index": data_run_index,
            "data_row_label": data_row_label,
        }

    if case_params:
        params = {p.get("name", ""): p.get("value", "") for p in case_params if p.get("name")}
    else:
        params = {p.get("name", ""): p.get("value", "") for p in api_params if p.get("name")}

    body = case.request_body if case.request_body else (api.body or {})
    body_type = case.request_body_type or api.body_type or "json"
    body_fields = resolve_body_fields(case.request_body_fields, api.body_fields)
    method = (api.method or "GET").upper()

    if protocol == "graphql":
        body = merge_graphql_body(case, api)
        body_type = "json"
        method = "POST"
        if isinstance(headers, dict):
            headers = dict(headers)
            headers.setdefault("Content-Type", "application/json")

    # 文件在下发前嵌入（与 api_debug 一致）
    if (body_type or "").strip().lower() == "form-data" and form_data_has_file(body_fields):
        body_fields = await asyncio.to_thread(
            prepare_body_fields_for_worker, body_type, body_fields
        )
    else:
        body_fields = serialize_body_fields(body_fields)

    wire = build_wire_http_fields(
        method=method,
        url=url,
        headers=headers if isinstance(headers, dict) else {},
        params=params,
        body=body,
        body_type=body_type,
        body_fields=body_fields,
    )

    return {
        "index": index,
        "case_id": case.id,
        "case_name": case.name,
        "protocol": "http" if protocol == "graphql" else protocol,
        "graphql": protocol == "graphql",
        "unsupported": False,
        "timeout": int(case.timeout or 30),
        "retry_count": int(case.retry_count or 0),
        "extractors": case.extractors or [],
        "assertions": case.assertions or [],
        "assertion_groups": case.assertion_groups or [],
        "data_run_index": data_run_index,
        "data_row_label": data_row_label,
        "row_vars": dict(row_vars or {}),
        "request_id": request_id,
        **wire,
    }


async def assemble_suite_steps(
    *,
    case_ids: list[int],
    env: Environment,
    suite_retry_count: int = 0,
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    index = 0
    for case_id in case_ids:
        case = await ApiTestCase.get_or_none(id=case_id, is_del=False)
        if not case:
            steps.append({
                "index": index,
                "case_id": case_id,
                "case_name": f"#{case_id}",
                "unsupported": True,
                "case_missing": True,
                "error": "用例不存在",
            })
            index += 1
            continue
        data_set = case.data_set or []
        if not data_set:
            step = await _build_case_step_skeleton(case=case, env=env, index=index)
            if suite_retry_count and not step.get("retry_count"):
                step["retry_count"] = suite_retry_count
            steps.append(step)
            index += 1
            continue
        for row_i, row in enumerate(data_set):
            row_vars = dict(row) if isinstance(row, dict) else {}
            label = ",".join(f"{k}={v}" for k, v in list(row_vars.items())[:3])[:80]
            step = await _build_case_step_skeleton(
                case=case,
                env=env,
                index=index,
                data_run_index=row_i,
                data_row_label=label or f"row-{row_i}",
                row_vars=row_vars,
            )
            if suite_retry_count and not step.get("retry_count"):
                step["retry_count"] = suite_retry_count
            steps.append(step)
            index += 1
    return steps


def _without_file_b64(fields) -> list:
    out = []
    for item in fields or []:
        if not isinstance(item, dict):
            continue
        out.append({k: v for k, v in item.items() if k != "file_content_b64"})
    return out


def build_suite_request_detail(step: dict, item: dict) -> dict:
    """报告详情：original 为下发模板，final 优先用执行机替换后的实际请求。"""
    if "final_url" in item and item.get("final_url") is not None:
        final_url = item.get("final_url") or ""
    else:
        final_url = step.get("url") or ""
    final_headers = item.get("final_headers")
    if not isinstance(final_headers, dict):
        final_headers = step.get("headers") or {}
    if "final_body" in item:
        final_body = item.get("final_body")
    else:
        final_body = step.get("body")
    final_fields = item.get("final_body_fields")
    if not isinstance(final_fields, list):
        final_fields = step.get("body_fields") or []
    from app.modules.stability.request_id import get_request_id, set_request_id

    request_id = str(step.get("request_id") or "").strip() or get_request_id(final_headers) or get_request_id(
        step.get("headers") or {}
    )
    detail = {
        "via_worker": True,
        "via_worker_suite": True,
        "url": {"original": step.get("url") or "", "final": final_url},
        "headers": {"original": step.get("headers") or {}, "final": final_headers},
        "body": {"original": step.get("body"), "final": final_body},
        "body_type": step.get("body_type"),
        "body_fields": {
            "original": _without_file_b64(step.get("body_fields")),
            "final": _without_file_b64(final_fields),
        },
    }
    if request_id:
        detail["request_id"] = request_id
        # 与落库顶层 request_headers 对齐；set_request_id 会去掉大小写同义键再写规范键
        if isinstance(final_headers, dict):
            detail["headers"] = {
                **(detail.get("headers") or {}),
                "final": set_request_id(final_headers, request_id),
            }
    return detail


def merge_suite_extracted_vars(runner_extracted: dict, platform_extracted: dict) -> dict:
    """平台提取用于报告明细；链式值以执行机为准（后续步骤已按此消费）。"""
    return {**(platform_extracted or {}), **(runner_extracted or {})}


class _RespMock:
    def __init__(self, status_code: int, headers: dict, body: Any, text: str):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body
        self.text = text

    def json(self):
        if isinstance(self._body, (dict, list)):
            return self._body
        if not self.text:
            return {}
        return json.loads(self.text)


async def _finalize_step_to_record(
    *,
    step: dict,
    item: dict,
    suite_record: Optional[ApiSuiteRunRecord],
    username: str,
    project_id: int,
    auto_validate_schema: bool,
) -> ApiRunResult:
    from app.modules.http.http_utils import run_case_assertions, extract_variables

    case_id = step.get("case_id")
    case_name = step.get("case_name") or ""
    err = item.get("error") or step.get("error")
    status_code = int(item.get("status_code") or 0)
    headers = dict(item.get("headers") or {})
    body = item.get("body")
    elapsed = float(item.get("time") or 0)
    extracted = dict(item.get("extracted_vars") or {})

    if isinstance(body, (dict, list)):
        response_body = body
        text = json.dumps(body, ensure_ascii=False)
    else:
        text = "" if body is None else str(body)
        response_body = body
        try:
            response_body = json.loads(text) if text else {}
        except Exception:
            response_body = text

    response = _RespMock(status_code, headers, response_body, text)
    assertions_result: list = []
    all_passed = True
    extractor_results: list = []

    if err:
        all_passed = False
    else:
        case_like = {
            "assertions": step.get("assertions") or [],
            "assertion_groups": step.get("assertion_groups") or [],
        }
        all_passed, raw_asserts, _ = run_case_assertions(response, response_body, case_like)
        for a in raw_asserts:
            assertions_result.append(ApiAssertionResult(
                type=a.get("type") or "",
                target=a.get("target"),
                operator=a.get("operator") or "",
                expected=a.get("expected"),
                actual=a.get("actual"),
                passed=bool(a.get("passed")),
                group_name=a.get("group_name"),
                description=a.get("description"),
            ))
        if step.get("extractors"):
            extracted2, extractor_results = extract_variables(
                response_body, step.get("extractors"), headers=headers
            )
            extracted = merge_suite_extracted_vars(extracted, extracted2)

    status = "success" if all_passed and not err else "failed"
    request_detail = build_suite_request_detail(step, item)
    response_detail = {
        "status_code": status_code,
        "headers": headers,
        "body": response_body,
        "time": elapsed,
        "size": int(item.get("size") or 0),
    }

    final_url = (request_detail.get("url") or {}).get("final") or ""
    final_headers = (request_detail.get("headers") or {}).get("final") or {}
    body_for_db = (request_detail.get("body") or {}).get("final")
    if isinstance(body_for_db, (dict, list)):
        body_for_db = json.dumps(body_for_db, ensure_ascii=False)
    resp_for_db = response_body
    if isinstance(resp_for_db, (dict, list)):
        resp_for_db = json.dumps(resp_for_db, ensure_ascii=False)
    elif isinstance(resp_for_db, str) and len(resp_for_db) > 500000:
        resp_for_db = resp_for_db[:500000]

    persist = True
    try:
        cid = int(case_id) if case_id not in (None, "") else 0
    except (TypeError, ValueError):
        cid = 0
    if step.get("case_missing") or cid <= 0:
        persist = False
        if not err:
            err = "用例不存在"
            status = "failed"
    elif not await ApiTestCase.filter(id=cid, is_del=False).exists():
        persist = False
        if not err:
            err = "用例不存在"
            status = "failed"

    record_id = 0
    if persist:
        record_data = {
            "case_id": cid,
            "project_id": project_id,
            "status": status,
            "request_url": str(final_url)[:1000],
            "request_method": (step.get("method") or "")[:10],
            "request_headers": final_headers if isinstance(final_headers, dict) else {},
            "request_body": body_for_db,
            "response_status": status_code or None,
            "response_headers": headers,
            "response_body": resp_for_db,
            "response_time": elapsed,
            "error_msg": err,
            "assertions_result": [a.model_dump() if hasattr(a, "model_dump") else a for a in assertions_result],
            "extracted_vars": extracted,
            "request_detail": {**request_detail, "response_detail": response_detail},
            "run_by": username or "",
            "data_run_index": step.get("data_run_index"),
            "data_row_label": step.get("data_row_label"),
        }
        if suite_record is not None:
            record_data["suite_run_record_id"] = suite_record.id
        record = await ApiRunRecord.create(**record_data)
        record_id = record.id

    return ApiRunResult(
        record_id=record_id,
        status=status,
        response_status=status_code or None,
        response_time=elapsed,
        http_response_time=elapsed,
        assertions=assertions_result,
        extracted_vars=extracted,
        extractor_results=extractor_results,
        error=err,
        request_detail=request_detail,
        response_detail=response_detail,
        case_id=case_id,
        case_name=case_name,
        data_run_index=step.get("data_run_index"),
        data_row_label=step.get("data_row_label"),
    )


async def execute_suite_via_worker(
    *,
    suite,
    env: Environment,
    case_ids: list[int],
    suite_record: Optional[ApiSuiteRunRecord],
    username: str,
    variables: dict,
    project_global_vars: Optional[dict],
    auto_validate_schema: bool,
    stop_on_failure: bool,
    worker_id: int,
) -> dict[str, Any]:
    """整包下发 + 分批收齐 + 断言落库。超时/未齐包：丢弃已收批不写记录。"""
    from app.modules.data_tools.tag_service import merge_execution_variables
    from app.modules.http.api_auth_service import inject_auth_variables
    from app.core.shared.global_vars_validate import flatten_global_vars
    from app.routers.perf import api_suite_bridge
    from app.routers.perf.workers import send_task_to_worker
    from app.routers.perf import worker_queue

    worker = await require_api_proxy_worker(suite.project_id, worker_id)
    require_api_suite_engine(worker)

    proj_vars = project_global_vars or {}
    if not proj_vars:
        proj = await Project.get_or_none(id=suite.project_id, is_del=False)
        proj_vars = (proj.global_vars or {}) if proj else {}
    all_variables = {
        **flatten_global_vars(proj_vars),
        **flatten_global_vars(env.global_vars or {}),
        **(variables or {}),
    }
    all_variables = await merge_execution_variables(suite.project_id, env.id, all_variables)
    auth_vars, auth_err = await inject_auth_variables(
        suite.project_id, env.id, all_variables, worker_id=worker_id
    )
    if auth_err:
        raise WorkerProxyError(f"授权刷新失败: {auth_err}。{SUITE_FAIL_HINT}", 400)
    if auth_vars:
        all_variables.update(auth_vars)

    steps = await assemble_suite_steps(
        case_ids=case_ids,
        env=env,
        suite_retry_count=int(getattr(suite, "retry_count", 0) or 0),
    )
    if not steps:
        return {
            "success_count": 0,
            "failed_count": 0,
            "case_results": [],
            "accumulated_vars": all_variables,
            "suite_mode": "api_suite",
        }

    has_files = any(
        form_data_has_file(s.get("body_fields"))
        for s in steps
        if not s.get("unsupported")
    )
    # 文件门禁已由整包 ≥ 1.6.2 覆盖；has_files 仅用于下方等待超时加成

    suite_run_id = api_suite_bridge.new_suite_run_id()
    task = {
        "task_type": "api_suite",
        "suite_run_id": suite_run_id,
        "record_id": suite_record.id if suite_record else None,
        "total": len(steps),
        "stop_on_fail": bool(stop_on_failure),
        "batch_size": BATCH_SIZE_DEFAULT,
        "variables": all_variables,
        "steps": steps,
    }
    payload_bytes = estimate_suite_task_bytes(task)
    if payload_bytes > MAX_WORKER_TASK_JSON_BYTES:
        raise WorkerProxyError(
            f"整包任务过大（约 {payload_bytes // (1024 * 1024)}MB），"
            f"上限约 {MAX_WORKER_TASK_JSON_BYTES // (1024 * 1024)}MB，请拆套件或减小 form-data 文件。"
            f"{SUITE_FAIL_HINT}",
            400,
        )

    await api_suite_bridge.register_suite(suite_run_id, len(steps))
    ok = await send_task_to_worker(worker, task)
    if not ok:
        await api_suite_bridge.cancel_suite(suite_run_id)
        busy = await worker_queue.has_pending_task(worker.id)
        raise WorkerProxyError(
            ("下发整包任务失败（执行机任务队列占用），" if busy else "下发整包任务失败，")
            + SUITE_FAIL_HINT,
            503,
        )

    # 等待：单步超时累加 + 缓冲
    sum_timeout = sum(max(1, int(s.get("timeout") or 30)) for s in steps if not s.get("unsupported"))
    wait_timeout = max(60.0, float(sum_timeout + 60 + len(steps) * 2))
    if has_files:
        wait_timeout += 60

    state = None
    try:
        state = await api_suite_bridge.wait_suite(suite_run_id, wait_timeout)
    finally:
        try:
            await worker_queue.clear_task_if_match(
                worker.id,
                task_type="api_suite",
                id_field="suite_run_id",
                id_value=suite_run_id,
            )
        except Exception:
            pass
        from app.routers.perf.workers import release_worker_after_proxy_task

        await release_worker_after_proxy_task(
            worker.id,
            record_id=suite_record.id if suite_record else None,
        )

    if state is None:
        raise WorkerProxyError(
            f"等待执行机整包结果超时或未齐包（suite_run_id={suite_run_id}）。{SUITE_FAIL_HINT}",
            408,
        )
    if state.fatal_error:
        # 未齐或致命：丢弃
        raise WorkerProxyError(
            f"执行机整包失败: {state.fatal_error}。{SUITE_FAIL_HINT}",
            400,
        )

    expected = state.expected_count() or 0
    if expected <= 0 or len(state.items) < expected:
        raise WorkerProxyError(
            f"整包结果未齐（收到 {len(state.items)}/{expected}）。{SUITE_FAIL_HINT}",
            408,
        )

    # stop_on_fail 或正常完成：保留已收批，写记录
    case_results: list[ApiRunResult] = []
    success_count = 0
    failed_count = 0
    accumulated = dict(all_variables)
    for i in range(expected):
        step = steps[i] if i < len(steps) else {"index": i, "case_id": None, "case_name": ""}
        item = state.items.get(i) or {"index": i, "error": "缺少步骤结果"}
        accumulated.update(item.get("extracted_vars") or {})
        # 合并行变量到提取（报告用）
        if step.get("row_vars"):
            accumulated.update(step["row_vars"])
        result = await _finalize_step_to_record(
            step=step,
            item=item,
            suite_record=suite_record,
            username=username,
            project_id=suite.project_id,
            auto_validate_schema=auto_validate_schema,
        )
        case_results.append(result)
        if result.status == "success":
            success_count += 1
        else:
            failed_count += 1

    return {
        "success_count": success_count,
        "failed_count": failed_count,
        "case_results": case_results,
        "accumulated_vars": accumulated,
        "suite_mode": "api_suite",
        "stopped_at": state.stopped_at,
        "suite_run_id": suite_run_id,
    }
