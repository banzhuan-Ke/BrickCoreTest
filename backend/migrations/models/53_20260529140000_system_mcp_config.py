from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `system_mcp_config` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `enabled` BOOL NOT NULL DEFAULT 1 COMMENT '是否启用 MCP Server',
            `base_url` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '平台对外访问地址',
            `api_key` VARCHAR(500) NOT NULL DEFAULT '' COMMENT 'MCP API Key（加密）',
            `update_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '最后修改人',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
        ) CHARACTER SET utf8mb4 COMMENT='全局MCP配置';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `system_mcp_config`;
    """
