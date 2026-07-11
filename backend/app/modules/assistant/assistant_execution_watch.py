"""平台助手：confirm 后后台轮询执行结果并追加会话消息"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.modules.assistant.assistant_session import load_session_messages, save_session_messages
from app.models.http import ApiPlanRunRecord, ApiSuiteRunRecord
from app.models.ui import UiCaseExecution, UiPlanExecution, UiSuiteExecution

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 3.0
MAX_POLL_SEC = 600

_TERMINAL_API = frozenset({"success", "failed", "partial"})
_TERMINAL_UI_PLAN = frozenset({"执行完成"})
_TERMINAL_UI_SUITE = frozenset({"执行完成"})
_TERMINAL_UI_CASE = frozenset({"success", "fail", "error", "skip", "no_run"})
_TERMINAL_QA = frozenset({"completed", "failed", "cancelled"})

_TRIGGER_LABELS = {"manual": "手动", "assistant": "小测", "cron": "定时任务"}


def build_execution_watch(action: str, result: dict[str, Any]) -> dict[str, Any] | None:
    """从 confirm 结果提取可轮询目标；同步完成的 action 返回 None。"""
    if action in ("run_api_case", "analyze_failure", "trigger_generate"):
        return None
    if not isinstance(result, dict):
        return None

    if action == "run_api_suite":
        rid = result.get("record_id")
        if rid:
            return {"action": action, "record_type": "api_suite", "record_id": int(rid)}
    elif action == "run_api_plan":
        rid = result.get("record_id")
        if rid:
            return {"action": action, "record_type": "api_plan", "record_id": int(rid)}
    elif action == "run_ui_task":
        rid = result.get("task_record_id")
        if not rid:
            nested = result.get("result") if isinstance(result.get("result"), dict) else result
            rid = (nested or {}).get("task_record_id")
        if rid:
            return {"action": action, "record_type": "ui_plan", "record_id": int(rid)}
    elif action == "run_ui_suite":
        rid = result.get("suite_record_id")
        if not rid:
            nested = result.get("result") if isinstance(result.get("result"), dict) else result
            rid = (nested or {}).get("suite_record_id")
        if rid:
            return {"action": action, "record_type": "ui_suite", "record_id": int(rid)}
    elif action == "run_ui_case":
        rid = result.get("execution_id")
        if rid:
            return {"action": action, "record_type": "ui_case", "record_id": int(rid)}
    elif action == "run_":
        rid = result.get("run_id")
        if rid:
            return {"action": action, "record_type": "", "record_id": int(rid)}
    elif action == "run_perf_scene":
        rid = result.get("record_id")
        if rid:
            return {"action": action, "record_type": "perf", "record_id": int(rid)}
    return None


async def _snapshot(record_type: str, record_id: int) -> tuple[str, dict[str, Any]] | None:
    record_type = (record_type or "").lower()
    if record_type == "api_suite":
        rec = await ApiSuiteRunRecord.get_or_none(id=record_id)
        if not rec:
            return None
        suite = await rec.suite
        return rec.status, {
            "name": suite.name if suite else "",
            "status": rec.status,
            "total_cases": rec.total_cases,
            "success_cases": rec.success_cases,
            "failed_cases": rec.failed_cases,
            "trigger_type": rec.trigger_type,
            "trigger_label": _TRIGGER_LABELS.get(rec.trigger_type, rec.trigger_type),
        }
    if record_type == "api_plan":
        rec = await ApiPlanRunRecord.get_or_none(id=record_id)
        if not rec:
            return None
        from app.models.http import ApiTestPlan

        p = await ApiTestPlan.get_or_none(id=rec.plan_id)
        return rec.status, {
            "name": p.name if p else "",
            "status": rec.status,
            "total_cases": rec.total_cases,
            "success_cases": rec.success_cases,
            "failed_cases": rec.failed_cases,
            "trigger_type": rec.trigger_type,
            "trigger_label": _TRIGGER_LABELS.get(rec.trigger_type, rec.trigger_type),
        }
    if record_type == "ui_plan":
        rec = await UiPlanExecution.get_or_none(id=record_id, is_del=False).prefetch_related("task")
        if not rec:
            return None
        env = rec.env if isinstance(rec.env, dict) else {}
        ts = env.get("trigger_source") or "manual"
        return rec.status, {
            "name": rec.task.name if rec.task else "",
            "status": rec.status,
            "case_count": rec.case_count,
            "success": rec.success,
            "fail": rec.fail,
            "error": rec.error,
            "pass_rate": rec.pass_rate,
            "trigger_source": ts,
            "trigger_label": _TRIGGER_LABELS.get(ts, ts),
        }
    if record_type == "ui_suite":
        rec = await UiSuiteExecution.get_or_none(id=record_id, is_del=False).prefetch_related("suite")
        if not rec:
            return None
        env = rec.env if isinstance(rec.env, dict) else {}
        ts = env.get("trigger_source") or "manual"
        return rec.status, {
            "name": rec.suite.name if rec.suite else "",
            "status": rec.status,
            "case_count": rec.case_count,
            "success": rec.success,
            "fail": rec.fail,
            "pass_rate": rec.pass_rate,
            "trigger_source": ts,
            "trigger_label": _TRIGGER_LABELS.get(ts, ts),
        }
    if record_type == "ui_case":
        rec = await UiCaseExecution.get_or_none(id=record_id, is_del=False).prefetch_related("case")
        if not rec:
            return None
        env = rec.env if isinstance(rec.env, dict) else {}
        ts = env.get("trigger_source") or "manual"
        return rec.status, {
            "name": rec.case.name if rec.case else "",
            "status": rec.status,
            "trigger_source": ts,
            "trigger_label": _TRIGGER_LABELS.get(ts, ts),
        }
    if record_type == "perf":
        from app.models.perf import PerfRecord

        rec = await PerfRecord.get_or_none(id=record_id)
        if not rec:
            return None
        return rec.status or "unknown", {
            "status": rec.status,
            "scene_id": rec.scene_id,
        }
    return None


def _is_terminal(record_type: str, status: str) -> bool:
    st = (status or "").strip()
    if record_type in ("api_suite", "api_plan"):
        return st in _TERMINAL_API
    if record_type == "ui_plan":
        return st in _TERMINAL_UI_PLAN
    if record_type == "ui_suite":
        return st in _TERMINAL_UI_SUITE
    if record_type == "ui_case":
        return st in _TERMINAL_UI_CASE
    if record_type == "":
        return st in _TERMINAL_QA
    if record_type == "perf":
        return st in ("success", "failed", "completed", "error")
    return False


def _format_follow_up(record_type: str, record_id: int, data: dict[str, Any]) -> str:
    name = data.get("name") or data.get("run_name") or f"#{record_id}"
    lines = [f"### 执行已完成：{name}", ""]

    if record_type in ("api_suite", "api_plan"):
        total = data.get("total_cases") or 0
        ok = data.get("success_cases") or 0
        fail = data.get("failed_cases") or 0
        lines.append(f"- **状态**：{data.get('status')}")
        lines.append(f"- **触发方式**：{data.get('trigger_label', '—')}")
        lines.append(f"- **用例**：共 {total}，成功 {ok}，失败 {fail}")
    elif record_type in ("ui_plan", "ui_suite"):
        lines.append(f"- **状态**：{data.get('status')}")
        lines.append(f"- **触发方式**：{data.get('trigger_label', '—')}")
        lines.append(
            f"- **用例**：共 {data.get('case_count', 0)}，成功 {data.get('success', 0)}，"
            f"失败 {data.get('fail', 0)}，错误 {data.get('error', 0)}"
        )
        pr = data.get("pass_rate")
        if pr is not None:
            lines.append(f"- **通过率**：{float(pr):.2f}%")
    elif record_type == "ui_case":
        lines.append(f"- **状态**：{data.get('status')}")
        lines.append(f"- **触发方式**：{data.get('trigger_label', '—')}")
    elif record_type == "":
        lines.append(f"- **状态**：{data.get('status')}")
        lines.append(f"- **触发方式**：{data.get('trigger_label', '—')}")
        lines.append(
            f"- **题目**：共 {data.get('total_count', 0)}，通过 {data.get('passed_count', 0)}，"
            f"未通过 {data.get('failed_count', 0)}"
        )
        if data.get("pass_rate") is not None:
            lines.append(f"- **通过率**：{float(data['pass_rate']):.2f}%")
    else:
        lines.append(f"- **状态**：{data.get('status', 'unknown')}")

    lines.append("")
    lines.append(f"记录 ID：`{record_id}`（类型 `{record_type}`）")
    return "\n".join(lines)


async def poll_execution_and_notify(
    *,
    user_id: int,
    project_id: int | None,
    session_id: int,
    watch: dict[str, Any],
) -> None:
    record_type = watch.get("record_type") or ""
    record_id = int(watch.get("record_id") or 0)
    if not record_id or not record_type:
        return

    elapsed = 0.0
    try:
        while elapsed < MAX_POLL_SEC:
            await asyncio.sleep(POLL_INTERVAL_SEC)
            elapsed += POLL_INTERVAL_SEC
            snap = await _snapshot(record_type, record_id)
            if not snap:
                continue
            status, data = snap
            if not _is_terminal(record_type, status):
                continue

            content = _format_follow_up(record_type, record_id, data)
            _, msgs = await load_session_messages(user_id, project_id, session_id=session_id)
            follow_msg = {
                "role": "assistant",
                "content": content,
                "tools": [f"watch:{record_type}:{record_id}"],
                "execution_follow_up": True,
                "watch_record_type": record_type,
                "watch_record_id": record_id,
            }
            await save_session_messages(
                user_id,
                project_id,
                msgs + [follow_msg],
                session_id=session_id,
            )
            return
    except Exception:
        logger.exception(
            "[assistant] execution watch failed user=%s session=%s type=%s id=%s",
            user_id,
            session_id,
            record_type,
            record_id,
        )


def schedule_execution_watch(
    *,
    user_id: int,
    project_id: int | None,
    session_id: int | None,
    action: str,
    result: dict[str, Any],
) -> dict[str, Any] | None:
    watch = build_execution_watch(action, result)
    if not watch or not session_id:
        return None
    asyncio.create_task(
        poll_execution_and_notify(
            user_id=user_id,
            project_id=project_id,
            session_id=session_id,
            watch=watch,
        )
    )
    return watch
