from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `case_review`
            ADD COLUMN `final_decision` VARCHAR(32) NULL COMMENT '版本负责人最终裁定 approved/changes_requested/rejected' AFTER `summary`,
            ADD COLUMN `final_decision_by` INT NULL COMMENT '最终裁定人用户 ID' AFTER `final_decision`,
            ADD COLUMN `final_decision_at` DATETIME(6) NULL COMMENT '最终裁定时间' AFTER `final_decision_by`,
            ADD COLUMN `final_comment` LONGTEXT NULL COMMENT '最终裁定说明' AFTER `final_decision_at`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `case_review`
            DROP COLUMN `final_comment`,
            DROP COLUMN `final_decision_at`,
            DROP COLUMN `final_decision_by`,
            DROP COLUMN `final_decision`;
    """
