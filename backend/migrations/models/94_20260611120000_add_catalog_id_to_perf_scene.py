from tortoise import BaseDBAsyncClient


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


async def upgrade(db: BaseDBAsyncClient) -> str:
    if not await _column_exists(db, "perf_scene", "catalog_id"):
        await db.execute_script(
            "ALTER TABLE `perf_scene` ADD COLUMN `catalog_id` INT NULL COMMENT '所属目录';"
        )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    if await _column_exists(db, "perf_scene", "catalog_id"):
        return "ALTER TABLE `perf_scene` DROP COLUMN `catalog_id`;"
    return "SELECT 1;"
