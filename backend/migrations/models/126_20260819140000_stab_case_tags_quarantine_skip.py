from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    await db.execute_script(
        """
        ALTER TABLE `case`
            ADD COLUMN `tags` JSON NULL COMMENT '用例标签（含 quarantine）' AFTER `description`;
        UPDATE `case` SET `tags` = JSON_ARRAY() WHERE `tags` IS NULL;

        ALTER TABLE `app_case`
            ADD COLUMN `tags` JSON NULL COMMENT '用例标签（含 quarantine）' AFTER `description`;
        UPDATE `app_case` SET `tags` = JSON_ARRAY() WHERE `tags` IS NULL;

        ALTER TABLE `ui_suite_execution`
            ADD COLUMN `quarantine_skip` INT NOT NULL DEFAULT 0 COMMENT '已隔离未跑数' AFTER `skip`;
        ALTER TABLE `ui_plan_execution`
            ADD COLUMN `quarantine_skip` INT NOT NULL DEFAULT 0 COMMENT '已隔离未跑数' AFTER `skip`;
        ALTER TABLE `app_suite_execution`
            ADD COLUMN `quarantine_skip` INT NOT NULL DEFAULT 0 COMMENT '已隔离未跑数' AFTER `skip`;
        ALTER TABLE `app_plan_execution`
            ADD COLUMN `quarantine_skip` INT NOT NULL DEFAULT 0 COMMENT '已隔离未跑数' AFTER `skip`;
        ALTER TABLE `api_suite_run_record`
            ADD COLUMN `quarantine_skip` INT NOT NULL DEFAULT 0 COMMENT '已隔离未跑数' AFTER `skipped_cases`;
        """
    )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    await db.execute_script(
        """
        ALTER TABLE `case` DROP COLUMN `tags`;
        ALTER TABLE `app_case` DROP COLUMN `tags`;
        ALTER TABLE `ui_suite_execution` DROP COLUMN `quarantine_skip`;
        ALTER TABLE `ui_plan_execution` DROP COLUMN `quarantine_skip`;
        ALTER TABLE `app_suite_execution` DROP COLUMN `quarantine_skip`;
        ALTER TABLE `app_plan_execution` DROP COLUMN `quarantine_skip`;
        ALTER TABLE `api_suite_run_record` DROP COLUMN `quarantine_skip`;
        """
    )
    return "SELECT 1;"
