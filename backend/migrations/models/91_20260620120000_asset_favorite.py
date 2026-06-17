from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `asset_favorite` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `user_id` INT NOT NULL,
            `project_id` INT NOT NULL,
            `asset_type` VARCHAR(16) NOT NULL COMMENT 'api|ui_case',
            `asset_id` INT NOT NULL,
            `sort_order` INT NOT NULL DEFAULT 0,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            UNIQUE KEY `uk_asset_fav` (`user_id`, `project_id`, `asset_type`, `asset_id`),
            CONSTRAINT `fk_asset_fav_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_asset_fav_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4 COMMENT='接口/Web用例收藏';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `asset_favorite`;
    """
