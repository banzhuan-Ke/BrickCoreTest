from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE `test_release_requirement`
        SET
            `ai_requirement_id` = CAST(SUBSTRING(`requirement_key`, 5) AS UNSIGNED),
            `source_type` = 'ai'
        WHERE `is_del` = 0
          AND UPPER(`requirement_key`) REGEXP '^REQ-[0-9]+$'
          AND (`source_type` = 'external' OR `ai_requirement_id` IS NULL);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        SELECT 1;
    """
