from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `api_definition`
            ADD COLUMN `grpc_config` JSON NOT NULL DEFAULT (JSON_OBJECT()) COMMENT 'gRPC 配置';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `api_definition` DROP COLUMN `grpc_config`;
    """
