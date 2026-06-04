from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `assistant_session` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `user_id` INT NOT NULL COMMENT '用户ID',
            `project_id` INT NULL COMMENT '项目ID',
            `messages` JSON NOT NULL COMMENT '消息列表',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            UNIQUE KEY `uid_assistant_session_user_project` (`user_id`, `project_id`),
            KEY `idx_assistant_session_user_id` (`user_id`),
            KEY `idx_assistant_session_project_id` (`project_id`)
        ) CHARACTER SET utf8mb4 COMMENT='平台 AI 助手会话';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `assistant_session`;
    """
