"""平台设置：小测多轮累计 Token 上限。"""
from tortoise import BaseDBAsyncClient


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


async def upgrade(db: BaseDBAsyncClient) -> str:
    if not await _column_exists(db, "system_platform_settings", "assist_max_tokens_total"):
        await db.execute_script(
            "ALTER TABLE `system_platform_settings` "
            "ADD COLUMN `assist_max_tokens_total` INT NOT NULL DEFAULT 80000 "
            "COMMENT '小测多轮累计 Token 上限' "
            "AFTER `assist_failure_digest_max_rounds`;"
        )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    if await _column_exists(db, "system_platform_settings", "assist_max_tokens_total"):
        await db.execute_script(
            "ALTER TABLE `system_platform_settings` DROP COLUMN `assist_max_tokens_total`;"
        )
    return "SELECT 1;"
