from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `user_notification_preference` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `user_id` INT NOT NULL UNIQUE,
            `inbox_enabled` BOOL NOT NULL DEFAULT 1 COMMENT '是否接收站内信',
            `external_enabled` BOOL NOT NULL DEFAULT 1 COMMENT '是否接收外发',
            `im_at_enabled` BOOL NOT NULL DEFAULT 1 COMMENT 'IM 是否 @ 本人手机号',
            `muted_events` JSON NULL COMMENT '静音事件类型列表',
            `dnd_enabled` BOOL NOT NULL DEFAULT 0 COMMENT '免打扰开关',
            `dnd_start` VARCHAR(8) NOT NULL DEFAULT '22:00' COMMENT '免打扰开始 HH:MM',
            `dnd_end` VARCHAR(8) NOT NULL DEFAULT '08:00' COMMENT '免打扰结束 HH:MM',
            `dnd_mute_inbox` BOOL NOT NULL DEFAULT 0 COMMENT '免打扰期间是否也屏蔽站内信',
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_user_notify_pref_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `user_notification_preference`;
    """
