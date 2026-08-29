"""API 套件执行公共逻辑（setup/teardown SQL、库断言）"""
from __future__ import annotations

import asyncio
import copy
from typing import Any, Callable, Awaitable

from app.models.sys import Environment, Project
from app.models.http import ApiTestSuite, ApiSuiteRunRecord
from app.modules.data_tools.inline_tools import ensure_dt_cache


async def merge_exec_variables(
    env: Environment,
    project_global_vars: dict | None,
    accumulated_vars: dict | None,
) -> dict:
    from app.core.shared.global_vars_validate import flatten_global_vars

    proj_vars = project_global_vars or {}
    if not proj_vars and env.project_id:
        proj = await Project.get_or_none(id=env.project_id, is_del=False)
        proj_vars = (proj.global_vars or {}) if proj else {}
    return {
        **flatten_global_vars(proj_vars),
        **flatten_global_vars(env.global_vars),
        **(accumulated_vars or {}),
    }


async def run_suite_hooks(
    suite: ApiTestSuite | None,
    env_id: int,
    variables: dict,
    *,
    setup: bool = False,
    teardown: bool = False,
) -> dict:
    """执行套件级 setup/teardown SQL 与库断言，返回 hooks_result。"""
    if not suite:
        return {"setup": [], "teardown": [], "db_assertions": [], "success": True}

    from app.core.db.db_factory_service import run_sql_templates_by_ids, run_suite_db_assertions

    hooks_result: dict = {"setup": [], "teardown": [], "db_assertions": [], "success": True}

    if setup and (suite.setup_sql_ids or []):
        setup_res = await run_sql_templates_by_ids(
            suite.setup_sql_ids, variables, env_id, suite.project_id, phase="setup"
        )
        hooks_result["setup"] = setup_res.get("logs", [])
        if not setup_res.get("success"):
            hooks_result["success"] = False

    if teardown:
        if suite.teardown_sql_ids:
            td_res = await run_sql_templates_by_ids(
                suite.teardown_sql_ids, variables, env_id, suite.project_id, phase="teardown"
            )
            hooks_result["teardown"] = td_res.get("logs", [])
            if not td_res.get("success"):
                hooks_result["success"] = False

        if suite.db_assertions:
            db_res = await run_suite_db_assertions(
                suite.db_assertions, variables, env_id, suite.project_id
            )
            hooks_result["db_assertions"] = db_res.get("results", [])
            if not db_res.get("all_passed"):
                hooks_result["success"] = False

    return hooks_result


async def _run_suite_cases_serial(
    *,
    case_ids: list[int],
    runner: Callable[..., Awaitable[Any]],
    suite: ApiTestSuite,
    env: Environment,
    suite_record: ApiSuiteRunRecord | None,
    username: str,
    accumulated_vars: dict,
    project_global_vars: dict | None,
    auto_validate_schema: bool,
    should_stop: bool,
    worker_id: int | None = None,
) -> tuple[list[Any], int, int, dict]:
    case_results: list[Any] = []
    success_count = 0
    failed_count = 0
    record_id = suite_record.id if suite_record else None

    for case_id in case_ids:
        result = await runner(
            case_id,
            env.id,
            record_id,
            username,
            accumulated_vars,
            auto_validate_schema,
            project_global_vars=project_global_vars,
            worker_id=worker_id,
        )
        case_results.append(result)
        accumulated_vars.update(result.extracted_vars or {})
        if result.status == "success":
            success_count += 1
        else:
            failed_count += 1
        if should_stop and result.status != "success":
            break
    return case_results, success_count, failed_count, accumulated_vars


async def _run_suite_cases_parallel(
    *,
    case_ids: list[int],
    runner: Callable[..., Awaitable[Any]],
    env: Environment,
    suite_record: ApiSuiteRunRecord | None,
    username: str,
    base_vars: dict,
    project_global_vars: dict | None,
    auto_validate_schema: bool,
) -> tuple[list[Any], int, int]:
    """并行执行：仅本机 httpx。有 worker_id 时走整包串行，不会进入本函数。"""
    record_id = suite_record.id if suite_record else None
    vars_snapshot = ensure_dt_cache(copy.copy(base_vars))

    async def _run_one(case_id: int):
        case_vars = ensure_dt_cache(copy.copy(vars_snapshot))
        return await runner(
            case_id,
            env.id,
            record_id,
            username,
            case_vars,
            auto_validate_schema,
            project_global_vars=project_global_vars,
        )

    gathered = await asyncio.gather(*[_run_one(cid) for cid in case_ids])
    success_count = sum(1 for r in gathered if r.status == "success")
    failed_count = len(gathered) - success_count
    return list(gathered), success_count, failed_count


async def execute_api_suite_cases(
    *,
    suite: ApiTestSuite,
    env: Environment,
    case_ids: list[int],
    suite_record: ApiSuiteRunRecord | None,
    username: str,
    variables: dict | None = None,
    project_global_vars: dict | None = None,
    auto_validate_schema: bool = False,
    stop_on_failure: bool | None = None,
    run_single_case_fn: Callable[..., Awaitable[Any]] | None = None,
    worker_id: int | None = None,
    include_quarantine: bool = False,
) -> dict[str, Any]:
    """执行套件用例（含 hooks）。parallel=True 时用例并发且变量不链式传递。有 worker_id 时整包下发并强制串行。"""
    from app.routers.http.suites import run_single_case
    from app.modules.http.worker_http_proxy import WorkerProxyError
    from app.modules.stability.quarantine import split_quarantined_ids, write_api_quarantine_skips

    runner = run_single_case_fn or run_single_case
    accumulated_vars = ensure_dt_cache(variables)
    hooks_result: dict = {"setup": [], "teardown": [], "db_assertions": [], "success": True}
    should_stop = stop_on_failure if stop_on_failure is not None else bool(suite.stop_on_failure)
    parallel = bool(getattr(suite, "parallel", False)) and worker_id is None

    runnable_ids, quarantined_ids = await split_quarantined_ids(
        "api", case_ids, include_quarantine=include_quarantine
    )
    quarantine_results = await write_api_quarantine_skips(
        case_ids=quarantined_ids,
        project_id=suite.project_id,
        username=username,
        suite_record_id=suite_record.id if suite_record else None,
    )
    quarantine_skip = len(quarantined_ids)

    merged = await merge_exec_variables(env, project_global_vars, accumulated_vars)
    setup_hooks = await run_suite_hooks(suite, env.id, merged, setup=True)
    hooks_result["setup"] = setup_hooks.get("setup", [])
    if not setup_hooks.get("success"):
        hooks_result["success"] = False

    success_count = 0
    failed_count = 0
    case_results: list[Any] = []

    try:
        if not runnable_ids:
            case_results = list(quarantine_results)
        elif worker_id is not None:
            from app.modules.http.api_suite_package import execute_suite_via_worker

            try:
                packaged = await execute_suite_via_worker(
                    suite=suite,
                    env=env,
                    case_ids=runnable_ids,
                    suite_record=suite_record,
                    username=username,
                    variables=accumulated_vars,
                    project_global_vars=project_global_vars,
                    auto_validate_schema=auto_validate_schema,
                    stop_on_failure=should_stop,
                    worker_id=worker_id,
                )
            except WorkerProxyError as exc:
                hooks_result["success"] = False
                hooks_result["worker_error"] = str(exc)
                return {
                    "success_count": 0,
                    "failed_count": max(1, len(runnable_ids) or 1),
                    "skipped_count": 0,
                    "quarantine_skip": quarantine_skip,
                    "case_results": list(quarantine_results),
                    "hooks_result": hooks_result,
                    "accumulated_vars": accumulated_vars,
                    "worker_proxy_error": str(exc),
                }
            case_results = list(quarantine_results) + list(packaged.get("case_results") or [])
            success_count = int(packaged.get("success_count") or 0)
            failed_count = int(packaged.get("failed_count") or 0)
            accumulated_vars = ensure_dt_cache(packaged.get("accumulated_vars") or accumulated_vars)
            if packaged.get("stopped_at") is not None:
                hooks_result["suite_stop_reason"] = (
                    f"因第 {int(packaged['stopped_at']) + 1} 步失败提前结束（整包经执行机）"
                )
        elif parallel:
            run_results, success_count, failed_count = await _run_suite_cases_parallel(
                case_ids=runnable_ids,
                runner=runner,
                env=env,
                suite_record=suite_record,
                username=username,
                base_vars=accumulated_vars,
                project_global_vars=project_global_vars,
                auto_validate_schema=auto_validate_schema,
            )
            case_results = list(quarantine_results) + list(run_results)
        else:
            run_results, success_count, failed_count, accumulated_vars = await _run_suite_cases_serial(
                case_ids=runnable_ids,
                runner=runner,
                suite=suite,
                env=env,
                suite_record=suite_record,
                username=username,
                accumulated_vars=accumulated_vars,
                project_global_vars=project_global_vars,
                auto_validate_schema=auto_validate_schema,
                should_stop=should_stop,
                worker_id=worker_id,
            )
            case_results = list(quarantine_results) + list(run_results)
    finally:
        merged = await merge_exec_variables(env, project_global_vars, accumulated_vars)
        teardown_hooks = await run_suite_hooks(suite, env.id, merged, teardown=True)
        hooks_result["teardown"] = teardown_hooks.get("teardown", [])
        hooks_result["db_assertions"] = teardown_hooks.get("db_assertions", [])
        if not teardown_hooks.get("success"):
            hooks_result["success"] = False
            if teardown_hooks.get("db_assertions"):
                failed_count = max(failed_count, 1)

    if suite_record is not None:
        # skipped_cases 仅计非隔离跳过；隔离单独落 quarantine_skip，避免报告双卡片同值
        suite_record.skipped_cases = 0
        suite_record.quarantine_skip = quarantine_skip
        await suite_record.save(update_fields=["skipped_cases", "quarantine_skip"])

    return {
        "success_count": success_count,
        "failed_count": failed_count,
        "skipped_count": 0,
        "quarantine_skip": quarantine_skip,
        "case_results": case_results,
        "hooks_result": hooks_result,
        "accumulated_vars": accumulated_vars,
    }
