from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `test_defect_link`
            ADD COLUMN `requirement_id` INT NULL COMMENT '关联需求 AiRequirement ID' AFTER `functional_case_id`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `test_defect_link`
            DROP COLUMN `requirement_id`;
    """
