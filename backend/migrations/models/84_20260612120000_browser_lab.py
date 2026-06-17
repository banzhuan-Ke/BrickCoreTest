from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `browser_lab_task` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '项目ID',
            `created_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '创建人',
            `task_text` LONGTEXT NOT NULL COMMENT '任务描述',
            `start_url` VARCHAR(500) NOT NULL COMMENT '起始URL',
            `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '任务状态',
            `engine` VARCHAR(32) NOT NULL DEFAULT 'browser_use' COMMENT '引擎',
            `config_json` JSON NOT NULL COMMENT '运行配置',
            `step_log` JSON NOT NULL COMMENT '步骤日志',
            `result_summary` LONGTEXT NULL COMMENT '结果摘要',
            `tokens_used` INT NOT NULL DEFAULT 0 COMMENT 'Token消耗',
            `steps_count` INT NOT NULL DEFAULT 0 COMMENT '步数',
            `gif_path` VARCHAR(500) NULL COMMENT 'GIF路径',
            `error_message` LONGTEXT NULL COMMENT '错误信息',
            `ai_config_id` INT NULL COMMENT 'AI配置ID',
            `started_at` DATETIME(6) NULL,
            `finished_at` DATETIME(6) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_browser_lab_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            INDEX `idx_browser_lab_project_time` (`project_id`, `create_time`),
            INDEX `idx_browser_lab_status` (`status`)
        ) CHARACTER SET utf8mb4 COMMENT='智能浏览器任务';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `browser_lab_task`;
    """
