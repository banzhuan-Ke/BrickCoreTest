from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `test_defect_comment` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL,
            `defect_id` INT NOT NULL,
            `body` LONGTEXT NOT NULL,
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            KEY `idx_defect_comment_defect` (`defect_id`, `is_del`),
            CONSTRAINT `fk_defect_comment_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_defect_comment_defect` FOREIGN KEY (`defect_id`) REFERENCES `test_defect` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `test_defect_activity` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL,
            `defect_id` INT NOT NULL,
            `action` VARCHAR(32) NOT NULL,
            `from_value` VARCHAR(255) NULL,
            `to_value` VARCHAR(255) NULL,
            `note` LONGTEXT NULL,
            `actor` VARCHAR(50) NOT NULL DEFAULT '',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            KEY `idx_defect_activity_defect` (`defect_id`, `create_time`),
            CONSTRAINT `fk_defect_activity_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_defect_activity_defect` FOREIGN KEY (`defect_id`) REFERENCES `test_defect` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `test_defect_activity`;
        DROP TABLE IF EXISTS `test_defect_comment`;
    """
