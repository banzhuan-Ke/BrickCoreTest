from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ai_requirement_generate_job` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/running/completed/failed/cancelled',
            `total_batches` INT NOT NULL DEFAULT 0 COMMENT '总批次数',
            `done_batches` INT NOT NULL DEFAULT 0 COMMENT '已完成批次数',
            `current_batch_name` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '当前批次名称',
            `payload` JSON NOT NULL COMMENT '生成配置快照',
            `batch_results` JSON NOT NULL COMMENT '各批执行结果',
            `generate_report` JSON NOT NULL COMMENT '汇总报告',
            `error` LONGTEXT COMMENT '失败原因',
            `tokens_used` INT NOT NULL DEFAULT 0 COMMENT 'Token消耗',
            `duration_ms` INT NOT NULL DEFAULT 0 COMMENT '耗时ms',
            `create_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '创建人',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `finish_time` DATETIME(6) NULL COMMENT '结束时间',
            `project_id` INT NOT NULL COMMENT '所属项目',
            `requirement_id` INT NOT NULL COMMENT '所属需求',
            CONSTRAINT `fk_ai_req_gen_job_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_ai_req_gen_job_requirement` FOREIGN KEY (`requirement_id`) REFERENCES `ai_requirement` (`id`) ON DELETE CASCADE,
            INDEX `idx_ai_req_gen_job_req_status` (`requirement_id`, `status`)
        ) CHARACTER SET utf8mb4 COMMENT='AI需求用例批量生成任务';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ai_requirement_generate_job`;
    """
