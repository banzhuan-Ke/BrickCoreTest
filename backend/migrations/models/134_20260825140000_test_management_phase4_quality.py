from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `release_quality_snapshot` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `conclusion` VARCHAR(32) NOT NULL,
            `metrics_json` JSON NOT NULL,
            `rules_json` JSON NOT NULL,
            `checks_json` JSON NOT NULL,
            `plan_run_ids` JSON NOT NULL,
            `waiver_reason` LONGTEXT NULL,
            `waiver_approved_by` VARCHAR(50) NULL,
            `waiver_approved_at` DATETIME(6) NULL,
            `note` LONGTEXT NULL,
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL,
            `release_id` INT NOT NULL,
            CONSTRAINT `fk_rqs_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_rqs_release` FOREIGN KEY (`release_id`) REFERENCES `test_release` (`id`) ON DELETE CASCADE,
            KEY `idx_rqs_release` (`project_id`, `release_id`, `is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='测试管理-版本质量快照';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `release_quality_snapshot`;
    """
