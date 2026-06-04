from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `notification_config`
    ADD COLUMN `api_auto_push_report` BOOL NOT NULL COMMENT 'API套件执行成功后自动推送报告' DEFAULT 0,
    ADD COLUMN `ui_auto_push_report` BOOL NOT NULL COMMENT 'UI计划执行成功后自动推送报告' DEFAULT 0;

UPDATE `notification_config` SET
    `api_auto_push_report` = `auto_push_report`,
    `ui_auto_push_report` = `auto_push_report`;

CREATE TABLE IF NOT EXISTS `notification_log` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '记录ID',
    `channel_type` VARCHAR(20) NOT NULL COMMENT '通知渠道: email/dingtalk/wechat',
    `notify_type` VARCHAR(20) NOT NULL COMMENT '通知类型: alert/report',
    `title` VARCHAR(255) NOT NULL COMMENT '消息标题',
    `content_summary` JSON NOT NULL COMMENT '内容摘要',
    `recipients` JSON NOT NULL COMMENT '接收人列表',
    `status` VARCHAR(20) NOT NULL COMMENT '推送状态: success/failed',
    `error_msg` LONGTEXT NOT NULL COMMENT '失败原因',
    `related_id` INT COMMENT '关联记录ID',
    `related_type` VARCHAR(50) NOT NULL COMMENT '关联类型' DEFAULT '',
    `create_time` DATETIME(6) NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP(6),
    `project_id` INT COMMENT '所属项目',
    CONSTRAINT `fk_notiflog_project_12345678` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE SET NULL
) CHARACTER SET utf8mb4 COMMENT='通知推送记录';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `notification_config`
    DROP COLUMN `api_auto_push_report`,
    DROP COLUMN `ui_auto_push_report`;

DROP TABLE IF EXISTS `notification_log`;
    """
