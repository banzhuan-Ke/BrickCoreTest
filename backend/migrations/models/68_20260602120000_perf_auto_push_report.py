from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True

_NOOP_SQL = "SELECT 1;"


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


async def upgrade(db: BaseDBAsyncClient) -> str:
    if await _column_exists(db, "notification_config", "perf_auto_push_report"):
        return _NOOP_SQL
    return """
        ALTER TABLE `notification_config`
        ADD COLUMN `perf_auto_push_report` BOOL NOT NULL COMMENT '性能测试执行完成后自动推送报告' DEFAULT 0;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    if not await _column_exists(db, "notification_config", "perf_auto_push_report"):
        return _NOOP_SQL
    return """
        ALTER TABLE `notification_config`
        DROP COLUMN `perf_auto_push_report`;
    """
