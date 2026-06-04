from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `role` ADD COLUMN `permissions` JSON DEFAULT (JSON_ARRAY()) COMMENT '权限列表';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `role` DROP COLUMN `permissions`;
    """
