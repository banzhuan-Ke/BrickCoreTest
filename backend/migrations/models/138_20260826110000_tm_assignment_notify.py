from tortoise import BaseDBAsyncClient


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


async def upgrade(db: BaseDBAsyncClient) -> str:
    table = "notification_config"
    if not await _column_exists(db, table, "tm_assignment_notify"):
        await db.execute_script(
            f"ALTER TABLE `{table}` "
            "ADD COLUMN `tm_assignment_notify` BOOL NOT NULL DEFAULT 1 "
            "COMMENT '是否接收测试管理指派类外发' AFTER `app_auto_push_report`;"
        )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    table = "notification_config"
    if await _column_exists(db, table, "tm_assignment_notify"):
        await db.execute_script(f"ALTER TABLE `{table}` DROP COLUMN `tm_assignment_notify`;")
    return "SELECT 1;"
