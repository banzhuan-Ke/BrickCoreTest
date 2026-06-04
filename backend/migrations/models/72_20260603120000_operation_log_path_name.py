from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `operation_log` ADD COLUMN `path_name` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '路径中文名称';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `operation_log` DROP COLUMN `path_name`;
    """
