"""AiConfig：supports_vision（多模态）字段 + 按模型名回填。"""
from tortoise import BaseDBAsyncClient


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


async def upgrade(db: BaseDBAsyncClient) -> str:
    if not await _column_exists(db, "ai_config", "supports_vision"):
        await db.execute_script(
            "ALTER TABLE `ai_config` ADD COLUMN `supports_vision` "
            "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否支持多模态（Vision/读图）'"
        )
    # 回填：模型名像 Vision 且非 DeepSeek → 开启
    await db.execute_script(
        """
        UPDATE `ai_config`
        SET `supports_vision` = 1
        WHERE `is_del` = 0
          AND LOWER(COALESCE(`provider`, '')) <> 'deepseek'
          AND (
            LOWER(COALESCE(`model`, '')) LIKE '%vl%'
            OR LOWER(COALESCE(`model`, '')) LIKE '%vision%'
            OR LOWER(COALESCE(`model`, '')) LIKE '%gpt-4o%'
            OR LOWER(COALESCE(`model`, '')) LIKE '%gpt-4-turbo%'
            OR LOWER(COALESCE(`model`, '')) LIKE '%claude-3%'
            OR LOWER(COALESCE(`model`, '')) LIKE '%gemini%'
            OR LOWER(COALESCE(`model`, '')) LIKE '%qvq%'
          )
        """
    )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    if await _column_exists(db, "ai_config", "supports_vision"):
        await db.execute_script(
            "ALTER TABLE `ai_config` DROP COLUMN `supports_vision`"
        )
    return "SELECT 1;"
