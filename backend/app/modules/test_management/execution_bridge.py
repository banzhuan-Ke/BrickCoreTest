"""计划运行项 → 各自动化引擎派发与结果同步"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException
from tortoise import transactions

from app.models.app import AppCase, AppCaseExecution
from app.models.http import ApiRunRecord, ApiTestCase
from app.models.sys import Device, Environment
from app.models.perf import PerfRecord, PerfScene
from app.models.test_management import TestPlanRun, TestPlanRunItem
from app.models.ui import Case as UiCase
from app.models.ui import UiCaseExecution
from app.modules.test_management import result_normalizer as norm
from app.modules.test_management.phase3_rules import assert_can_dispatch_automation
from app.modules.test_management.plan_service import _maybe_complete_run, run_item_to_dict
from app.modules.ui.ui_device_guard import assert_device_available_for_ui_execution, lock_device_row
from app.modules.ui.ui_project_guard import assert_environment_for_project

logger = logging.getLogger(__name__)

# 保留 perf 后台 task 引用，避免 GC；见 start_perf_record_background
_perf_background_tasks: set[asyncio.Task] = set()

# 认领后长时间未挂上 original_record_id 才重置（须覆盖慢派发/压测拉起；过短会与在途派发竞态）
ZOMBIE_CLAIM_TIMEOUT = timedelta(minutes=15)
# unknown 非终态最长停留；超时强制 error，避免 run 永久 running
UNKNOWN_RESULT_MAX_AGE = timedelta(minutes=30)
_UNKNOWN_SINCE_KEY = "_tm_unknown_since"


@dataclass
class DispatchResult:
    ok: bool
    result_status: str
    result_message: Optional[str] = None
    original_record_type: Optional[str] = None
    original_record_id: Optional[int] = None
    evidence_json: Optional[dict] = None


async def _require_env(project_id: int, environment_id: Optional[int]) -> Environment:
    if environment_id is None:
        raise HTTPException(status_code=400, detail="自动化派发需要指定环境")
    env = await Environment.get_or_none(id=environment_id, project_id=project_id, is_del=False)
    if not env:
        raise HTTPException(status_code=400, detail="环境不存在")
    assert_environment_for_project(env, project_id)
    return env


async def dispatch_api_case(
    *,
    asset_id: int,
    project_id: int,
    environment_id: int,
    username: str,
) -> DispatchResult:
    from app.routers.http.suites import run_single_case

    case = await ApiTestCase.get_or_none(id=asset_id, project_id=project_id, is_del=False)
    if not case:
        return DispatchResult(
            ok=False,
            result_status="blocked",
            result_message="接口用例不存在或已删除",
        )
    try:
        result = await run_single_case(
            case_id=asset_id,
            env_id=environment_id,
            suite_record_id=None,
            username=username,
        )
    except Exception as exc:  # noqa: BLE001 — 派发失败保留运行项
        return DispatchResult(
            ok=False,
            result_status="error",
            result_message=str(exc)[:500],
        )
    record_id = int(result.record_id or 0)
    unified = norm.normalize_api_status(result.status)
    if unified == "not_run" and record_id:
        unified = "passed" if result.status == "success" else "failed"
    evidence = (
        norm.build_report_paths("api_run_record", record_id, asset_id=asset_id)
        if record_id
        else {}
    )
    if result.error:
        evidence["error_summary"] = str(result.error)[:500]
    msg = result.error or (None if unified == "passed" else result.status)
    return DispatchResult(
        ok=record_id > 0,
        result_status=unified if record_id else "error",
        result_message=msg,
        original_record_type="api_run_record",
        original_record_id=record_id or None,
        evidence_json=evidence,
    )


async def dispatch_ui_case(
    *,
    asset_id: int,
    project_id: int,
    environment_id: int,
    username: str,
    device_id: Optional[str] = None,
) -> DispatchResult:
    if not device_id:
        return DispatchResult(
            ok=False,
            result_status="blocked",
            result_message="Web 自动化派发需要指定在线 Runner 设备",
        )
    from app.routers.ui.exec import ExecutionService

    case = await UiCase.get_or_none(id=asset_id, project_id=project_id, is_del=False)
    if not case:
        return DispatchResult(
            ok=False,
            result_status="blocked",
            result_message="Web 用例不存在或已删除",
        )
    env = await _require_env(project_id, environment_id)
    try:
        async with transactions.in_transaction():
            await lock_device_row(device_id)
            await assert_device_available_for_ui_execution(device_id)
            env_payload = await ExecutionService.build_env_payload(
                env, "chromium", True, project_id
            )
            env_payload = ExecutionService.with_trigger_source(env_payload, "test_management")
            env_payload["device_id"] = device_id
            case_execution = await UiCaseExecution.create(
                case=case,
                username=username,
                env=env_payload,
                is_del=False,
            )
            case_execution_id = case_execution.id

        expanded_steps = await ExecutionService.expand_steps_or_raise(case.steps, project_id)
        suite_payload = {
            "id": case.id,
            "name": case.name,
            "case_execution_id": case_execution_id,
            "pre_actions": [],
            "username": username,
            "cases": [
                {
                    "execution_id": case_execution_id,
                    "id": case.id,
                    "name": case.name,
                    "skip": False,
                    "steps": expanded_steps,
                }
            ],
        }
        dispatched = await ExecutionService.dispatch_to_device(env_payload, suite_payload, device_id)
        evidence = norm.build_report_paths(
            "ui_case_execution", case_execution_id, asset_id=asset_id
        )
        if not dispatched:
            return DispatchResult(
                ok=False,
                result_status="blocked",
                result_message="Runner 不在线或不支持 Web 引擎",
                original_record_type="ui_case_execution",
                original_record_id=case_execution_id,
                evidence_json=evidence,
            )
        return DispatchResult(
            ok=True,
            result_status="not_run",
            result_message="已派发至 Runner，等待执行完成",
            original_record_type="ui_case_execution",
            original_record_id=case_execution_id,
            evidence_json=evidence,
        )
    except HTTPException as exc:
        return DispatchResult(ok=False, result_status="blocked", result_message=str(exc.detail))
    except Exception as exc:  # noqa: BLE001
        return DispatchResult(ok=False, result_status="error", result_message=str(exc)[:500])


async def dispatch_app_case(
    *,
    asset_id: int,
    project_id: int,
    environment_id: int,
    username: str,
    device_id: Optional[str] = None,
) -> DispatchResult:
    if not device_id:
        return DispatchResult(
            ok=False,
            result_status="blocked",
            result_message="App 自动化派发需要指定在线 Runner 设备",
        )
    from app.routers.app.exec import AppExecutionService, AppRunForm, build_case_env, expand_app_steps

    case = await AppCase.get_or_none(id=asset_id, project_id=project_id, is_del=False)
    if not case:
        return DispatchResult(
            ok=False,
            result_status="blocked",
            result_message="App 用例不存在或已删除",
        )
    device = await Device.get_or_none(id=device_id)
    if not device or device.status != "在线":
        return DispatchResult(
            ok=False,
            result_status="blocked",
            result_message="设备不在线",
        )
    env = await _require_env(project_id, environment_id)
    try:
        item = AppRunForm(env_id=environment_id, device_id=device_id, trigger_source="test_management")
        async with transactions.in_transaction():
            env_payload = AppExecutionService.with_trigger_source(
                await AppExecutionService.build_env_payload(env, case.project_id, device, item),
                "test_management",
            )
            env_payload = build_case_env(env_payload, case, trigger_source="test_management")
            case_execution = await AppCaseExecution.create(
                case=case, username=username, env=env_payload, is_del=False
            )
            case_execution_id = case_execution.id
        expanded_steps = await expand_app_steps(case.steps or [], case.project_id)
        suite_payload = {
            "engine_type": "app",
            "id": case.id,
            "name": case.name,
            "case_execution_id": case_execution_id,
            "pre_actions": [],
            "username": username,
            "cases": [
                {
                    "execution_id": case_execution_id,
                    "id": case.id,
                    "name": case.name,
                    "skip": False,
                    "driver_mode": case.driver_mode,
                    "steps": expanded_steps,
                }
            ],
        }
        dispatched = await AppExecutionService.dispatch_to_device(
            env_payload, suite_payload, device_id
        )
        evidence = norm.build_report_paths(
            "app_case_execution", case_execution_id, asset_id=asset_id
        )
        if not dispatched:
            return DispatchResult(
                ok=False,
                result_status="blocked",
                result_message="Runner 未检测到 App 设备或未在线",
                original_record_type="app_case_execution",
                original_record_id=case_execution_id,
                evidence_json=evidence,
            )
        return DispatchResult(
            ok=True,
            result_status="not_run",
            result_message="已派发至 Runner，等待执行完成",
            original_record_type="app_case_execution",
            original_record_id=case_execution_id,
            evidence_json=evidence,
        )
    except HTTPException as exc:
        return DispatchResult(ok=False, result_status="blocked", result_message=str(exc.detail))
    except Exception as exc:  # noqa: BLE001
        return DispatchResult(ok=False, result_status="error", result_message=str(exc)[:500])


async def dispatch_perf_scene(
    *,
    asset_id: int,
    project_id: int,
    environment_id: int,
    username: str,
) -> DispatchResult:
    from app.routers.perf.exec import snapshot_scene_items_with_case_meta
    from app.routers.perf.workers import get_active_workers, resolve_worker_selection
    from app.modules.ai.ai_project_settings import resolve_perf_ai_for_run

    scene = await PerfScene.get_or_none(id=asset_id, project_id=project_id, is_del=False)
    if not scene:
        return DispatchResult(
            ok=False,
            result_status="blocked",
            result_message="压测场景不存在或已删除",
        )
    active = await get_active_workers(scene.project_id, exclude_busy=True)
    if not active:
        return DispatchResult(
            ok=False,
            result_status="blocked",
            result_message="无可用压测 Worker，请上线执行器后再派发",
        )
    config = dict(scene.config or {})
    config["env_id"] = environment_id
    config["request_detail_level"] = config.get("request_detail_level") or "brief"
    config["ai_analyze_on_complete"] = await resolve_perf_ai_for_run(scene.project_id)
    needed = int(config.get("concurrent_users", 1) or 1)
    if config.get("mode") == "stepping":
        steps = config.get("steps") or []
        needed = max((int(s.get("users", 1) or 1) for s in steps), default=1)
    try:
        selected, _weights = resolve_worker_selection(active)
    except ValueError as exc:
        return DispatchResult(ok=False, result_status="blocked", result_message=str(exc))
    capacity = sum(w.max_concurrent for w in selected)
    if capacity < needed:
        return DispatchResult(
            ok=False,
            result_status="blocked",
            result_message=f"Worker 容量不足：需要并发 {needed}，当前 {capacity}",
        )
    record = await PerfRecord.create(
        scene_id=scene.id,
        project_id=scene.project_id,
        status="pending",
        trigger_type="test_management",
        config_snapshot=config,
        scene_items_snapshot=await snapshot_scene_items_with_case_meta(scene.scene_items or []),
        run_by=username,
    )
    evidence = norm.build_report_paths("perf_record", record.id, asset_id=asset_id)
    return DispatchResult(
        ok=True,
        result_status="not_run",
        result_message="压测已启动，等待 Worker 执行完成",
        original_record_type="perf_record",
        original_record_id=record.id,
        evidence_json=evidence,
    )


def start_perf_record_background(record_id: int) -> None:
    """在 run_item 已落库 original_record_id 后再启动压测协调任务。"""
    from app.routers.perf.exec import run_perf_scene

    task = asyncio.create_task(run_perf_scene(record_id, True))
    _perf_background_tasks.add(task)
    task.add_done_callback(_perf_background_tasks.discard)


async def dispatch_plan_run_item(
    run_item: TestPlanRunItem,
    *,
    username: str,
    environment_id: Optional[int],
    device_id: Optional[str] = None,
) -> DispatchResult:
    if run_item.execution_mode != "automation":
        return DispatchResult(ok=False, result_status="blocked", result_message="非自动化项")
    if run_item.asset_id is None:
        return DispatchResult(ok=False, result_status="blocked", result_message="缺少自动化资产 ID")

    item_type = (run_item.item_type or "").strip()
    if item_type == "api_case":
        if environment_id is None:
            return DispatchResult(
                ok=False,
                result_status="blocked",
                result_message="接口自动化派发需要指定环境",
            )
        return await dispatch_api_case(
            asset_id=run_item.asset_id,
            project_id=run_item.project_id,
            environment_id=environment_id,
            username=username,
        )
    if item_type == "ui_case":
        return await dispatch_ui_case(
            asset_id=run_item.asset_id,
            project_id=run_item.project_id,
            environment_id=environment_id,
            username=username,
            device_id=device_id,
        )
    if item_type == "app_case":
        return await dispatch_app_case(
            asset_id=run_item.asset_id,
            project_id=run_item.project_id,
            environment_id=environment_id,
            username=username,
            device_id=device_id,
        )
    if item_type == "perf_scene":
        if environment_id is None:
            return DispatchResult(
                ok=False,
                result_status="blocked",
                result_message="压测派发需要指定环境",
            )
        return await dispatch_perf_scene(
            asset_id=run_item.asset_id,
            project_id=run_item.project_id,
            environment_id=environment_id,
            username=username,
        )
    return DispatchResult(
        ok=False,
        result_status="blocked",
        result_message=f"不支持的自动化类型: {item_type}",
    )


async def _load_original_status(
    record_type: str,
    record_id: int,
    *,
    asset_id: Optional[int] = None,
    project_id: Optional[int] = None,
) -> tuple[Optional[str], Optional[str], dict]:
    rt = (record_type or "").strip().lower()
    evidence: dict[str, Any] = norm.build_report_paths(rt, record_id, asset_id=asset_id)
    if rt == "api_run_record":
        row = await ApiRunRecord.get_or_none(id=record_id)
        if not row:
            return None, "原始记录不存在", evidence
        if project_id is not None:
            rec_pid = getattr(row, "project_id", None)
            if rec_pid is not None and int(rec_pid) != int(project_id):
                return None, "原始记录与项目不匹配", evidence
            if rec_pid is None and row.case_id:
                case = await ApiTestCase.get_or_none(id=row.case_id, is_del=False)
                if not case or case.project_id != project_id:
                    return None, "原始记录与项目不匹配", evidence
        msg = row.error_msg
        if not msg and row.assertions_result:
            failed = [a for a in (row.assertions_result or []) if not a.get("passed", True)]
            if failed:
                msg = failed[0].get("message") or failed[0].get("expression")
        return row.status, msg, evidence
    if rt == "ui_case_execution":
        row = await UiCaseExecution.get_or_none(id=record_id, is_del=False)
        if not row:
            return None, "原始记录不存在", evidence
        case_id = asset_id or getattr(row, "case_id", None)
        if project_id is not None and case_id:
            case = await UiCase.get_or_none(id=case_id, is_del=False)
            if not case or case.project_id != project_id:
                return None, "原始记录与项目不匹配", evidence
        evidence = norm.build_report_paths(rt, record_id, asset_id=case_id)
        rd = row.result_data or {}
        msg = rd.get("error") or rd.get("message")
        if isinstance(msg, dict):
            msg = str(msg)
        return row.status, msg, evidence
    if rt == "app_case_execution":
        row = await AppCaseExecution.get_or_none(id=record_id, is_del=False)
        if not row:
            return None, "原始记录不存在", evidence
        case_id = asset_id or getattr(row, "case_id", None)
        if project_id is not None and case_id:
            case = await AppCase.get_or_none(id=case_id, is_del=False)
            if not case or case.project_id != project_id:
                return None, "原始记录与项目不匹配", evidence
        evidence = norm.build_report_paths(rt, record_id, asset_id=case_id)
        rd = row.result_data or {}
        msg = rd.get("error") or rd.get("message")
        return row.status, msg, evidence
    if rt == "perf_record":
        row = await PerfRecord.get_or_none(id=record_id)
        if not row:
            return None, "原始记录不存在", evidence
        if project_id is not None and int(row.project_id) != int(project_id):
            return None, "原始记录与项目不匹配", evidence
        evidence = norm.build_report_paths(rt, record_id, asset_id=asset_id)
        msg = row.status
        if row.fail_count and row.status in ("failed", "stopped"):
            msg = f"失败 {row.fail_count} 次"
        return row.status, msg, evidence
    return None, "未知记录类型", evidence


async def sync_plan_run_item_from_record(
    run_item: TestPlanRunItem,
    *,
    username: str,
) -> TestPlanRunItem:
    if not run_item.original_record_type or not run_item.original_record_id:
        return run_item
    if run_item.result_status in norm.TERMINAL_RESULTS:
        return run_item
    if run_item.result_status in ("skipped", "cancelled"):
        return run_item

    # 批次已取消/结束时禁止回写，避免覆盖 cancel_run 写入的 skipped
    parent = await TestPlanRun.get_or_none(
        id=run_item.run_id, project_id=run_item.project_id, is_del=False
    )
    if not parent or parent.status != "running":
        return run_item

    raw_status, raw_msg, evidence = await _load_original_status(
        run_item.original_record_type,
        int(run_item.original_record_id),
        asset_id=run_item.asset_id,
        project_id=run_item.project_id,
    )
    if raw_status is None:
        msg = (raw_msg or "").strip()
        permanent = any(
            token in msg
            for token in ("不存在", "不匹配", "未知记录类型")
        )
        if permanent:
            await _safe_write_run_item_result(
                run_item,
                username=username,
                result_status="error",
                result_message=msg or "原始记录不可用",
                status="done",
            )
        elif msg:
            await _safe_write_run_item_result(
                run_item,
                username=username,
                result_message=msg[:2000],
            )
        return await TestPlanRunItem.get(id=run_item.id)

    unified = norm.normalize_by_record_type(run_item.original_record_type, raw_status)
    now = datetime.now(timezone.utc)
    merged = dict(run_item.evidence_json or {})
    merged.update(evidence)

    if unified == "unknown":
        since = _parse_iso_dt(merged.get(_UNKNOWN_SINCE_KEY))
        if since is None:
            merged[_UNKNOWN_SINCE_KEY] = now.isoformat()
            since = now
        if now - since > UNKNOWN_RESULT_MAX_AGE:
            unified = "error"
            raw_msg = raw_msg or "原始状态长期无法识别，已强制结束"
            merged.pop(_UNKNOWN_SINCE_KEY, None)
        else:
            await _safe_write_run_item_result(
                run_item,
                username=username,
                status="running",
                result_status="unknown",
                result_message=str(raw_msg)[:2000] if raw_msg else None,
                evidence_json=merged,
            )
            return await TestPlanRunItem.get(id=run_item.id)
    else:
        merged.pop(_UNKNOWN_SINCE_KEY, None)

    patch: dict[str, Any] = {
        "evidence_json": merged,
        "result_status": unified,
    }
    if unified == "not_run":
        patch["status"] = "running"
    else:
        patch["status"] = "done"
        patch["finished_at"] = now
        if run_item.started_at is None:
            patch["started_at"] = now
    if raw_msg and unified in ("failed", "blocked", "error"):
        patch["result_message"] = str(raw_msg)[:2000]
    await _safe_write_run_item_result(run_item, username=username, **patch)
    return await TestPlanRunItem.get(id=run_item.id)


async def _safe_write_run_item_result(
    run_item: TestPlanRunItem,
    *,
    username: str,
    **fields: Any,
) -> bool:
    """仅在批次仍 running 且项尚未终态/跳过时写入，堵住 cancel 竞态。"""
    parent = await TestPlanRun.get_or_none(
        id=run_item.run_id, project_id=run_item.project_id, is_del=False
    )
    if not parent or parent.status != "running":
        return False
    fresh = await TestPlanRunItem.get_or_none(id=run_item.id, is_del=False)
    if not fresh:
        return False
    if fresh.result_status in norm.TERMINAL_RESULTS:
        return False
    if fresh.result_status in ("skipped", "cancelled"):
        return False
    for k, v in fields.items():
        if v is not None or k in ("evidence_json", "result_message"):
            setattr(fresh, k, v)
    fresh.update_by = username
    await fresh.save()
    return True


def _parse_iso_dt(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def _revert_dispatch_claim(item_id: int, username: str) -> None:
    """派发失败回滚：仅当尚未挂上 original_record_id 时重置为 pending。"""
    await TestPlanRunItem.filter(
        id=item_id,
        result_status="not_run",
        original_record_id__isnull=True,
        status="running",
    ).update(
        status="pending",
        result_message=None,
        evidence_json={},
        update_by=username,
        update_time=datetime.now(timezone.utc),
    )


async def _reset_zombie_dispatch_claims(run: TestPlanRun, username: str) -> int:
    """认领后长时间无 original_record_id 的僵尸项重置为 pending，避免 run 永久卡死。"""
    cutoff = datetime.now(timezone.utc) - ZOMBIE_CLAIM_TIMEOUT
    now = datetime.now(timezone.utc)
    return await TestPlanRunItem.filter(
        run_id=run.id,
        project_id=run.project_id,
        is_del=False,
        execution_mode="automation",
        status="running",
        result_status="not_run",
        original_record_id__isnull=True,
        update_time__lt=cutoff,
    ).update(
        status="pending",
        result_message=None,
        evidence_json={},
        update_by=username,
        update_time=now,
    )


async def _abort_perf_record(record_id: int, *, reason: str) -> None:
    row = await PerfRecord.get_or_none(id=record_id)
    if not row or row.status in ("stopped", "failed", "success", "completed"):
        return
    if not isinstance(row.error_breakdown, dict):
        row.error_breakdown = {}
    row.error_breakdown["stop_reason"] = reason[:500]
    row.status = "stopped"
    row.ended_at = datetime.now(timezone.utc)
    await row.save()


async def apply_dispatch_result(
    run_item: TestPlanRunItem,
    result: DispatchResult,
    *,
    username: str,
) -> Optional[TestPlanRunItem]:
    """将派发结果写回 item。须仍处于 CAS 认领态（status=running 且无 record），否则丢弃（防僵尸重置竞态）。"""
    now = datetime.now(timezone.utc)
    status = "running" if result.result_status == "not_run" else "done"
    values: dict[str, Any] = {
        "started_at": run_item.started_at or now,
        "evidence_json": result.evidence_json or {},
        "result_message": result.result_message,
        "result_status": result.result_status,
        "status": status,
        "update_by": username,
        "update_time": now,
    }
    if result.original_record_type:
        values["original_record_type"] = result.original_record_type
    if result.original_record_id:
        values["original_record_id"] = result.original_record_id
    if status == "done":
        values["finished_at"] = now

    claimed = await TestPlanRunItem.filter(
        id=run_item.id,
        status="running",
        original_record_id__isnull=True,
        result_status="not_run",
    ).update(**values)
    if not claimed:
        logger.warning(
            "apply_dispatch_result CAS 未命中 item=%s（可能已被僵尸重置），丢弃写回",
            run_item.id,
        )
        return None
    return await TestPlanRunItem.get(id=run_item.id)


async def _abort_orphan_dispatch(result: DispatchResult, *, reason: str) -> None:
    """认领丢失后中止已创建的孤儿执行记录。"""
    if not result.original_record_id:
        return
    rt = (result.original_record_type or "").strip().lower()
    rid = int(result.original_record_id)
    try:
        if rt == "perf_record":
            await _abort_perf_record(rid, reason=reason)
        elif rt == "ui_case_execution":
            from app.modules.ui.ui_execution_stop import stop_case_execution

            row = await UiCaseExecution.get_or_none(id=rid, is_del=False)
            if row and row.status == "running":
                await stop_case_execution(rid)
        elif rt == "app_case_execution":
            from app.modules.app.app_execution_stop import stop_case_execution

            row = await AppCaseExecution.get_or_none(id=rid, is_del=False)
            if row and row.status == "running":
                await stop_case_execution(rid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("中止孤儿派发记录失败 %s/%s: %s", rt, rid, exc)


async def stop_dispatched_automation_for_run(run: TestPlanRun) -> dict[str, int]:
    """取消计划运行时，通知 Runner 停止已派发且仍在执行的 UI/App 自动化。"""
    items = await TestPlanRunItem.filter(
        run_id=run.id,
        project_id=run.project_id,
        is_del=False,
        execution_mode="automation",
        original_record_id__not_isnull=True,
    )
    stopped = 0
    skipped = 0
    for item in items:
        rt = (item.original_record_type or "").strip().lower()
        rid = int(item.original_record_id)
        try:
            if rt == "ui_case_execution":
                from app.modules.ui.ui_execution_stop import stop_case_execution

                row = await UiCaseExecution.get_or_none(id=rid, is_del=False)
                if not row:
                    skipped += 1
                    continue
                if row.status != "running":
                    skipped += 1
                    continue
                await stop_case_execution(rid)
                stopped += 1
            elif rt == "app_case_execution":
                from app.modules.app.app_execution_stop import stop_case_execution

                row = await AppCaseExecution.get_or_none(id=rid, is_del=False)
                if not row:
                    skipped += 1
                    continue
                if row.status != "running":
                    skipped += 1
                    continue
                await stop_case_execution(rid)
                stopped += 1
            elif rt == "perf_record":
                row = await PerfRecord.get_or_none(id=rid, project_id=run.project_id)
                if not row:
                    skipped += 1
                    continue
                if row.status not in ("running", "pending"):
                    skipped += 1
                    continue
                try:
                    from app.routers.perf.exec import _running_records

                    stop_event = _running_records.get(rid)
                    if stop_event:
                        stop_event.set()
                    if not isinstance(row.error_breakdown, dict):
                        row.error_breakdown = {}
                    row.error_breakdown["stop_reason"] = "测试计划运行已取消"
                    row.status = "stopped"
                    row.ended_at = datetime.now(timezone.utc)
                    await row.save()
                    try:
                        from app.routers.perf.workers import finalize_distributed_record

                        await finalize_distributed_record(rid)
                    except Exception as fin_exc:  # noqa: BLE001
                        logger.warning(
                            "取消计划后 finalize 压测失败 perf_record=%s: %s",
                            rid,
                            fin_exc,
                        )
                    stopped += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "停止压测执行失败 run_item=%s perf_record=%s: %s",
                        item.id,
                        rid,
                        exc,
                    )
                    skipped += 1
        except HTTPException as exc:
            logger.warning(
                "停止自动化执行失败 run_item=%s record=%s/%s: %s",
                item.id,
                rt,
                rid,
                exc.detail,
            )
            skipped += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "停止自动化执行异常 run_item=%s record=%s/%s: %s",
                item.id,
                rt,
                rid,
                exc,
            )
            skipped += 1
    return {"stopped": stopped, "skipped": skipped}


async def sync_run_automation_items(
    run: TestPlanRun,
    *,
    username: str,
) -> dict[str, int]:
    if run.status != "running":
        return {"synced": 0, "total": 0, "skipped": True}
    fresh_run = await TestPlanRun.get_or_none(id=run.id, project_id=run.project_id, is_del=False)
    if not fresh_run or fresh_run.status != "running":
        return {"synced": 0, "total": 0, "skipped": True}
    await _reset_zombie_dispatch_claims(fresh_run, username)
    items = await TestPlanRunItem.filter(
        run_id=fresh_run.id,
        project_id=fresh_run.project_id,
        is_del=False,
        execution_mode="automation",
    )
    synced = 0
    for item in items:
        fresh_run = await TestPlanRun.get_or_none(
            id=run.id, project_id=run.project_id, is_del=False
        )
        if not fresh_run or fresh_run.status != "running":
            break
        if not item.original_record_id:
            continue
        if item.result_status == "skipped":
            continue
        try:
            before = item.result_status
            await sync_plan_run_item_from_record(item, username=username)
            item = await TestPlanRunItem.get(id=item.id)
            if item.result_status != before:
                synced += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "同步自动化运行项失败 run=%s item=%s: %s",
                fresh_run.id,
                item.id,
                exc,
            )
    fresh_run = await TestPlanRun.get_or_none(id=run.id, project_id=run.project_id, is_del=False)
    if fresh_run and fresh_run.status == "running":
        await _maybe_complete_run(fresh_run, username)
    return {"synced": synced, "total": len(items)}


async def dispatch_run_automation_items(
    run: TestPlanRun,
    *,
    username: str,
    device_id: Optional[str] = None,
    user_permissions: Optional[set[str]] = None,
    is_superuser: bool = False,
) -> dict[str, Any]:
    async with transactions.in_transaction():
        locked_run = await TestPlanRun.select_for_update().get_or_none(
            id=run.id, project_id=run.project_id, is_del=False
        )
        if not locked_run or locked_run.status != "running":
            raise HTTPException(status_code=400, detail="仅运行中的批次可派发自动化")
        env_id = locked_run.environment_id

    items = await TestPlanRunItem.filter(
        run_id=run.id,
        project_id=run.project_id,
        is_del=False,
        execution_mode="automation",
        result_status="not_run",
        original_record_id__isnull=True,
    )
    if user_permissions is not None:
        for item in items:
            assert_can_dispatch_automation(
                item.item_type or "",
                user_permissions,
                is_superuser=is_superuser,
            )
    dispatched = 0
    blocked = 0
    results = []
    for item in items:
        fresh_run = await TestPlanRun.get_or_none(
            id=run.id, project_id=run.project_id, is_del=False
        )
        if not fresh_run or fresh_run.status != "running":
            break
        claimed = await TestPlanRunItem.filter(
            id=item.id,
            run_id=run.id,
            project_id=run.project_id,
            is_del=False,
            execution_mode="automation",
            status="pending",
            result_status="not_run",
            original_record_id__isnull=True,
        ).update(
            status="running",
            update_by=username,
            update_time=datetime.now(timezone.utc),
        )
        if not claimed:
            continue
        item = await TestPlanRunItem.get(id=item.id)
        dr: Optional[DispatchResult] = None
        try:
            dr = await dispatch_plan_run_item(
                item, username=username, environment_id=env_id, device_id=device_id
            )
            applied = await apply_dispatch_result(item, dr, username=username)
            if applied is None:
                await _abort_orphan_dispatch(
                    dr, reason="测试计划认领已失效（僵尸重置），丢弃本次派发写回"
                )
                blocked += 1
                item = await TestPlanRunItem.get(id=item.id)
                results.append(run_item_to_dict(item))
                continue
            item = applied
            if (
                dr.ok
                and dr.result_status == "not_run"
                and (item.item_type or "").strip() == "perf_scene"
                and dr.original_record_id
            ):
                start_perf_record_background(int(dr.original_record_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "派发自动化失败 run=%s item=%s: %s",
                run.id,
                item.id,
                exc,
            )
            if dr and dr.original_record_type == "perf_record" and dr.original_record_id:
                await _abort_perf_record(
                    int(dr.original_record_id),
                    reason="测试计划派发落库失败，已中止压测",
                )
            await _revert_dispatch_claim(item.id, username)
            blocked += 1
            item = await TestPlanRunItem.get(id=item.id)
            results.append(run_item_to_dict(item))
            continue
        if dr.ok and dr.result_status == "not_run":
            dispatched += 1
        elif dr.result_status in ("passed", "failed", "error"):
            dispatched += 1
        else:
            blocked += 1
        results.append(run_item_to_dict(item))
    fresh_run = await TestPlanRun.get_or_none(id=run.id, project_id=run.project_id, is_del=False)
    if fresh_run and fresh_run.status == "running":
        await _maybe_complete_run(fresh_run, username)
    return {"dispatched": dispatched, "blocked": blocked, "items": results}
