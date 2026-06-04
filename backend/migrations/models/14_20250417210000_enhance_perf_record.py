from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
SET @exist_median := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'perf_record' AND COLUMN_NAME = 'median_response_time');
SET @sql1 := IF(@exist_median = 0, 'ALTER TABLE `perf_record` ADD COLUMN `median_response_time` DOUBLE NOT NULL DEFAULT 0 COMMENT "中位数响应时间(ms)"', 'SELECT 1');
PREPARE stmt1 FROM @sql1; EXECUTE stmt1; DEALLOCATE PREPARE stmt1;

SET @exist_p90 := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'perf_record' AND COLUMN_NAME = 'p90_response_time');
SET @sql2 := IF(@exist_p90 = 0, 'ALTER TABLE `perf_record` ADD COLUMN `p90_response_time` DOUBLE NOT NULL DEFAULT 0 COMMENT "P90响应时间(ms)"', 'SELECT 1');
PREPARE stmt2 FROM @sql2; EXECUTE stmt2; DEALLOCATE PREPARE stmt2;

SET @exist_std := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'perf_record' AND COLUMN_NAME = 'std_dev_response_time');
SET @sql3 := IF(@exist_std = 0, 'ALTER TABLE `perf_record` ADD COLUMN `std_dev_response_time` DOUBLE NOT NULL DEFAULT 0 COMMENT "响应时间标准差(ms)"', 'SELECT 1');
PREPARE stmt3 FROM @sql3; EXECUTE stmt3; DEALLOCATE PREPARE stmt3;

SET @exist_recv := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'perf_record' AND COLUMN_NAME = 'received_kb_per_sec');
SET @sql4 := IF(@exist_recv = 0, 'ALTER TABLE `perf_record` ADD COLUMN `received_kb_per_sec` DOUBLE NOT NULL DEFAULT 0 COMMENT "接收数据速率(KB/s)"', 'SELECT 1');
PREPARE stmt4 FROM @sql4; EXECUTE stmt4; DEALLOCATE PREPARE stmt4;

SET @exist_sent := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'perf_record' AND COLUMN_NAME = 'sent_kb_per_sec');
SET @sql5 := IF(@exist_sent = 0, 'ALTER TABLE `perf_record` ADD COLUMN `sent_kb_per_sec` DOUBLE NOT NULL DEFAULT 0 COMMENT "发送数据速率(KB/s)"', 'SELECT 1');
PREPARE stmt5 FROM @sql5; EXECUTE stmt5; DEALLOCATE PREPARE stmt5;

SET @exist_err := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'perf_record' AND COLUMN_NAME = 'error_breakdown');
SET @sql6 := IF(@exist_err = 0, 'ALTER TABLE `perf_record` ADD COLUMN `error_breakdown` JSON NOT NULL DEFAULT (JSON_OBJECT()) COMMENT "错误分类统计"', 'SELECT 1');
PREPARE stmt6 FROM @sql6; EXECUTE stmt6; DEALLOCATE PREPARE stmt6;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE `perf_record`
    DROP COLUMN IF EXISTS `median_response_time`,
    DROP COLUMN IF EXISTS `p90_response_time`,
    DROP COLUMN IF EXISTS `std_dev_response_time`,
    DROP COLUMN IF EXISTS `received_kb_per_sec`,
    DROP COLUMN IF EXISTS `sent_kb_per_sec`,
    DROP COLUMN IF EXISTS `error_breakdown`;
    """
