from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `api_test_case` ADD COLUMN `api_version_snapshot` INT NOT NULL DEFAULT 1;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `api_test_case` DROP COLUMN `api_version_snapshot`;
    """
