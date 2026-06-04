from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ai_record_session'
    AND COLUMN_NAME = 'actions_count');
SET @sql := IF(@exist = 0,
    'ALTER TABLE `ai_record_session` ADD COLUMN `actions_count` INT NOT NULL DEFAULT 0',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE `ai_record_session` DROP COLUMN IF EXISTS `actions_count`;
    """
