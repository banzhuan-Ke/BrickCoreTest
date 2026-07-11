from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_embed_config`
        ADD COLUMN `dimensions` INT NOT NULL DEFAULT 1024 COMMENT '向量维度（text-embedding-v3/v4 等可调）'
        AFTER `model`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_embed_config` DROP COLUMN `dimensions`;
    """
