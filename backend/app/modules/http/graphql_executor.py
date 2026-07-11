"""GraphQL 接口调试与用例执行"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from app.core.case.variable_resolver import VariableResolver
from app.modules.http.http_utils import extract_variables, replace_variables_with_detail


@dataclass
class GraphqlResponseMock:
    status_code: int = 200
    headers: dict = field(default_factory=dict)
    text: str = ""

    def json(self):
        import json

        return json.loads(self.text) if self.text else {}


def build_graphql_payload(body: Any) -> dict:
    if isinstance(body, dict):
        payload = dict(body)
        if payload.get("query"):
            return payload
    if isinstance(body, str) and body.strip():
        return {"query": body.strip()}
    return {"query": "", "variables": {}}


def merge_graphql_body(case, api) -> dict:
    body = getattr(case, "request_body", None)
    if body is None and isinstance(case, dict):
        body = case.get("request_body")
    if body:
        return build_graphql_payload(body)
    api_body = getattr(api, "body", None) or {}
    if isinstance(api, dict):
        api_body = api.get("body") or {}
    return build_graphql_payload(api_body)


async def execute_graphql_request(
    *,
    url: str,
    headers: dict,
    payload: dict,
    timeout: int = 30,
    variables: Optional[dict] = None,
    var_resolver: Optional[VariableResolver] = None,
) -> tuple[GraphqlResponseMock, Any, float, Optional[str]]:
    variables = variables or {}
    if var_resolver is None:
        var_resolver = VariableResolver(variables)

    resolved_payload, _ = replace_variables_with_detail(payload, variables, "graphql.body", resolver=var_resolver)
    if not isinstance(resolved_payload, dict):
        resolved_payload = build_graphql_payload(resolved_payload)

    req_headers = dict(headers or {})
    req_headers.setdefault("Content-Type", "application/json")

    _t0 = time.time()
    error = None
    response_body: Any = {}
    mock = GraphqlResponseMock()
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.post(url, headers=req_headers, json=resolved_payload)
            mock.status_code = resp.status_code
            mock.headers = dict(resp.headers)
            mock.text = resp.text
            try:
                response_body = resp.json()
            except Exception:
                response_body = resp.text
    except Exception as exc:
        error = str(exc)
    elapsed_ms = round((time.time() - _t0) * 1000, 2)
    return mock, response_body, elapsed_ms, error


async def execute_graphql_case_attempt(
    *,
    url: str,
    headers: dict,
    case,
    api,
    all_variables: dict,
    var_resolver: VariableResolver,
    auto_validate_schema: bool = False,
    env_id: Optional[int] = None,
    script_logs: Optional[list] = None,
):
    from app.core.db.db_factory_service import evaluate_db_assertions
    from app.routers.http.utils import run_case_assertions, validate_response_schema
    from app.schemas.http import ApiAssertionResult

    script_logs = script_logs if script_logs is not None else []
    payload = merge_graphql_body(case, api)
    timeout = getattr(case, "timeout", None) or 30

    _t0 = time.time()
    response, response_body, request_ms, error = await execute_graphql_request(
        url=url,
        headers=headers if isinstance(headers, dict) else {},
        payload=payload,
        timeout=timeout,
        variables=all_variables,
        var_resolver=var_resolver,
    )
    if error:
        raise RuntimeError(error)

    all_passed, assertion_rows, matched_group = run_case_assertions(response, response_body, case)
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
        headers=response.headers,
    )

    if getattr(case, "post_script", None):
        from app.routers.http.script_runner import run_script

        resp_ctx = {
            "status_code": response.status_code,
            "body": response_body,
            "headers": response.headers,
        }
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
