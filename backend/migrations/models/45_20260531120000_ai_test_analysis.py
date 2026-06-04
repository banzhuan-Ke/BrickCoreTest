from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ai_requirement_test_point` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `requirement_id` INT NOT NULL,
            `project_id` INT NOT NULL,
            `title` VARCHAR(300) NOT NULL,
            `description` LONGTEXT NULL,
            `test_type` VARCHAR(30) NOT NULL DEFAULT '正向',
            `priority` VARCHAR(10) NOT NULL DEFAULT 'P2',
            `module_path` VARCHAR(200) NOT NULL DEFAULT '',
            `main_module` VARCHAR(100) NOT NULL DEFAULT '',
            `sub_module` VARCHAR(100) NOT NULL DEFAULT '',
            `acceptance_ref` LONGTEXT NULL,
            `section_ids` JSON NOT NULL,
            `source_ref` VARCHAR(200) NULL,
            `status` VARCHAR(20) NOT NULL DEFAULT 'draft',
            `sort_order` INT NOT NULL DEFAULT 0,
            `extra` JSON NOT NULL,
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_ai_test_point_requirement` FOREIGN KEY (`requirement_id`) REFERENCES `ai_requirement` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_ai_test_point_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4 COMMENT='AI需求测试点';

        CREATE TABLE IF NOT EXISTS `ai_requirement_test_scheme` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `requirement_id` INT NOT NULL,
            `project_id` INT NOT NULL,
            `title` VARCHAR(200) NOT NULL,
            `version` INT NOT NULL DEFAULT 1,
            `status` VARCHAR(20) NOT NULL DEFAULT 'draft',
            `content` JSON NOT NULL,
            `content_md` LONGTEXT NULL,
            `test_point_ids` JSON NOT NULL,
            `scope_section_ids` JSON NOT NULL,
            `generate_report` JSON NOT NULL,
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_ai_test_scheme_requirement` FOREIGN KEY (`requirement_id`) REFERENCES `ai_requirement` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_ai_test_scheme_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4 COMMENT='AI需求测试方案';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ai_requirement_test_scheme`;
        DROP TABLE IF EXISTS `ai_requirement_test_point`;
    """
