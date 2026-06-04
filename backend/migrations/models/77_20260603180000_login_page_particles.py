from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `system_login_page_config`
            ADD COLUMN `bg_brick_count` INT NOT NULL DEFAULT 30 COMMENT '登录页漂浮积木数量' AFTER `show_register`,
            ADD COLUMN `bg_star_count` INT NOT NULL DEFAULT 15 COMMENT '登录页四角星数量' AFTER `bg_brick_count`,
            ADD COLUMN `bg_dot_count` INT NOT NULL DEFAULT 15 COMMENT '登录页半透明光点数量' AFTER `bg_star_count`,
            ADD COLUMN `bg_motion_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用登录页漂浮动效' AFTER `bg_dot_count`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `system_login_page_config`
            DROP COLUMN `bg_brick_count`,
            DROP COLUMN `bg_star_count`,
            DROP COLUMN `bg_dot_count`,
            DROP COLUMN `bg_motion_enabled`;
    """
