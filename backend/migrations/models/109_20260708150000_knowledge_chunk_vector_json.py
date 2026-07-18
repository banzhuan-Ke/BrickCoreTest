from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_knowledge_chunk`
            ADD COLUMN `vector_json` JSON NULL COMMENT '向量Embedding float[]' AFTER `embedding_model`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_knowledge_chunk`
            DROP COLUMN `vector_json`;
    """
