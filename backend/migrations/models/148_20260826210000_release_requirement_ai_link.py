from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `test_release_requirement`
            ADD COLUMN `ai_requirement_id` INT NULL COMMENT '关联 AI 需求 ID',
            ADD COLUMN `source_type` VARCHAR(16) NOT NULL DEFAULT 'external'
                COMMENT 'ai=项目需求 external=外部手工';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `test_release_requirement`
            DROP COLUMN `ai_requirement_id`,
            DROP COLUMN `source_type`;
    """
