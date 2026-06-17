from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
CREATE INDEX `idx_perf_record_project_started`
    ON `perf_record` (`project_id`, `started_at`);
CREATE INDEX `idx_perf_record_project_id_desc`
    ON `perf_record` (`project_id`, `id`);
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP INDEX `idx_perf_record_project_id_desc` ON `perf_record`;
DROP INDEX `idx_perf_record_project_started` ON `perf_record`;
"""
