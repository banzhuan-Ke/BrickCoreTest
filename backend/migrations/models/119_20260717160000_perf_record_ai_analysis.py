from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `perf_record` ADD COLUMN `ai_analysis` JSON NULL COMMENT 'AI 分析结果';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `perf_record` DROP COLUMN `ai_analysis`;
    """
