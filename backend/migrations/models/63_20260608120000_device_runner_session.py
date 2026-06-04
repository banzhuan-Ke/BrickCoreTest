from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `device`
            ADD COLUMN `runner_session_jti` VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'Runner 会话 jti，空表示未绑定' AFTER `is_del`,
            ADD COLUMN `runner_bound_user_id` INT NULL COMMENT 'Runner 绑定用户 ID' AFTER `runner_session_jti`,
            ADD COLUMN `runner_client_version` VARCHAR(50) NOT NULL DEFAULT '' COMMENT 'Runner 客户端版本' AFTER `runner_bound_user_id`,
            ADD COLUMN `runner_last_heartbeat` DATETIME NULL COMMENT 'Runner 最后心跳' AFTER `runner_client_version`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `device`
            DROP COLUMN `runner_last_heartbeat`,
            DROP COLUMN `runner_client_version`,
            DROP COLUMN `runner_bound_user_id`,
            DROP COLUMN `runner_session_jti`;
    """
