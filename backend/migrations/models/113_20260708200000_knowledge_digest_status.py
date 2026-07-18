from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_knowledge_document`
            ADD COLUMN `digest_status` VARCHAR(20) NOT NULL DEFAULT 'none' COMMENT 'AI摘要状态' AFTER `vector_error`,
            ADD COLUMN `digest_error` LONGTEXT NULL COMMENT 'AI摘要错误' AFTER `digest_status`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_knowledge_document`
            DROP COLUMN `digest_error`,
            DROP COLUMN `digest_status`;
    """
