from tortoise import BaseDBAsyncClient


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


async def upgrade(db: BaseDBAsyncClient) -> str:
    if not await _column_exists(db, "app_plan", "record_video"):
        await db.execute_script(
            "ALTER TABLE `app_plan` ADD COLUMN `record_video` TINYINT(1) NOT NULL DEFAULT 1 "
            "COMMENT '执行时录制用例视频';"
        )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    if await _column_exists(db, "app_plan", "record_video"):
        return "ALTER TABLE `app_plan` DROP COLUMN `record_video`;"
    return "SELECT 1;"
