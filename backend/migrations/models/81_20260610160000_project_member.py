from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `project_member` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '成员记录ID',
            `role` VARCHAR(20) NOT NULL DEFAULT 'member' COMMENT '项目角色',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `is_del` BOOL NOT NULL DEFAULT 0,
            `invited_by_id` INT NULL,
            `project_id` INT NOT NULL,
            `user_id` INT NOT NULL,
            CONSTRAINT `fk_pm_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_pm_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_pm_invited_by` FOREIGN KEY (`invited_by_id`) REFERENCES `user` (`id`) ON DELETE SET NULL,
            UNIQUE KEY `uidx_project_member` (`project_id`, `user_id`)
        ) CHARACTER SET utf8mb4 COMMENT='项目成员';
        INSERT INTO `project_member` (`project_id`, `user_id`, `role`, `invited_by_id`, `is_del`)
        SELECT p.`id`, p.`user_id`, 'owner', p.`user_id`, 0
        FROM `project` p
        WHERE p.`is_del` = 0
          AND NOT EXISTS (
            SELECT 1 FROM `project_member` pm
            WHERE pm.`project_id` = p.`id` AND pm.`user_id` = p.`user_id` AND pm.`is_del` = 0
          );
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `project_member`;
    """
