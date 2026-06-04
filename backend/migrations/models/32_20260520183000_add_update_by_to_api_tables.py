from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
-- api_definition 表添加 update_by
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'api_definition'
    AND COLUMN_NAME = 'update_by');
SET @sql := IF(@exist = 0,
    'ALTER TABLE `api_definition` ADD COLUMN `update_by` VARCHAR(50) NULL COMMENT "修改人"',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- api_test_case 表添加 update_by
SET @exist2 := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'api_test_case'
    AND COLUMN_NAME = 'update_by');
SET @sql2 := IF(@exist2 = 0,
    'ALTER TABLE `api_test_case` ADD COLUMN `update_by` VARCHAR(50) NULL COMMENT "修改人"',
    'SELECT 1');
PREPARE stmt2 FROM @sql2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE `api_definition` DROP COLUMN IF EXISTS `update_by`;
ALTER TABLE `api_test_case` DROP COLUMN IF EXISTS `update_by`;
    """
