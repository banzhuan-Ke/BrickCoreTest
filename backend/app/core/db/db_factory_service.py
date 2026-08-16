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

from app.core.db.db_drivers import execute_on_datasource, test_connection as driver_test_connection, validate_command
from app.core.platform.encryption import decrypt_value, encrypt_value
from app.core.case.variable_resolver import VariableResolver
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

# 调试/报告中返回的查询行预览上限（完整断言仍基于全量拉取结果，受数据源 max_rows 约束）
DB_ASSERT_PREVIEW_ROWS = 10

_FIELD_COMPARE_OPS = frozenset({
    "equals",
    "not_equals",
    "gt",
    "gte",
    "lt",
    "lte",
    "contains",
})


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


def validate_sql(
    sql: str,
    *,
    allow_write: bool,
    for_assertion: bool = False,
    db_type: str = "mysql",
) -> tuple[bool, str]:
    return validate_command(sql, db_type=db_type, allow_write=allow_write, for_assertion=for_assertion)


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


def _execute_sql_sync(ds: EnvDatasource, sql: str, *, allow_write: bool, for_assertion: bool, max_rows: int) -> dict[str, Any]:
    return execute_on_datasource(
        ds, sql, allow_write=allow_write, for_assertion=for_assertion, max_rows=max_rows
    )


async def test_datasource_connection(ds: EnvDatasource) -> dict[str, Any]:
    result = await asyncio.to_thread(driver_test_connection, ds)
    return result


async def get_datasource_by_id(datasource_id: int, project_id: Optional[int] = None) -> Optional[EnvDatasource]:
    qs = EnvDatasource.filter(id=datasource_id, is_del=False, is_enabled=True)
    if project_id:
        qs = qs.filter(project_id=project_id)
    return await qs.first()


def _format_env_ref(env_id: Optional[int], env_name: Optional[str] = None) -> str:
    if env_name:
        return f"「{env_name}」(id={env_id})"
    if env_id is not None:
        return f"环境 id={env_id}"
    return "未知环境"


def build_datasource_env_mismatch_message(
    *,
    ds_name: str,
    ds_id: int,
    ds_env_id: int,
    ds_env_name: Optional[str],
    current_env_id: int,
    current_env_name: Optional[str],
) -> str:
    return (
        f"数据源「{ds_name}」(id={ds_id}) 绑定在 {_format_env_ref(ds_env_id, ds_env_name)}，"
        f"与当前调试环境 {_format_env_ref(current_env_id, current_env_name)} 不一致。"
        "请切换顶部调试环境，或在断言中改选当前环境下的数据源。"
    )


async def _env_name(env_id: Optional[int]) -> Optional[str]:
    if not env_id:
        return None
    from app.models.sys import Environment

    env = await Environment.get_or_none(id=env_id)
    return getattr(env, "name", None) if env else None


async def diagnose_datasource_resolve_error(
    *,
    datasource_id: int,
    project_id: int,
    env_id: int,
) -> str:
    """生成可读的数据源解析失败原因（环境不一致 / 禁用 / 删除等）。"""
    ds = await EnvDatasource.filter(id=datasource_id).first()
    if not ds:
        return f"数据源 id={datasource_id} 不存在，请重新选择数据源"
    if ds.is_del:
        return f"数据源「{ds.name}」(id={datasource_id}) 已删除，请重新选择数据源"
    if project_id and ds.project_id != project_id:
        return f"数据源「{ds.name}」(id={datasource_id}) 不属于当前项目，请重新选择数据源"
    if not ds.is_enabled:
        return (
            f"数据源「{ds.name}」(id={datasource_id}) 已禁用。"
            "请到「数据工厂 → 数据源」启用，或改选其他数据源"
        )
    if ds.environment_id != env_id:
        return build_datasource_env_mismatch_message(
            ds_name=ds.name,
            ds_id=ds.id,
            ds_env_id=ds.environment_id,
            ds_env_name=await _env_name(ds.environment_id),
            current_env_id=env_id,
            current_env_name=await _env_name(env_id),
        )
    return f"数据源「{ds.name}」(id={datasource_id}) 不可用，请检查配置"


async def resolve_datasource(
    env_id: int,
    project_id: int,
    datasource_id: Optional[int] = None,
) -> tuple[Optional[EnvDatasource], Optional[str]]:
    if datasource_id:
        ds = await get_datasource_by_id(datasource_id, project_id)
        if ds and ds.environment_id == env_id:
            return ds, None
        return None, await diagnose_datasource_resolve_error(
            datasource_id=int(datasource_id),
            project_id=project_id,
            env_id=env_id,
        )

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
    env_label = _format_env_ref(env_id, await _env_name(env_id))
    return None, (
        f"当前调试环境 {env_label} 未配置可用数据源。"
        "请先在「数据工厂 → 数据源」为该环境添加并启用"
    )


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


def _field_resolve_note(rows: list[dict], field: Optional[str]) -> str:
    """说明字段取值来源（首行 / 首列回退）。"""
    if not rows:
        return "查询无结果"
    row = rows[0]
    field_name = (field or "").strip()
    if field_name and field_name in row:
        return f"首行.{field_name}"
    if field_name:
        first_key = next(iter(row.keys()), None) if row else None
        if first_key is not None:
            return f"字段「{field_name}」不存在，已回退首行首列「{first_key}」"
        return f"字段「{field_name}」不存在"
    first_key = next(iter(row.keys()), None) if row else None
    if first_key is not None:
        return f"未填字段，取首行首列「{first_key}」"
    return "首行"


def _build_db_assert_message(
    *,
    operator: str,
    field: Optional[str],
    expected: Any,
    actual: Any,
    rows: list[dict],
    passed: bool,
) -> str:
    op = (operator or "equals").lower()
    row_count = len(rows or [])

    if op == "row_count_equals":
        base = f"行数实际={actual}，期望={expected}"
        return f"{base}，{'通过' if passed else '未通过'}"

    if op == "exists":
        if passed:
            return f"存在记录（共 {row_count} 行）"
        return "期望存在记录，但查询无结果"

    if op == "not_exists":
        if passed:
            return "不存在记录（查询为空）"
        return f"期望无记录，但查询返回 {row_count} 行"

    source = _field_resolve_note(rows, field)
    parts = [f"实际值={actual!r}（{source}）", f"期望 {op} {expected!r}"]
    if op in _FIELD_COMPARE_OPS and row_count > 1:
        parts.append(
            f"字段比较仅取查询结果首行，共 {row_count} 行；"
            "若要对指定记录断言，请用 WHERE 收窄，或改用「行数等于 / 存在记录」"
        )
    parts.append("通过" if passed else "未通过")
    return "；".join(parts)


def _preview_rows(rows: list[dict], limit: int = DB_ASSERT_PREVIEW_ROWS) -> tuple[list[dict], bool]:
    preview = list(rows or [])[:limit]
    truncated = len(rows or []) > limit
    return preview, truncated


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
        field = raw.get("field")
        expected = raw.get("expected")
        if operator not in DB_ASSERT_OPERATORS:
            results.append({
                "type": "db",
                "target": name,
                "operator": operator,
                "field": field,
                "expected": expected,
                "actual": None,
                "passed": False,
                "error": f"不支持的操作符: {operator}",
                "message": f"不支持的操作符: {operator}",
                "sql": raw.get("sql"),
                "row_count": 0,
                "rows_preview": [],
                "preview_truncated": False,
            })
            all_passed = False
            continue

        sql = (raw.get("sql") or "").strip()
        if not sql:
            results.append({
                "type": "db",
                "target": name,
                "operator": operator,
                "field": field,
                "expected": expected,
                "actual": None,
                "passed": False,
                "error": "SQL 不能为空",
                "message": "SQL 不能为空",
                "row_count": 0,
                "rows_preview": [],
                "preview_truncated": False,
            })
            all_passed = False
            continue

        ds, ds_err = await resolve_datasource(env_id, project_id, raw.get("datasource_id"))
        if ds_err or not ds:
            results.append({
                "type": "db",
                "target": name,
                "operator": operator,
                "field": field,
                "expected": expected,
                "actual": None,
                "passed": False,
                "error": ds_err or "数据源不可用",
                "message": ds_err or "数据源不可用",
                "sql": sql,
                "row_count": 0,
                "rows_preview": [],
                "preview_truncated": False,
            })
            all_passed = False
            continue

        exec_result = await execute_sql_on_datasource(ds, sql, variables, for_assertion=True)
        if not exec_result.get("success"):
            err = exec_result.get("error")
            results.append({
                "type": "db",
                "target": name,
                "operator": operator,
                "field": field,
                "expected": expected,
                "actual": None,
                "passed": False,
                "error": err,
                "message": err or "SQL 执行失败",
                "sql": exec_result.get("sql"),
                "row_count": 0,
                "rows_preview": [],
                "preview_truncated": False,
            })
            all_passed = False
            continue

        rows = exec_result.get("rows") or []
        actual = _extract_actual_from_rows(rows, field, operator)
        passed = _compare(actual, expected, operator)
        if not passed:
            all_passed = False
        preview, truncated = _preview_rows(rows)
        message = _build_db_assert_message(
            operator=operator,
            field=field,
            expected=expected,
            actual=actual,
            rows=rows,
            passed=passed,
        )

        results.append({
            "type": "db",
            "target": name,
            "operator": operator,
            "field": field,
            "expected": expected,
            "actual": actual,
            "passed": passed,
            "message": message,
            "sql": exec_result.get("sql"),
            "row_count": len(rows),
            "rows_preview": preview,
            "preview_truncated": truncated,
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
