from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `requirement_review`
            ADD COLUMN `decisions_json` JSON NULL COMMENT '各评审人结论';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `requirement_review`
            DROP COLUMN `decisions_json`;
    """
