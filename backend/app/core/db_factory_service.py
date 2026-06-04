"""
数据工厂 + 数据库断言执行服务。

- 数据源：环境级 MySQL 连接（密码 Fernet 加密存储）
- SQL 模板：setup / teardown / query，支持 ${{var}} 变量替换
- 库断言：仅允许 SELECT，结果写入断言报告
"""
from __future__ import annotations

import asyncio
import re
from decimal import Decimal
from typing import Any, Optional

import pymysql

from app.core.encryption import decrypt_value, encrypt_value
from app.core.variable_resolver import VariableResolver
from app.models.http import EnvDatasource, SqlTemplate

FORBIDDEN_SQL = re.compile(
    r"\b(DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|LOAD\s+FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE)\b",
    re.IGNORECASE,
)
WRITE_SQL = re.compile(r"\b(INSERT|UPDATE|DELETE|REPLACE)\b", re.IGNORECASE)
READ_SQL = re.compile(r"^\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN)\b", re.IGNORECASE)

DB_ASSERT_OPERATORS = {
    "equals",
    "not_equals",
    "gt",
    "gte",
    "lt",
    "lte",
    "contains",
    "row_count_equals",
    "exists",
    "not_exists",
}


def mask_password(_: str) -> str:
    return "******"


def datasource_to_dict(ds: EnvDatasource, env_name: str = "") -> dict[str, Any]:
    return {
        "id": ds.id,
        "project_id": ds.project_id,
        "environment_id": ds.environment_id,
        "environment_name": env_name,
        "name": ds.name,
        "db_type": ds.db_type,
        "host": ds.host,
        "port": ds.port,
        "database_name": ds.database_name,
        "username": ds.username,
        "has_password": bool(ds.password_encrypted),
        "allow_write": ds.allow_write,
        "max_rows": ds.max_rows,
        "timeout_seconds": ds.timeout_seconds,
        "is_default": ds.is_default,
        "is_enabled": ds.is_enabled,
        "create_by": ds.create_by,
        "update_by": ds.update_by,
        "create_time": ds.create_time,
        "update_time": ds.update_time,
    }


def sql_template_to_dict(tpl: SqlTemplate, datasource_name: str = "", env_name: str = "") -> dict[str, Any]:
    return {
        "id": tpl.id,
        "project_id": tpl.project_id,
        "environment_id": tpl.environment_id,
        "environment_name": env_name,
        "datasource_id": tpl.datasource_id,
        "datasource_name": datasource_name,
        "name": tpl.name,
        "template_type": tpl.template_type,
        "sql_text": tpl.sql_text,
        "description": tpl.description or "",
        "is_enabled": tpl.is_enabled,
        "create_by": tpl.create_by,
        "update_by": tpl.update_by,
        "create_time": tpl.create_time,
        "update_time": tpl.update_time,
    }


def validate_sql(sql: str, *, allow_write: bool, for_assertion: bool = False) -> tuple[bool, str]:
    text = (sql or "").strip()
    if not text:
        return False, "SQL 不能为空"
    if FORBIDDEN_SQL.search(text):
        return False, "禁止执行 DROP/TRUNCATE/ALTER 等危险语句"
    if for_assertion or not allow_write:
        if WRITE_SQL.search(text):
            return False, "当前模式仅允许 SELECT 查询"
        if not READ_SQL.match(text):
            return False, "仅允许 SELECT/SHOW/DESCRIBE/EXPLAIN 语句"
    return True, ""


def _normalize_value(val: Any) -> Any:
    if isinstance(val, Decimal):
        return float(val) if val % 1 else int(val)
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except Exception:
            return val.hex()
    return val


def _compare(actual: Any, expected: Any, operator: str) -> bool:
    op = (operator or "equals").lower()
    if op == "exists":
        return actual is not None
    if op == "not_exists":
        return actual is None
    if op == "row_count_equals":
        try:
            return int(actual) == int(expected)
        except (TypeError, ValueError):
            return False
    if actual is None:
        return op == "not_equals" and expected not in (None, "")

    act_str = str(actual)
    exp_str = str(expected) if expected is not None else ""

    if op == "equals":
        try:
            return float(act_str) == float(exp_str)
        except (TypeError, ValueError):
            return act_str == exp_str
    if op == "not_equals":
        try:
            return float(act_str) != float(exp_str)
        except (TypeError, ValueError):
            return act_str != exp_str
    if op == "contains":
        return exp_str in act_str
    try:
        a_num = float(act_str)
        e_num = float(exp_str)
        if op == "gt":
            return a_num > e_num
        if op == "gte":
            return a_num >= e_num
        if op == "lt":
            return a_num < e_num
        if op == "lte":
            return a_num <= e_num
    except (TypeError, ValueError):
        pass
    return False


def _connection_kwargs(ds: EnvDatasource) -> dict[str, Any]:
    password = ""
    if ds.password_encrypted:
        try:
            password = decrypt_value(ds.password_encrypted)
        except Exception:
            password = ""
    return {
        "host": ds.host,
        "port": int(ds.port or 3306),
        "user": ds.username,
        "password": password,
        "database": ds.database_name,
        "charset": "utf8mb4",
        "connect_timeout": int(ds.timeout_seconds or 10),
        "read_timeout": int(ds.timeout_seconds or 10),
        "write_timeout": int(ds.timeout_seconds or 10),
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": True,
    }


def _execute_sql_sync(ds: EnvDatasource, sql: str, *, allow_write: bool, for_assertion: bool, max_rows: int) -> dict[str, Any]:
    ok, err = validate_sql(sql, allow_write=allow_write, for_assertion=for_assertion)
    if not ok:
        return {"success": False, "error": err, "rows": [], "row_count": 0, "affected_rows": 0}

    conn = None
    try:
        conn = pymysql.connect(**_connection_kwargs(ds))
        with conn.cursor() as cursor:
            cursor.execute(sql)
            if READ_SQL.match(sql.strip()):
                rows = cursor.fetchmany(max_rows + 1)
                truncated = len(rows) > max_rows
                if truncated:
                    rows = rows[:max_rows]
                normalized = [{k: _normalize_value(v) for k, v in row.items()} for row in rows]
                return {
                    "success": True,
                    "rows": normalized,
                    "row_count": len(normalized),
                    "affected_rows": 0,
                    "truncated": truncated,
                }
            return {
                "success": True,
                "rows": [],
                "row_count": 0,
                "affected_rows": cursor.rowcount,
            }
    except Exception as exc:
        return {"success": False, "error": str(exc), "rows": [], "row_count": 0, "affected_rows": 0}
    finally:
        if conn:
            conn.close()


async def test_datasource_connection(ds: EnvDatasource) -> dict[str, Any]:
    sql = "SELECT 1 AS ok"
    result = await asyncio.to_thread(
        _execute_sql_sync, ds, sql, allow_write=False, for_assertion=True, max_rows=1
    )
    return {"success": result.get("success", False), "error": result.get("error"), "rows": result.get("rows", [])}


async def get_datasource_by_id(datasource_id: int, project_id: Optional[int] = None) -> Optional[EnvDatasource]:
    qs = EnvDatasource.filter(id=datasource_id, is_del=False, is_enabled=True)
    if project_id:
        qs = qs.filter(project_id=project_id)
    return await qs.first()


async def resolve_datasource(
    env_id: int,
    project_id: int,
    datasource_id: Optional[int] = None,
) -> tuple[Optional[EnvDatasource], Optional[str]]:
    if datasource_id:
        ds = await get_datasource_by_id(datasource_id, project_id)
        if not ds or ds.environment_id != env_id:
            return None, f"数据源 {datasource_id} 不存在或未绑定当前环境"
        return ds, None

    ds = await EnvDatasource.filter(
        project_id=project_id,
        environment_id=env_id,
        is_del=False,
        is_enabled=True,
        is_default=True,
    ).first()
    if ds:
        return ds, None
    ds = await EnvDatasource.filter(
        project_id=project_id,
        environment_id=env_id,
        is_del=False,
        is_enabled=True,
    ).order_by("id").first()
    if ds:
        return ds, None
    return None, "当前环境未配置可用数据源，请先在「数据工厂」中添加"


def substitute_sql(sql: str, variables: dict[str, Any]) -> tuple[str, list[dict]]:
    resolver = VariableResolver(variables or {})
    final_sql = resolver.replace_in_string(sql or "")
    return final_sql, []


async def execute_sql_on_datasource(
    ds: EnvDatasource,
    sql: str,
    variables: dict[str, Any],
    *,
    for_assertion: bool = False,
) -> dict[str, Any]:
    final_sql, replacements = substitute_sql(sql, variables)
    allow_write = bool(ds.allow_write) and not for_assertion
    result = await asyncio.to_thread(
        _execute_sql_sync,
        ds,
        final_sql,
        allow_write=allow_write,
        for_assertion=for_assertion,
        max_rows=int(ds.max_rows or 100),
    )
    result["sql"] = final_sql
    result["replacements"] = replacements
    return result


async def run_sql_templates_by_ids(
    template_ids: list[int],
    variables: dict[str, Any],
    env_id: int,
    project_id: int,
    *,
    phase: str = "setup",
) -> dict[str, Any]:
    logs: list[dict[str, Any]] = []
    success = True
    extracted_vars = dict(variables or {})

    for tpl_id in template_ids or []:
        tpl = await SqlTemplate.get_or_none(id=tpl_id, project_id=project_id, is_del=False, is_enabled=True)
        if not tpl:
            logs.append({"template_id": tpl_id, "success": False, "error": "SQL 模板不存在或已禁用"})
            success = False
            continue
        if tpl.environment_id and tpl.environment_id != env_id:
            logs.append({"template_id": tpl_id, "name": tpl.name, "success": False, "error": "模板不属于当前环境"})
            success = False
            continue

        ds = await get_datasource_by_id(tpl.datasource_id, project_id)
        if not ds or ds.environment_id != env_id:
            logs.append({"template_id": tpl_id, "name": tpl.name, "success": False, "error": "关联数据源不可用"})
            success = False
            continue

        exec_result = await execute_sql_on_datasource(ds, tpl.sql_text, extracted_vars, for_assertion=False)
        log_item = {
            "phase": phase,
            "template_id": tpl.id,
            "name": tpl.name,
            "template_type": tpl.template_type,
            "datasource_id": ds.id,
            "sql": exec_result.get("sql"),
            "success": exec_result.get("success", False),
            "row_count": exec_result.get("row_count", 0),
            "affected_rows": exec_result.get("affected_rows", 0),
            "error": exec_result.get("error"),
        }
        logs.append(log_item)
        if not exec_result.get("success"):
            success = False

    return {"success": success, "logs": logs, "variables": extracted_vars}


def _extract_actual_from_rows(rows: list[dict], field: Optional[str], operator: str) -> Any:
    op = (operator or "equals").lower()
    if op == "row_count_equals":
        return len(rows or [])
    if op == "exists":
        return rows[0] if rows else None
    if op == "not_exists":
        return None if not rows else rows[0]

    if not rows:
        return None
    row = rows[0]
    if field and field in row:
        return row[field]
    if row:
        return next(iter(row.values()))
    return None


async def evaluate_db_assertions(
    assertions: list[dict],
    variables: dict[str, Any],
    env_id: int,
    project_id: int,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    all_passed = True

    for raw in assertions or []:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name") or raw.get("description") or "数据库断言"
        operator = (raw.get("operator") or "equals").lower()
        if operator not in DB_ASSERT_OPERATORS:
            results.append({
                "type": "db",
                "target": name,
                "operator": operator,
                "expected": raw.get("expected"),
                "actual": None,
                "passed": False,
                "error": f"不支持的操作符: {operator}",
                "sql": raw.get("sql"),
            })
            all_passed = False
            continue

        sql = (raw.get("sql") or "").strip()
        if not sql:
            results.append({
                "type": "db",
                "target": name,
                "operator": operator,
                "expected": raw.get("expected"),
                "actual": None,
                "passed": False,
                "error": "SQL 不能为空",
            })
            all_passed = False
            continue

        ds, ds_err = await resolve_datasource(env_id, project_id, raw.get("datasource_id"))
        if ds_err or not ds:
            results.append({
                "type": "db",
                "target": name,
                "operator": operator,
                "expected": raw.get("expected"),
                "actual": None,
                "passed": False,
                "error": ds_err or "数据源不可用",
                "sql": sql,
            })
            all_passed = False
            continue

        exec_result = await execute_sql_on_datasource(ds, sql, variables, for_assertion=True)
        if not exec_result.get("success"):
            results.append({
                "type": "db",
                "target": name,
                "operator": operator,
                "expected": raw.get("expected"),
                "actual": None,
                "passed": False,
                "error": exec_result.get("error"),
                "sql": exec_result.get("sql"),
            })
            all_passed = False
            continue

        rows = exec_result.get("rows") or []
        actual = _extract_actual_from_rows(rows, raw.get("field"), operator)
        passed = _compare(actual, raw.get("expected"), operator)
        if not passed:
            all_passed = False

        results.append({
            "type": "db",
            "target": name,
            "operator": operator,
            "expected": raw.get("expected"),
            "actual": actual,
            "passed": passed,
            "sql": exec_result.get("sql"),
            "row_count": len(rows),
            "rows_preview": rows[:5],
        })

    return {"all_passed": all_passed, "results": results}


async def run_suite_db_assertions(
    assertions: list[dict],
    variables: dict[str, Any],
    env_id: int,
    project_id: int,
) -> dict[str, Any]:
    return await evaluate_db_assertions(assertions, variables, env_id, project_id)


def encrypt_datasource_password(password: Optional[str]) -> Optional[str]:
    if password is None:
        return None
    text = password.strip()
    if not text:
        return None
    return encrypt_value(text)
