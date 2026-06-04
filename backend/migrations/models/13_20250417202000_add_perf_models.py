from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
CREATE TABLE IF NOT EXISTS `perf_scene` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '场景ID',
    `name` VARCHAR(100) NOT NULL COMMENT '场景名称',
    `description` LONGTEXT COMMENT '场景描述',
    `project_id` INT NOT NULL COMMENT '所属项目',
    `scene_items` JSON NOT NULL COMMENT '场景用例项',
    `config` JSON NOT NULL COMMENT '压测配置',
    `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
    `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
    `create_by` VARCHAR(50) NOT NULL COMMENT '创建人',
    CONSTRAINT `fk_perfscene_project_12345678` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='性能测试场景';

CREATE TABLE IF NOT EXISTS `perf_record` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '记录ID',
    `scene_id` INT NOT NULL COMMENT '关联场景',
    `project_id` INT NOT NULL COMMENT '所属项目',
    `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '执行状态',
    `trigger_type` VARCHAR(20) NOT NULL DEFAULT 'manual' COMMENT '触发方式',
    `config_snapshot` JSON NOT NULL COMMENT '配置快照',
    `scene_items_snapshot` JSON NOT NULL COMMENT '场景项快照',
    `total_requests` INT NOT NULL DEFAULT 0 COMMENT '总请求数',
    `success_count` INT NOT NULL DEFAULT 0 COMMENT '成功数',
    `fail_count` INT NOT NULL DEFAULT 0 COMMENT '失败数',
    `qps` DOUBLE NOT NULL DEFAULT 0 COMMENT 'QPS',
    `avg_response_time` DOUBLE NOT NULL DEFAULT 0 COMMENT '平均响应时间(ms)',
    `min_response_time` DOUBLE NOT NULL DEFAULT 0 COMMENT '最小响应时间(ms)',
    `max_response_time` DOUBLE NOT NULL DEFAULT 0 COMMENT '最大响应时间(ms)',
    `p95_response_time` DOUBLE NOT NULL DEFAULT 0 COMMENT 'P95响应时间(ms)',
    `p99_response_time` DOUBLE NOT NULL DEFAULT 0 COMMENT 'P99响应时间(ms)',
    `error_rate` DOUBLE NOT NULL DEFAULT 0 COMMENT '错误率(%)',
    `time_series_data` JSON NOT NULL COMMENT '秒级时序数据',
    `case_aggregations` JSON NOT NULL COMMENT '接口维度聚合',
    `started_at` DATETIME(6) COMMENT '开始时间',
    `ended_at` DATETIME(6) COMMENT '结束时间',
    `duration` DOUBLE NOT NULL DEFAULT 0 COMMENT '实际执行时长(秒)',
    `run_by` VARCHAR(50) NOT NULL COMMENT '执行人',
    CONSTRAINT `fk_perfrecord_scene_12345678` FOREIGN KEY (`scene_id`) REFERENCES `perf_scene` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_perfrecord_project_12345678` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='性能测试执行记录';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP TABLE IF EXISTS `perf_record`;
DROP TABLE IF EXISTS `perf_scene`;
    """
