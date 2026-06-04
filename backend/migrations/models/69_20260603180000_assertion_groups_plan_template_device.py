from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `api_test_case`
            ADD COLUMN `assertion_groups` JSON NOT NULL COMMENT '条件分支断言组' DEFAULT (JSON_ARRAY());
        ALTER TABLE `api_test_plan`
            ADD COLUMN `is_template` BOOL NOT NULL COMMENT '是否为计划模板' DEFAULT 0;
        ALTER TABLE `ui_plan_execution`
            ADD COLUMN `device_id` VARCHAR(100) NULL COMMENT '执行设备ID';
        ALTER TABLE `ui_suite_execution`
            ADD COLUMN `device_id` VARCHAR(100) NULL COMMENT '执行设备ID';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `api_test_case` DROP COLUMN `assertion_groups`;
        ALTER TABLE `api_test_plan` DROP COLUMN `is_template`;
        ALTER TABLE `ui_plan_execution` DROP COLUMN `device_id`;
        ALTER TABLE `ui_suite_execution` DROP COLUMN `device_id`;
    """
