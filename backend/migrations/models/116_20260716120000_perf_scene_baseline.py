from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `perf_scene`
            ADD COLUMN `baseline_record_id` INT NULL COMMENT '钉选基线执行记录ID' AFTER `csv_config`,
            ADD COLUMN `baseline_policy` JSON NOT NULL DEFAULT (JSON_OBJECT()) COMMENT '基线阈值策略' AFTER `baseline_record_id`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `perf_scene`
            DROP COLUMN `baseline_policy`,
            DROP COLUMN `baseline_record_id`;
    """
