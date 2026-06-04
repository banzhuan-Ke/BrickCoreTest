from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `case`
            ADD COLUMN `source_functional_case_id` INT NULL COMMENT '来源功能用例库ID' AFTER `level`,
            ADD COLUMN `source_functional_case_title` VARCHAR(500) NULL COMMENT '来源功能用例标题快照' AFTER `source_functional_case_id`;
        CREATE INDEX `idx_case_source_functional_case` ON `case` (`source_functional_case_id`);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX `idx_case_source_functional_case` ON `case`;
        ALTER TABLE `case`
            DROP COLUMN `source_functional_case_title`,
            DROP COLUMN `source_functional_case_id`;
    """
