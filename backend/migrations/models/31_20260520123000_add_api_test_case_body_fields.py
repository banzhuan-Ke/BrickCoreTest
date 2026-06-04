from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'api_test_case'
    AND COLUMN_NAME = 'request_body_type');
SET @sql := IF(@exist = 0,
    'ALTER TABLE `api_test_case` ADD COLUMN `request_body_type` VARCHAR(20) NOT NULL DEFAULT "json" COMMENT "请求体类型"',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @exist2 := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'api_test_case'
    AND COLUMN_NAME = 'request_body_fields');
SET @sql2 := IF(@exist2 = 0,
    'ALTER TABLE `api_test_case` ADD COLUMN `request_body_fields` JSON NOT NULL DEFAULT (JSON_ARRAY()) COMMENT "form-data 字段覆盖"',
    'SELECT 1');
PREPARE stmt2 FROM @sql2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE `api_test_case` DROP COLUMN IF EXISTS `request_body_fields`;
ALTER TABLE `api_test_case` DROP COLUMN IF EXISTS `request_body_type`;
    """
