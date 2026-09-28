"""平台设置：小测助手 LLM / 墙钟超时。"""
from tortoise import BaseDBAsyncClient


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


async def upgrade(db: BaseDBAsyncClient) -> str:
    if not await _column_exists(db, "system_platform_settings", "assist_llm_timeout_sec"):
        await db.execute_script(
            "ALTER TABLE `system_platform_settings` "
            "ADD COLUMN `assist_llm_timeout_sec` INT NOT NULL DEFAULT 180 "
            "COMMENT '小测多轮单次 LLM 调用超时（秒）' "
            "AFTER `knowledge_report_delete_mode`;"
        )
    if not await _column_exists(db, "system_platform_settings", "assist_max_wall_sec"):
        await db.execute_script(
            "ALTER TABLE `system_platform_settings` "
            "ADD COLUMN `assist_max_wall_sec` INT NOT NULL DEFAULT 240 "
            "COMMENT '小测多轮整轮墙钟上限（秒）' "
            "AFTER `assist_llm_timeout_sec`;"
        )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    if await _column_exists(db, "system_platform_settings", "assist_max_wall_sec"):
        await db.execute_script(
            "ALTER TABLE `system_platform_settings` DROP COLUMN `assist_max_wall_sec`;"
        )
    if await _column_exists(db, "system_platform_settings", "assist_llm_timeout_sec"):
        await db.execute_script(
            "ALTER TABLE `system_platform_settings` DROP COLUMN `assist_llm_timeout_sec`;"
        )
    return "SELECT 1;"
