from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `system_login_page_config` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `pro_bg_key` VARCHAR(20) NOT NULL DEFAULT 'opt3' COMMENT '清新 Pro 背景方案',
            `classic_bg_key` VARCHAR(20) NOT NULL DEFAULT 'classic' COMMENT '经典风格背景方案',
            `welcome_title` VARCHAR(200) NOT NULL DEFAULT '欢迎登录 BrickCore' COMMENT '登录页标题',
            `footer_text` VARCHAR(500) NOT NULL DEFAULT '© 2025-2026 BrickCore. All Rights Reserved.' COMMENT '页脚文案',
            `show_register` BOOL NOT NULL DEFAULT 1 COMMENT '是否显示注册入口',
            `update_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '最后修改人',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
        ) CHARACTER SET utf8mb4 COMMENT='登录页配置';

        INSERT INTO `system_login_page_config`
            (`pro_bg_key`, `classic_bg_key`, `welcome_title`, `footer_text`, `show_register`, `update_by`)
        SELECT 'opt3', 'classic', '欢迎登录 BrickCore', '© 2025-2026 BrickCore. All Rights Reserved.', 1, 'system'
        FROM DUAL
        WHERE NOT EXISTS (SELECT 1 FROM `system_login_page_config` LIMIT 1);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `system_login_page_config`;
    """
