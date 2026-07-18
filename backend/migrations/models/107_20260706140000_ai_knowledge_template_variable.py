from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ai_knowledge_template_variable` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '项目ID',
            `name` VARCHAR(64) NOT NULL COMMENT '变量名',
            `label` VARCHAR(100) NOT NULL COMMENT '显示名称',
            `category` VARCHAR(32) NOT NULL DEFAULT 'custom' COMMENT '类别',
            `description` LONGTEXT NULL COMMENT '说明',
            `default_value` LONGTEXT NULL COMMENT '默认值',
            `sort` INT NOT NULL DEFAULT 0 COMMENT '排序',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '逻辑删除',
            `created_by` VARCHAR(50) NULL COMMENT '创建人',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_ai_knowledge_tpl_var_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            INDEX `idx_ai_knowledge_tpl_var_project` (`project_id`, `is_del`, `name`)
        ) CHARACTER SET utf8mb4 COMMENT='迭代测试资料库-自定义模板变量';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ai_knowledge_template_variable`;
    """
