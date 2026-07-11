"""App 套件执行完成后的 teardown SQL 与库断言"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.core.db.db_factory_service import evaluate_db_assertions, run_sql_templates_by_ids
from app.models.app import AppSuite, AppSuiteExecution

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


async def trigger_app_suite_hooks_for_execution(suite_execution_id: int) -> None:
    record = await AppSuiteExecution.get_or_none(id=suite_execution_id, is_del=False)
    if not record:
        return
    suite = await AppSuite.get_or_none(id=record.suite_id, is_del=False)
    if not suite:
        return
    env = _parse_env(record.env)
    environment_id = env.get("environment_id")
    if not environment_id:
        return
    variables = dict(env.get("variables") or {})
    teardown = await run_sql_templates_by_ids(
        suite.teardown_sql_ids or [], variables, environment_id, suite.project_id, phase="teardown"
    )
    db_result = await evaluate_db_assertions(
        suite.db_assertions or [], variables, environment_id, suite.project_id
    )
    if not teardown.get("success") or not db_result.get("all_passed"):
        record.fail = (record.fail or 0) + 1
        log = list(record.execution_log or [])
        log.append({"level": "error", "message": "App 套件 teardown/库断言未通过"})
        record.execution_log = log
        await record.save()
