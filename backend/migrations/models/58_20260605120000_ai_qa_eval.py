from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ai_qa_eval_set` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '项目ID',
            `name` VARCHAR(200) NOT NULL COMMENT '评测集名称',
            `description` TEXT NULL COMMENT '描述',
            `is_del` TINYINT(1) NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            KEY `idx_ai_qa_eval_set_project` (`project_id`)
        ) CHARACTER SET utf8mb4 COMMENT='问答评测集';

        CREATE TABLE IF NOT EXISTS `ai_qa_eval_case` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `set_id` INT NOT NULL COMMENT '评测集ID',
            `question` TEXT NOT NULL COMMENT '测试问题',
            `expected_points` JSON NOT NULL COMMENT '标准要点列表',
            `expected_answer` LONGTEXT NULL COMMENT '标准完整答案',
            `category` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '分类/模块',
            `case_type` VARCHAR(32) NOT NULL DEFAULT '事实' COMMENT '题型',
            `sort_order` INT NOT NULL DEFAULT 0,
            `is_del` TINYINT(1) NOT NULL DEFAULT 0,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            KEY `idx_ai_qa_eval_case_set` (`set_id`)
        ) CHARACTER SET utf8mb4 COMMENT='问答评测用例';

        CREATE TABLE IF NOT EXISTS `ai_qa_eval_target` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '项目ID',
            `name` VARCHAR(200) NOT NULL COMMENT '配置名称',
            `config` JSON NOT NULL COMMENT 'API配置(url/method/headers/body/answer_jsonpath)',
            `is_del` TINYINT(1) NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            KEY `idx_ai_qa_eval_target_project` (`project_id`)
        ) CHARACTER SET utf8mb4 COMMENT='被测问答API配置';

        CREATE TABLE IF NOT EXISTS `ai_qa_eval_run` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL,
            `set_id` INT NOT NULL,
            `target_id` INT NOT NULL,
            `judge_config_id` INT NULL COMMENT '评判用LLM配置',
            `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/running/completed/failed',
            `total_count` INT NOT NULL DEFAULT 0,
            `passed_count` INT NOT NULL DEFAULT 0,
            `failed_count` INT NOT NULL DEFAULT 0,
            `avg_score` DECIMAL(5,2) NOT NULL DEFAULT 0,
            `pass_rate` DECIMAL(5,2) NOT NULL DEFAULT 0,
            `error` TEXT NULL,
            `extra` JSON NOT NULL,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `started_at` DATETIME(6) NULL,
            `finished_at` DATETIME(6) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            KEY `idx_ai_qa_eval_run_set` (`set_id`),
            KEY `idx_ai_qa_eval_run_project` (`project_id`)
        ) CHARACTER SET utf8mb4 COMMENT='问答评测跑批';

        CREATE TABLE IF NOT EXISTS `ai_qa_eval_result` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `run_id` INT NOT NULL,
            `case_id` INT NOT NULL,
            `question` TEXT NOT NULL,
            `actual_answer` LONGTEXT NULL,
            `score` DECIMAL(5,2) NOT NULL DEFAULT 0,
            `passed` TINYINT(1) NOT NULL DEFAULT 0,
            `hallucination` TINYINT(1) NOT NULL DEFAULT 0,
            `level` VARCHAR(20) NOT NULL DEFAULT '',
            `dimension_scores` JSON NOT NULL,
            `missed_points` JSON NOT NULL,
            `extra_issues` JSON NOT NULL,
            `reason` LONGTEXT NULL,
            `judge_raw` LONGTEXT NULL,
            `api_error` TEXT NULL,
            `api_latency_ms` INT NOT NULL DEFAULT 0,
            `judge_tokens` INT NOT NULL DEFAULT 0,
            `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/api_failed/judged/skipped',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            KEY `idx_ai_qa_eval_result_run` (`run_id`)
        ) CHARACTER SET utf8mb4 COMMENT='问答评测单题结果';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ai_qa_eval_result`;
        DROP TABLE IF EXISTS `ai_qa_eval_run`;
        DROP TABLE IF EXISTS `ai_qa_eval_target`;
        DROP TABLE IF EXISTS `ai_qa_eval_case`;
        DROP TABLE IF EXISTS `ai_qa_eval_set`;
    """
