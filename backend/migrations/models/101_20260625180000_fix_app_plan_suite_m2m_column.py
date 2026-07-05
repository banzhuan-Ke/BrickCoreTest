from tortoise import BaseDBAsyncClient


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


async def upgrade(db: BaseDBAsyncClient) -> str:
    # Tortoise M2M 默认 forward_key 为 appsuite_id（旧迁移误写为 app_suite_id）
    table = "app_plan_app_suite"
    if await _column_exists(db, table, "app_suite_id") and not await _column_exists(db, table, "appsuite_id"):
        await db.execute_script(
            f"ALTER TABLE `{table}` CHANGE COLUMN `app_suite_id` `appsuite_id` INT NOT NULL;"
        )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    table = "app_plan_app_suite"
    if await _column_exists(db, table, "appsuite_id") and not await _column_exists(db, table, "app_suite_id"):
        return f"ALTER TABLE `{table}` CHANGE COLUMN `appsuite_id` `app_suite_id` INT NOT NULL;"
    return "SELECT 1;"
