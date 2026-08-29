from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    await db.execute_script(
        """
        ALTER TABLE `api_plan_run_record`
            ADD COLUMN `quarantine_skip` INT NOT NULL DEFAULT 0 COMMENT '已隔离未跑数' AFTER `failed_cases`;
        """
    )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    await db.execute_script(
        """
        ALTER TABLE `api_plan_run_record` DROP COLUMN `quarantine_skip`;
        """
    )
    return "SELECT 1;"
