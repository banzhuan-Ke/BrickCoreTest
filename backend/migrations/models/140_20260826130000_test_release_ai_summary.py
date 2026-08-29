from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `test_release_ai_summary` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL,
            `release_id` INT NOT NULL UNIQUE,
            `summary_json` JSON NOT NULL COMMENT 'AI 版本总结缓存',
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_tm_ai_summary_release` FOREIGN KEY (`release_id`) REFERENCES `test_release` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_tm_ai_summary_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            INDEX `idx_tm_ai_summary_project` (`project_id`, `release_id`)
        ) CHARACTER SET utf8mb4;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `test_release_ai_summary`;
    """
