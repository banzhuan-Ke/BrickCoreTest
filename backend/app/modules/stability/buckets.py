"""失败桶：映射既有 failure_code / HTTP 状态 / 文案，不另起平行枚举。"""
from __future__ import annotations

from typing import Any

BUCKET_ENV_TIMEOUT = "env_timeout"
BUCKET_LOCATOR_INTERCEPT = "locator_intercept"
BUCKET_ASSERT = "assert"
BUCKET_HTTP_SERVER = "http_server"
BUCKET_CANCELLED = "cancelled"
BUCKET_OTHER = "other"

BUCKET_LABELS = {
    BUCKET_ENV_TIMEOUT: "环境/等待超时",
    BUCKET_LOCATOR_INTERCEPT: "定位/拦截",
    BUCKET_ASSERT: "断言失败",
    BUCKET_HTTP_SERVER: "被测服务异常",
    BUCKET_CANCELLED: "取消",
    BUCKET_OTHER: "其他",
}

_ENV_TIMEOUT_CODES = frozenset({
    "BUSY_TIMEOUT",
    "READY_TIMEOUT",
    "ACTION_TIMEOUT",
    "STEP_BUDGET_EXHAUSTED",
})
_CANCELLED_CODES = frozenset({"CANCELLED", "CANCELED"})
_LOCATOR_CODES = frozenset({
    "LOCATOR_NOT_FOUND",
    "POINTER_INTERCEPT",
    "HEAL_FAILED",
    "HEAL_EXHAUSTED",
    "ELEMENT_NOT_FOUND",
    "INTERCEPT",
})
_ASSERT_CODES = frozenset({
    "ASSERT_FAILED",
    "ASSERTION_FAILED",
    "SCHEMA_FAILED",
    "DB_ASSERT_FAILED",
})

_TIMEOUT_HINTS = (
    "timeout",
    "timed out",
    "超时",
    "read timed out",
    "connect timeout",
    "busy_timeout",
    "ready_timeout",
)
_LOCATOR_HINTS = (
    "locator",
    "selector",
    "element not found",
    "intercept",
    "拦截",
    "定位",
    "not found",
    "strict mode violation",
)
_ASSERT_HINTS = (
    "assert",
    "assertion",
    "断言",
    "schema",
    "expected",
    "db assertion",
)


def _norm_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _norm_text(value: Any) -> str:
    return str(value or "").strip().lower()


def bucket_label(bucket: str | None) -> str:
    if not bucket:
        return BUCKET_LABELS[BUCKET_OTHER]
    return BUCKET_LABELS.get(bucket, BUCKET_LABELS[BUCKET_OTHER])


def map_failure_bucket(
    *,
    failure_code: Any = None,
    response_status: Any = None,
    error_msg: Any = None,
    status: Any = None,
) -> str:
    code = _norm_code(failure_code)
    if code in _CANCELLED_CODES:
        return BUCKET_CANCELLED
    if code in _ENV_TIMEOUT_CODES:
        return BUCKET_ENV_TIMEOUT
    if code in _LOCATOR_CODES:
        return BUCKET_LOCATOR_INTERCEPT
    if code in _ASSERT_CODES:
        return BUCKET_ASSERT

    try:
        http_status = int(response_status) if response_status is not None else None
    except (TypeError, ValueError):
        http_status = None
    if http_status is not None and 500 <= http_status <= 599:
        return BUCKET_HTTP_SERVER

    text = " ".join(filter(None, [_norm_text(error_msg), _norm_text(status), _norm_text(code)]))
    if any(h in text for h in ("cancel", "已取消", "cancelled")):
        return BUCKET_CANCELLED
    if any(h in text for h in _TIMEOUT_HINTS):
        return BUCKET_ENV_TIMEOUT
    if any(h in text for h in _ASSERT_HINTS):
        return BUCKET_ASSERT
    if any(h in text for h in _LOCATOR_HINTS):
        return BUCKET_LOCATOR_INTERCEPT
    return BUCKET_OTHER


def extract_ui_failure_code(result_data: Any) -> str | None:
    """从 UI/App result_data 取主导 failure_code（首个失败步骤）。"""
    if not isinstance(result_data, dict):
        return None
    code = result_data.get("failure_code")
    if code:
        return str(code)
    steps = result_data.get("steps") or []
    fail_statuses = {"fail", "failed", "error"}
    for step in steps:
        if not isinstance(step, dict):
            continue
        st = str(step.get("status") or "").strip().lower()
        if st in fail_statuses and step.get("failure_code"):
            return str(step.get("failure_code"))
    for step in steps:
        if isinstance(step, dict) and step.get("failure_code"):
            return str(step.get("failure_code"))
    return None


def extract_api_failure_code(
    *,
    request_detail: Any = None,
    assertions_result: Any = None,
    error_msg: Any = None,
) -> str | None:
    """从 API run 的 request_detail / assertions 取 failure_code。"""
    detail = request_detail if isinstance(request_detail, dict) else {}
    code = detail.get("failure_code")
    if code:
        return str(code)
    asserts = assertions_result
    if not asserts:
        asserts = detail.get("assertions_result") or detail.get("assertions") or []
    if isinstance(asserts, list):
        for a in asserts:
            if not isinstance(a, dict) or a.get("passed") is not False:
                continue
            t = str(a.get("type") or "").strip().lower()
            if "schema" in t:
                return "SCHEMA_FAILED"
            return "ASSERT_FAILED"
    text = _norm_text(error_msg or detail.get("error_msg"))
    if any(h in text for h in _ASSERT_HINTS):
        if "schema" in text:
            return "SCHEMA_FAILED"
        return "ASSERT_FAILED"
    return None


def extract_ui_error_msg(result_data: Any, fallback: Any = None) -> str:
    if isinstance(result_data, dict):
        for key in ("error_msg", "error", "message"):
            val = result_data.get(key)
            if val:
                return str(val)
        steps = result_data.get("steps") or []
        for step in steps:
            if not isinstance(step, dict):
                continue
            st = str(step.get("status") or "").strip().lower()
            if st in {"fail", "failed", "error"}:
                msg = step.get("message") or step.get("error") or step.get("error_msg")
                if msg:
                    return str(msg)
    return str(fallback or "")
