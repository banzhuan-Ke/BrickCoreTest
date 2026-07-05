from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `app_case` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `name` VARCHAR(100) NOT NULL COMMENT '用例名称',
            `project_id` INT NOT NULL COMMENT '所属项目',
            `catalog_id` INT NULL COMMENT '所属目录',
            `steps` JSON NOT NULL COMMENT '用例步骤',
            `level` VARCHAR(10) NOT NULL DEFAULT 'P2' COMMENT '用例等级',
            `platform_scope` VARCHAR(20) NOT NULL DEFAULT 'android' COMMENT '目标平台',
            `driver_mode` VARCHAR(20) NOT NULL DEFAULT 'hybrid' COMMENT 'native|vision|hybrid',
            `description` LONGTEXT NULL COMMENT '用例描述',
            `username` VARCHAR(50) NOT NULL COMMENT '创建人',
            `update_by` VARCHAR(50) NULL COMMENT '最后更新人',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            CONSTRAINT `fk_app_case_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_app_case_catalog` FOREIGN KEY (`catalog_id`) REFERENCES `test_catalog` (`id`) ON DELETE SET NULL,
            KEY `idx_app_case_project` (`project_id`)
        ) CHARACTER SET utf8mb4 COMMENT='App测试用例';

        CREATE TABLE IF NOT EXISTS `app_element` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `name` VARCHAR(100) NOT NULL COMMENT '逻辑元素名',
            `project_id` INT NOT NULL COMMENT '所属项目',
            `element_type` VARCHAR(20) NOT NULL COMMENT 'control|image',
            `locator` JSON NOT NULL COMMENT 'Locator DSL',
            `platform_map` JSON NOT NULL COMMENT '多平台定位',
            `remark` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '备注',
            `username` VARCHAR(50) NOT NULL COMMENT '创建人',
            `update_by` VARCHAR(50) NULL COMMENT '最后更新人',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            CONSTRAINT `fk_app_element_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            KEY `idx_app_element_project` (`project_id`),
            KEY `idx_app_element_name` (`project_id`, `name`)
        ) CHARACTER SET utf8mb4 COMMENT='App元素库';

        CREATE TABLE IF NOT EXISTS `app_suite` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `name` VARCHAR(100) NOT NULL COMMENT '套件名称',
            `project_id` INT NOT NULL COMMENT '所属项目',
            `catalog_id` INT NULL COMMENT '所属目录',
            `pre_actions` JSON NOT NULL COMMENT '前置步骤',
            `setup_sql_ids` JSON NOT NULL COMMENT 'setup SQL',
            `teardown_sql_ids` JSON NOT NULL COMMENT 'teardown SQL',
            `db_assertions` JSON NOT NULL COMMENT '库断言',
            `suite_type` VARCHAR(10) NOT NULL DEFAULT '1' COMMENT '套件类型',
            `stop_on_failure` BOOL NOT NULL DEFAULT 0 COMMENT '失败停止',
            `propagate_variables` BOOL NOT NULL DEFAULT 0 COMMENT '变量传递',
            `username` VARCHAR(50) NOT NULL COMMENT '创建人',
            `update_by` VARCHAR(50) NULL COMMENT '最后更新人',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            CONSTRAINT `fk_app_suite_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_app_suite_catalog` FOREIGN KEY (`catalog_id`) REFERENCES `test_catalog` (`id`) ON DELETE SET NULL,
            KEY `idx_app_suite_project` (`project_id`)
        ) CHARACTER SET utf8mb4 COMMENT='App测试套件';

        CREATE TABLE IF NOT EXISTS `app_suite_step` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `suite_id` INT NOT NULL COMMENT '套件id',
            `case_id` INT NOT NULL COMMENT '用例id',
            `sort` INT NOT NULL DEFAULT 0 COMMENT '排序',
            `skip` BOOL NOT NULL DEFAULT 0 COMMENT '跳过',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            CONSTRAINT `fk_app_suite_step_suite` FOREIGN KEY (`suite_id`) REFERENCES `app_suite` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_app_suite_step_case` FOREIGN KEY (`case_id`) REFERENCES `app_case` (`id`) ON DELETE CASCADE,
            KEY `idx_app_suite_step_suite` (`suite_id`)
        ) CHARACTER SET utf8mb4 COMMENT='App套件用例关联';

        CREATE TABLE IF NOT EXISTS `app_plan` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `name` VARCHAR(255) NOT NULL COMMENT '计划名称',
            `project_id` INT NOT NULL COMMENT '所属项目',
            `catalog_id` INT NULL COMMENT '所属目录',
            `parallel` BOOL NOT NULL DEFAULT 0 COMMENT '并行执行',
            `record_video` BOOL NOT NULL DEFAULT 1 COMMENT '执行时录制用例视频',
            `username` VARCHAR(50) NOT NULL COMMENT '创建人',
            `update_by` VARCHAR(50) NULL COMMENT '最后更新人',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            CONSTRAINT `fk_app_plan_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_app_plan_catalog` FOREIGN KEY (`catalog_id`) REFERENCES `test_catalog` (`id`) ON DELETE SET NULL,
            KEY `idx_app_plan_project` (`project_id`)
        ) CHARACTER SET utf8mb4 COMMENT='App测试计划';

        CREATE TABLE IF NOT EXISTS `app_plan_app_suite` (
            `app_plan_id` INT NOT NULL,
            `appsuite_id` INT NOT NULL,
            FOREIGN KEY (`app_plan_id`) REFERENCES `app_plan` (`id`) ON DELETE CASCADE,
            FOREIGN KEY (`appsuite_id`) REFERENCES `app_suite` (`id`) ON DELETE CASCADE,
            UNIQUE KEY `uidx_app_plan_app_suite` (`app_plan_id`, `appsuite_id`)
        ) CHARACTER SET utf8mb4 COMMENT='App计划套件关联';

        CREATE TABLE IF NOT EXISTS `app_plan_execution` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '所属项目',
            `plan_id` INT NOT NULL COMMENT '计划id',
            `cronjob_id` VARCHAR(100) NULL COMMENT '定时任务',
            `env` JSON NOT NULL COMMENT '执行环境',
            `start_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `duration` DOUBLE NOT NULL DEFAULT 0 COMMENT '耗时',
            `device_id` VARCHAR(100) NULL COMMENT '设备ID',
            `status` VARCHAR(255) NOT NULL DEFAULT '执行中' COMMENT '状态',
            `case_count` INT NOT NULL DEFAULT 0,
            `run_all` INT NOT NULL DEFAULT 0,
            `no_run` INT NOT NULL DEFAULT 0,
            `success` INT NOT NULL DEFAULT 0,
            `fail` INT NOT NULL DEFAULT 0,
            `error` INT NOT NULL DEFAULT 0,
            `skip` INT NOT NULL DEFAULT 0,
            `pass_rate` DOUBLE NOT NULL DEFAULT 0,
            `execution_log` JSON NULL COMMENT '执行日志',
            `username` VARCHAR(50) NOT NULL COMMENT '创建人',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            CONSTRAINT `fk_app_plan_exec_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_app_plan_exec_plan` FOREIGN KEY (`plan_id`) REFERENCES `app_plan` (`id`) ON DELETE CASCADE,
            KEY `idx_app_plan_exec_project` (`project_id`)
        ) CHARACTER SET utf8mb4 COMMENT='App计划执行记录';

        CREATE TABLE IF NOT EXISTS `app_suite_execution` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `suite_id` INT NOT NULL COMMENT '套件id',
            `plan_execution_id` INT NULL COMMENT '计划执行id',
            `device_id` VARCHAR(100) NULL COMMENT '设备ID',
            `status` VARCHAR(255) NOT NULL DEFAULT '执行中',
            `case_count` INT NOT NULL DEFAULT 0,
            `run_all` INT NOT NULL DEFAULT 0,
            `no_run` INT NOT NULL DEFAULT 0,
            `success` INT NOT NULL DEFAULT 0,
            `fail` INT NOT NULL DEFAULT 0,
            `error` INT NOT NULL DEFAULT 0,
            `skip` INT NOT NULL DEFAULT 0,
            `start_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `duration` DOUBLE NOT NULL DEFAULT 0,
            `execution_log` JSON NOT NULL,
            `pass_rate` DOUBLE NOT NULL DEFAULT 0,
            `env` JSON NULL,
            `username` VARCHAR(50) NOT NULL COMMENT '创建人',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            CONSTRAINT `fk_app_suite_exec_suite` FOREIGN KEY (`suite_id`) REFERENCES `app_suite` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_app_suite_exec_plan` FOREIGN KEY (`plan_execution_id`) REFERENCES `app_plan_execution` (`id`) ON DELETE SET NULL,
            KEY `idx_app_suite_exec_suite` (`suite_id`)
        ) CHARACTER SET utf8mb4 COMMENT='App套件执行记录';

        CREATE TABLE IF NOT EXISTS `app_case_execution` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `case_id` INT NOT NULL COMMENT '用例id',
            `suite_execution_id` INT NULL COMMENT '套件执行id',
            `status` VARCHAR(255) NOT NULL DEFAULT 'running',
            `result_data` JSON NOT NULL COMMENT '执行详情',
            `start_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `env` JSON NOT NULL,
            `username` VARCHAR(50) NOT NULL COMMENT '创建人',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            CONSTRAINT `fk_app_case_exec_case` FOREIGN KEY (`case_id`) REFERENCES `app_case` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_app_case_exec_suite` FOREIGN KEY (`suite_execution_id`) REFERENCES `app_suite_execution` (`id`) ON DELETE SET NULL,
            KEY `idx_app_case_exec_case` (`case_id`)
        ) CHARACTER SET utf8mb4 COMMENT='App用例执行记录';

        ALTER TABLE `device`
            ADD COLUMN `runner_engine_types` JSON NULL COMMENT 'Runner引擎能力' AFTER `runner_redis_password`,
            ADD COLUMN `app_platform` VARCHAR(20) NOT NULL DEFAULT '' COMMENT 'App平台' AFTER `runner_engine_types`,
            ADD COLUMN `app_udid` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '设备udid' AFTER `app_platform`,
            ADD COLUMN `app_connection` VARCHAR(20) NOT NULL DEFAULT '' COMMENT 'usb|wifi' AFTER `app_udid`,
            ADD COLUMN `toolchain_status` JSON NULL COMMENT '工具链状态' AFTER `app_connection`;

        UPDATE `device` SET `runner_engine_types` = JSON_ARRAY('web') WHERE `runner_engine_types` IS NULL;
        UPDATE `device` SET `toolchain_status` = JSON_OBJECT() WHERE `toolchain_status` IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `device`
            DROP COLUMN `toolchain_status`,
            DROP COLUMN `app_connection`,
            DROP COLUMN `app_udid`,
            DROP COLUMN `app_platform`,
            DROP COLUMN `runner_engine_types`;

        DROP TABLE IF EXISTS `app_case_execution`;
        DROP TABLE IF EXISTS `app_suite_execution`;
        DROP TABLE IF EXISTS `app_plan_execution`;
        DROP TABLE IF EXISTS `app_plan_app_suite`;
        DROP TABLE IF EXISTS `app_plan`;
        DROP TABLE IF EXISTS `app_suite_step`;
        DROP TABLE IF EXISTS `app_suite`;
        DROP TABLE IF EXISTS `app_element`;
        DROP TABLE IF EXISTS `app_case`;
    """
