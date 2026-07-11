"""WebSocket 接口调试与用例执行"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import websockets

from app.core.case.variable_resolver import VariableResolver
from app.modules.http.http_utils import (
    assert_values_equal,
    extract_variables,
    get_json_path_value,
    replace_variables_with_detail,
)


@dataclass
class WsResponseMock:
    """模拟 HTTP Response，供断言/变量提取复用"""

    status_code: int = 101
    headers: dict = field(default_factory=dict)
    messages: list = field(default_factory=list)

    @property
    def body(self) -> dict:
        return build_ws_response_body(self.messages)


def build_ws_response_body(messages: List[dict]) -> dict:
    received = [m.get("content", "") for m in messages if m.get("direction") == "received"]
    last = received[-1] if received else ""
    parsed_last: Any = last
    if last:
        try:
            parsed_last = json.loads(last)
        except Exception:
            parsed_last = last
    return {
        "messages": received,
        "last": last,
        "parsed_last": parsed_last,
        "count": len(received),
        "combined": "\n".join(received),
    }


def ensure_ws_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith(("ws://", "wss://")):
        return url
    if url.startswith("http://"):
        return "ws://" + url[7:]
    if url.startswith("https://"):
        return "wss://" + url[8:]
    return url


def normalize_ws_headers(headers) -> dict:
    if isinstance(headers, dict):
        return {k: str(v) for k, v in headers.items() if k}
    if isinstance(headers, list):
        out = {}
        for h in headers:
            if not isinstance(h, dict):
                continue
            key = h.get("key") or h.get("name")
            if key and h.get("enabled", True) is not False:
                out[key] = str(h.get("value", ""))
        return out
    return {}


def merge_ws_steps(case, api) -> list:
    case_steps = getattr(case, "ws_steps", None) or []
    if isinstance(case, dict):
        case_steps = case.get("ws_steps") or []
    if case_steps:
        return case_steps
    ws_config = getattr(api, "ws_config", None) or {}
    if isinstance(api, dict):
        ws_config = api.get("ws_config") or {}
    if isinstance(ws_config, dict):
        return ws_config.get("steps") or ws_config.get("messages") or []
    return []


def resolve_ws_steps(steps: list, variables: dict, var_resolver: VariableResolver) -> list:
    resolved = []
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        item = dict(step)
        if "message" in item:
            msg, _ = replace_variables_with_detail(
                item["message"], variables, "ws.message", resolver=var_resolver
            )
            item["message"] = msg
        resolved.append(item)
    return resolved


async def execute_ws_steps(
    url: str,
    headers: Optional[dict] = None,
    steps: Optional[list] = None,
    timeout: int = 30,
    variables: Optional[dict] = None,
    var_resolver: Optional[VariableResolver] = None,
) -> Tuple[List[dict], Optional[str], float]:
    headers = normalize_ws_headers(headers or {})
    steps = steps or []
    variables = variables or {}
    if var_resolver is None:
        var_resolver = VariableResolver(variables)
    steps = resolve_ws_steps(steps, variables, var_resolver)

    ws_url = ensure_ws_url(url)
    message_log: List[dict] = []
    start = time.time()

    try:
        async with websockets.connect(
            ws_url,
            additional_headers=headers,
            open_timeout=timeout,
            close_timeout=5,
        ) as ws:
            message_log.append(
                {
                    "direction": "info",
                    "content": f"Connected to {ws_url}",
                    "timestamp": time.time(),
                }
            )

            for step in steps:
                action = (step.get("action") or "send").lower()
                if action == "wait":
                    delay = int(step.get("delay_ms") or step.get("delay") or 0)
                    if delay > 0:
                        await asyncio.sleep(delay / 1000.0)
                    continue
                if action == "send":
                    msg = step.get("message", "")
                    msg_type = (step.get("message_type") or "text").lower()
                    if msg_type == "json" and isinstance(msg, (dict, list)):
                        payload = json.dumps(msg, ensure_ascii=False)
                    else:
                        payload = str(msg) if msg is not None else ""
                    await ws.send(payload)
                    message_log.append(
                        {"direction": "sent", "content": payload, "timestamp": time.time()}
                    )
                    delay = int(step.get("delay_ms") or 0)
                    if delay > 0:
                        await asyncio.sleep(delay / 1000.0)
                elif action == "receive":
                    count = max(int(step.get("count") or 1), 1)
                    recv_timeout = float(step.get("timeout") or timeout)
                    per_wait = max(recv_timeout / count, 0.5)
                    for _ in range(count):
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=per_wait)
                            content = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                            message_log.append(
                                {
                                    "direction": "received",
                                    "content": content,
                                    "timestamp": time.time(),
                                }
                            )
                        except asyncio.TimeoutError as exc:
                            raise TimeoutError(
                                f"等待 WebSocket 消息超时（{recv_timeout}s）"
                            ) from exc
                elif action == "close":
                    await ws.close()
                    message_log.append(
                        {
                            "direction": "info",
                            "content": "Connection closed",
                            "timestamp": time.time(),
                        }
                    )
                    break
    except Exception as exc:
        elapsed = (time.time() - start) * 1000
        return message_log, str(exc), elapsed

    elapsed = (time.time() - start) * 1000
    return message_log, None, elapsed


def evaluate_ws_assertion(response_body: dict, assertion: dict) -> Tuple[bool, Any]:
    assertion_type = assertion.get("type") or ""
    operator = assertion.get("operator") or "contains"
    expected = assertion.get("expected")
    target = assertion.get("target")

    if assertion_type == "ws_message_count":
        actual = response_body.get("count", 0)
    elif assertion_type == "ws_contains":
        actual = response_body.get("combined", "")
        if operator == "equals":
            return str(actual) == str(expected), actual
        if operator == "not_equals":
            return str(actual) != str(expected), actual
        if operator == "not_contains":
            return str(expected) not in str(actual), actual
        return str(expected) in str(actual), actual
    elif assertion_type == "ws_json_path":
        parsed = response_body.get("parsed_last")
        actual = get_json_path_value(parsed, target)
    elif assertion_type == "contains":
        actual = response_body.get("combined", "")
        if operator == "not_contains":
            return str(expected) not in str(actual), actual
        return str(expected) in str(actual), actual
    elif assertion_type == "json_path":
        parsed = response_body.get("parsed_last")
        actual = get_json_path_value(parsed, target)
    elif assertion_type == "status_code":
        actual = 101
    else:
        return False, None

    if operator == "equals":
        return assert_values_equal(actual, expected), actual
    if operator == "not_equals":
        return not assert_values_equal(actual, expected), actual
    if operator == "contains":
        return str(expected) in str(actual), actual
    if operator == "not_contains":
        return str(expected) not in str(actual), actual
    if operator == "gt":
        try:
            return float(actual) > float(expected), actual
        except Exception:
            return False, actual
    if operator == "gte":
        try:
            return float(actual) >= float(expected), actual
        except Exception:
            return False, actual
    if operator == "lt":
        try:
            return float(actual) < float(expected), actual
        except Exception:
            return False, actual
    if operator == "lte":
        try:
            return float(actual) <= float(expected), actual
        except Exception:
            return False, actual
    return False, actual


def run_ws_assertions(response_body: dict, case) -> Tuple[bool, list, Optional[str]]:
    assertions = getattr(case, "assertions", None)
    if assertions is None and isinstance(case, dict):
        assertions = case.get("assertions") or []
    else:
        assertions = assertions or []

    results = []
    all_passed = True
    for assertion in assertions:
        passed, actual = evaluate_ws_assertion(response_body, assertion)
        results.append(
            {
                "type": assertion.get("type"),
                "target": assertion.get("target"),
                "operator": assertion.get("operator"),
                "expected": assertion.get("expected"),
                "actual": actual,
                "passed": passed,
                "group_name": None,
                "description": assertion.get("description"),
            }
        )
        if not passed:
            all_passed = False
    return all_passed, results, None


async def execute_ws_case_attempt(
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
    """执行一次 WS 用例，返回与 HTTP _execute_once 相同结构"""
    from app.schemas.http import ApiAssertionResult
    from app.core.db.db_factory_service import evaluate_db_assertions

    script_logs = script_logs if script_logs is not None else []
    steps = merge_ws_steps(case, api)
    timeout = getattr(case, "timeout", None) or 30

    _t0 = time.time()
    message_log, error, elapsed_ms = await execute_ws_steps(
        url=url,
        headers=headers,
        steps=steps,
        timeout=timeout,
        variables=all_variables,
        var_resolver=var_resolver,
    )
    request_ms = round(elapsed_ms, 2)

    if error:
        raise RuntimeError(error)

    ws_response = WsResponseMock(messages=message_log)
    response_body = ws_response.body

    all_passed, assertion_rows, _ = run_ws_assertions(response_body, case)
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

    extracted_vars, extractor_results = extract_variables(
        response_body.get("parsed_last") or response_body,
        getattr(case, "extractors", None) or [],
        headers=ws_response.headers,
    )

    if getattr(case, "post_script", None):
        from app.routers.http.script_runner import run_script

        resp_ctx = {
            "status_code": ws_response.status_code,
            "body": response_body,
            "headers": ws_response.headers,
            "messages": message_log,
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

    return (
        ws_response,
        response_body,
        assertions_result,
        all_passed,
        extracted_vars,
        extractor_results,
        db_assertion_results,
        last_attempt_timings,
        message_log,
    )
