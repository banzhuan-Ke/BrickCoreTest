from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `env_datasource` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '所属项目',
            `environment_id` INT NOT NULL COMMENT '生效环境',
            `name` VARCHAR(100) NOT NULL COMMENT '数据源名称',
            `db_type` VARCHAR(20) NOT NULL DEFAULT 'mysql' COMMENT '数据库类型',
            `host` VARCHAR(255) NOT NULL COMMENT '主机',
            `port` INT NOT NULL DEFAULT 3306 COMMENT '端口',
            `database_name` VARCHAR(128) NOT NULL COMMENT '数据库名',
            `username` VARCHAR(128) NOT NULL COMMENT '用户名',
            `password_encrypted` TEXT NULL COMMENT '加密密码',
            `allow_write` BOOL NOT NULL DEFAULT 0 COMMENT '是否允许写操作(INSERT/UPDATE/DELETE)',
            `max_rows` INT NOT NULL DEFAULT 100 COMMENT '查询最大返回行数',
            `timeout_seconds` INT NOT NULL DEFAULT 10 COMMENT '连接/执行超时(秒)',
            `is_default` BOOL NOT NULL DEFAULT 0 COMMENT '环境默认数据源',
            `is_enabled` BOOL NOT NULL DEFAULT 1 COMMENT '是否启用',
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_env_ds_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_env_ds_env` FOREIGN KEY (`environment_id`) REFERENCES `environment` (`id`) ON DELETE CASCADE,
            UNIQUE KEY `uk_env_ds_project_env_name` (`project_id`, `environment_id`, `name`)
        ) CHARACTER SET utf8mb4 COMMENT='环境级数据库数据源';

        CREATE INDEX `idx_env_ds_project_env` ON `env_datasource` (`project_id`, `environment_id`, `is_enabled`, `is_del`);

        CREATE TABLE IF NOT EXISTS `sql_template` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '所属项目',
            `environment_id` INT NULL COMMENT '可选绑定环境',
            `datasource_id` INT NOT NULL COMMENT '数据源',
            `name` VARCHAR(100) NOT NULL COMMENT '模板名称',
            `template_type` VARCHAR(20) NOT NULL DEFAULT 'setup' COMMENT 'setup/teardown/query',
            `sql_text` LONGTEXT NOT NULL COMMENT 'SQL 模板',
            `description` TEXT NULL COMMENT '描述',
            `is_enabled` BOOL NOT NULL DEFAULT 1 COMMENT '是否启用',
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_sql_tpl_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_sql_tpl_env` FOREIGN KEY (`environment_id`) REFERENCES `environment` (`id`) ON DELETE SET NULL,
            CONSTRAINT `fk_sql_tpl_ds` FOREIGN KEY (`datasource_id`) REFERENCES `env_datasource` (`id`) ON DELETE CASCADE,
            UNIQUE KEY `uk_sql_tpl_project_name` (`project_id`, `name`)
        ) CHARACTER SET utf8mb4 COMMENT='数据工厂 SQL 模板';

        CREATE INDEX `idx_sql_tpl_project_env` ON `sql_template` (`project_id`, `environment_id`, `is_enabled`, `is_del`);

        ALTER TABLE `api_test_case`
            ADD COLUMN `db_assertions` JSON NOT NULL DEFAULT (JSON_ARRAY()) COMMENT '数据库断言规则';

        ALTER TABLE `api_test_suite`
            ADD COLUMN `setup_sql_ids` JSON NOT NULL DEFAULT (JSON_ARRAY()) COMMENT '套件前置 SQL 模板 ID 列表',
            ADD COLUMN `teardown_sql_ids` JSON NOT NULL DEFAULT (JSON_ARRAY()) COMMENT '套件后置 SQL 模板 ID 列表',
            ADD COLUMN `db_assertions` JSON NOT NULL DEFAULT (JSON_ARRAY()) COMMENT '套件级数据库断言';

        ALTER TABLE `api_suite_run_record`
            ADD COLUMN `hooks_result` JSON NOT NULL DEFAULT (JSON_OBJECT()) COMMENT '数据工厂/setup/teardown/套件断言结果';

        ALTER TABLE `suite`
            ADD COLUMN `setup_sql_ids` JSON NOT NULL DEFAULT (JSON_ARRAY()) COMMENT 'UI套件前置SQL模板ID',
            ADD COLUMN `teardown_sql_ids` JSON NOT NULL DEFAULT (JSON_ARRAY()) COMMENT 'UI套件后置SQL模板ID',
            ADD COLUMN `db_assertions` JSON NOT NULL DEFAULT (JSON_ARRAY()) COMMENT 'UI套件数据库断言';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `suite`
            DROP COLUMN `setup_sql_ids`,
            DROP COLUMN `teardown_sql_ids`,
            DROP COLUMN `db_assertions`;
        ALTER TABLE `api_suite_run_record` DROP COLUMN `hooks_result`;
        ALTER TABLE `api_test_suite`
            DROP COLUMN `setup_sql_ids`,
            DROP COLUMN `teardown_sql_ids`,
            DROP COLUMN `db_assertions`;
        ALTER TABLE `api_test_case` DROP COLUMN `db_assertions`;
        DROP TABLE IF EXISTS `sql_template`;
        DROP TABLE IF EXISTS `env_datasource`;
    """
