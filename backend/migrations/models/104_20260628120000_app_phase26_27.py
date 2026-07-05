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
    statements: list[str] = []
    if not await _column_exists(db, "notification_config", "app_auto_push_report"):
        statements.append(
            "ALTER TABLE `notification_config` "
            "ADD COLUMN `app_auto_push_report` BOOL NOT NULL "
            "COMMENT 'App计划/套件执行完成后自动推送报告' DEFAULT 0;"
        )
    if not await _column_exists(db, "app_suite_execution", "cronjob_id"):
        statements.append(
            "ALTER TABLE `app_suite_execution` "
            "ADD COLUMN `cronjob_id` VARCHAR(100) NULL COMMENT '定时任务ID';"
        )
    if not statements:
        return _NOOP_SQL
    return "\n".join(statements)


async def downgrade(db: BaseDBAsyncClient) -> str:
    statements: list[str] = []
    if await _column_exists(db, "notification_config", "app_auto_push_report"):
        statements.append("ALTER TABLE `notification_config` DROP COLUMN `app_auto_push_report`;")
    if await _column_exists(db, "app_suite_execution", "cronjob_id"):
        statements.append("ALTER TABLE `app_suite_execution` DROP COLUMN `cronjob_id`;")
    if not statements:
        return _NOOP_SQL
    return "\n".join(statements)
