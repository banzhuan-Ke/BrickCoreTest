from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `device`
            ADD COLUMN `runner_mq_username` VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Runner 隔离 MQ 用户名' AFTER `runner_last_heartbeat`,
            ADD COLUMN `runner_mq_password` VARCHAR(256) NOT NULL DEFAULT '' COMMENT 'Runner 隔离 MQ 密码' AFTER `runner_mq_username`,
            ADD COLUMN `runner_redis_username` VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Runner 隔离 Redis 用户名' AFTER `runner_mq_password`,
            ADD COLUMN `runner_redis_password` VARCHAR(256) NOT NULL DEFAULT '' COMMENT 'Runner 隔离 Redis 密码' AFTER `runner_redis_username`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `device`
            DROP COLUMN `runner_redis_password`,
            DROP COLUMN `runner_redis_username`,
            DROP COLUMN `runner_mq_password`,
            DROP COLUMN `runner_mq_username`;
    """
