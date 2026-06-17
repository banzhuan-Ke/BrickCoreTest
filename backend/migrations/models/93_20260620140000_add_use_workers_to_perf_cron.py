from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `perf_cron_job`
        ADD COLUMN `use_workers` BOOL NOT NULL DEFAULT 0 COMMENT '是否使用分布式Worker执行';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `perf_cron_job` DROP COLUMN `use_workers`;
    """
