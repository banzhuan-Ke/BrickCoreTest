from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_functional_case`
            ADD COLUMN `zentao_case_id` VARCHAR(64) NULL COMMENT '禅道用例ID' AFTER `title`,
            ADD COLUMN `update_by` VARCHAR(50) NULL COMMENT '修改人' AFTER `create_by`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_functional_case`
            DROP COLUMN `zentao_case_id`,
            DROP COLUMN `update_by`;
    """
