"""
测试失败上下文采集：接口 / UI 执行记录 → Prompt 变量 + Vision 截图
"""
from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any, Optional

from app.core.infra.minio_client import minio_client
from app.modules.ui.ui_result_extract import (
    extract_ui_case_failure_summary,
    find_failed_step,
    normalize_result_data,
)
from app.models.http import ApiRunRecord
from app.models.ui import UiCaseExecution
from app.models.app import AppCaseExecution

FAIL_STEP_STATUSES = frozenset({"fail", "failed", "error"})
SENSITIVE_HEADER_KEYS = frozenset(
    {"authorization", "cookie", "set-cookie", "x-api-key", "token", "x-auth-token"}
)

MAX_BODY_CHARS = 8000
MAX_LOG_CHARS = 4000
MAX_STEPS_JSON_CHARS = 48000


def _serialize_steps_for_prompt(step_summaries: list[dict[str, Any]]) -> str:
    """优先保留全量标题；超长时先压非邻域 message，再压 detail，最后才截字符串。"""
    text = json.dumps(step_summaries, ensure_ascii=False, default=str)
    if len(text) <= MAX_STEPS_JSON_CHARS:
        return text
    slim = []
    for item in step_summaries:
        if not isinstance(item, dict):
            continue
        row = {
            "index": item.get("index"),
            "keyword": item.get("keyword"),
            "status": item.get("status"),
        }
        if item.get("detail"):
            row["detail"] = True
            row["message"] = str(item.get("message") or "")[:200]
        slim.append(row)
    text = json.dumps(slim, ensure_ascii=False, default=str)
    if len(text) <= MAX_STEPS_JSON_CHARS:
        return text
    outline = [
        {"index": x.get("index"), "keyword": x.get("keyword"), "status": x.get("status")}
        for x in slim
        if isinstance(x, dict)
    ]
    return _truncate(json.dumps(outline, ensure_ascii=False), MAX_STEPS_JSON_CHARS)
# 失败步前后保留详细 message；其余步骤只放标题/状态，不丢步骤清单
DETAIL_STEP_RADIUS = 5
MAX_OUTLINE_KEYWORD = 80
MAX_DETAIL_MESSAGE = 600


def _truncate(value: Any, max_len: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = text or ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 20] + "\n…（已截断）"


def _step_title(step: dict[str, Any]) -> str:
    return str(step.get("keyword") or step.get("name") or "")[:MAX_OUTLINE_KEYWORD]


def _build_step_summaries(
    steps: list[Any],
    failed_idx: int,
    *,
    extra_keys: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """全量步骤标题 + 失败邻域详述。不因条数丢掉中间步骤。"""
    if not isinstance(steps, list) or not steps:
        return []
    step_summaries: list[dict[str, Any]] = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        near = failed_idx < 0 or abs(i - failed_idx) <= DETAIL_STEP_RADIUS
        item: dict[str, Any] = {
            "index": i + 1,
            "keyword": _step_title(step),
            "status": step.get("status") or "",
        }
        if near:
            item["detail"] = True
            item["message"] = str(
                step.get("message") or step.get("desc") or step.get("content") or ""
            )[:MAX_DETAIL_MESSAGE]
            for key in extra_keys:
                if step.get(key) is not None:
                    item[key] = step.get(key)
        step_summaries.append(item)
    return step_summaries


def _mask_headers(headers: Any) -> dict:
    if not isinstance(headers, dict):
        return {}
    masked: dict[str, Any] = {}
    for key, val in headers.items():
        k = str(key).lower()
        masked[key] = "***" if k in SENSITIVE_HEADER_KEYS else val
    return masked


def extract_minio_object_name(url: str) -> Optional[str]:
    """从 MinIO 静态 URL 或预签名 URL 提取 object name"""
    if not url or not isinstance(url, str):
        return None
    bucket = minio_client.bucket_name
    marker = f"/{bucket}/"
    if marker in url:
        return urllib.parse.unquote(url.split(marker, 1)[-1].split("?")[0])
    if url.startswith("http"):
        path = urllib.parse.urlparse(url).path.lstrip("/")
        if path.startswith(f"{bucket}/"):
            return urllib.parse.unquote(path[len(bucket) + 1 :].split("?")[0])
        return urllib.parse.unquote(path.split("?")[0]) or None
    return urllib.parse.unquote(url.lstrip("/").split("?")[0]) or None


def _guess_image_mime(object_name: str) -> str:
    lower = (object_name or "").lower()
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".gif"):
        return "image/gif"
    return "image/png"


def load_image_from_url(url: str) -> Optional[tuple[bytes, str]]:
    """从 MinIO 下载截图二进制"""
    object_name = extract_minio_object_name(url)
    if not object_name:
        return None
    data = minio_client.download_object(object_name)
    if not data:
        return None
    return data, _guess_image_mime(object_name)


def collect_step_screenshots_around_failure(
    steps: list,
    failed_idx: int,
    *,
    lookback: int = 2,
    lookahead: int = 2,
) -> list[tuple[int, str]]:
    """收集失败步前后上下文截图 URL（1-based 步骤号，默认 ±2 步）。"""
    if failed_idx < 0 or not steps:
        return []
    items: list[tuple[int, str]] = []
    start = max(0, failed_idx - lookback)
    end = min(len(steps) - 1, failed_idx + lookahead)
    for i in range(start, end + 1):
        step = steps[i] if i < len(steps) and isinstance(steps[i], dict) else None
        if not step:
            continue
        shot = step.get("screenshot") or step.get("image")
        if shot:
            items.append((i + 1, str(shot)))
    return items


def load_context_images(
    steps: list,
    failed_idx: int,
    *,
    lookback: int = 2,
    lookahead: int = 2,
    fallback_url: Optional[str] = None,
) -> list[tuple[bytes, str, str]]:
    """加载失败上下文多张截图，返回 (bytes, mime, caption)。"""
    shot_items = collect_step_screenshots_around_failure(
        steps, failed_idx, lookback=lookback, lookahead=lookahead
    )
    if not shot_items and fallback_url:
        shot_items = [(failed_idx + 1 if failed_idx >= 0 else 0, fallback_url)]
    images: list[tuple[bytes, str, str]] = []
    for step_no, url in shot_items:
        loaded = load_image_from_url(url)
        if loaded:
            images.append((loaded[0], loaded[1], f"第{step_no}步截图"))
    return images


def _pick_failure_screenshot(result_data: dict, failed_step: Optional[dict]) -> Optional[str]:
    if failed_step:
        shot = failed_step.get("screenshot") or failed_step.get("image")
        if shot:
            return str(shot)
    for step in reversed(result_data.get("steps") or []):
        if not isinstance(step, dict):
            continue
        status = str(step.get("status") or "").lower()
        if status in FAIL_STEP_STATUSES:
            shot = step.get("screenshot") or step.get("image")
            if shot:
                return str(shot)
    if result_data.get("img") or result_data.get("img_url"):
        return str(result_data.get("img") or result_data.get("img_url"))
    return None


def _format_assertions(assertions: Any) -> str:
    if not isinstance(assertions, list):
        return "[]"
    lines = []
    for item in assertions:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("field") or "断言"
        passed = item.get("passed")
        expected = item.get("expected")
        actual = item.get("actual")
        msg = item.get("message") or item.get("error") or ""
        lines.append(
            f"- {name}: passed={passed}, expected={expected}, actual={actual}, message={msg}"
        )
    return "\n".join(lines) if lines else "（无断言明细）"


async def build_api_failure_context(record: ApiRunRecord) -> dict[str, Any]:
    """采集接口执行失败上下文"""
    case = await record.case
    req_detail = record.request_detail if isinstance(record.request_detail, dict) else {}
    logs_parts = [
        f"断言结果:\n{_format_assertions(record.assertions_result)}",
        f"提取变量: {json.dumps(record.extracted_vars or {}, ensure_ascii=False)}",
    ]
    if req_detail.get("retry_info"):
        logs_parts.append(f"重试信息: {_truncate(req_detail.get('retry_info'), 1500)}")
    if req_detail.get("pre_script_error"):
        logs_parts.append(f"前置脚本错误: {req_detail.get('pre_script_error')}")
    if req_detail.get("post_script_error"):
        logs_parts.append(f"后置脚本错误: {req_detail.get('post_script_error')}")

    from app.modules.stability.buckets import extract_api_failure_code, map_failure_bucket
    from app.modules.stability.request_id import extract_request_id_from_detail

    request_id = extract_request_id_from_detail(req_detail, record.request_headers)
    failure_code = extract_api_failure_code(
        request_detail=req_detail,
        assertions_result=getattr(record, "assertions_result", None),
        error_msg=record.error_msg,
    ) or ""
    failure_bucket = map_failure_bucket(
        failure_code=failure_code or None,
        response_status=record.response_status,
        error_msg=record.error_msg,
        status=record.status,
    )

    return {
        "target_type": "api",
        "case_name": case.name if case else "未知用例",
        "request_method": record.request_method or "",
        "request_url": record.request_url or "",
        "request_headers": _truncate(_mask_headers(record.request_headers), 2000),
        "request_body": _truncate(record.request_body or "", MAX_BODY_CHARS),
        "response_status": record.response_status or "",
        "response_body": _truncate(record.response_body or "", MAX_BODY_CHARS),
        "error_msg": _truncate(record.error_msg or "", 2000),
        "logs": _truncate("\n".join(logs_parts), MAX_LOG_CHARS),
        "screenshot_desc": "",
        "steps": "",
        "failed_step_index": "",
        "record_status": record.status or "",
        "request_id": request_id,
        "failure_code": failure_code,
        "failure_bucket": failure_bucket,
    }


async def build_ui_failure_context(
    execution: UiCaseExecution,
) -> tuple[dict[str, Any], list[tuple[bytes, str, str]], Optional[str]]:
    """
    采集 UI 执行失败上下文
    返回 (prompt_vars, context_images, primary_screenshot_url)
    """
    result_data = normalize_result_data(execution.result_data)
    summary = extract_ui_case_failure_summary(result_data)
    steps = result_data.get("steps") or []
    failed_idx, failed_step = find_failed_step(steps)
    screenshot_url = _pick_failure_screenshot(result_data, failed_step)

    step_summaries = _build_step_summaries(
        steps,
        failed_idx,
        extra_keys=("locator_healed", "ai_act", "heal_retry_status"),
    )

    error_msg = summary.get("error_hint") or ""
    if not error_msg and summary.get("log_error_excerpt"):
        error_msg = summary["log_error_excerpt"]

    logs = summary.get("log_tail") or result_data.get("log") or result_data.get("logs") or result_data.get("execution_log") or []
    if isinstance(logs, list):
        log_text = "\n".join(str(x) for x in logs[-80:])
    else:
        log_text = str(logs)
    if summary.get("log_tail"):
        log_text = summary["log_tail"]

    screenshot_desc = ""
    context_images = load_context_images(
        steps,
        failed_idx,
        lookback=2,
        lookahead=2,
        fallback_url=screenshot_url,
    )
    if context_images:
        labels = "、".join(caption for _, _, caption in context_images)
        screenshot_desc = (
            f"已提供失败上下文截图（{labels}），请对比失败步前后步骤的页面状态、"
            "弹窗、下拉选项等视觉差异综合判断。"
        )
    elif screenshot_url:
        screenshot_desc = (
            f"失败步骤截图已提供（步骤 {failed_idx + 1 if failed_idx >= 0 else '?'}），"
            "请结合截图中的页面元素、错误提示、弹窗等视觉信息综合判断。"
        )
    else:
        screenshot_desc = "（无可用截图，仅依据步骤与日志分析）"

    image_payload = context_images

    case = await execution.case
    from app.modules.stability.buckets import (
        extract_ui_error_msg,
        extract_ui_failure_code,
        map_failure_bucket,
    )

    failure_code = extract_ui_failure_code(result_data)
    failure_bucket = map_failure_bucket(
        failure_code=failure_code,
        error_msg=error_msg or extract_ui_error_msg(result_data),
        status=execution.status,
    )
    prompt_vars = {
        "target_type": "ui",
        "case_name": result_data.get("name") or result_data.get("case_name") or (case.name if case else "未知用例"),
        "request_method": "",
        "request_url": "",
        "request_headers": "",
        "request_body": "",
        "response_status": "",
        "response_body": "",
        "error_msg": _truncate(error_msg, 2000),
        "logs": _truncate(log_text, MAX_LOG_CHARS),
        "steps": _serialize_steps_for_prompt(step_summaries),
        "failed_step_index": str(failed_idx + 1 if failed_idx >= 0 else ""),
        "screenshot_desc": screenshot_desc,
        "record_status": execution.status or "",
        "request_id": "",
        "failure_code": failure_code or "",
        "failure_bucket": failure_bucket,
    }
    return prompt_vars, image_payload, screenshot_url


async def build_app_failure_context(
    execution: "AppCaseExecution",
) -> tuple[dict[str, Any], Optional[tuple[bytes, str]], Optional[str]]:
    """采集 App 执行失败上下文"""
    result_data = normalize_result_data(execution.result_data)
    summary = extract_ui_case_failure_summary(result_data)
    steps = result_data.get("steps") or []
    failed_idx, failed_step = find_failed_step(steps)
    screenshot_url = _pick_failure_screenshot(result_data, failed_step)

    env = execution.env if isinstance(execution.env, dict) else {}
    case = await execution.case
    driver_mode = (
        env.get("driver_mode")
        or result_data.get("driver_mode")
        or (case.driver_mode if case else "")
        or ""
    )

    step_summaries = _build_step_summaries(
        steps,
        failed_idx,
        extra_keys=(
            "locator_type",
            "execution_context",
            "webview_page_url",
            "match_score",
        ),
    )

    error_msg = summary.get("error_hint") or ""
    if not error_msg and summary.get("log_error_excerpt"):
        error_msg = summary["log_error_excerpt"]

    logs = summary.get("log_tail") or result_data.get("log") or result_data.get("logs") or result_data.get("execution_log") or []
    if isinstance(logs, list):
        log_text = "\n".join(str(x) for x in logs[-80:])
    else:
        log_text = str(logs)

    screenshot_desc = ""
    if screenshot_url:
        extra = ""
        if failed_step and failed_step.get("match_score") is not None:
            extra = f" 图像最高相似度 {failed_step.get('match_score')}"
        screenshot_desc = (
            f"失败步骤截图已提供（步骤 {failed_idx + 1 if failed_idx >= 0 else '?'}）"
            f"{extra}，请结合移动端 UI、H5 或图像匹配信息综合判断。"
        )
    else:
        screenshot_desc = "（无可用截图，仅依据步骤与日志分析）"

    image_payload = load_image_from_url(screenshot_url) if screenshot_url else None

    from app.modules.stability.buckets import (
        extract_ui_error_msg,
        extract_ui_failure_code,
        map_failure_bucket,
    )

    failure_code = extract_ui_failure_code(result_data)
    failure_bucket = map_failure_bucket(
        failure_code=failure_code,
        error_msg=error_msg or extract_ui_error_msg(result_data),
        status=execution.status,
    )
    prompt_vars = {
        "target_type": "app",
        "case_name": result_data.get("name") or result_data.get("case_name") or (case.name if case else "未知用例"),
        "request_method": "",
        "request_url": "",
        "request_headers": "",
        "request_body": "",
        "response_status": "",
        "response_body": "",
        "error_msg": _truncate(error_msg, 2000),
        "logs": _truncate(log_text, MAX_LOG_CHARS),
        "steps": _serialize_steps_for_prompt(step_summaries),
        "failed_step_index": str(failed_idx + 1 if failed_idx >= 0 else ""),
        "screenshot_desc": screenshot_desc,
        "record_status": execution.status or "",
        "driver_mode": driver_mode or "",
        "device_udid": env.get("device_udid") or "",
        "platform": env.get("platform") or "android",
        "request_id": "",
        "failure_code": failure_code or "",
        "failure_bucket": failure_bucket,
    }
    return prompt_vars, image_payload, screenshot_url


def slim_prompt_vars_for_batch(prompt_vars: dict[str, Any]) -> dict[str, Any]:
    """分批汇总用：去掉超大 body，保留错误与步骤结构。"""
    steps_raw = prompt_vars.get("steps") or ""
    steps_obj: Any = steps_raw
    if isinstance(steps_raw, str) and steps_raw.strip().startswith("["):
        try:
            steps_obj = json.loads(steps_raw)
        except json.JSONDecodeError:
            steps_obj = steps_raw[:4000]
    return {
        "target_type": prompt_vars.get("target_type"),
        "case_name": prompt_vars.get("case_name") or "",
        "error_msg": (prompt_vars.get("error_msg") or "")[:800],
        "record_status": prompt_vars.get("record_status") or "",
        "failed_step_index": prompt_vars.get("failed_step_index") or "",
        "failure_code": prompt_vars.get("failure_code") or "",
        "failure_bucket": prompt_vars.get("failure_bucket") or "",
        "request_method": prompt_vars.get("request_method") or "",
        "request_url": (prompt_vars.get("request_url") or "")[:300],
        "response_status": prompt_vars.get("response_status") or "",
        "steps": steps_obj,
    }
