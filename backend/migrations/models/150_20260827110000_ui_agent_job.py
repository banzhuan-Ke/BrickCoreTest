from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ui_agent_job` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '项目ID',
            `source` VARCHAR(64) NOT NULL DEFAULT 'ui_case_edit' COMMENT '来源',
            `source_ref` JSON NOT NULL COMMENT '来源引用',
            `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending|running|done|failed|stopped',
            `run_mode` VARCHAR(16) NOT NULL DEFAULT 'local' COMMENT 'local|runner',
            `device_id` VARCHAR(100) NULL COMMENT 'Runner 设备ID',
            `page_url` VARCHAR(500) NOT NULL COMMENT '起始 URL',
            `description` TEXT NOT NULL COMMENT '测试描述',
            `max_steps` INT NOT NULL DEFAULT 15 COMMENT '最大步数',
            `steps_json` JSON NOT NULL COMMENT '已产出步骤',
            `agent_log_json` JSON NOT NULL COMMENT '探索日志',
            `tokens_used` INT NOT NULL DEFAULT 0 COMMENT 'Token 消耗',
            `error_message` TEXT NULL COMMENT '失败原因',
            `ai_config_id` INT NULL COMMENT 'AI 配置',
            `created_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '创建人',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `started_at` DATETIME(6) NULL,
            `finished_at` DATETIME(6) NULL,
            KEY `idx_ui_agent_job_project` (`project_id`),
            KEY `idx_ui_agent_job_status` (`status`)
        ) CHARACTER SET utf8mb4 COMMENT='UI Agent 探索任务';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ui_agent_job`;
    """
