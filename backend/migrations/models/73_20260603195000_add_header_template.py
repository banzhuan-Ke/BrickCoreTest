from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `header_template` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `name` VARCHAR(100) NOT NULL COMMENT '模板名称',
            `description` LONGTEXT COMMENT '模板说明',
            `headers` JSON NOT NULL COMMENT 'Header 列表',
            `is_default` BOOL NOT NULL DEFAULT 0 COMMENT '是否默认模板',
            `sort_order` INT NOT NULL DEFAULT 0 COMMENT '排序',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            `create_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '创建人',
            `update_by` VARCHAR(50) COMMENT '修改人',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL COMMENT '所属项目',
            CONSTRAINT `fk_header_template_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4 COMMENT='Header 模板';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `header_template`;
    """
