from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `browser_lab_case` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '项目ID',
            `name` VARCHAR(200) NOT NULL COMMENT '用例名称',
            `description` LONGTEXT NULL COMMENT '用例说明',
            `task_text` LONGTEXT NOT NULL COMMENT '任务描述',
            `start_url` VARCHAR(500) NOT NULL COMMENT '起始URL',
            `config_json` JSON NOT NULL COMMENT '默认配置',
            `tags` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '标签',
            `created_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '创建人',
            `update_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '更新人',
            `run_count` INT NOT NULL DEFAULT 0 COMMENT '执行次数',
            `last_run_at` DATETIME(6) NULL COMMENT '最近执行',
            `last_status` VARCHAR(20) NULL COMMENT '最近状态',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '软删除',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_browser_lab_case_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            INDEX `idx_browser_lab_case_project` (`project_id`, `is_del`),
            INDEX `idx_browser_lab_case_time` (`project_id`, `update_time`)
        ) CHARACTER SET utf8mb4 COMMENT='智能浏览器用例';

        ALTER TABLE `browser_lab_task`
            ADD COLUMN `case_id` INT NULL COMMENT '来源用例ID' AFTER `project_id`,
            ADD COLUMN `case_name` VARCHAR(200) NULL COMMENT '用例名称快照' AFTER `case_id`,
            ADD COLUMN `source_task_id` INT NULL COMMENT '重跑来源任务' AFTER `case_name`,
            ADD INDEX `idx_browser_lab_task_case` (`case_id`);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `browser_lab_task`
            DROP INDEX `idx_browser_lab_task_case`,
            DROP COLUMN `source_task_id`,
            DROP COLUMN `case_name`,
            DROP COLUMN `case_id`;
        DROP TABLE IF EXISTS `browser_lab_case`;
    """
