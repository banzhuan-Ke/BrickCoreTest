"""数据工厂多数据源驱动：MySQL / PostgreSQL / Redis / Elasticsearch"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

import pymysql
import redis

from app.core.platform.encryption import decrypt_value
from app.models.http import EnvDatasource

READ_SQL = re.compile(r"^\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN)\b", re.IGNORECASE)
WRITE_SQL = re.compile(r"\b(INSERT|UPDATE|DELETE|REPLACE)\b", re.IGNORECASE)
FORBIDDEN_SQL = re.compile(
    r"\b(DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|LOAD\s+FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE)\b",
    re.IGNORECASE,
)

REDIS_READ_CMDS = frozenset(
    {
        "GET",
        "HGET",
        "HGETALL",
        "EXISTS",
        "TYPE",
        "LLEN",
        "SCARD",
        "ZCARD",
        "TTL",
        "STRLEN",
        "MGET",
        "HMGET",
        "ZRANGE",
        "LRANGE",
        "SMEMBERS",
        "SCAN",
    }
)
REDIS_WRITE_CMDS = frozenset({"SET", "DEL", "HDEL", "HSET", "LPUSH", "RPUSH", "SADD", "ZADD"})

# ES 只读路径片段（POST 到这些仍视为读）
ES_READ_PATH_MARKERS = (
    "/_search",
    "/_msearch",
    "/_count",
    "/_explain",
    "/_validate",
    "/_field_caps",
    "/_mapping",
    "/_settings",
    "/_aliases",
    "/_stats",
    "/_cat/",
    "/_cluster/",
    "/_nodes/",
    "/_resolve/",
    "/_sql",
)
ES_HTTP_LINE = re.compile(r"^(GET|POST|PUT|DELETE|HEAD)\s+(\S+)\s*$", re.IGNORECASE)

# 查询控制台默认行数上限（可再被数据源 max_rows 收紧）
CONSOLE_DEFAULT_MAX_ROWS = 200
CONSOLE_HARD_MAX_ROWS = 1000


def is_write_command(text: str, *, db_type: str = "mysql") -> bool:
    """判断语句/命令是否为写操作（控制台二次确认用）。"""
    cmd = (text or "").strip()
    if not cmd:
        return False
    db_type = (db_type or "mysql").lower()
    if db_type == "redis":
        op = cmd.split()[0].upper()
        return op in REDIS_WRITE_CMDS
    if db_type == "elasticsearch":
        try:
            method, path, _body = parse_es_request(cmd, default_index="_all")
        except ValueError:
            return False
        return es_path_is_write(method, path)
    return bool(WRITE_SQL.search(cmd))

def enrich_execute_result(result: dict[str, Any] | None) -> dict[str, Any]:
    """补齐 columns / truncated 等控制台统一字段。"""
    out = dict(result or {})
    rows = out.get("rows") if isinstance(out.get("rows"), list) else []
    columns: list[str] = []
    if rows and isinstance(rows[0], dict):
        # 保序：首行 keys，再并入后续行出现的新列
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            for k in row.keys():
                sk = str(k)
                if sk not in seen:
                    seen.add(sk)
                    columns.append(sk)
    out.setdefault("columns", columns)
    out.setdefault("truncated", bool(out.get("truncated")))
    out.setdefault("row_count", len(rows) if rows else int(out.get("row_count") or 0))
    out.setdefault("affected_rows", int(out.get("affected_rows") or 0))
    out.setdefault("success", bool(out.get("success")))
    if "error" not in out:
        out["error"] = None
    return out


def resolve_console_max_rows(ds_max_rows: int | None, requested: int | None = None) -> int:
    base = int(ds_max_rows or 100)
    base = max(1, min(base, CONSOLE_HARD_MAX_ROWS))
    if requested is None:
        return min(base, CONSOLE_DEFAULT_MAX_ROWS)
    try:
        req = int(requested)
    except (TypeError, ValueError):
        req = CONSOLE_DEFAULT_MAX_ROWS
    return max(1, min(req, base, CONSOLE_HARD_MAX_ROWS))


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

    if db_type == "elasticsearch":
        try:
            method, path, _body = parse_es_request(cmd, default_index="_all")
        except ValueError as exc:
            return False, str(exc)
        if for_assertion or not allow_write:
            if es_path_is_write(method, path):
                return False, "当前模式仅允许 Elasticsearch 只读请求（GET/_search/_count 等）；写 API 需开启「允许写操作」"
        return True, ""

    if FORBIDDEN_SQL.search(cmd):
        # 仅放行单条 SHOW CREATE …；禁止夹带其它语句
        if not re.match(
            r"^\s*SHOW\s+CREATE\s+(TABLE|VIEW|DATABASE)\s+\S+\s*;?\s*$",
            cmd,
            re.IGNORECASE,
        ):
            return False, "禁止执行 DROP/TRUNCATE/ALTER 等危险语句"
    if for_assertion or not allow_write:
        if WRITE_SQL.search(cmd):
            return False, "当前模式仅允许 SELECT 查询"
        if not READ_SQL.match(cmd):
            return False, "仅允许 SELECT/SHOW/DESCRIBE/EXPLAIN 语句"
        # EXPLAIN ANALYZE / ANALYSE 会实际执行语句，只读模式禁止
        if re.match(r"^\s*EXPLAIN\s+ANALY[SZ]E\b", cmd, re.IGNORECASE):
            return False, "只读模式禁止 EXPLAIN ANALYZE（会实际执行语句）；请用 EXPLAIN"
    return True, ""


def es_path_is_write(method: str, path: str) -> bool:
    """判断 ES HTTP 方法+路径是否为写操作。"""
    m = (method or "GET").upper()
    p = "/" + (path or "").lstrip("/").lower()
    if m in ("GET", "HEAD"):
        return False
    if m == "DELETE":
        return True
    if m == "PUT":
        return True
    if m == "POST":
        for marker in ES_READ_PATH_MARKERS:
            if marker in p:
                return False
        return True
    return True


def flatten_es_value(val: Any) -> Any:
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return _normalize_value(val)


def flatten_es_dict(obj: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """嵌套对象摊成点路径；数组/复杂值序列化为 JSON 字符串。"""
    out: dict[str, Any] = {}
    for key, val in (obj or {}).items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(val, dict):
            out.update(flatten_es_dict(val, path))
        else:
            out[path] = flatten_es_value(val)
    return out


def hits_to_rows(payload: Any, max_rows: int) -> tuple[list[dict[str, Any]], bool]:
    """
    将 ES 响应摊成行：
    - `_search`：每条 hit 一行，含 `_index`/`_id`/`_score` + 扁平化 `_source`
    - `get` 单文档：一行（found=false 时 0 行）
    - `_cat/*?format=json`：数组逐行
    - 其它（health/mapping）：顶层字段摊成一行
    """
    if isinstance(payload, list):
        rows: list[dict[str, Any]] = []
        for item in payload[:max_rows]:
            if isinstance(item, dict):
                rows.append({str(k): flatten_es_value(v) for k, v in item.items()})
            else:
                rows.append({"value": flatten_es_value(item)})
        return rows, len(payload) > max_rows

    if not isinstance(payload, dict):
        return [{"value": flatten_es_value(payload)}], False

    hits_block = payload.get("hits")
    if isinstance(hits_block, dict) and isinstance(hits_block.get("hits"), list):
        hits = hits_block["hits"]
        total_raw = hits_block.get("total")
        if isinstance(total_raw, dict):
            total_val = int(total_raw.get("value") or 0)
        else:
            try:
                total_val = int(total_raw or 0)
            except (TypeError, ValueError):
                total_val = len(hits)
        rows = []
        for hit in hits[:max_rows]:
            if not isinstance(hit, dict):
                continue
            row: dict[str, Any] = {
                "_index": hit.get("_index"),
                "_id": hit.get("_id"),
            }
            if "_score" in hit:
                row["_score"] = hit.get("_score")
            src = hit.get("_source")
            if isinstance(src, dict):
                row.update(flatten_es_dict(src))
            elif src is not None:
                row["_source"] = flatten_es_value(src)
            rows.append(row)
        truncated = len(hits) > max_rows or (total_val > len(rows) and len(hits) >= max_rows)
        return rows, truncated

    if "found" in payload or ("_source" in payload and "_id" in payload):
        if payload.get("found") is False:
            return [], False
        row = {
            "_index": payload.get("_index"),
            "_id": payload.get("_id"),
            "found": payload.get("found", True),
        }
        src = payload.get("_source")
        if isinstance(src, dict):
            row.update(flatten_es_dict(src))
        elif src is not None:
            row["_source"] = flatten_es_value(src)
        return [row], False

    # field_caps：转成字段表
    fields_block = payload.get("fields")
    if isinstance(fields_block, dict):
        rows = []
        for fname, type_map in list(fields_block.items())[:max_rows]:
            if not isinstance(type_map, dict):
                continue
            types = ",".join(sorted(str(t) for t in type_map.keys()))
            rows.append({"name": str(fname), "type": types})
        return rows, len(fields_block) > max_rows

    return [flatten_es_dict(payload)], False


def parse_es_request(text: str, *, default_index: str) -> tuple[str, str, Any | None]:
    """
    解析控制台/模板语句为 (method, path, body)。
    支持：
    1) 纯 JSON → POST /{default_index}/_search
    2) 首行 `METHOD path` + 可选 JSON body（如 GET my-index/_search）
    3) PING / HEALTH → GET /_cluster/health
    """
    cmd = (text or "").strip()
    if not cmd:
        raise ValueError("Elasticsearch 查询不能为空")

    upper = cmd.upper()
    if upper in ("PING", "HEALTH", "GET /", "GET /_CLUSTER/HEALTH"):
        return "GET", "/_cluster/health", None

    index = (default_index or "").strip() or "_all"

    if cmd.startswith("{"):
        try:
            body = json.loads(cmd)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 解析失败: {exc}") from exc
        return "POST", f"/{index.lstrip('/')}/_search", body

    lines = cmd.split("\n", 1)
    first = lines[0].strip()
    rest = lines[1].strip() if len(lines) > 1 else ""
    m = ES_HTTP_LINE.match(first)
    if not m:
        raise ValueError(
            "ES 语句须为 JSON 查询体，或首行 METHOD path（如 GET logs-*/_search）后跟可选 JSON body"
        )
    method = m.group(1).upper()
    path = m.group(2).strip()
    if not path.startswith("/"):
        path = "/" + path
    body: Any | None = None
    if rest:
        try:
            body = json.loads(rest)
        except json.JSONDecodeError as exc:
            raise ValueError(f"请求体 JSON 解析失败: {exc}") from exc
    return method, path, body


def _es_base_url(ds: EnvDatasource) -> tuple[str, bool]:
    """返回 (base_url, verify_ssl)。主机可用 https://host；前缀 insecure: 关闭证书校验。"""
    raw = (ds.host or "").strip()
    verify_ssl = True
    lower = raw.lower()
    if lower.startswith("insecure:"):
        verify_ssl = False
        raw = raw.split(":", 1)[1].strip()
    port = int(ds.port or 9200)
    if "://" in raw:
        parsed = urlparse(raw)
        scheme = parsed.scheme or "http"
        hostname = parsed.hostname or raw
        port = parsed.port or port
        if scheme == "http":
            verify_ssl = True
        return f"{scheme}://{hostname}:{port}", verify_ssl
    scheme = "https" if port == 443 else "http"
    return f"{scheme}://{raw}:{port}", verify_ssl


def _execute_elasticsearch(
    ds: EnvDatasource,
    command: str,
    *,
    allow_write: bool,
    for_assertion: bool,
    max_rows: int,
) -> dict[str, Any]:
    ok, err = validate_command(
        command, db_type="elasticsearch", allow_write=allow_write, for_assertion=for_assertion
    )
    if not ok:
        return {"success": False, "error": err, "rows": [], "row_count": 0, "affected_rows": 0}

    try:
        method, path, body = parse_es_request(command, default_index=ds.database_name or "_all")
    except ValueError as exc:
        return {"success": False, "error": str(exc), "rows": [], "row_count": 0, "affected_rows": 0}

    is_write = es_path_is_write(method, path)
    if is_write and (for_assertion or not allow_write):
        return {
            "success": False,
            "error": "当前模式不允许 Elasticsearch 写 API",
            "rows": [],
            "row_count": 0,
            "affected_rows": 0,
        }

    try:
        import httpx
    except ImportError:
        return {
            "success": False,
            "error": "未安装 httpx，无法连接 Elasticsearch",
            "rows": [],
            "row_count": 0,
            "affected_rows": 0,
        }

    base, verify_ssl = _es_base_url(ds)
    url = base.rstrip("/") + path
    timeout = float(ds.timeout_seconds or 10)
    user = (ds.username or "").strip()
    password = _decrypt_password(ds)
    auth = (user, password) if (user or password) else None

    try:
        with httpx.Client(timeout=timeout, verify=verify_ssl) as client:
            kwargs: dict[str, Any] = {"method": method, "url": url, "auth": auth}
            if body is not None:
                kwargs["json"] = body
            resp = client.request(**kwargs)
    except Exception as exc:
        return {"success": False, "error": str(exc), "rows": [], "row_count": 0, "affected_rows": 0}

    if resp.status_code >= 400:
        detail = resp.text[:500] if resp.text else resp.reason_phrase
        return {
            "success": False,
            "error": f"ES HTTP {resp.status_code}: {detail}",
            "rows": [],
            "row_count": 0,
            "affected_rows": 0,
        }

    try:
        payload = resp.json() if resp.content else {}
    except Exception:
        payload = {"raw": (resp.text or "")[:2000]}

    if is_write:
        affected = 1
        if isinstance(payload, dict):
            if "items" in payload and isinstance(payload["items"], list):
                affected = len(payload["items"])
            elif payload.get("result") in ("created", "updated", "deleted", "noop"):
                affected = 1
        return {
            "success": True,
            "rows": [],
            "row_count": 0,
            "affected_rows": affected,
            "truncated": False,
        }

    rows, truncated = hits_to_rows(payload, max_rows)
    return {
        "success": True,
        "rows": rows,
        "row_count": len(rows),
        "affected_rows": 0,
        "truncated": truncated,
    }


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
        elif op == "ZCARD" and len(args) >= 1:
            rows = [{"count": client.zcard(args[0])}]
        elif op == "TTL" and len(args) >= 1:
            rows = [{"ttl": client.ttl(args[0])}]
        elif op == "STRLEN" and len(args) >= 1:
            rows = [{"length": client.strlen(args[0])}]
        elif op == "SMEMBERS" and len(args) >= 1:
            val = client.smembers(args[0])
            rows = _redis_value_to_row(sorted(val) if isinstance(val, set) else val)
        elif op == "ZRANGE" and len(args) >= 1:
            start = int(args[1]) if len(args) >= 2 else 0
            end = int(args[2]) if len(args) >= 3 else max_rows - 1
            val = client.zrange(args[0], start, end)
            rows = _redis_value_to_row(val)
        elif op == "LRANGE" and len(args) >= 1:
            start = int(args[1]) if len(args) >= 2 else 0
            end = int(args[2]) if len(args) >= 3 else max_rows - 1
            val = client.lrange(args[0], start, end)
            rows = _redis_value_to_row(val)
        elif op == "SCAN":
            cursor = 0
            match = "*"
            count = min(max_rows, 100)
            i = 0
            while i < len(args):
                tok = args[i]
                if i == 0 and tok.isdigit():
                    cursor = int(tok)
                    i += 1
                    continue
                up = tok.upper()
                if up == "MATCH" and i + 1 < len(args):
                    match = args[i + 1]
                    i += 2
                    continue
                if up == "COUNT" and i + 1 < len(args):
                    try:
                        count = max(1, min(int(args[i + 1]), max_rows))
                    except ValueError:
                        pass
                    i += 2
                    continue
                i += 1
            next_cursor, keys = client.scan(cursor=cursor, match=match, count=count)
            rows = [{"cursor": int(next_cursor), "key": k} for k in (keys or [])]
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
    if db_type == "elasticsearch":
        return _execute_elasticsearch(ds, sql, allow_write=allow_write, for_assertion=for_assertion, max_rows=max_rows)
    return _execute_mysql(ds, sql, allow_write=allow_write, for_assertion=for_assertion, max_rows=max_rows)


_SAFE_SQL_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SAFE_ES_INDEX = re.compile(r"^[A-Za-z0-9_.*\-]+$")
_SAFE_REDIS_PREFIX = re.compile(r"^[A-Za-z0-9_.:\-/@*]*$")
CATALOG_OBJECT_LIMIT = 500
CATALOG_REDIS_LIMIT = 100
_ES_CAT_INDICES = "GET _cat/indices?format=json&h=index,docs.count,store.size,health,status"


def es_cat_indices_statement(pattern: str | None = None) -> str:
    """按名字向 ES 拉索引。空则列全集（调用方再截断）；有筛选则走 _cat/indices/pattern。"""
    raw = (pattern or "").strip()
    if not raw:
        return _ES_CAT_INDICES
    if not _SAFE_ES_INDEX.match(raw):
        raise ValueError("索引筛选只允许字母、数字以及 _ . * -")
    pat = raw if "*" in raw else f"*{raw}*"
    return f"GET _cat/indices/{pat}?format=json&h=index,docs.count,store.size,health,status"


def es_index_listed(name: str, pattern: str | None = None) -> bool:
    """默认隐藏系统索引（. 开头）；用户显式搜 . 开头时保留。"""
    if not name or not _SAFE_ES_INDEX.match(name):
        return False
    if name.startswith(".") and not (pattern or "").strip().startswith("."):
        return False
    return True


def collect_es_catalog_objects(
    rows: list[Any] | None,
    pattern: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """把 _cat/indices 行收成对象列表。超过上限时 hint 提示用名字再查。"""
    objects: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("index") or "").strip()
        if not es_index_listed(name, pattern):
            continue
        objects.append(
            {
                "name": name,
                "kind": "index",
                "meta": {
                    "docs": row.get("docs.count") or row.get("docs_count"),
                    "store": row.get("store.size") or row.get("store_size"),
                    "health": row.get("health"),
                    "status": row.get("status"),
                },
            }
        )
    objects.sort(key=lambda x: x["name"])
    truncated = len(objects) > CATALOG_OBJECT_LIMIT
    hint = ""
    if truncated and not (pattern or "").strip():
        hint = (
            f"集群索引超过 {CATALOG_OBJECT_LIMIT} 个，这里只列出按名字排序的前 {CATALOG_OBJECT_LIMIT} 个。"
            "在左侧筛选框输入索引名后回车或点刷新，会按名字向 Elasticsearch 查询。"
        )
    elif truncated:
        hint = f"匹配超过 {CATALOG_OBJECT_LIMIT} 个，请把名字写得更具体后再刷新。"
    return objects[:CATALOG_OBJECT_LIMIT], hint


def quote_sql_ident(name: str, *, db_type: str = "mysql") -> str:
    """安全引用表名（仅允许字母数字下划线）。"""
    if not _SAFE_SQL_IDENT.match(name or ""):
        raise ValueError(f"非法标识符: {name}")
    if (db_type or "mysql").lower() == "postgresql":
        return f'"{name}"'
    return f"`{name}`"


def sample_select_sql(table: str, *, db_type: str = "mysql", limit: int = 20) -> str:
    q = quote_sql_ident(table, db_type=db_type)
    lim = max(1, min(int(limit or 20), 100))
    return f"SELECT * FROM {q} LIMIT {lim}"


def sample_es_search(index: str, *, size: int = 20) -> str:
    idx = (index or "").strip() or "_all"
    if not _SAFE_ES_INDEX.match(idx):
        raise ValueError(f"非法索引名: {index}")
    sz = max(1, min(int(size or 20), 100))
    body = {"query": {"match_all": {}}, "size": sz}
    return f"GET {idx}/_search\n{json.dumps(body, ensure_ascii=False, indent=2)}"


def sample_explain_sql(table: str, *, db_type: str = "mysql", limit: int = 20) -> str:
    """生成只读 EXPLAIN 样例（不执行 ANALYZE，避免改写统计外的额外开销语义）。"""
    select = sample_select_sql(table, db_type=db_type, limit=limit)
    return f"EXPLAIN {select}"


def sample_redis_command(key: str, key_type: str = "string") -> str:
    """按 Redis 类型生成只读样例命令。"""
    k = (key or "").strip()
    t = (key_type or "string").lower()
    if t == "hash":
        return f"HGETALL {k}"
    if t == "list":
        return f"LRANGE {k} 0 19"
    if t == "set":
        return f"SMEMBERS {k}"
    if t == "zset":
        return f"ZRANGE {k} 0 19"
    return f"GET {k}"


def _redis_scan_match(prefix: str | None) -> str:
    raw = (prefix or "").strip()
    if not raw:
        return "*"
    if not _SAFE_REDIS_PREFIX.match(raw):
        raise ValueError("Redis 前缀仅允许字母数字及 _.:-/@*")
    if "*" in raw:
        return raw
    return f"{raw}*"


def _fetch_redis_catalog(
    ds: EnvDatasource,
    *,
    scope: str,
    object_name: str | None,
) -> dict[str, Any]:
    default_target = str(ds.database_name or "0")
    base: dict[str, Any] = {
        "success": True,
        "db_type": "redis",
        "default_target": default_target,
        "objects": [],
        "columns": [],
        "indexes": [],
        "ddl": None,
        "sample": None,
        "hint": "",
        "error": None,
    }
    scope_n = (scope or "objects").strip().lower()
    if scope_n in ("indexes", "ddl", "sample"):
        return {
            **base,
            "success": False,
            "error": "Redis 不支持 indexes/ddl/sample 目录；请用 objects（SCAN）或 columns（TYPE）",
        }
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
        try:
            info = client.info("keyspace") or {}
            db_key = f"db{db_index}"
            keys_approx = None
            entry = info.get(db_key)
            if isinstance(entry, dict):
                keys_approx = entry.get("keys")
            if keys_approx is not None:
                base["hint"] = (
                    f"DB {db_index} 约 {keys_approx} 个 key；"
                    f"SCAN 最多 {CATALOG_REDIS_LIMIT} 条，勿用 KEYS *。"
                )
            else:
                base["hint"] = f"DB {db_index}；SCAN 最多 {CATALOG_REDIS_LIMIT} 条。"
        except Exception:
            base["hint"] = f"DB {db_index}；按前缀 SCAN，最多 {CATALOG_REDIS_LIMIT} 条。"

        if scope_n in ("columns", "fields"):
            key = (object_name or "").strip()
            if not key or "*" in key or not _SAFE_REDIS_PREFIX.match(key):
                return {**base, "success": False, "error": "请指定合法 Redis key"}
            typ = str(client.type(key) or "none")
            ttl = client.ttl(key)
            base["columns"] = [
                {
                    "name": key,
                    "type": typ,
                    "nullable": True,
                    "key": "",
                    "comment": f"ttl={ttl}",
                }
            ]
            return base

        match = _redis_scan_match(object_name)
        keys: list[str] = []
        cursor = 0
        while len(keys) < CATALOG_REDIS_LIMIT:
            cursor, batch = client.scan(cursor=cursor, match=match, count=50)
            for k in batch or []:
                if k not in keys:
                    keys.append(k)
                if len(keys) >= CATALOG_REDIS_LIMIT:
                    break
            if cursor == 0:
                break
        keys = keys[:CATALOG_REDIS_LIMIT]
        types: list[str] = []
        if keys:
            pipe = client.pipeline(transaction=False)
            for k in keys:
                pipe.type(k)
            types = [str(t or "string") for t in pipe.execute()]
        objects = []
        for k, t in zip(keys, types or ["string"] * len(keys)):
            objects.append({"name": k, "kind": t, "meta": {}})
        objects.sort(key=lambda x: x["name"])
        base["objects"] = objects
        if len(keys) >= CATALOG_REDIS_LIMIT:
            base["hint"] = (base.get("hint") or "") + " 结果已截断，请缩小前缀。"
        return base
    except ValueError as exc:
        return {**base, "success": False, "error": str(exc)}
    except Exception as exc:
        return {**base, "success": False, "error": str(exc)}
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass


def _flatten_es_mapping_props(
    props: dict[str, Any],
    prefix: str = "",
    out: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    out = out if out is not None else []
    if not isinstance(props, dict):
        return out
    for name, spec in props.items():
        if not isinstance(spec, dict):
            continue
        path = f"{prefix}.{name}" if prefix else name
        nested = spec.get("properties")
        if isinstance(nested, dict) and nested:
            _flatten_es_mapping_props(nested, path, out)
        else:
            out.append(
                {
                    "name": path,
                    "type": str(spec.get("type") or "object"),
                    "nullable": True,
                    "key": "",
                    "comment": "",
                }
            )
    return out


def fetch_catalog(
    ds: EnvDatasource,
    *,
    scope: str = "objects",
    object_name: str | None = None,
) -> dict[str, Any]:
    """只读浏览库对象：SQL 表/列/索引/DDL，ES 索引/字段，Redis SCAN。"""
    db_type = (ds.db_type or "mysql").lower()
    default_target = (ds.database_name or "").strip()
    if db_type == "elasticsearch" and not default_target:
        default_target = "_all"
    base = {
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
    }
    scope_n = (scope or "objects").strip().lower()
    try:
        if db_type == "redis":
            return _fetch_redis_catalog(ds, scope=scope_n, object_name=object_name)
        if db_type == "elasticsearch":
            if scope_n in ("indexes", "ddl"):
                return {**base, "success": False, "error": "Elasticsearch 不支持 indexes/ddl 目录"}
            if scope_n == "sample":
                idx = (object_name or "").strip()
                if not idx or not _SAFE_ES_INDEX.match(idx):
                    return {**base, "success": False, "error": "请指定合法索引名"}
                result = _execute_elasticsearch(
                    ds,
                    sample_es_search(idx, size=1),
                    allow_write=False,
                    for_assertion=True,
                    max_rows=1,
                )
                if not result.get("success"):
                    return {**base, "success": False, "error": result.get("error") or "读取样例失败"}
                rows = result.get("rows") or []
                base["sample"] = rows[0] if rows else None
                base["hint"] = "已取至多 1 条样例文档（match_all）。"
                return base
            if scope_n in ("columns", "fields"):
                idx = (object_name or "").strip()
                if not idx or not _SAFE_ES_INDEX.match(idx):
                    return {**base, "success": False, "error": "请指定合法索引名"}
                # field_caps 比 mapping 更易摊成字段表，且经执行机 execute 也可复用
                result = _execute_elasticsearch(
                    ds,
                    f"GET {idx}/_field_caps?fields=*",
                    allow_write=False,
                    for_assertion=True,
                    max_rows=CATALOG_OBJECT_LIMIT,
                )
                if not result.get("success"):
                    return {**base, "success": False, "error": result.get("error") or "读取字段失败"}
                cols = []
                for row in result.get("rows") or []:
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
                base["columns"] = cols[:CATALOG_OBJECT_LIMIT]
                return base
            try:
                statement = es_cat_indices_statement(object_name)
            except ValueError as exc:
                return {**base, "success": False, "error": str(exc)}
            raw = _es_raw_json(ds, statement.split(" ", 1)[1])
            if not raw.get("success"):
                # 回退 execute 路径（与经执行机结果形态一致）
                result = _execute_elasticsearch(
                    ds,
                    statement,
                    allow_write=False,
                    for_assertion=True,
                    max_rows=CATALOG_OBJECT_LIMIT,
                )
                if not result.get("success"):
                    return {**base, "success": False, "error": result.get("error") or raw.get("error")}
                objects, hint = collect_es_catalog_objects(result.get("rows") or [], object_name)
                base["objects"] = objects
                if hint:
                    base["hint"] = hint
                elif result.get("truncated") and not (object_name or "").strip():
                    base["hint"] = (
                        f"集群索引超过 {CATALOG_OBJECT_LIMIT} 个，这里只列出前 {CATALOG_OBJECT_LIMIT} 个。"
                        "在左侧筛选框输入索引名后回车或点刷新，会按名字向 Elasticsearch 查询。"
                    )
                return base
            payload = raw.get("payload")
            objects, hint = collect_es_catalog_objects(
                payload if isinstance(payload, list) else [],
                object_name,
            )
            base["objects"] = objects
            if hint:
                base["hint"] = hint
            return base

        # MySQL / PostgreSQL
        if scope_n == "sample":
            return {
                **base,
                "success": False,
                "error": "sample 仅支持 Elasticsearch；SQL 请用 objects/columns/indexes/ddl",
            }
        if scope_n == "indexes":
            table = (object_name or "").strip()
            if not _SAFE_SQL_IDENT.match(table):
                return {**base, "success": False, "error": "请指定合法表名"}
            if db_type == "postgresql":
                sql = (
                    "SELECT indexname AS name, indexdef AS definition "
                    "FROM pg_indexes "
                    f"WHERE schemaname = current_schema() AND tablename = '{table}' "
                    "ORDER BY indexname"
                )
            else:
                sql = (
                    "SELECT INDEX_NAME AS name, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS columns, "
                    "MAX(NON_UNIQUE) AS non_unique, MAX(INDEX_TYPE) AS index_type "
                    "FROM information_schema.STATISTICS "
                    f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table}' "
                    "GROUP BY INDEX_NAME ORDER BY INDEX_NAME"
                )
            result = execute_on_datasource(
                ds, sql, allow_write=False, for_assertion=True, max_rows=CATALOG_OBJECT_LIMIT
            )
            if not result.get("success"):
                return {**base, "success": False, "error": result.get("error") or "读取索引失败"}
            indexes = []
            for row in result.get("rows") or []:
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
            if not _SAFE_SQL_IDENT.match(table):
                return {**base, "success": False, "error": "请指定合法表名"}
            if db_type == "postgresql":
                col_sql = (
                    "SELECT column_name AS name, data_type AS type, is_nullable AS nullable "
                    "FROM information_schema.columns "
                    f"WHERE table_schema = current_schema() AND table_name = '{table}' "
                    "ORDER BY ordinal_position"
                )
                result = execute_on_datasource(
                    ds, col_sql, allow_write=False, for_assertion=True, max_rows=CATALOG_OBJECT_LIMIT
                )
                if not result.get("success"):
                    return {**base, "success": False, "error": result.get("error") or "读取建表信息失败"}
                lines = []
                for row in result.get("rows") or []:
                    cname = str(row.get("name") or "")
                    ctype = str(row.get("type") or "text")
                    null_ok = str(row.get("nullable") or "").upper() in ("YES", "Y", "TRUE", "1")
                    if not cname:
                        continue
                    lines.append(f'  "{cname}" {ctype}{"" if null_ok else " NOT NULL"}')
                q = quote_sql_ident(table, db_type="postgresql")
                base["ddl"] = (
                    f"CREATE TABLE {q} (\n" + ",\n".join(lines) + "\n);"
                    if lines
                    else f"-- 无列: {table}"
                )
                return base
            q = quote_sql_ident(table, db_type="mysql")
            result = execute_on_datasource(
                ds,
                f"SHOW CREATE TABLE {q}",
                allow_write=False,
                for_assertion=True,
                max_rows=10,
            )
            if not result.get("success"):
                return {**base, "success": False, "error": result.get("error") or "读取建表语句失败"}
            ddl = ""
            for row in result.get("rows") or []:
                for k, v in row.items():
                    if "create" in str(k).lower() and v:
                        ddl = str(v)
                        break
                if ddl:
                    break
            base["ddl"] = ddl or None
            if not base["ddl"]:
                return {**base, "success": False, "error": "未返回建表语句"}
            return base

        if scope_n in ("columns", "fields"):
            table = (object_name or "").strip()
            if not _SAFE_SQL_IDENT.match(table):
                return {**base, "success": False, "error": "请指定合法表名"}
            if db_type == "postgresql":
                sql = (
                    "SELECT column_name AS name, data_type AS type, is_nullable AS nullable, "
                    "'' AS col_key, '' AS comment, ordinal_position "
                    "FROM information_schema.columns "
                    f"WHERE table_schema = current_schema() AND table_name = '{table}' "
                    "ORDER BY ordinal_position"
                )
            else:
                sql = (
                    "SELECT COLUMN_NAME AS name, COLUMN_TYPE AS type, IS_NULLABLE AS nullable, "
                    "COLUMN_KEY AS col_key, COLUMN_COMMENT AS comment, ORDINAL_POSITION "
                    "FROM information_schema.COLUMNS "
                    f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table}' "
                    "ORDER BY ORDINAL_POSITION"
                )
            result = execute_on_datasource(
                ds, sql, allow_write=False, for_assertion=True, max_rows=CATALOG_OBJECT_LIMIT
            )
            if not result.get("success"):
                return {**base, "success": False, "error": result.get("error") or "读取列失败"}
            cols = []
            for row in result.get("rows") or []:
                cols.append(
                    {
                        "name": str(row.get("name") or ""),
                        "type": str(row.get("type") or ""),
                        "nullable": str(row.get("nullable") or "").upper() in ("YES", "Y", "TRUE", "1"),
                        "key": str(row.get("col_key") or ""),
                        "comment": str(row.get("comment") or ""),
                    }
                )
            base["columns"] = cols
            return base

        if db_type == "postgresql":
            sql = (
                "SELECT table_name AS name, table_type AS kind "
                "FROM information_schema.tables "
                "WHERE table_schema = current_schema() "
                "ORDER BY table_name "
                f"LIMIT {CATALOG_OBJECT_LIMIT}"
            )
        else:
            sql = (
                "SELECT TABLE_NAME AS name, TABLE_TYPE AS kind, TABLE_ROWS AS approx_rows, "
                "TABLE_COMMENT AS comment "
                "FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "ORDER BY TABLE_NAME "
                f"LIMIT {CATALOG_OBJECT_LIMIT}"
            )
        result = execute_on_datasource(
            ds, sql, allow_write=False, for_assertion=True, max_rows=CATALOG_OBJECT_LIMIT
        )
        if not result.get("success"):
            return {**base, "success": False, "error": result.get("error") or "读取对象失败"}
        objects = []
        for row in result.get("rows") or []:
            kind_raw = str(row.get("kind") or "BASE TABLE").upper()
            kind = "view" if "VIEW" in kind_raw else "table"
            name = str(row.get("name") or "")
            if not name or not _SAFE_SQL_IDENT.match(name):
                continue
            objects.append(
                {
                    "name": name,
                    "kind": kind,
                    "meta": {
                        "rows": row.get("approx_rows"),
                        "comment": row.get("comment") or "",
                    },
                }
            )
        base["objects"] = objects
        return base
    except Exception as exc:
        return {**base, "success": False, "error": str(exc)}


def _es_raw_json(ds: EnvDatasource, path: str) -> dict[str, Any]:
    """ES 原始 JSON（catalog 用，不走 hits 摊行）。"""
    try:
        import httpx
    except ImportError:
        return {"success": False, "error": "未安装 httpx，无法连接 Elasticsearch"}
    base, verify_ssl = _es_base_url(ds)
    url = base.rstrip("/") + ("/" + path.lstrip("/"))
    timeout = float(ds.timeout_seconds or 10)
    user = (ds.username or "").strip()
    password = _decrypt_password(ds)
    auth = (user, password) if (user or password) else None
    try:
        with httpx.Client(timeout=timeout, verify=verify_ssl) as client:
            resp = client.get(url, auth=auth)
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    if resp.status_code >= 400:
        detail = resp.text[:500] if resp.text else resp.reason_phrase
        return {"success": False, "error": f"ES HTTP {resp.status_code}: {detail}"}
    try:
        payload = resp.json() if resp.content else {}
    except Exception:
        return {"success": False, "error": "ES 返回非 JSON"}
    return {"success": True, "payload": payload}


def test_connection(ds: EnvDatasource) -> dict[str, Any]:
    db_type = (ds.db_type or "mysql").lower()
    if db_type == "redis":
        probe = "EXISTS __brickcore_ping__"
    elif db_type == "elasticsearch":
        probe = "PING"
    elif db_type == "postgresql":
        probe = "SELECT 1 AS ok"
    else:
        probe = "SELECT 1 AS ok"
    result = execute_on_datasource(ds, probe, allow_write=False, for_assertion=True, max_rows=1)
    return {"success": result.get("success", False), "error": result.get("error"), "rows": result.get("rows", [])}
