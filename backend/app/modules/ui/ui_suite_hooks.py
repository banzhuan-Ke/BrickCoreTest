"""UI 套件执行完成后的 teardown SQL 与库断言（Runner API 回传路径统一触发）。"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.core.db.db_factory_service import evaluate_db_assertions, run_sql_templates_by_ids
from app.models.ui import Suite, UiSuiteExecution

logger = logging.getLogger(__name__)


def _parse_env(env_data: Any) -> dict[str, Any]:
    if isinstance(env_data, dict):
        return env_data
    if isinstance(env_data, str):
        try:
            parsed = json.loads(env_data)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


async def run_ui_suite_post_hooks(
    *,
    suite: Suite,
    record: UiSuiteExecution,
    environment_id: int,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """执行 teardown SQL 与套件级库断言，失败时更新执行记录。"""
    variables = dict(variables or {})
    hooks_result: dict[str, Any] = {"teardown": [], "db_assertions": []}

    teardown = await run_sql_templates_by_ids(
        suite.teardown_sql_ids or [],
        variables,
        environment_id,
        suite.project_id,
        phase="teardown",
    )
    hooks_result["teardown"] = teardown.get("logs", [])

    db_result = await evaluate_db_assertions(
        suite.db_assertions or [],
        variables,
        environment_id,
        suite.project_id,
    )
    hooks_result["db_assertions"] = db_result.get("results", [])

    all_passed = bool(teardown.get("success")) and bool(db_result.get("all_passed"))
    hooks_result["all_passed"] = all_passed

    if not all_passed:
        if not db_result.get("all_passed") or not teardown.get("success"):
            record.fail = (record.fail or 0) + 1
        log = record.execution_log or []
        if isinstance(log, str):
            try:
                log = json.loads(log)
            except Exception:
                log = []
        if not isinstance(log, list):
            log = []
        log.append({"type": "db_hooks", "hooks_result": hooks_result})
        record.execution_log = log
        await record.save()

    return hooks_result


async def trigger_ui_suite_hooks_for_execution(suite_execution_id: int) -> dict[str, Any] | None:
    """
    根据套件执行记录触发 post-hooks。
    无 teardown / 库断言配置、或缺少环境信息时跳过。
    """
    record = await UiSuiteExecution.get_or_none(id=suite_execution_id, is_del=False)
    if not record or not record.suite_id:
        return None

    suite = await Suite.get_or_none(id=record.suite_id, is_del=False)
    if not suite:
        logger.warning("跳过 UI 套件 hooks：套件不存在 suite_id=%s", record.suite_id)
        return None

    if not (suite.teardown_sql_ids or suite.db_assertions):
        return None

    env_data = _parse_env(record.env)
    environment_id = env_data.get("environment_id")
    if not environment_id:
        logger.warning(
            "跳过 UI 套件 hooks：缺少 environment_id exec_id=%s suite_id=%s",
            suite_execution_id,
            suite.id,
        )
        return None

    try:
        return await run_ui_suite_post_hooks(
            suite=suite,
            record=record,
            environment_id=int(environment_id),
            variables=env_data.get("variables") or {},
        )
    except Exception as exc:
        logger.error(
            "UI 套件 hooks 执行失败 exec_id=%s suite_id=%s: %s",
            suite_execution_id,
            suite.id,
            exc,
        )
        return None
