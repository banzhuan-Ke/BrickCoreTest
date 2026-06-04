from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'api_definition'
    AND COLUMN_NAME = 'body_fields');
SET @sql := IF(@exist = 0,
    'ALTER TABLE `api_definition` ADD COLUMN `body_fields` JSON NOT NULL DEFAULT (JSON_ARRAY()) COMMENT "form-data 字段"',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE `api_definition` DROP COLUMN IF EXISTS `body_fields`;
    """
