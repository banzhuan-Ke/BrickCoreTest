from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE `system_login_page_config`
        SET `pro_bg_key` = CASE `pro_bg_key`
                WHEN 'pro1' THEN 'opt1' WHEN 'pro2' THEN 'opt2'
                WHEN 'pro3' THEN 'opt3' WHEN 'pro4' THEN 'opt4'
                WHEN 'opt1' THEN 'opt1' WHEN 'opt2' THEN 'opt2'
                WHEN 'opt3' THEN 'opt3' WHEN 'opt4' THEN 'opt4'
                ELSE 'opt3' END
        WHERE 1=1;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE `system_login_page_config`
        SET `pro_bg_key` = CASE `pro_bg_key`
                WHEN 'opt1' THEN 'pro1' WHEN 'opt2' THEN 'pro2'
                WHEN 'opt3' THEN 'pro3' WHEN 'opt4' THEN 'pro4'
                ELSE `pro_bg_key` END
        WHERE 1=1;
    """
