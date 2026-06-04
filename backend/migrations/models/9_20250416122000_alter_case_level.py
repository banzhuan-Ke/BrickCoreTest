from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `case` MODIFY COLUMN `level` VARCHAR(10) NOT NULL DEFAULT 'P2';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `case` MODIFY COLUMN `level` VARCHAR(50) NOT NULL DEFAULT '1';
    """
