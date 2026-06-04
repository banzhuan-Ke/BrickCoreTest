from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `api_cron_job`
            ADD COLUMN `plan_id` INT NULL COMMENT '关联测试计划ID（与 suite_id 二选一）',
            ADD CONSTRAINT `fk_api_cron_plan` FOREIGN KEY (`plan_id`) REFERENCES `api_test_plan` (`id`) ON DELETE SET NULL,
            MODIFY COLUMN `suite_id` INT NULL COMMENT '关联套件ID（与 plan_id 二选一）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `api_cron_job`
            DROP FOREIGN KEY `fk_api_cron_plan`,
            DROP COLUMN `plan_id`,
            MODIFY COLUMN `suite_id` INT NOT NULL COMMENT '关联套件ID';
    """
