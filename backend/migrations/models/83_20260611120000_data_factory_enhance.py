from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `data_tool_favorite` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `user_id` INT NOT NULL COMMENT '用户ID',
            `project_id` INT NOT NULL COMMENT '项目ID',
            `item_type` VARCHAR(16) NOT NULL COMMENT 'tool|tag',
            `item_key` VARCHAR(64) NOT NULL COMMENT 'tool_id 或标签名',
            `sort_order` INT NOT NULL DEFAULT 0 COMMENT '排序',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_dtf_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_dtf_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            UNIQUE KEY `uk_dtf_user_project_item` (`user_id`, `project_id`, `item_type`, `item_key`),
            INDEX `idx_dtf_project_user` (`project_id`, `user_id`)
        ) CHARACTER SET utf8mb4 COMMENT='数据工厂工具/标签收藏';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `data_tool_favorite`;
    """
