from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `api_definition`
            ADD COLUMN `protocol` VARCHAR(20) NOT NULL DEFAULT 'http' COMMENT '协议 http/websocket';
        ALTER TABLE `api_definition`
            ADD COLUMN `ws_config` JSON NOT NULL DEFAULT (JSON_OBJECT()) COMMENT 'WebSocket 默认配置';
        ALTER TABLE `api_test_case`
            ADD COLUMN `ws_steps` JSON NOT NULL DEFAULT (JSON_ARRAY()) COMMENT 'WebSocket 步骤序列';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `api_test_case` DROP COLUMN `ws_steps`;
        ALTER TABLE `api_definition` DROP COLUMN `ws_config`;
        ALTER TABLE `api_definition` DROP COLUMN `protocol`;
    """
