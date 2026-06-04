from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `api_plan_run_record` (
            `id`           INT          NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '记录ID',
            `plan_id`      INT          NOT NULL COMMENT '所属计划ID',
            `project_id`   INT          NOT NULL COMMENT '所属项目ID',
            `status`       VARCHAR(20)  NOT NULL COMMENT '状态: running/success/failed',
            `trigger_type` VARCHAR(20)  NOT NULL DEFAULT 'manual' COMMENT '触发类型: manual/cron',
            `total_cases`  INT          NOT NULL DEFAULT 0 COMMENT '总用例数',
            `success_cases` INT         NOT NULL DEFAULT 0 COMMENT '成功用例数',
            `failed_cases` INT          NOT NULL DEFAULT 0 COMMENT '失败用例数',
            `env_id`       INT          NULL COMMENT '执行环境ID',
            `env_name`     VARCHAR(100) NULL COMMENT '执行环境名称',
            `duration`     DOUBLE       NULL COMMENT '总耗时(ms)',
            `item_results` JSON         NOT NULL COMMENT '各 Item 执行结果快照',
            `run_by`       VARCHAR(50)  NOT NULL DEFAULT 'admin' COMMENT '执行人',
            `start_time`   DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '开始时间',
            `end_time`     DATETIME(6)  NULL COMMENT '结束时间',
            CONSTRAINT `fk_plan_run_plan`    FOREIGN KEY (`plan_id`)    REFERENCES `api_test_plan` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_plan_run_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4 COMMENT='测试计划执行记录';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `api_plan_run_record`;
    """
