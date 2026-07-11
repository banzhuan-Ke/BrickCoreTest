from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ai_embed_config` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `name` VARCHAR(100) NOT NULL DEFAULT 'Default Embedding' COMMENT 'Config name',
            `provider` VARCHAR(20) NOT NULL COMMENT 'Provider',
            `api_key` VARCHAR(255) NOT NULL COMMENT 'Encrypted API key',
            `api_base` VARCHAR(500) NULL COMMENT 'Custom Base URL',
            `model` VARCHAR(100) NOT NULL DEFAULT 'text-embedding-v3' COMMENT 'Embedding model',
            `timeout` INT NOT NULL DEFAULT 120 COMMENT 'Request timeout (seconds)',
            `is_default` BOOL NOT NULL DEFAULT 0 COMMENT 'Default config',
            `is_enabled` BOOL NOT NULL DEFAULT 1 COMMENT 'Enabled',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT 'Soft delete',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `create_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT 'Created by'
        ) CHARACTER SET utf8mb4 COMMENT='Embedding config';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ai_embed_config`;
    """
