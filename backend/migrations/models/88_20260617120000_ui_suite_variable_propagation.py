from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `suite` ADD `propagate_variables` BOOL NOT NULL DEFAULT 0 COMMENT '是否将链路用例变量传递给后续链路用例';
        ALTER TABLE `step` ADD `run_mode` VARCHAR(20) NOT NULL DEFAULT 'standalone' COMMENT '运行模式：chain=链路用例 standalone=独立用例';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `suite` DROP COLUMN `propagate_variables`;
        ALTER TABLE `step` DROP COLUMN `run_mode`;
    """
