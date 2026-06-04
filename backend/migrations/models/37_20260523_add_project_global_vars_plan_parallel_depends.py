from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `project` ADD COLUMN `global_vars` JSON;
        ALTER TABLE `api_test_plan` ADD COLUMN `parallel` TINYINT(1) NOT NULL DEFAULT 0;
        ALTER TABLE `api_plan_item` ADD COLUMN `depends_on` JSON;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `project` DROP COLUMN `global_vars`;
        ALTER TABLE `api_test_plan` DROP COLUMN `parallel`;
        ALTER TABLE `api_plan_item` DROP COLUMN `depends_on`;
    """
