from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
CREATE TABLE IF NOT EXISTS `perf_cron_job` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '任务ID',
    `name` VARCHAR(100) NOT NULL COMMENT '任务名称',
    `scene_id` INT NOT NULL COMMENT '关联场景',
    `project_id` INT NOT NULL COMMENT '所属项目',
    `env_id` INT NOT NULL COMMENT '执行环境',
    `cron_expr` VARCHAR(100) NOT NULL COMMENT 'Cron表达式',
    `status` VARCHAR(20) NOT NULL DEFAULT 'enabled' COMMENT '状态',
    `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
    `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
    `create_by` VARCHAR(50) NOT NULL COMMENT '创建人',
    CONSTRAINT `fk_perfcronjob_scene_12345678` FOREIGN KEY (`scene_id`) REFERENCES `perf_scene` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_perfcronjob_project_12345678` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_perfcronjob_env_12345678` FOREIGN KEY (`env_id`) REFERENCES `environment` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='性能测试定时任务';

CREATE TABLE IF NOT EXISTS `perf_worker` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '节点ID',
    `name` VARCHAR(100) NOT NULL COMMENT '节点名称',
    `host` VARCHAR(100) NOT NULL COMMENT '主机地址',
    `port` INT NOT NULL DEFAULT 0 COMMENT '端口',
    `token` VARCHAR(100) NOT NULL COMMENT '认证令牌',
    `max_concurrent` INT NOT NULL DEFAULT 100 COMMENT '最大并发数',
    `status` VARCHAR(20) NOT NULL DEFAULT 'idle' COMMENT '状态',
    `last_heartbeat` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '最后心跳时间',
    `current_record_id` INT NULL COMMENT '当前执行记录ID',
    `project_id` INT NOT NULL COMMENT '所属项目',
    `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
    CONSTRAINT `fk_perfworker_project_12345678` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='性能测试Worker节点';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP TABLE IF EXISTS `perf_worker`;
DROP TABLE IF EXISTS `perf_cron_job`;
    """
