from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'perf_scene'
    AND COLUMN_NAME = 'csv_data');
SET @sql := IF(@exist = 0,
    'ALTER TABLE `perf_scene` ADD COLUMN `csv_data` JSON DEFAULT NULL',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE `perf_scene` DROP COLUMN IF EXISTS `csv_data`;
    """
