from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ui_step_fragment` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `name` VARCHAR(100) NOT NULL COMMENT '片段名称',
            `project_id` INT NOT NULL COMMENT '所属项目',
            `description` VARCHAR(500) COMMENT '片段描述',
            `steps` JSON NOT NULL COMMENT '步骤 JSON',
            `tags` VARCHAR(200) COMMENT '分类标签',
            `version` INT NOT NULL DEFAULT 1 COMMENT '版本号',
            `username` VARCHAR(50) NOT NULL COMMENT '创建人',
            `update_by` VARCHAR(50) COMMENT '最后更新人',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
            CONSTRAINT `fk_ui_step_fragment_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4 COMMENT='UI步骤片段';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ui_step_fragment`;
    """
