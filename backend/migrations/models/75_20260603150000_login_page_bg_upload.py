from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `system_login_page_config`
            ADD COLUMN `pro_bg_url` VARCHAR(500) NOT NULL DEFAULT '' COMMENT 'Pro 自定义背景 URL' AFTER `classic_bg_key`,
            ADD COLUMN `classic_bg_url` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '经典自定义背景 URL' AFTER `pro_bg_url`;

        UPDATE `system_login_page_config`
        SET `pro_bg_key` = CASE `pro_bg_key`
                WHEN 'opt1' THEN 'pro1' WHEN 'opt2' THEN 'pro2'
                WHEN 'opt3' THEN 'pro3' WHEN 'opt4' THEN 'pro4' ELSE `pro_bg_key` END,
            `classic_bg_key` = CASE `classic_bg_key`
                WHEN 'classic' THEN 'legacy' WHEN 'opt1' THEN 'classic1'
                WHEN 'opt2' THEN 'classic2' WHEN 'opt3' THEN 'classic3'
                WHEN 'opt4' THEN 'classic4' ELSE `classic_bg_key` END
        WHERE 1=1;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `system_login_page_config`
            DROP COLUMN `pro_bg_url`,
            DROP COLUMN `classic_bg_url`;
    """
