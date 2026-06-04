from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `project` ADD COLUMN `default_headers` JSON COMMENT '项目级默认请求头';
        ALTER TABLE `environment` ADD COLUMN `default_headers` JSON COMMENT '环境级默认请求头';
        ALTER TABLE `api_definition` ADD COLUMN `global_header_policy` JSON COMMENT '全局Header使用策略';
        ALTER TABLE `api_test_case` ADD COLUMN `global_header_policy` JSON COMMENT '全局Header使用策略';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `project` DROP COLUMN `default_headers`;
        ALTER TABLE `environment` DROP COLUMN `default_headers`;
        ALTER TABLE `api_definition` DROP COLUMN `global_header_policy`;
        ALTER TABLE `api_test_case` DROP COLUMN `global_header_policy`;
    """
