from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `case_review_template` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `name` VARCHAR(200) NOT NULL,
            `description` LONGTEXT NULL,
            `checklist` JSON NOT NULL,
            `is_default` BOOL NOT NULL DEFAULT 0,
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL,
            CONSTRAINT `fk_case_review_tpl_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            KEY `idx_case_review_tpl_proj` (`project_id`, `is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='测试管理-评审模板';

        CREATE TABLE IF NOT EXISTS `case_review` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `title` VARCHAR(200) NOT NULL,
            `status` VARCHAR(32) NOT NULL DEFAULT 'pending',
            `due_at` DATETIME(6) NULL,
            `reviewer_ids` JSON NOT NULL,
            `summary` LONGTEXT NULL,
            `checklist_snapshot` JSON NOT NULL,
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL,
            `release_id` INT NULL,
            `template_id` INT NULL,
            CONSTRAINT `fk_case_review_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_case_review_release` FOREIGN KEY (`release_id`) REFERENCES `test_release` (`id`) ON DELETE SET NULL,
            CONSTRAINT `fk_case_review_template` FOREIGN KEY (`template_id`) REFERENCES `case_review_template` (`id`) ON DELETE SET NULL,
            KEY `idx_case_review_proj` (`project_id`, `is_del`),
            KEY `idx_case_review_release` (`release_id`, `is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='测试管理-评审批次';

        CREATE TABLE IF NOT EXISTS `case_review_item` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `functional_case_id` INT NOT NULL,
            `decision` VARCHAR(32) NOT NULL DEFAULT 'pending',
            `comment` LONGTEXT NULL,
            `checklist_result` JSON NOT NULL,
            `decisions_json` JSON NOT NULL,
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL,
            `review_id` INT NOT NULL,
            CONSTRAINT `fk_case_review_item_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_case_review_item_review` FOREIGN KEY (`review_id`) REFERENCES `case_review` (`id`) ON DELETE CASCADE,
            KEY `idx_case_review_item_review` (`review_id`, `is_del`),
            UNIQUE KEY `uniq_case_review_item` (`review_id`, `functional_case_id`, `is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='测试管理-评审项';

        CREATE TABLE IF NOT EXISTS `tm_test_plan` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `name` VARCHAR(200) NOT NULL,
            `plan_type` VARCHAR(32) NOT NULL DEFAULT 'regression',
            `environment_id` INT NULL,
            `entry_criteria` LONGTEXT NULL,
            `exit_criteria` LONGTEXT NULL,
            `status` VARCHAR(32) NOT NULL DEFAULT 'draft',
            `description` LONGTEXT NULL,
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL,
            `release_id` INT NOT NULL,
            CONSTRAINT `fk_tm_plan_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_tm_plan_release` FOREIGN KEY (`release_id`) REFERENCES `test_release` (`id`) ON DELETE CASCADE,
            KEY `idx_tm_plan_release` (`release_id`, `is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='测试管理-测试计划';

        CREATE TABLE IF NOT EXISTS `tm_test_plan_item` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `item_type` VARCHAR(32) NOT NULL DEFAULT 'functional_manual',
            `source_scope_id` INT NULL,
            `functional_case_id` INT NULL,
            `asset_id` INT NULL,
            `title` VARCHAR(500) NOT NULL DEFAULT '',
            `execution_mode` VARCHAR(32) NOT NULL DEFAULT 'manual',
            `order_no` INT NOT NULL DEFAULT 0,
            `required` BOOL NOT NULL DEFAULT 1,
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL,
            `plan_id` INT NOT NULL,
            CONSTRAINT `fk_tm_plan_item_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_tm_plan_item_plan` FOREIGN KEY (`plan_id`) REFERENCES `tm_test_plan` (`id`) ON DELETE CASCADE,
            KEY `idx_tm_plan_item_plan` (`plan_id`, `is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='测试管理-计划项';

        CREATE TABLE IF NOT EXISTS `tm_test_plan_run` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `release_id` INT NOT NULL,
            `environment_id` INT NULL,
            `status` VARCHAR(32) NOT NULL DEFAULT 'running',
            `trigger_source` VARCHAR(32) NOT NULL DEFAULT 'web',
            `snapshot_json` JSON NOT NULL,
            `started_at` DATETIME(6) NULL,
            `finished_at` DATETIME(6) NULL,
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL,
            `plan_id` INT NOT NULL,
            CONSTRAINT `fk_tm_run_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_tm_run_plan` FOREIGN KEY (`plan_id`) REFERENCES `tm_test_plan` (`id`) ON DELETE CASCADE,
            KEY `idx_tm_run_plan` (`plan_id`, `is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='测试管理-计划运行';

        CREATE TABLE IF NOT EXISTS `tm_test_plan_run_item` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `plan_item_id` INT NULL,
            `item_type` VARCHAR(32) NOT NULL DEFAULT 'functional_manual',
            `functional_case_id` INT NULL,
            `asset_id` INT NULL,
            `title` VARCHAR(500) NOT NULL DEFAULT '',
            `execution_mode` VARCHAR(32) NOT NULL DEFAULT 'manual',
            `required` BOOL NOT NULL DEFAULT 1,
            `order_no` INT NOT NULL DEFAULT 0,
            `status` VARCHAR(32) NOT NULL DEFAULT 'pending',
            `result_status` VARCHAR(32) NOT NULL DEFAULT 'not_run',
            `assignee_id` INT NULL,
            `started_at` DATETIME(6) NULL,
            `finished_at` DATETIME(6) NULL,
            `result_message` LONGTEXT NULL,
            `evidence_json` JSON NOT NULL,
            `original_record_type` VARCHAR(32) NULL,
            `original_record_id` INT NULL,
            `attempt_count` INT NOT NULL DEFAULT 0,
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL,
            `run_id` INT NOT NULL,
            CONSTRAINT `fk_tm_run_item_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_tm_run_item_run` FOREIGN KEY (`run_id`) REFERENCES `tm_test_plan_run` (`id`) ON DELETE CASCADE,
            KEY `idx_tm_run_item_run` (`run_id`, `is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='测试管理-运行项';

        CREATE TABLE IF NOT EXISTS `tm_test_plan_run_item_attempt` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `attempt_no` INT NOT NULL,
            `result_status` VARCHAR(32) NOT NULL,
            `result_message` LONGTEXT NULL,
            `evidence_json` JSON NOT NULL,
            `operator` VARCHAR(50) NOT NULL DEFAULT '',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL,
            `run_item_id` INT NOT NULL,
            CONSTRAINT `fk_tm_attempt_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_tm_attempt_item` FOREIGN KEY (`run_item_id`) REFERENCES `tm_test_plan_run_item` (`id`) ON DELETE CASCADE,
            KEY `idx_tm_attempt_item` (`run_item_id`)
        ) CHARACTER SET utf8mb4 COMMENT='测试管理-运行项尝试';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `tm_test_plan_run_item_attempt`;
        DROP TABLE IF EXISTS `tm_test_plan_run_item`;
        DROP TABLE IF EXISTS `tm_test_plan_run`;
        DROP TABLE IF EXISTS `tm_test_plan_item`;
        DROP TABLE IF EXISTS `tm_test_plan`;
        DROP TABLE IF EXISTS `case_review_item`;
        DROP TABLE IF EXISTS `case_review`;
        DROP TABLE IF EXISTS `case_review_template`;
    """
