"""首页看板：执行记录与操作日志按时间过滤，避免全表扫大 JSON。"""
from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = False

_INDEXES = (
    ("operation_log", "idx_operation_log_create_time", "`create_time`"),
    ("ui_case_execution", "idx_ui_case_exec_start_status", "`start_time`, `status`, `case_id`"),
    ("api_run_record", "idx_api_run_start_status", "`start_time`, `status`, `case_id`"),
    ("app_case_execution", "idx_app_case_exec_start_status", "`start_time`, `status`, `case_id`"),
)


async def _index_exists(db: BaseDBAsyncClient, table: str, index_name: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s",
        [table, index_name],
    )
    return bool(rows and int(rows[0]["cnt"] or 0))


async def upgrade(db: BaseDBAsyncClient) -> str:
    for table, index_name, columns in _INDEXES:
        if await _index_exists(db, table, index_name):
            continue
        await db.execute_script(
            f"CREATE INDEX `{index_name}` ON `{table}` ({columns});"
        )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    parts = [
        f"DROP INDEX `{index_name}` ON `{table}`;"
        for table, index_name, _columns in _INDEXES
    ]
    return "\n".join(parts)
