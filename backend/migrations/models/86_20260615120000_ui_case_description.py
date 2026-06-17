from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `case`
            ADD COLUMN `description` TEXT NULL COMMENT '用例描述（功能背景/步骤预期，供 AI 优化）' AFTER `source_functional_case_title`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `case` DROP COLUMN `description`;
    """
