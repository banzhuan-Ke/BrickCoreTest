from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `perf_comparison_report` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '对比报告ID',
            `title` VARCHAR(200) NOT NULL COMMENT '报告标题',
            `record_ids` JSON NOT NULL COMMENT '参与对比的执行记录ID列表',
            `reference_record_id` INT NOT NULL COMMENT '基准记录ID',
            `snapshot` JSON NOT NULL COMMENT '对比快照',
            `ai_analysis` JSON NULL COMMENT 'AI 分析结果',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `create_by` VARCHAR(50) NOT NULL COMMENT '创建人',
            `project_id` INT NOT NULL COMMENT '所属项目',
            CONSTRAINT `fk_perf_cmp_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            KEY `idx_perf_cmp_project` (`project_id`),
            KEY `idx_perf_cmp_create` (`create_time`)
        ) CHARACTER SET utf8mb4 COMMENT='性能测试对比报告';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `perf_comparison_report`;
    """
