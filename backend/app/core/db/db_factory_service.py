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

from app.core.db.db_drivers import (
    enrich_execute_result,
    execute_on_datasource,
    is_write_command,
    resolve_console_max_rows,
    test_connection as driver_test_connection,
    validate_command,
)
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


async def resolve_env_default_df_worker_id(environment_id: int | None) -> int | None:
    """环境「默认接口执行机」。未配置则 None，调用方继续本机连库。"""
    if not environment_id:
        return None
    from app.core.shared.global_vars_validate import ENV_DEFAULT_PERF_WORKER_ID_KEY
    from app.models.sys import Environment

    env = await Environment.get_or_none(id=int(environment_id), is_del=False)
    if not env:
        return None
    vars_ = env.global_vars if isinstance(env.global_vars, dict) else {}
    raw = vars_.get(ENV_DEFAULT_PERF_WORKER_ID_KEY)
    if isinstance(raw, dict):
        raw = raw.get("value")
    try:
        wid = int(raw)
    except (TypeError, ValueError):
        return None
    return wid if wid > 0 else None


async def execute_sql_on_datasource(
    ds: EnvDatasource,
    sql: str,
    variables: dict[str, Any],
    *,
    for_assertion: bool = False,
    max_rows: int | None = None,
    worker_id: int | None = None,
) -> dict[str, Any]:
    import time

    final_sql, replacements = substitute_sql(sql, variables)
    allow_write = bool(ds.allow_write) and not for_assertion
    limit = int(max_rows) if max_rows is not None else int(ds.max_rows or 100)
    limit = max(1, min(limit, 1000))
    start = time.monotonic()

    if worker_id:
        from app.modules.http.worker_df_proxy import (
            WorkerProxyError,
            map_proxy_error_to_result,
            require_df_proxy_worker,
            send_df_probe_via_worker,
        )

        try:
            worker = await require_df_proxy_worker(int(ds.project_id), int(worker_id))
            result = await send_df_probe_via_worker(
                worker=worker,
                ds=ds,
                mode="execute",
                statement=final_sql,
                allow_write=allow_write,
                for_assertion=for_assertion,
                max_rows=limit,
            )
        except WorkerProxyError as exc:
            result = map_proxy_error_to_result(exc)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        out = enrich_execute_result(result if isinstance(result, dict) else {})
        out["sql"] = final_sql
        out["replacements"] = replacements
        out["elapsed_ms"] = elapsed_ms
        return out

    result = await asyncio.to_thread(
        _execute_sql_sync,
        ds,
        final_sql,
        allow_write=allow_write,
        for_assertion=for_assertion,
        max_rows=limit,
    )
    elapsed_ms = int((time.monotonic() - start) * 1000)
    out = enrich_execute_result(result)
    out["sql"] = final_sql
    out["replacements"] = replacements
    out["elapsed_ms"] = elapsed_ms
    return out


async def execute_console_on_datasource(
    ds: EnvDatasource,
    sql: str,
    variables: dict[str, Any] | None = None,
    *,
    max_rows: int | None = None,
    confirm_write: bool = False,
) -> dict[str, Any]:
    """查询控制台执行：写操作需 confirm_write；默认行数更保守。"""
    statement = (sql or "").strip()
    if not statement:
        return enrich_execute_result(
            {
                "success": False,
                "error": "语句不能为空",
                "rows": [],
                "row_count": 0,
                "affected_rows": 0,
                "elapsed_ms": 0,
            }
        )

    db_type = (ds.db_type or "mysql").lower()
    needs_write = is_write_command(statement, db_type=db_type)
    if needs_write and not bool(ds.allow_write):
        return enrich_execute_result(
            {
                "success": False,
                "error": "当前数据源为只读，不允许执行写操作；请在数据源配置中开启「允许写操作」",
                "rows": [],
                "row_count": 0,
                "affected_rows": 0,
                "elapsed_ms": 0,
                "requires_confirm": False,
                "is_write": True,
            }
        )
    if needs_write and not confirm_write:
        return enrich_execute_result(
            {
                "success": False,
                "error": "写操作需二次确认后重试",
                "rows": [],
                "row_count": 0,
                "affected_rows": 0,
                "elapsed_ms": 0,
                "requires_confirm": True,
                "is_write": True,
            }
        )

    limit = resolve_console_max_rows(ds.max_rows, max_rows)
    out = await execute_sql_on_datasource(
        ds, statement, variables or {}, for_assertion=False, max_rows=limit
    )
    out["is_write"] = needs_write
    out["requires_confirm"] = False
    out["max_rows_applied"] = limit
    return out


def _catalog_sql_statements(ds: EnvDatasource, *, scope: str, object_name: str | None) -> str:
    """生成 catalog 用的只读语句（可经执行机 execute）。"""
    from app.core.db.db_drivers import (
        CATALOG_OBJECT_LIMIT,
        CATALOG_REDIS_LIMIT,
        _SAFE_ES_INDEX,
        _SAFE_REDIS_PREFIX,
        _SAFE_SQL_IDENT,
        _redis_scan_match,
        es_cat_indices_statement,
        quote_sql_ident,
    )

    db_type = (ds.db_type or "mysql").lower()
    scope_n = (scope or "objects").strip().lower()
    if db_type == "elasticsearch":
        if scope_n in ("indexes", "ddl"):
            raise ValueError("Elasticsearch 不支持 indexes/ddl 目录")
        if scope_n == "sample":
            idx = (object_name or "").strip()
            if not idx or not _SAFE_ES_INDEX.match(idx):
                raise ValueError("请指定合法索引名")
            from app.core.db.db_drivers import sample_es_search

            return sample_es_search(idx, size=1)
        if scope_n in ("columns", "fields"):
            idx = (object_name or "").strip()
            if not idx or not _SAFE_ES_INDEX.match(idx):
                raise ValueError("请指定合法索引名")
            return f"GET {idx}/_field_caps?fields=*"
        return es_cat_indices_statement(object_name)
    if db_type == "redis":
        if scope_n in ("indexes", "ddl", "sample"):
            raise ValueError("Redis 不支持 indexes/ddl/sample 目录；请用 objects（SCAN）或 columns（TYPE）")
        if scope_n in ("columns", "fields"):
            key = (object_name or "").strip()
            if not key or "*" in key or not _SAFE_REDIS_PREFIX.match(key):
                raise ValueError("请指定合法 Redis key")
            return f"TYPE {key}"
        match = _redis_scan_match(object_name)
        return f"SCAN 0 MATCH {match} COUNT {CATALOG_REDIS_LIMIT}"
    if scope_n == "sample":
        raise ValueError("sample 仅支持 Elasticsearch；SQL 请用 objects/columns/indexes/ddl")
    if scope_n == "indexes":
        table = (object_name or "").strip()
        if not _SAFE_SQL_IDENT.match(table):
            raise ValueError("请指定合法表名")
        if db_type == "postgresql":
            return (
                "SELECT indexname AS name, indexdef AS definition "
                "FROM pg_indexes "
                f"WHERE schemaname = current_schema() AND tablename = '{table}' "
                "ORDER BY indexname"
            )
        return (
            "SELECT INDEX_NAME AS name, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS columns, "
            "MAX(NON_UNIQUE) AS non_unique, MAX(INDEX_TYPE) AS index_type "
            "FROM information_schema.STATISTICS "
            f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table}' "
            "GROUP BY INDEX_NAME ORDER BY INDEX_NAME"
        )
    if scope_n == "ddl":
        table = (object_name or "").strip()
        if not _SAFE_SQL_IDENT.match(table):
            raise ValueError("请指定合法表名")
        if db_type == "postgresql":
            return (
                "SELECT column_name AS name, data_type AS type, is_nullable AS nullable "
                "FROM information_schema.columns "
                f"WHERE table_schema = current_schema() AND table_name = '{table}' "
                "ORDER BY ordinal_position"
            )
        q = quote_sql_ident(table, db_type="mysql")
        return f"SHOW CREATE TABLE {q}"
    if scope_n in ("columns", "fields"):
        table = (object_name or "").strip()
        if not _SAFE_SQL_IDENT.match(table):
            raise ValueError("请指定合法表名")
        if db_type == "postgresql":
            return (
                "SELECT column_name AS name, data_type AS type, is_nullable AS nullable, "
                "'' AS col_key, '' AS comment "
                "FROM information_schema.columns "
                f"WHERE table_schema = current_schema() AND table_name = '{table}' "
                "ORDER BY ordinal_position"
            )
        return (
            "SELECT COLUMN_NAME AS name, COLUMN_TYPE AS type, IS_NULLABLE AS nullable, "
            "COLUMN_KEY AS col_key, COLUMN_COMMENT AS comment "
            "FROM information_schema.COLUMNS "
            f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table}' "
            "ORDER BY ORDINAL_POSITION"
        )
    if db_type == "postgresql":
        return (
            "SELECT table_name AS name, table_type AS kind "
            "FROM information_schema.tables "
            "WHERE table_schema = current_schema() "
            "ORDER BY table_name "
            f"LIMIT {CATALOG_OBJECT_LIMIT}"
        )
    return (
        "SELECT TABLE_NAME AS name, TABLE_TYPE AS kind, TABLE_ROWS AS approx_rows, "
        "TABLE_COMMENT AS comment "
        "FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() "
        "ORDER BY TABLE_NAME "
        f"LIMIT {CATALOG_OBJECT_LIMIT}"
    )


def reshape_catalog_execute_result(
    ds: EnvDatasource,
    *,
    scope: str,
    execute_result: dict[str, Any],
    object_name: str | None = None,
) -> dict[str, Any]:
    """把 execute 结果折成 catalog 结构（经执行机与直连共用）。"""
    from app.core.db.db_drivers import _SAFE_SQL_IDENT, collect_es_catalog_objects, quote_sql_ident

    db_type = (ds.db_type or "mysql").lower()
    default_target = (ds.database_name or "").strip()
    if db_type == "elasticsearch" and not default_target:
        default_target = "_all"
    if db_type == "redis" and not default_target:
        default_target = "0"
    base: dict[str, Any] = {
        "success": True,
        "db_type": db_type,
        "default_target": default_target,
        "objects": [],
        "columns": [],
        "indexes": [],
        "ddl": None,
        "sample": None,
        "hint": "",
        "error": None,
        "via_worker": bool(execute_result.get("via_worker")),
    }
    if not execute_result.get("success"):
        base["success"] = False
        base["error"] = execute_result.get("error") or "读取目录失败"
        return base
    scope_n = (scope or "objects").strip().lower()
    rows = execute_result.get("rows") or []
    if db_type == "redis":
        if scope_n in ("columns", "fields"):
            typ = "string"
            if rows:
                typ = str(rows[0].get("type") or "string")
            key = (object_name or "").strip()
            base["columns"] = [
                {
                    "name": key or "key",
                    "type": typ,
                    "nullable": True,
                    "key": "",
                    "comment": "",
                }
            ]
            return base
        objects = []
        for row in rows:
            name = str(row.get("key") or row.get("name") or "").strip()
            if not name:
                continue
            objects.append({"name": name, "kind": str(row.get("type") or "key"), "meta": {}})
        objects.sort(key=lambda x: x["name"])
        base["objects"] = objects
        base["hint"] = "经执行机 SCAN 单轮结果；类型可能需双击后按 string 处理，或直连刷新。"
        return base
    if db_type == "elasticsearch":
        if scope_n == "sample":
            base["sample"] = rows[0] if rows else None
            base["hint"] = "已取至多 1 条样例文档（match_all）。"
            return base
        if scope_n in ("columns", "fields"):
            cols = []
            for row in rows:
                name = str(row.get("name") or "").strip()
                if not name:
                    continue
                cols.append(
                    {
                        "name": name,
                        "type": str(row.get("type") or ""),
                        "nullable": True,
                        "key": "",
                        "comment": "",
                    }
                )
            base["columns"] = cols
            return base
        objects, hint = collect_es_catalog_objects(rows, object_name)
        if not hint and execute_result.get("truncated") and not (object_name or "").strip():
            hint = (
                f"集群索引很多，经执行机这次只带回前 {len(objects)} 个。"
                "在左侧筛选框输入索引名后回车或点刷新，会按名字向 Elasticsearch 查询。"
            )
        base["objects"] = objects
        if hint:
            base["hint"] = hint
        return base
    if scope_n == "indexes":
        indexes = []
        for row in rows:
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            if db_type == "postgresql":
                definition = str(row.get("definition") or "")
                indexes.append(
                    {
                        "name": name,
                        "definition": definition,
                        "columns": "",
                        "unique": "UNIQUE" in definition.upper(),
                        "type": "",
                    }
                )
            else:
                indexes.append(
                    {
                        "name": name,
                        "definition": "",
                        "columns": str(row.get("columns") or ""),
                        "unique": str(row.get("non_unique")).lower() in ("0", "false"),
                        "type": str(row.get("index_type") or ""),
                    }
                )
        base["indexes"] = indexes
        return base
    if scope_n == "ddl":
        table = (object_name or "").strip()
        if db_type == "postgresql":
            lines = []
            for row in rows:
                cname = str(row.get("name") or "")
                ctype = str(row.get("type") or "text")
                null_ok = str(row.get("nullable") or "").upper() in ("YES", "Y", "TRUE", "1")
                if not cname:
                    continue
                lines.append(f'  "{cname}" {ctype}{"" if null_ok else " NOT NULL"}')
            q = quote_sql_ident(table or "t", db_type="postgresql")
            base["ddl"] = (
                f"CREATE TABLE {q} (\n" + ",\n".join(lines) + "\n);"
                if lines
                else f"-- 无列: {table}"
            )
            return base
        ddl = ""
        for row in rows:
            for k, v in row.items():
                if "create" in str(k).lower() and v:
                    ddl = str(v)
                    break
            if ddl:
                break
        base["ddl"] = ddl or None
        if not base["ddl"]:
            base["success"] = False
            base["error"] = "未返回建表语句"
        return base
    if scope_n in ("columns", "fields"):
        cols = []
        for row in rows:
            cols.append(
                {
                    "name": str(row.get("name") or ""),
                    "type": str(row.get("type") or ""),
                    "nullable": str(row.get("nullable") or "").upper() in ("YES", "Y", "TRUE", "1"),
                    "key": str(row.get("col_key") or ""),
                    "comment": str(row.get("comment") or ""),
                }
            )
        base["columns"] = [c for c in cols if c["name"]]
        return base
    objects = []
    for row in rows:
        kind_raw = str(row.get("kind") or "BASE TABLE").upper()
        kind = "view" if "VIEW" in kind_raw else "table"
        name = str(row.get("name") or "")
        if not name or not _SAFE_SQL_IDENT.match(name):
            continue
        objects.append(
            {
                "name": name,
                "kind": kind,
                "meta": {"rows": row.get("approx_rows"), "comment": row.get("comment") or ""},
            }
        )
    base["objects"] = objects
    return base


async def fetch_catalog_on_datasource(
    ds: EnvDatasource,
    *,
    scope: str = "objects",
    object_name: str | None = None,
) -> dict[str, Any]:
    from app.core.db.db_drivers import fetch_catalog

    return await asyncio.to_thread(
        fetch_catalog, ds, scope=scope, object_name=object_name
    )


async def run_sql_templates_by_ids(
    template_ids: list[int],
    variables: dict[str, Any],
    env_id: int,
    project_id: int,
    *,
    phase: str = "setup",
    worker_id: int | None = None,
    use_env_default: bool = False,
) -> dict[str, Any]:
    logs: list[dict[str, Any]] = []
    success = True
    extracted_vars = dict(variables or {})
    if worker_id is None and use_env_default:
        worker_id = await resolve_env_default_df_worker_id(env_id)

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

        exec_result = await execute_sql_on_datasource(
            ds, tpl.sql_text, extracted_vars, for_assertion=False, worker_id=worker_id
        )
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
            "via_worker": bool(exec_result.get("via_worker")),
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
    *,
    worker_id: int | None = None,
    use_env_default: bool = False,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    all_passed = True
    if worker_id is None and use_env_default:
        worker_id = await resolve_env_default_df_worker_id(env_id)

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

        exec_result = await execute_sql_on_datasource(
            ds, sql, variables, for_assertion=True, worker_id=worker_id
        )
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
                "via_worker": bool(exec_result.get("via_worker")),
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
            "via_worker": bool(exec_result.get("via_worker")),
        })

    return {"all_passed": all_passed, "results": results}


async def run_suite_db_assertions(
    assertions: list[dict],
    variables: dict[str, Any],
    env_id: int,
    project_id: int,
    *,
    worker_id: int | None = None,
) -> dict[str, Any]:
    return await evaluate_db_assertions(
        assertions, variables, env_id, project_id, worker_id=worker_id
    )


def encrypt_datasource_password(password: Optional[str]) -> Optional[str]:
    if password is None:
        return None
    text = password.strip()
    if not text:
        return None
    return encrypt_value(text)
