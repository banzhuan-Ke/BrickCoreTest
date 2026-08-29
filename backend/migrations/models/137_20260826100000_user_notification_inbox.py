from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `user_notification` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL,
            `user_id` INT NOT NULL,
            `category` VARCHAR(32) NOT NULL DEFAULT 'test_management',
            `event_type` VARCHAR(64) NOT NULL,
            `title` VARCHAR(255) NOT NULL,
            `body` LONGTEXT NULL,
            `link_path` VARCHAR(255) NOT NULL DEFAULT '',
            `link_query` JSON NULL,
            `entity_type` VARCHAR(64) NOT NULL DEFAULT '',
            `entity_id` INT NULL,
            `actor_id` INT NULL,
            `is_read` BOOL NOT NULL DEFAULT 0,
            `read_at` DATETIME(6) NULL,
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            KEY `idx_user_notification_inbox` (`user_id`, `project_id`, `is_read`, `create_time`),
            KEY `idx_user_notification_user` (`user_id`, `is_del`, `create_time`),
            CONSTRAINT `fk_user_notification_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `user_notification`;
    """
