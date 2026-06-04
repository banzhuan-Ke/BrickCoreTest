from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ai_usage_log` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `scene` VARCHAR(64) NOT NULL COMMENT '场景编码',
            `scene_label` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '场景名称',
            `user_id` INT NULL COMMENT '用户ID',
            `username` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '用户名',
            `project_id` INT NULL COMMENT '项目ID',
            `project_name` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '项目名称',
            `ai_config_id` INT NULL COMMENT 'AI 配置ID',
            `model` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '模型名称',
            `provider` VARCHAR(20) NOT NULL DEFAULT '' COMMENT '供应商',
            `tokens_used` INT NOT NULL DEFAULT 0 COMMENT 'Token 消耗',
            `duration_ms` INT NOT NULL DEFAULT 0 COMMENT '耗时(ms)',
            `status` VARCHAR(20) NOT NULL DEFAULT 'success' COMMENT 'success/failed',
            `input_summary` LONGTEXT NOT NULL COMMENT '输入摘要',
            `output_summary` LONGTEXT NULL COMMENT '输出摘要',
            `extra` JSON NOT NULL COMMENT '扩展信息',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            KEY `idx_ai_usage_log_scene` (`scene`),
            KEY `idx_ai_usage_log_user_id` (`user_id`),
            KEY `idx_ai_usage_log_project_id` (`project_id`),
            KEY `idx_ai_usage_log_create_time` (`create_time`)
        ) CHARACTER SET utf8mb4 COMMENT='AI 模型使用记录';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ai_usage_log`;
    """
