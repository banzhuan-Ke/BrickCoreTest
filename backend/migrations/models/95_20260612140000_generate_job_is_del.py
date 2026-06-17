from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_requirement_generate_job`
        ADD COLUMN `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除（软删，仅隐藏记录）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_requirement_generate_job` DROP COLUMN `is_del`;
    """
