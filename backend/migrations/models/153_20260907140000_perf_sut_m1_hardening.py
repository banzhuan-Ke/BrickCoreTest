from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `sut_server` ADD COLUMN `last_metrics_at` DATETIME(6) NULL COMMENT '最近成功接收指标';
        ALTER TABLE `sut_metric_chunk` ADD INDEX `idx_sut_chunk_received` (`received_at`);
        ALTER TABLE `perf_record_sut_metric` ADD UNIQUE KEY `uid_perf_rec_sut_rec_srv` (`record_id`, `server_id`);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `perf_record_sut_metric` DROP INDEX `uid_perf_rec_sut_rec_srv`;
        ALTER TABLE `sut_metric_chunk` DROP INDEX `idx_sut_chunk_received`;
        ALTER TABLE `sut_server` DROP COLUMN `last_metrics_at`;
    """
