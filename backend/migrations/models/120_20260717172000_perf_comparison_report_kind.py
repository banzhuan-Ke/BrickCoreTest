from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `perf_comparison_report`
            ADD COLUMN `kind` VARCHAR(20) NOT NULL DEFAULT 'compare' COMMENT '报告类型: compare=对比 / merge=汇总 / hybrid=合并+对比' AFTER `title`;
        UPDATE `perf_comparison_report`
            SET `kind` = COALESCE(JSON_UNQUOTE(JSON_EXTRACT(`snapshot`, '$.kind')), 'compare')
            WHERE `snapshot` IS NOT NULL;
        ALTER TABLE `perf_comparison_report`
            ADD KEY `idx_perf_cmp_kind` (`project_id`, `kind`);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `perf_comparison_report` DROP INDEX `idx_perf_cmp_kind`;
        ALTER TABLE `perf_comparison_report` DROP COLUMN `kind`;
    """
