from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `task` ADD `parallel` BOOL NOT NULL DEFAULT 0 COMMENT '计划级并行执行（按执行器权重分配套件）';
        ALTER TABLE `suite` ADD `stop_on_failure` BOOL NOT NULL DEFAULT 0 COMMENT '用例失败时停止后续用例';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `task` DROP COLUMN `parallel`;
        ALTER TABLE `suite` DROP COLUMN `stop_on_failure`;
    """
