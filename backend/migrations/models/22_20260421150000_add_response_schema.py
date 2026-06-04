from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'api_definition'
    AND COLUMN_NAME = 'response_schema');
SET @sql := IF(@exist = 0,
    'ALTER TABLE `api_definition` ADD COLUMN `response_schema` JSON NULL COMMENT "响应结构定义"',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE `api_definition` DROP COLUMN IF EXISTS `response_schema`;
    """
