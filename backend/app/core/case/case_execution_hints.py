"""用例编辑页 execution-hints 组装（Web / App 共用）。"""
from __future__ import annotations

from typing import Any

from app.modules.ui.ui_case_status import normalize_ui_case_status
from app.modules.ui.ui_result_extract import build_case_execution_hints, remap_step_failures_to_case_steps

_FAIL_STATUSES = frozenset({"fail", "error"})


def enrich_execution_hints_from_record(hints: dict[str, Any], record: Any) -> dict[str, Any]:
    """合并执行记录表 status，避免 result_data 不完整时编辑页无失败提示。"""
    out = dict(hints)
    rec_status = normalize_ui_case_status(getattr(record, "status", None)) or ""
    if not out.get("has_failure") and rec_status in _FAIL_STATUSES:
        out["has_failure"] = True
        out["status"] = rec_status
        if not out.get("error_msg"):
            out["error_msg"] = "用例执行未通过，请查看步骤或执行记录详情"
    out["execution_id"] = getattr(record, "id", None)
    start_time = getattr(record, "start_time", None)
    out["start_time"] = start_time.isoformat() if start_time else None
    return out


async def resolve_latest_failure_record(model: Any, case_id: int, execution_id: int | None = None) -> Any | None:
    """取指定或最近一次执行；仅当最近一次为失败/错误时返回记录。"""
    if execution_id:
        record = await model.get_or_none(id=execution_id, is_del=False)
        if not record or record.case_id != case_id:
            return None
        return record

    latest = await model.filter(case_id=case_id, is_del=False).order_by("-id").first()
    if not latest:
        return None
    rec_status = normalize_ui_case_status(getattr(latest, "status", None)) or ""
    if rec_status in _FAIL_STATUSES:
        return latest
    return None


def build_execution_hints_response(
    record: Any | None,
    case_steps: list[Any] | None = None,
) -> dict[str, Any]:
    if not record:
        return {
            "has_failure": False,
            "execution_id": None,
            "start_time": None,
            "status": "",
            "error_msg": "",
            "log_excerpt": "",
            "log_tail": "",
            "step_failures": [],
        }
    hints = build_case_execution_hints(getattr(record, "result_data", None))
    hints = enrich_execution_hints_from_record(hints, record)
    hints["step_failures"] = remap_step_failures_to_case_steps(
        hints.get("step_failures"),
        case_steps,
    )
    return hints
