from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `system_runner_release_config` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `external_download_url` VARCHAR(1000) NOT NULL DEFAULT '' COMMENT '执行器安装包外链（网盘/OSS）',
            `external_download_label` VARCHAR(100) NOT NULL DEFAULT '网盘下载' COMMENT '外链按钮文案',
            `update_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '最后修改人',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
        ) CHARACTER SET utf8mb4 COMMENT='执行器客户端发布配置';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `system_runner_release_config`;
    """
