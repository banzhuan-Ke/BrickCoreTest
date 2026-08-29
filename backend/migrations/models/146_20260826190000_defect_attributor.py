from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `test_defect`
            ADD COLUMN `attributor_id` INT NULL COMMENT '缺陷归属人（引入问题者，可与处理人不同）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `test_defect`
            DROP COLUMN `attributor_id`;
    """
