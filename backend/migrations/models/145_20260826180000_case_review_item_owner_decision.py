from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `case_review_item`
            ADD COLUMN `owner_decision` VARCHAR(32) NULL COMMENT '版本负责人单条裁定',
            ADD COLUMN `owner_decision_by` INT NULL COMMENT '单条裁定人',
            ADD COLUMN `owner_decision_at` DATETIME(6) NULL COMMENT '单条裁定时间',
            ADD COLUMN `owner_comment` LONGTEXT NULL COMMENT '单条裁定说明';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `case_review_item`
            DROP COLUMN `owner_decision`,
            DROP COLUMN `owner_decision_by`,
            DROP COLUMN `owner_decision_at`,
            DROP COLUMN `owner_comment`;
    """
