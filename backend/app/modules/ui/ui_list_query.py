"""UI 列表页批量统计查询，避免 SELECT 大 JSON 列后排序或 N+1。"""
from __future__ import annotations

from tortoise import connections
from tortoise.functions import Count


def row_value(row, key: str, index: int = 0):
    if isinstance(row, dict):
        return row.get(key)
    if isinstance(row, (list, tuple)):
        return row[index]
    return None


async def load_count_by_fk(
    model,
    fk_field: str,
    ids: list[int],
    *,
    is_del: bool = True,
) -> dict[int, int]:
    result = {item_id: 0 for item_id in ids}
    if not ids:
        return result
    query = model.filter(**{f"{fk_field}__in": ids})
    if is_del and hasattr(model, "is_del"):
        query = query.filter(is_del=False)
    rows = (
        await query.annotate(cnt=Count("id"))
        .group_by(fk_field)
        .values(fk_field, "cnt")
    )
    for row in rows:
        result[row[fk_field]] = int(row["cnt"])
    return result


async def load_latest_status_by_fk(
    table: str,
    fk_column: str,
    ids: list[int],
    *,
    default: str,
) -> dict[int, str]:
    if not ids:
        return {}
    conn = connections.get("default")
    placeholders = ",".join(["%s"] * len(ids))
    sql = f"""
        SELECT e.{fk_column}, e.status FROM {table} e
        INNER JOIN (
            SELECT {fk_column}, MAX(id) AS max_id
            FROM {table}
            WHERE {fk_column} IN ({placeholders}) AND is_del = 0
            GROUP BY {fk_column}
        ) t ON e.id = t.max_id
    """
    _, rows = await conn.execute_query(sql, ids)
    return {
        fk_id: status or default
        for fk_id, status in (
            (row_value(row, fk_column, 0), row_value(row, "status", 1))
            for row in rows
        )
        if fk_id is not None
    }


async def load_json_array_length(
    table: str,
    ids: list[int],
    json_column: str,
    *,
    id_column: str = "id",
) -> dict[int, int]:
    if not ids:
        return {}
    conn = connections.get("default")
    placeholders = ",".join(["%s"] * len(ids))
    sql = f"""
        SELECT {id_column}, COALESCE(JSON_LENGTH(`{json_column}`), 0) AS item_count
        FROM `{table}`
        WHERE {id_column} IN ({placeholders})
    """
    _, rows = await conn.execute_query(sql, ids)
    return {
        item_id: int(item_count or 0)
        for item_id, item_count in (
            (row_value(row, id_column, 0), row_value(row, "item_count", 1))
            for row in rows
        )
        if item_id is not None
    }


async def load_catalog_names(catalog_ids: list[int]) -> dict[int, str]:
    if not catalog_ids:
        return {}
    from app.models.sys import TestCatalog

    rows = await TestCatalog.filter(id__in=catalog_ids).values("id", "name")
    return {row["id"]: row["name"] for row in rows}


async def load_task_suite_count(task_ids: list[int]) -> dict[int, int]:
    result = {task_id: 0 for task_id in task_ids}
    if not task_ids:
        return result
    conn = connections.get("default")
    placeholders = ",".join(["%s"] * len(task_ids))
    sql = f"""
        SELECT ts.task_id, COUNT(*) AS cnt
        FROM task_suite ts
        INNER JOIN suite s ON s.id = ts.suite_id AND s.is_del = 0
        WHERE ts.task_id IN ({placeholders})
        GROUP BY ts.task_id
    """
    _, rows = await conn.execute_query(sql, task_ids)
    for row in rows:
        task_id = row_value(row, "task_id", 0)
        if task_id is not None:
            result[task_id] = int(row_value(row, "cnt", 1) or 0)
    return result
