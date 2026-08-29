from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    await db.execute_script(
        """
        CREATE TABLE IF NOT EXISTS `browser_lab_action_cache` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '项目ID',
            `case_id` INT NULL COMMENT '用例ID',
            `cache_key` VARCHAR(64) NOT NULL UNIQUE COMMENT '缓存键 SHA256',
            `start_url` VARCHAR(500) NOT NULL COMMENT '归一化起始 URL',
            `task_text` LONGTEXT NOT NULL COMMENT '归一化任务描述',
            `tags_json` JSON NOT NULL COMMENT '用例标签',
            `variable_keys_json` JSON NOT NULL COMMENT '变量名集合',
            `actions_json` JSON NOT NULL COMMENT '可回放动作',
            `assertions_json` JSON NOT NULL COMMENT '终态断言',
            `status` VARCHAR(20) NOT NULL DEFAULT 'ready' COMMENT 'ready|stale|disabled',
            `source_task_id` INT NULL COMMENT '写入来源任务',
            `config_fingerprint` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '配置指纹',
            `hit_count` INT NOT NULL DEFAULT 0 COMMENT '命中次数',
            `last_hit_at` DATETIME(6) NULL COMMENT '最近命中',
            `schema_version` INT NOT NULL DEFAULT 1 COMMENT 'schema 版本',
            `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            KEY `idx_bl_action_cache_project` (`project_id`),
            KEY `idx_bl_action_cache_case` (`case_id`)
        ) CHARACTER SET utf8mb4 COMMENT='智能浏览器动作缓存';
        """
    )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    await db.execute_script("DROP TABLE IF EXISTS `browser_lab_action_cache`;")
    return "SELECT 1;"
