from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_knowledge_document`
            ADD COLUMN `embed_mode` VARCHAR(20) NOT NULL DEFAULT 'inherit' COMMENT 'Embedding策略 inherit|lexical_only|vector|none' AFTER `embed_status`,
            ADD COLUMN `vector_status` VARCHAR(20) NOT NULL DEFAULT 'none' COMMENT '向量索引状态' AFTER `embed_mode`,
            ADD COLUMN `vector_model` VARCHAR(80) NULL COMMENT '向量Embedding模型' AFTER `vector_status`,
            ADD COLUMN `vector_error` LONGTEXT NULL COMMENT '向量索引错误' AFTER `vector_model`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_knowledge_document`
            DROP COLUMN `vector_error`,
            DROP COLUMN `vector_model`,
            DROP COLUMN `vector_status`,
            DROP COLUMN `embed_mode`;
    """
