from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `assistant_session`
            DROP INDEX `uid_assistant_session_user_project`;
        ALTER TABLE `assistant_session`
            ADD COLUMN `title` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '会话标题' AFTER `project_id`;
        ALTER TABLE `assistant_session`
            ADD KEY `idx_assistant_session_user_proj_upd` (`user_id`, `project_id`, `update_time`);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `assistant_session`
            DROP INDEX `idx_assistant_session_user_proj_upd`;
        ALTER TABLE `assistant_session`
            DROP COLUMN `title`;
        ALTER TABLE `assistant_session`
            ADD UNIQUE KEY `uid_assistant_session_user_project` (`user_id`, `project_id`);
    """
