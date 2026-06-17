"""API 套件执行公共逻辑（setup/teardown SQL、库断言）"""
from __future__ import annotations

import asyncio
import copy
from typing import Any, Callable, Awaitable

from app.models.sys import Environment, Project
from app.models.http import ApiTestSuite, ApiSuiteRunRecord
from app.core.data_tools.inline_tools import ensure_dt_cache


async def merge_exec_variables(
    env: Environment,
    project_global_vars: dict | None,
    accumulated_vars: dict | None,
) -> dict:
    from app.core.global_vars_validate import flatten_global_vars

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

    from app.core.db_factory_service import run_sql_templates_by_ids, run_suite_db_assertions

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
    """并行执行：用例共享 setup 后变量快照，彼此不传递提取变量。"""
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
) -> dict[str, Any]:
    """执行套件用例（含 hooks）。parallel=True 时用例并发且变量不链式传递。"""
    from app.routers.http.suites import run_single_case

    runner = run_single_case_fn or run_single_case
    accumulated_vars = ensure_dt_cache(variables)
    hooks_result: dict = {"setup": [], "teardown": [], "db_assertions": [], "success": True}
    should_stop = stop_on_failure if stop_on_failure is not None else bool(suite.stop_on_failure)
    parallel = bool(getattr(suite, "parallel", False))

    merged = await merge_exec_variables(env, project_global_vars, accumulated_vars)
    setup_hooks = await run_suite_hooks(suite, env.id, merged, setup=True)
    hooks_result["setup"] = setup_hooks.get("setup", [])
    if not setup_hooks.get("success"):
        hooks_result["success"] = False

    success_count = 0
    failed_count = 0
    case_results: list[Any] = []

    try:
        if parallel:
            case_results, success_count, failed_count = await _run_suite_cases_parallel(
                case_ids=case_ids,
                runner=runner,
                env=env,
                suite_record=suite_record,
                username=username,
                base_vars=accumulated_vars,
                project_global_vars=project_global_vars,
                auto_validate_schema=auto_validate_schema,
            )
        else:
            case_results, success_count, failed_count, accumulated_vars = await _run_suite_cases_serial(
                case_ids=case_ids,
                runner=runner,
                suite=suite,
                env=env,
                suite_record=suite_record,
                username=username,
                accumulated_vars=accumulated_vars,
                project_global_vars=project_global_vars,
                auto_validate_schema=auto_validate_schema,
                should_stop=should_stop,
            )
    finally:
        merged = await merge_exec_variables(env, project_global_vars, accumulated_vars)
        teardown_hooks = await run_suite_hooks(suite, env.id, merged, teardown=True)
        hooks_result["teardown"] = teardown_hooks.get("teardown", [])
        hooks_result["db_assertions"] = teardown_hooks.get("db_assertions", [])
        if not teardown_hooks.get("success"):
            hooks_result["success"] = False
            if teardown_hooks.get("db_assertions"):
                failed_count = max(failed_count, 1)

    return {
        "success_count": success_count,
        "failed_count": failed_count,
        "case_results": case_results,
        "hooks_result": hooks_result,
        "accumulated_vars": accumulated_vars,
    }
