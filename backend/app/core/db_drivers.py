"""数据工厂多数据源驱动：MySQL / PostgreSQL / Redis"""
from __future__ import annotations

import re
from typing import Any

import pymysql
import redis

from app.core.encryption import decrypt_value
from app.models.http import EnvDatasource

READ_SQL = re.compile(r"^\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN)\b", re.IGNORECASE)
WRITE_SQL = re.compile(r"\b(INSERT|UPDATE|DELETE|REPLACE)\b", re.IGNORECASE)
FORBIDDEN_SQL = re.compile(
    r"\b(DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|LOAD\s+FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE)\b",
    re.IGNORECASE,
)

REDIS_READ_CMDS = frozenset(
    {"GET", "HGET", "HGETALL", "EXISTS", "TYPE", "LLEN", "SCARD", "TTL", "STRLEN", "MGET", "HMGET", "ZRANGE", "LRANGE"}
)
REDIS_WRITE_CMDS = frozenset({"SET", "DEL", "HDEL", "HSET", "LPUSH", "RPUSH", "SADD", "ZADD"})


def _decrypt_password(ds: EnvDatasource) -> str:
    if not ds.password_encrypted:
        return ""
    try:
        return decrypt_value(ds.password_encrypted) or ""
    except Exception:
        return ""


def _normalize_value(val: Any) -> Any:
    from decimal import Decimal

    if isinstance(val, Decimal):
        return float(val) if val % 1 else int(val)
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except Exception:
            return val.hex()
    return val


def validate_command(
    text: str,
    *,
    db_type: str,
    allow_write: bool,
    for_assertion: bool = False,
) -> tuple[bool, str]:
    cmd = (text or "").strip()
    if not cmd:
        return False, "命令/SQL 不能为空"

    db_type = (db_type or "mysql").lower()
    if db_type == "redis":
        parts = cmd.split()
        if not parts:
            return False, "Redis 命令不能为空"
        op = parts[0].upper()
        if FORBIDDEN_SQL.search(cmd):
            return False, "禁止危险命令"
        if for_assertion or not allow_write:
            if op not in REDIS_READ_CMDS:
                return False, f"当前模式仅允许只读 Redis 命令：{', '.join(sorted(REDIS_READ_CMDS))}"
        else:
            if op not in REDIS_READ_CMDS and op not in REDIS_WRITE_CMDS:
                return False, "不支持的 Redis 命令"
        return True, ""

    if FORBIDDEN_SQL.search(cmd):
        return False, "禁止执行 DROP/TRUNCATE/ALTER 等危险语句"
    if for_assertion or not allow_write:
        if WRITE_SQL.search(cmd):
            return False, "当前模式仅允许 SELECT 查询"
        if not READ_SQL.match(cmd):
            return False, "仅允许 SELECT/SHOW/DESCRIBE/EXPLAIN 语句"
    return True, ""


def _mysql_kwargs(ds: EnvDatasource, password: str) -> dict[str, Any]:
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


def _execute_mysql(ds: EnvDatasource, sql: str, *, allow_write: bool, for_assertion: bool, max_rows: int) -> dict[str, Any]:
    ok, err = validate_command(sql, db_type="mysql", allow_write=allow_write, for_assertion=for_assertion)
    if not ok:
        return {"success": False, "error": err, "rows": [], "row_count": 0, "affected_rows": 0}

    conn = None
    try:
        conn = pymysql.connect(**_mysql_kwargs(ds, _decrypt_password(ds)))
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
            return {"success": True, "rows": [], "row_count": 0, "affected_rows": cursor.rowcount}
    except Exception as exc:
        return {"success": False, "error": str(exc), "rows": [], "row_count": 0, "affected_rows": 0}
    finally:
        if conn:
            conn.close()


def _execute_postgresql(ds: EnvDatasource, sql: str, *, allow_write: bool, for_assertion: bool, max_rows: int) -> dict[str, Any]:
    ok, err = validate_command(sql, db_type="postgresql", allow_write=allow_write, for_assertion=for_assertion)
    if not ok:
        return {"success": False, "error": err, "rows": [], "row_count": 0, "affected_rows": 0}

    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        return {"success": False, "error": "未安装 psycopg2，请在后端 requirements 中添加 psycopg2-binary", "rows": [], "row_count": 0, "affected_rows": 0}

    conn = None
    try:
        conn = psycopg2.connect(
            host=ds.host,
            port=int(ds.port or 5432),
            user=ds.username,
            password=_decrypt_password(ds),
            dbname=ds.database_name,
            connect_timeout=int(ds.timeout_seconds or 10),
        )
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql)
            if READ_SQL.match(sql.strip()):
                rows = cursor.fetchmany(max_rows + 1)
                truncated = len(rows) > max_rows
                if truncated:
                    rows = rows[:max_rows]
                normalized = [{k: _normalize_value(v) for k, v in dict(row).items()} for row in rows]
                return {
                    "success": True,
                    "rows": normalized,
                    "row_count": len(normalized),
                    "affected_rows": 0,
                    "truncated": truncated,
                }
            conn.commit()
            return {"success": True, "rows": [], "row_count": 0, "affected_rows": cursor.rowcount}
    except Exception as exc:
        return {"success": False, "error": str(exc), "rows": [], "row_count": 0, "affected_rows": 0}
    finally:
        if conn:
            conn.close()


def _redis_value_to_row(value: Any, field: str = "value") -> list[dict]:
    if value is None:
        return []
    if isinstance(value, dict):
        if not value:
            return []
        return [dict(value)]
    if isinstance(value, (list, tuple, set)):
        return [{"value": _normalize_value(v)} for v in value] or [{"value": ""}]
    return [{field: _normalize_value(value)}]


def _execute_redis(ds: EnvDatasource, command: str, *, allow_write: bool, for_assertion: bool, max_rows: int) -> dict[str, Any]:
    ok, err = validate_command(command, db_type="redis", allow_write=allow_write, for_assertion=for_assertion)
    if not ok:
        return {"success": False, "error": err, "rows": [], "row_count": 0, "affected_rows": 0}

    try:
        db_index = int(ds.database_name or "0")
    except ValueError:
        db_index = 0

    client = None
    try:
        client = redis.Redis(
            host=ds.host,
            port=int(ds.port or 6379),
            db=db_index,
            password=_decrypt_password(ds) or None,
            username=ds.username or None,
            socket_timeout=int(ds.timeout_seconds or 10),
            decode_responses=True,
        )
        parts = command.strip().split()
        op = parts[0].upper()
        args = parts[1:]

        if op == "GET" and len(args) >= 1:
            val = client.get(args[0])
            rows = _redis_value_to_row(val)
        elif op == "HGET" and len(args) >= 2:
            val = client.hget(args[0], args[1])
            rows = _redis_value_to_row(val, field=args[1])
        elif op == "HGETALL" and len(args) >= 1:
            val = client.hgetall(args[0])
            rows = _redis_value_to_row(val)
        elif op == "EXISTS" and len(args) >= 1:
            rows = [{"exists": int(client.exists(args[0]))}]
        elif op == "TYPE" and len(args) >= 1:
            rows = [{"type": client.type(args[0])}]
        elif op == "LLEN" and len(args) >= 1:
            rows = [{"length": client.llen(args[0])}]
        elif op == "SCARD" and len(args) >= 1:
            rows = [{"count": client.scard(args[0])}]
        elif op == "TTL" and len(args) >= 1:
            rows = [{"ttl": client.ttl(args[0])}]
        elif op == "STRLEN" and len(args) >= 1:
            rows = [{"length": client.strlen(args[0])}]
        elif op in REDIS_WRITE_CMDS and allow_write and not for_assertion:
            if op == "SET" and len(args) >= 2:
                client.set(args[0], " ".join(args[1:]))
            elif op == "DEL" and args:
                client.delete(*args)
            else:
                return {"success": False, "error": f"暂不支持的写命令: {op}", "rows": [], "row_count": 0, "affected_rows": 0}
            rows = []
            return {"success": True, "rows": rows, "row_count": 0, "affected_rows": 1}
        else:
            return {"success": False, "error": f"不支持的 Redis 命令: {op}", "rows": [], "row_count": 0, "affected_rows": 0}

        if len(rows) > max_rows:
            rows = rows[:max_rows]
        return {"success": True, "rows": rows, "row_count": len(rows), "affected_rows": 0}
    except Exception as exc:
        return {"success": False, "error": str(exc), "rows": [], "row_count": 0, "affected_rows": 0}
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass


def execute_on_datasource(
    ds: EnvDatasource,
    sql: str,
    *,
    allow_write: bool,
    for_assertion: bool,
    max_rows: int,
) -> dict[str, Any]:
    db_type = (ds.db_type or "mysql").lower()
    if db_type == "postgresql":
        return _execute_postgresql(ds, sql, allow_write=allow_write, for_assertion=for_assertion, max_rows=max_rows)
    if db_type == "redis":
        return _execute_redis(ds, sql, allow_write=allow_write, for_assertion=for_assertion, max_rows=max_rows)
    return _execute_mysql(ds, sql, allow_write=allow_write, for_assertion=for_assertion, max_rows=max_rows)


def test_connection(ds: EnvDatasource) -> dict[str, Any]:
    db_type = (ds.db_type or "mysql").lower()
    if db_type == "redis":
        probe = "EXISTS __brickcore_ping__"
    elif db_type == "postgresql":
        probe = "SELECT 1 AS ok"
    else:
        probe = "SELECT 1 AS ok"
    result = execute_on_datasource(ds, probe, allow_write=False, for_assertion=True, max_rows=1)
    return {"success": result.get("success", False), "error": result.get("error"), "rows": result.get("rows", [])}
