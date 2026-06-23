from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'case'
    AND COLUMN_NAME = 'update_by');
SET @sql := IF(@exist = 0,
    'ALTER TABLE `case` ADD COLUMN `update_by` VARCHAR(50) NULL COMMENT "最后更新人"',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @exist2 := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'suite'
    AND COLUMN_NAME = 'update_by');
SET @sql2 := IF(@exist2 = 0,
    'ALTER TABLE `suite` ADD COLUMN `update_by` VARCHAR(50) NULL COMMENT "最后更新人"',
    'SELECT 1');
PREPARE stmt2 FROM @sql2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;

SET @exist3 := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'task'
    AND COLUMN_NAME = 'update_by');
SET @sql3 := IF(@exist3 = 0,
    'ALTER TABLE `task` ADD COLUMN `update_by` VARCHAR(50) NULL COMMENT "最后更新人"',
    'SELECT 1');
PREPARE stmt3 FROM @sql3;
EXECUTE stmt3;
DEALLOCATE PREPARE stmt3;

UPDATE `case` SET `update_by` = `username` WHERE `update_by` IS NULL OR `update_by` = '';
UPDATE `suite` SET `update_by` = `username` WHERE `update_by` IS NULL OR `update_by` = '';
UPDATE `task` SET `update_by` = `username` WHERE `update_by` IS NULL OR `update_by` = '';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE `case` DROP COLUMN IF EXISTS `update_by`;
ALTER TABLE `suite` DROP COLUMN IF EXISTS `update_by`;
ALTER TABLE `task` DROP COLUMN IF EXISTS `update_by`;
    """
