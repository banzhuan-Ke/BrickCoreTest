from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `role` ADD COLUMN `code` VARCHAR(50) NULL UNIQUE COMMENT '角色唯一标识';
        ALTER TABLE `role` ADD COLUMN `is_system` BOOL NOT NULL DEFAULT 0 COMMENT '是否系统预置角色';
        CREATE TABLE IF NOT EXISTS `invite_code` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '邀请码ID',
            `code` VARCHAR(32) NOT NULL UNIQUE COMMENT '邀请码',
            `role_ids` JSON NOT NULL COMMENT '注册后绑定的角色ID列表',
            `max_uses` INT NOT NULL DEFAULT 1 COMMENT '最大可用次数',
            `used_count` INT NOT NULL DEFAULT 0 COMMENT '已使用次数',
            `expires_at` DATETIME(6) NULL COMMENT '过期时间',
            `note` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '备注',
            `created_by_id` INT NULL COMMENT '创建人ID',
            `created_by_username` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '创建人用户名',
            `is_active` BOOL NOT NULL DEFAULT 1 COMMENT '是否启用',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除'
        ) CHARACTER SET utf8mb4 COMMENT='注册邀请码';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `invite_code`;
        ALTER TABLE `role` DROP COLUMN `is_system`;
        ALTER TABLE `role` DROP COLUMN `code`;
    """
