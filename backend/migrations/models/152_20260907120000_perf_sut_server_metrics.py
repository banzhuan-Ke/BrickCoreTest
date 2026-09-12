from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `sut_server` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '所属项目',
            `agent_uid` VARCHAR(64) NULL COMMENT 'Agent 本地稳定身份',
            `name` VARCHAR(100) NOT NULL COMMENT '展示名称',
            `hostname` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '主机名',
            `role` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '角色标签',
            `token_hash` VARCHAR(128) NOT NULL COMMENT 'Token 哈希',
            `monitoring_enabled` BOOL NOT NULL DEFAULT 1 COMMENT '是否启用监控采样',
            `schedule_json` JSON NULL COMMENT '免监控/仅监控时段配置',
            `last_heartbeat_at` DATETIME(6) NULL COMMENT '最近心跳',
            `host_info` JSON NOT NULL COMMENT '主机探测摘要',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `create_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '创建人',
            KEY `idx_sut_server_project` (`project_id`),
            KEY `idx_sut_server_del` (`is_del`),
            KEY `idx_sut_server_token` (`token_hash`)
        ) CHARACTER SET utf8mb4 COMMENT='被测服务器';

        CREATE TABLE IF NOT EXISTS `sut_metric_chunk` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `server_id` INT NOT NULL COMMENT '被测服务器',
            `start_ms` BIGINT NOT NULL COMMENT '批次起始 epoch ms',
            `end_ms` BIGINT NOT NULL COMMENT '批次结束 epoch ms',
            `points_json` JSON NOT NULL COMMENT '采样点数组',
            `received_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '入库时间',
            UNIQUE KEY `uid_sut_chunk_server_start` (`server_id`, `start_ms`),
            KEY `idx_sut_chunk_server_range` (`server_id`, `start_ms`, `end_ms`)
        ) CHARACTER SET utf8mb4 COMMENT='被测服务器指标 chunk';

        CREATE TABLE IF NOT EXISTS `perf_record_sut_metric` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `record_id` INT NOT NULL COMMENT '压测记录',
            `server_id` INT NULL COMMENT '被测服务器',
            `server_snapshot_json` JSON NOT NULL COMMENT '当时服务器快照',
            `series_json` JSON NOT NULL COMMENT '降采样曲线',
            `summary_json` JSON NOT NULL COMMENT '汇总指标',
            `source` VARCHAR(32) NOT NULL DEFAULT 'agent' COMMENT 'agent|vm|grafana_link',
            `status` VARCHAR(32) NOT NULL DEFAULT 'no_data' COMMENT 'complete|partial|no_data|offline|failed',
            `coverage` DOUBLE NULL COMMENT '覆盖率 0~1',
            `grafana_url` VARCHAR(1024) NULL COMMENT 'Grafana 深链',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            KEY `idx_perf_rec_sut_record` (`record_id`),
            KEY `idx_perf_rec_sut_server` (`server_id`)
        ) CHARACTER SET utf8mb4 COMMENT='压测记录被测资源快照';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `perf_record_sut_metric`;
        DROP TABLE IF EXISTS `sut_metric_chunk`;
        DROP TABLE IF EXISTS `sut_server`;
    """
