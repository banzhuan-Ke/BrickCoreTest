from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `sut_server`
            ADD COLUMN `force_from_ms` BIGINT NULL COMMENT '压测强制采集起始 epoch ms' AFTER `config_rev`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `sut_server` DROP COLUMN `force_from_ms`;
    """
