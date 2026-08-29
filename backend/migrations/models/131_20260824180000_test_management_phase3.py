from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `test_defect` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `defect_key` VARCHAR(64) NOT NULL,
            `title` VARCHAR(500) NOT NULL,
            `description` LONGTEXT NULL,
            `severity` VARCHAR(32) NOT NULL DEFAULT 'major',
            `priority` VARCHAR(8) NOT NULL DEFAULT 'p2',
            `status` VARCHAR(32) NOT NULL DEFAULT 'open',
            `found_in` VARCHAR(128) NULL,
            `fixed_in` VARCHAR(128) NULL,
            `assignee_id` INT NULL,
            `reporter_id` INT NULL,
            `external_system` VARCHAR(64) NULL,
            `external_key` VARCHAR(128) NULL,
            `external_url` VARCHAR(500) NULL,
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL,
            `release_id` INT NULL,
            CONSTRAINT `fk_test_defect_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_test_defect_release` FOREIGN KEY (`release_id`) REFERENCES `test_release` (`id`) ON DELETE SET NULL,
            UNIQUE KEY `uniq_test_defect_key` (`project_id`, `defect_key`, `is_del`),
            KEY `idx_test_defect_release` (`release_id`, `is_del`),
            KEY `idx_test_defect_status` (`project_id`, `status`, `is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='测试管理-缺陷';

        CREATE TABLE IF NOT EXISTS `test_defect_link` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `link_type` VARCHAR(32) NOT NULL,
            `run_item_id` INT NULL,
            `functional_case_id` INT NULL,
            `asset_type` VARCHAR(32) NULL,
            `asset_id` INT NULL,
            `external_url` VARCHAR(500) NULL,
            `note` LONGTEXT NULL,
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL,
            `defect_id` INT NOT NULL,
            CONSTRAINT `fk_test_defect_link_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_test_defect_link_defect` FOREIGN KEY (`defect_id`) REFERENCES `test_defect` (`id`) ON DELETE CASCADE,
            KEY `idx_test_defect_link_defect` (`defect_id`, `is_del`),
            KEY `idx_test_defect_link_run_item` (`run_item_id`)
        ) CHARACTER SET utf8mb4 COMMENT='测试管理-缺陷关联';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `test_defect_link`;
        DROP TABLE IF EXISTS `test_defect`;
    """
