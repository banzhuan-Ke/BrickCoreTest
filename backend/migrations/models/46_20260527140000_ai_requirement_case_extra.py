from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_requirement_case`
        ADD COLUMN `extra` JSON NOT NULL COMMENT '扩展字段（如 test_point_ids）' DEFAULT (JSON_OBJECT());
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_requirement_case`
        DROP COLUMN `extra`;
    """
