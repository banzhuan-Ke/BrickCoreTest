from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'perf_record'
    AND COLUMN_NAME = 'cron_job_id');
SET @sql := IF(@exist = 0,
    'ALTER TABLE `perf_record` ADD COLUMN `cron_job_id` VARCHAR(100) NULL COMMENT "定时任务ID"',
    'ALTER TABLE `perf_record` MODIFY COLUMN `cron_job_id` VARCHAR(100) NULL COMMENT "定时任务ID"');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE `perf_record` DROP COLUMN IF EXISTS `cron_job_id`;
    """
