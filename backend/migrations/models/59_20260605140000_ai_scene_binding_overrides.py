from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_scene_binding`
            ADD COLUMN `overrides` JSON NOT NULL DEFAULT (JSON_OBJECT()) COMMENT '场景级参数覆盖(max_tokens/temperature/timeout)' AFTER `config_id`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_scene_binding` DROP COLUMN `overrides`;
    """
