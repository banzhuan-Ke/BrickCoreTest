"""从 UI 用例 result_data 提取失败摘要（报告摘要 / 失败分析共用）"""
from __future__ import annotations

import json
from typing import Any, Optional

FAIL_STEP_STATUSES = frozenset({"fail", "failed", "error"})


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
