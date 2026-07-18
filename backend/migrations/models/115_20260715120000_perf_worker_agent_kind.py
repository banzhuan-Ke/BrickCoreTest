from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `perf_worker`
            ADD COLUMN `agent_kind` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '来源 perf_slim|runner_client' AFTER `max_concurrent`,
            ADD COLUMN `engine_version` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '压测引擎版本' AFTER `agent_kind`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `perf_worker`
            DROP COLUMN `engine_version`,
            DROP COLUMN `agent_kind`;
    """
