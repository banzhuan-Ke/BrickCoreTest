from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `perf_journey_template` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '模板ID',
            `name` VARCHAR(100) NOT NULL COMMENT '模板名称',
            `description` LONGTEXT NULL COMMENT '描述',
            `journey` JSON NOT NULL COMMENT '链路配置',
            `source_scene_id` INT NULL COMMENT '来源场景ID',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `create_by` VARCHAR(50) NOT NULL COMMENT '创建人',
            `project_id` INT NOT NULL COMMENT '所属项目',
            CONSTRAINT `fk_perf_jt_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4 COMMENT='性能测试业务链路模板';
        CREATE INDEX `idx_perf_jt_project` ON `perf_journey_template` (`project_id`);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `perf_journey_template`;
    """
