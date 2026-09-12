from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `perf_csv_dataset` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '所属项目',
            `name` VARCHAR(100) NOT NULL COMMENT '数据集名称',
            `description` TEXT NULL COMMENT '描述',
            `row_data` JSON NULL COMMENT 'CSV行数据',
            `columns` JSON NOT NULL COMMENT '列名列表',
            `file_name` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '来源文件名',
            `row_count` INT NOT NULL DEFAULT 0 COMMENT '行数',
            `source_scene_id` INT NULL COMMENT '迁出来源场景ID',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `create_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '创建人',
            KEY `idx_perf_csv_dataset_project` (`project_id`),
            KEY `idx_perf_csv_dataset_del` (`is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='性能测试 CSV 数据集';

        SET @dbname = DATABASE();
        SET @tablename = 'perf_scene';
        SET @columnname = 'csv_dataset_id';
        SET @preparedStatement = (SELECT IF(
          (
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = @tablename AND COLUMN_NAME = @columnname
          ) > 0,
          'SELECT 1',
          'ALTER TABLE `perf_scene` ADD COLUMN `csv_dataset_id` INT NULL COMMENT ''绑定的 CSV 数据集ID'' AFTER `csv_config`'
        ));
        PREPARE alterIfNotExists FROM @preparedStatement;
        EXECUTE alterIfNotExists;
        DEALLOCATE PREPARE alterIfNotExists;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `perf_scene` DROP COLUMN IF EXISTS `csv_dataset_id`;
        DROP TABLE IF EXISTS `perf_csv_dataset`;
    """
