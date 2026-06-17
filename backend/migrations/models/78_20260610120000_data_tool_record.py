from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `data_tool_record` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '所属项目',
            `environment_id` INT NULL COMMENT '生效环境',
            `tool_id` VARCHAR(64) NOT NULL COMMENT '工具ID',
            `tool_name` VARCHAR(100) NOT NULL COMMENT '工具名称',
            `tool_category` VARCHAR(32) NOT NULL COMMENT '工具分类',
            `tag` VARCHAR(64) NOT NULL COMMENT '主标签',
            `tags` JSON NOT NULL DEFAULT (JSON_ARRAY()) COMMENT '附加标签',
            `input_data` JSON NOT NULL DEFAULT (JSON_OBJECT()) COMMENT '输入参数',
            `output_data` JSON NULL COMMENT '输出结果',
            `output_text` LONGTEXT NULL COMMENT '输出文本',
            `remark` VARCHAR(255) NULL COMMENT '备注',
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_dtr_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_dtr_env` FOREIGN KEY (`environment_id`) REFERENCES `environment` (`id`) ON DELETE SET NULL,
            INDEX `idx_dtr_project_env` (`project_id`, `environment_id`, `is_del`),
            INDEX `idx_dtr_tag` (`project_id`, `tag`)
        ) CHARACTER SET utf8mb4 COMMENT='数据工厂通用工具记录';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `data_tool_record`;
    """
