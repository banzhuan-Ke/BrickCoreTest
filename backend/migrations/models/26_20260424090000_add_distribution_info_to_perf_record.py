from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'perf_record'
    AND COLUMN_NAME = 'distribution_info');
SET @sql := IF(@exist = 0,
    'ALTER TABLE `perf_record` ADD COLUMN `distribution_info` JSON NOT NULL DEFAULT ("")',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE `perf_record` DROP COLUMN IF EXISTS `distribution_info`;
    """
