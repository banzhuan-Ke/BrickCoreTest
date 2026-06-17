from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `system_platform_settings` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `ui_case_record_delete_mode` VARCHAR(20) NOT NULL DEFAULT 'logical' COMMENT 'UI用例运行记录删除模式：logical|physical|recycle_bin',
            `update_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '最后修改人',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
        ) CHARACTER SET utf8mb4 COMMENT='平台全局设置';

        INSERT INTO `system_platform_settings`
            (`ui_case_record_delete_mode`, `update_by`)
        SELECT 'logical', 'system'
        FROM DUAL
        WHERE NOT EXISTS (SELECT 1 FROM `system_platform_settings` LIMIT 1);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `system_platform_settings`;
    """
