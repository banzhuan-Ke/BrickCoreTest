from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
SET @exist1 := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ai_config'
    AND COLUMN_NAME = 'thinking_enabled');
SET @sql1 := IF(@exist1 = 0,
    'ALTER TABLE `ai_config` ADD COLUMN `thinking_enabled` BOOL NOT NULL DEFAULT 0',
    'SELECT 1');
PREPARE stmt1 FROM @sql1;
EXECUTE stmt1;
DEALLOCATE PREPARE stmt1;

SET @exist2 := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ai_config'
    AND COLUMN_NAME = 'reasoning_effort');
SET @sql2 := IF(@exist2 = 0,
    "ALTER TABLE `ai_config` ADD COLUMN `reasoning_effort` VARCHAR(20) NOT NULL DEFAULT 'medium'",
    'SELECT 1');
PREPARE stmt2 FROM @sql2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE `ai_config` DROP COLUMN IF EXISTS `thinking_enabled`;
ALTER TABLE `ai_config` DROP COLUMN IF EXISTS `reasoning_effort`;
    """
