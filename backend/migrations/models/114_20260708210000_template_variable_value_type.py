from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_knowledge_template_variable`
            ADD COLUMN `value_type` VARCHAR(20) NOT NULL DEFAULT 'text' COMMENT '变量值类型' AFTER `category`,
            ADD COLUMN `value_schema` JSON NULL COMMENT '表格等结构化类型配置' AFTER `value_type`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_knowledge_template_variable`
            DROP COLUMN `value_schema`,
            DROP COLUMN `value_type`;
    """
