from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `perf_record`
            ADD COLUMN `phase_metrics` JSON NULL COMMENT 'SSE问答阶段压测聚合指标' AFTER `case_aggregations`,
            ADD COLUMN `request_details` JSON NULL COMMENT 'SSE问答阶段压测请求明细' AFTER `phase_metrics`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `perf_record`
            DROP COLUMN `phase_metrics`,
            DROP COLUMN `request_details`;
    """
