from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `app_step_fragment` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `name` VARCHAR(100) NOT NULL COMMENT '片段名称',
            `project_id` INT NOT NULL COMMENT '所属项目',
            `description` VARCHAR(500) NULL COMMENT '片段描述',
            `steps` JSON NOT NULL COMMENT '步骤 JSON',
            `tags` VARCHAR(200) NULL COMMENT '分类标签',
            `version` INT NOT NULL DEFAULT 1 COMMENT '版本号',
            `username` VARCHAR(50) NOT NULL COMMENT '创建人',
            `update_by` VARCHAR(50) NULL COMMENT '最后更新人',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_app_step_fragment_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            KEY `idx_app_step_fragment_project` (`project_id`)
        ) CHARACTER SET utf8mb4 COMMENT='App步骤片段';

        CREATE TABLE IF NOT EXISTS `app_cron_job` (
            `id` VARCHAR(100) NOT NULL PRIMARY KEY COMMENT '任务ID',
            `name` VARCHAR(100) NOT NULL COMMENT '任务名称',
            `project_id` INT NOT NULL COMMENT '所属项目',
            `plan_id` INT NULL COMMENT '关联 App 计划',
            `suite_id` INT NULL COMMENT '关联 App 套件',
            `run_type` VARCHAR(20) NOT NULL COMMENT 'Interval|date|crontab',
            `interval` INT NOT NULL DEFAULT 3600 COMMENT '间隔秒',
            `run_date` DATETIME(6) NULL COMMENT '固定执行时间',
            `crontab` JSON NOT NULL COMMENT 'cron 规则',
            `env_id` INT NOT NULL COMMENT '执行环境 ID',
            `device_id` VARCHAR(100) NULL COMMENT '默认执行设备',
            `app_udid` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '覆盖 UDID',
            `app_id` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '默认包名',
            `last_run_record_id` INT NULL COMMENT '最近执行记录 ID',
            `last_run_time` DATETIME(6) NULL,
            `last_run_status` VARCHAR(20) NULL,
            `state` BOOL NOT NULL DEFAULT 0 COMMENT '是否启用',
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL,
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_app_cron_job_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_app_cron_job_plan` FOREIGN KEY (`plan_id`) REFERENCES `app_plan` (`id`) ON DELETE SET NULL,
            CONSTRAINT `fk_app_cron_job_suite` FOREIGN KEY (`suite_id`) REFERENCES `app_suite` (`id`) ON DELETE SET NULL,
            KEY `idx_app_cron_job_project` (`project_id`)
        ) CHARACTER SET utf8mb4 COMMENT='App定时任务';
    """

async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `app_cron_job`;
        DROP TABLE IF EXISTS `app_step_fragment`;
    """
