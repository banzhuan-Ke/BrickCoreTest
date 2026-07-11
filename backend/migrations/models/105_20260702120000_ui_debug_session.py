from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ui_debug_session` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `case_id` INT NOT NULL COMMENT '用例ID',
            `project_id` INT NOT NULL COMMENT '项目ID',
            `device_id` VARCHAR(100) NOT NULL COMMENT 'Runner 设备ID',
            `username` VARCHAR(50) NOT NULL COMMENT '创建人',
            `status` VARCHAR(20) NOT NULL DEFAULT 'starting' COMMENT 'starting/ready/running/closed/error',
            `env` JSON NOT NULL COMMENT '执行环境配置',
            `steps` JSON NOT NULL COMMENT '调试步骤快照',
            `pending_command` JSON NULL COMMENT '待 Runner 执行的命令',
            `last_result` JSON NOT NULL COMMENT '最近一次执行结果',
            `error` TEXT NULL COMMENT '错误信息',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            KEY `idx_ui_debug_session_device` (`device_id`),
            KEY `idx_ui_debug_session_case` (`case_id`)
        ) CHARACTER SET utf8mb4 COMMENT='UI 交互调试会话';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ui_debug_session`;
    """
