from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `system_stream_parser_config` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `name` VARCHAR(200) NOT NULL COMMENT '配置名称',
            `description` LONGTEXT NULL COMMENT '说明文档',
            `parser_id` VARCHAR(64) NOT NULL COMMENT '内置解析器 ID',
            `parser_options` JSON NOT NULL COMMENT '解析器选项',
            `success_rule` JSON NOT NULL COMMENT '成功判定规则',
            `is_builtin` BOOL NOT NULL DEFAULT 0 COMMENT '内置预置',
            `is_enabled` BOOL NOT NULL DEFAULT 1 COMMENT '是否启用',
            `sort_order` INT NOT NULL DEFAULT 0 COMMENT '排序',
            `create_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '创建人',
            `update_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '最后修改人',
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
        ) CHARACTER SET utf8mb4 COMMENT='SSE流式解析配置';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `system_stream_parser_config`;
    """
