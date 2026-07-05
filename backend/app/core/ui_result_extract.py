"""从 UI 用例 result_data 提取失败摘要（报告摘要 / 失败分析共用）"""
from __future__ import annotations

import json
from typing import Any, Optional

FAIL_STEP_STATUSES = frozenset({"fail", "failed", "error"})
CASE_FAIL_STATUSES = FAIL_STEP_STATUSES


def normalize_result_data(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def find_failed_step(steps: list) -> tuple[int, Optional[dict]]:
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        status = str(step.get("status") or "").lower()
        if status in FAIL_STEP_STATUSES:
            return idx, step
    return -1, None


def _format_log_data(log_data: Any, *, tail: int = 25) -> str:
    if not log_data:
        return ""
    lines: list[str] = []
    if isinstance(log_data, list):
        for item in log_data:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                lines.append(f"[{item[0]}] {item[1]}")
            elif isinstance(item, dict):
                lines.append(json.dumps(item, ensure_ascii=False))
            else:
                lines.append(str(item))
    else:
        lines.append(str(log_data))
    return "\n".join(lines[-tail:])


def _pick_error_lines(log_text: str) -> str:
    if not log_text:
        return ""
    picked: list[str] = []
    for line in log_text.splitlines():
        upper = line.upper()
        if any(k in upper for k in ("ERROR", "FAIL", "ASSERT", "EXCEPTION", "TRACEBACK")):
            picked.append(line)
        elif any(k in line for k in ("失败", "错误", "断言", "异常")):
            picked.append(line)
    if picked:
        return "\n".join(picked[-8:])
    tail = log_text.strip().splitlines()
    return "\n".join(tail[-5:]) if tail else ""


def extract_ui_case_failure_summary(result_data: Any) -> dict[str, Any]:
    """
    从 UiCaseExecution.result_data 提取结构化失败信息。
    兼容历史数据：error 字段缺失时从失败步骤 / 日志尾部推断。
    """
    rd = normalize_result_data(result_data)
    steps = rd.get("steps") or []
    failed_idx, failed_step = find_failed_step(steps)

    error_msg = (
        rd.get("error_msg")
        or rd.get("error")
        or rd.get("message")
        or ""
    )
    if isinstance(error_msg, dict):
        error_msg = json.dumps(error_msg, ensure_ascii=False)
    error_msg = str(error_msg or "").strip()

    if not error_msg and failed_step:
        error_msg = str(
            failed_step.get("message")
            or failed_step.get("error")
            or failed_step.get("desc")
            or failed_step.get("keyword")
            or ""
        ).strip()

    log_text = _format_log_data(rd.get("log_data") or rd.get("logs") or rd.get("log") or rd.get("execution_log"))
    log_error_hint = _pick_error_lines(log_text)
    if not error_msg and log_error_hint:
        error_msg = log_error_hint.splitlines()[0][:500]

    screenshot = None
    if failed_step:
        screenshot = failed_step.get("screenshot") or failed_step.get("image")
    if not screenshot:
        screenshot = rd.get("img") or rd.get("img_url") or rd.get("video_url")

    return {
        "case_name": rd.get("name") or rd.get("case_name") or "",
        "status": rd.get("status") or "",
        "error_hint": error_msg[:800] if error_msg else "",
        "failed_step_index": failed_idx + 1 if failed_idx >= 0 else None,
        "failed_step_keyword": (failed_step or {}).get("keyword") or (failed_step or {}).get("desc") or "",
        "failed_step_desc": (failed_step or {}).get("desc") or "",
        "log_tail": log_text[-1500:] if log_text else "",
        "log_error_excerpt": log_error_hint[:800] if log_error_hint else "",
        "has_screenshot": bool(screenshot),
        "has_steps": bool(steps),
        "data_complete": bool(error_msg or failed_step or log_error_hint),
    }


def build_case_execution_hints(result_data: Any) -> dict[str, Any]:
    """
    从用例 result_data 提取编辑页用的失败高亮信息（Web / App 共用结构）。
    """
    rd = normalize_result_data(result_data)
    summary = extract_ui_case_failure_summary(rd)
    steps = rd.get("steps") or []
    step_failures: list[dict[str, Any]] = []
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        status = str(step.get("status") or "").lower()
        if status not in FAIL_STEP_STATUSES:
            continue
        step_index = step.get("step_index")
        if step_index is None:
            step_index = idx
        try:
            step_index = int(step_index)
        except (TypeError, ValueError):
            step_index = idx
        message = str(
            step.get("message")
            or step.get("error")
            or step.get("desc")
            or step.get("keyword")
            or ""
        ).strip()
        step_failures.append(
            {
                "step_index": step_index,
                "status": status,
                "keyword": step.get("keyword") or step.get("desc") or "",
                "desc": step.get("desc") or "",
                "message": message,
            }
        )

    status = str(rd.get("status") or summary.get("status") or "").lower()
    has_failure = status in CASE_FAIL_STATUSES or bool(step_failures)

    if not step_failures and has_failure:
        failed_idx_raw = summary.get("failed_step_index")
        if failed_idx_raw is None:
            failed_idx_raw = rd.get("failed_step_index")
        nested_summary = rd.get("summary")
        if failed_idx_raw is None and isinstance(nested_summary, dict):
            failed_idx_raw = nested_summary.get("failed_step_index")
        idx = -1
        if failed_idx_raw is not None:
            try:
                raw = int(failed_idx_raw)
            except (TypeError, ValueError):
                raw = -1
            if raw >= 1:
                idx = raw - 1
            elif raw >= 0:
                idx = raw
        if idx >= 0:
            step = steps[idx] if idx < len(steps) else None
            error_hint = summary.get("error_hint") or ""
            if isinstance(nested_summary, dict):
                error_hint = error_hint or str(nested_summary.get("error_hint") or "")
            step_failures.append(
                {
                    "step_index": idx,
                    "status": status or "fail",
                    "keyword": (step or {}).get("keyword") or (step or {}).get("desc") or "",
                    "desc": (step or {}).get("desc") or "",
                    "message": (
                        (step or {}).get("message")
                        or (step or {}).get("error")
                        or error_hint
                        or ""
                    ),
                }
            )

    return {
        "has_failure": has_failure,
        "status": status,
        "error_msg": summary.get("error_hint") or "",
        "log_excerpt": summary.get("log_error_excerpt") or "",
        "log_tail": summary.get("log_tail") or "",
        "step_failures": step_failures,
    }
