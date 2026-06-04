from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_requirement_case`
            ADD COLUMN `section_ids` JSON NULL COMMENT '来源章节ID列表' AFTER `source_ref`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_requirement_case`
            DROP COLUMN `section_ids`;
    """
