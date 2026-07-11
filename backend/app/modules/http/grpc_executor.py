"""gRPC 接口调试与用例执行（依赖 Server Reflection）"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.case.variable_resolver import VariableResolver
from app.modules.http.http_utils import extract_variables, replace_variables_with_detail


@dataclass
class GrpcResponseMock:
    status_code: int = 0
    headers: dict = field(default_factory=dict)
    body: Any = None


def merge_grpc_config(case, api) -> dict:
    cfg = getattr(api, "grpc_config", None) or {}
    if isinstance(api, dict):
        cfg = api.get("grpc_config") or {}
    if not isinstance(cfg, dict):
        cfg = {}
    return dict(cfg)


def merge_grpc_request_body(case, api) -> dict:
    body = getattr(case, "request_body", None)
    if body is None and isinstance(case, dict):
        body = case.get("request_body")
    if body:
        return body if isinstance(body, dict) else {}
    api_body = getattr(api, "body", None) or {}
    if isinstance(api, dict):
        api_body = api.get("body") or {}
    return api_body if isinstance(api_body, dict) else {}


def normalize_grpc_host(url: str) -> str:
    host = (url or "").strip()
    for prefix in ("grpc://", "grpcs://", "http://", "https://"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
            break
    return host.rstrip("/")


def _invoke_grpc_sync(
    host: str,
    *,
    service: str,
    method: str,
    full_method: str,
    request_json: dict,
    metadata: Optional[dict],
    timeout: int,
    use_tls: bool,
) -> dict:
    import grpc
    from google.protobuf import descriptor_pool, json_format
    from google.protobuf.message_factory import GetMessageClass
    from grpc_reflection.v1alpha.proto_reflection_descriptor_database import (
        ProtoReflectionDescriptorDatabase,
    )

    if not full_method:
        if not service or not method:
            raise ValueError("请在 grpc_config 中配置 full_method 或 service + method")
        full_method = f"/{service}/{method}" if not service.startswith("/") else f"{service}/{method}"
        if not full_method.startswith("/"):
            full_method = "/" + full_method.lstrip("/")

    channel = (
        grpc.secure_channel(host, grpc.ssl_channel_credentials())
        if use_tls
        else grpc.insecure_channel(host)
    )
    try:
        db = ProtoReflectionDescriptorDatabase(channel)
        pool = descriptor_pool.DescriptorPool(db)
        parts = full_method.strip("/").split("/")
        if len(parts) != 2:
            raise ValueError("full_method 格式应为 /package.Service/Method")
        service_name, method_name = parts
        service_desc = pool.FindServiceByName(service_name)
        method_desc = service_desc.FindMethodByName(method_name)
        request_class = GetMessageClass(method_desc.input_type)
        response_class = GetMessageClass(method_desc.output_type)
        request_msg = json_format.ParseDict(request_json or {}, request_class())
        md = [(k, str(v)) for k, v in (metadata or {}).items()]
        stub = channel.unary_unary(
            full_method,
            request_serializer=request_class.SerializeToString,
            response_deserializer=response_class.FromString,
        )
        response_msg = stub(request_msg, timeout=timeout, metadata=md)
        return json_format.MessageToDict(response_msg, preserving_proto_field_name=True)
    finally:
        channel.close()


async def execute_grpc_request(
    *,
    host: str,
    grpc_config: dict,
    request_json: dict,
    timeout: int = 30,
    variables: Optional[dict] = None,
    var_resolver: Optional[VariableResolver] = None,
) -> tuple[GrpcResponseMock, Any, float, Optional[str]]:
    variables = variables or {}
    if var_resolver is None:
        var_resolver = VariableResolver(variables)

    resolved_request, _ = replace_variables_with_detail(
        request_json or {},
        variables,
        "grpc.request",
        resolver=var_resolver,
    )
    if not isinstance(resolved_request, dict):
        resolved_request = {}

    metadata = grpc_config.get("metadata") or {}
    if isinstance(metadata, list):
        meta_dict = {}
        for item in metadata:
            if isinstance(item, dict) and item.get("key"):
                meta_dict[item["key"]] = item.get("value", "")
        metadata = meta_dict
    resolved_metadata, _ = replace_variables_with_detail(
        metadata,
        variables,
        "grpc.metadata",
        resolver=var_resolver,
    )

    _t0 = time.time()
    error = None
    response_body: Any = {}
    mock = GrpcResponseMock(status_code=0)
    try:
        response_body = await asyncio.to_thread(
            _invoke_grpc_sync,
            normalize_grpc_host(host),
            service=str(grpc_config.get("service") or ""),
            method=str(grpc_config.get("method") or ""),
            full_method=str(grpc_config.get("full_method") or ""),
            request_json=resolved_request,
            metadata=resolved_metadata if isinstance(resolved_metadata, dict) else {},
            timeout=timeout,
            use_tls=bool(grpc_config.get("use_tls")),
        )
        mock.body = response_body
    except Exception as exc:
        error = str(exc)
    elapsed_ms = round((time.time() - _t0) * 1000, 2)
    return mock, response_body, elapsed_ms, error


async def execute_grpc_case_attempt(
    *,
    host: str,
    case,
    api,
    all_variables: dict,
    var_resolver: VariableResolver,
    auto_validate_schema: bool = False,
    env_id: Optional[int] = None,
    script_logs: Optional[list] = None,
):
    from app.core.db.db_factory_service import evaluate_db_assertions
    from app.routers.http.utils import validate_response_schema
    from app.schemas.http import ApiAssertionResult

    script_logs = script_logs if script_logs is not None else []
    grpc_config = merge_grpc_config(case, api)
    request_json = merge_grpc_request_body(case, api)
    timeout = getattr(case, "timeout", None) or 30

    _t0 = time.time()
    response, response_body, request_ms, error = await execute_grpc_request(
        host=host,
        grpc_config=grpc_config,
        request_json=request_json,
        timeout=timeout,
        variables=all_variables,
        var_resolver=var_resolver,
    )
    if error:
        raise RuntimeError(error)

    class _RespAdapter:
        status_code = 0

        def json(self):
            return response_body

    resp_adapter = _RespAdapter()
    from app.routers.http.utils import run_case_assertions

    all_passed, assertion_rows, matched_group = run_case_assertions(resp_adapter, response_body, case)
    assertions_result = [
        ApiAssertionResult(
            type=row.get("type"),
            target=row.get("target"),
            operator=row.get("operator"),
            expected=row.get("expected"),
            actual=row.get("actual"),
            passed=row.get("passed"),
            group_name=row.get("group_name"),
            description=row.get("description"),
        )
        for row in assertion_rows
    ]
    if auto_validate_schema:
        schema_data = getattr(api, "response_schema", None) or {}
        if isinstance(api, dict):
            schema_data = api.get("response_schema") or {}
        schema_obj = schema_data.get("schema") if isinstance(schema_data, dict) else None
        if schema_obj:
            for sa in validate_response_schema(response_body, schema_obj):
                assertions_result.append(sa)
                if not sa.get("passed"):
                    all_passed = False

    extracted_vars, extractor_results = extract_variables(
        response_body,
        getattr(case, "extractors", None) or [],
        headers={},
    )

    if getattr(case, "post_script", None):
        from app.routers.http.script_runner import run_script

        resp_ctx = {"status_code": 0, "body": response_body, "headers": {}}
        script_vars = {**all_variables, **extracted_vars}
        post_result = run_script(case.post_script, script_vars, resp_ctx)
        for key, val in post_result["variables"].items():
            if key not in all_variables or val != all_variables.get(key):
                extracted_vars[key] = val
                all_variables[key] = val
        script_logs.extend(post_result["logs"])
        if post_result["error"]:
            script_logs.append(f"[post_script ERROR] {post_result['error']}")

    db_assertion_results = []
    if getattr(case, "db_assertions", None):
        script_vars = {**all_variables, **extracted_vars}
        db_eval = await evaluate_db_assertions(
            case.db_assertions or [],
            script_vars,
            env_id,
            case.project_id,
        )
        for dr in db_eval.get("results", []):
            db_assertion_results.append(
                ApiAssertionResult(
                    type="db",
                    target=dr.get("target"),
                    operator=dr.get("operator", "equals"),
                    expected=dr.get("expected"),
                    actual=dr.get("actual"),
                    passed=bool(dr.get("passed")),
                )
            )
            if not dr.get("passed"):
                all_passed = False

    last_attempt_timings = {
        "request_ms": request_ms,
        "assertion_ms": round((time.time() - _t0) * 1000 - request_ms, 2),
    }
    if matched_group:
        last_attempt_timings["assertion_group"] = matched_group

    return (
        response,
        response_body,
        assertions_result,
        all_passed,
        extracted_vars,
        extractor_results,
        db_assertion_results,
        last_attempt_timings,
        None,
    )
