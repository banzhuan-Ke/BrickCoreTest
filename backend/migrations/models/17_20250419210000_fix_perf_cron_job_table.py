from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
-- 删除字段不匹配的旧表（刚创建，无数据）
DROP TABLE IF EXISTS `perf_cron_job`;

-- 按模型正确定义重建
CREATE TABLE `perf_cron_job` (
    `id` VARCHAR(100) NOT NULL PRIMARY KEY COMMENT '任务ID',
    `name` VARCHAR(100) NOT NULL COMMENT '任务名称',
    `project_id` INT NOT NULL COMMENT '所属项目',
    `scene_id` INT NOT NULL COMMENT '关联场景',
    `run_type` VARCHAR(20) NOT NULL COMMENT '类型: Interval/date/crontab',
    `interval` INT NOT NULL DEFAULT 3600 COMMENT '间隔(秒)',
    `run_date` DATETIME(6) NULL COMMENT '固定执行时间',
    `crontab` JSON NOT NULL COMMENT 'cron表达式',
    `env_id` INT NOT NULL COMMENT '执行环境ID',
    `last_run_record_id` INT NULL COMMENT '最后一次执行记录ID',
    `last_run_time` DATETIME(6) NULL COMMENT '最后一次执行时间',
    `last_run_status` VARCHAR(20) NULL COMMENT '最后一次执行状态',
    `state` BOOL NOT NULL DEFAULT 0 COMMENT '是否启用',
    `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
    `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
    `create_by` VARCHAR(50) NOT NULL COMMENT '创建人',
    CONSTRAINT `fk_perfcronjob_project_12345678` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_perfcronjob_scene_12345678` FOREIGN KEY (`scene_id`) REFERENCES `perf_scene` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='性能测试定时任务';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP TABLE IF EXISTS `perf_cron_job`;
    """
