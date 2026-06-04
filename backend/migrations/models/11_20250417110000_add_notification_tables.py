from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `notification_config` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '配置ID',
    `channel_type` VARCHAR(20) NOT NULL COMMENT '通知渠道: email/dingtalk/wechat',
    `enabled` BOOL NOT NULL COMMENT '是否启用' DEFAULT 1,
    `config` JSON NOT NULL COMMENT '渠道参数',
    `auto_push_report` BOOL NOT NULL COMMENT '是否自动推送报告' DEFAULT 0,
    `create_time` DATETIME(6) NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL COMMENT '更新时间' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `project_id` INT NOT NULL COMMENT '所属项目',
    CONSTRAINT `fk_notifica_project_4c4a4a4a` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='项目通知配置';

CREATE TABLE IF NOT EXISTS `system_smtp_config` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '配置ID',
    `host` VARCHAR(255) NOT NULL COMMENT 'SMTP服务器',
    `port` INT NOT NULL COMMENT '端口',
    `username` VARCHAR(255) NOT NULL COMMENT '发件账号',
    `password` VARCHAR(255) NOT NULL COMMENT '密码/授权码',
    `use_tls` BOOL NOT NULL COMMENT '是否启用TLS/SSL' DEFAULT 1,
    `sender` VARCHAR(255) NOT NULL COMMENT '发件人显示名称',
    `create_time` DATETIME(6) NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL COMMENT '更新时间' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4 COMMENT='全局SMTP配置';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `notification_config`;
        DROP TABLE IF EXISTS `system_smtp_config`;
    """
