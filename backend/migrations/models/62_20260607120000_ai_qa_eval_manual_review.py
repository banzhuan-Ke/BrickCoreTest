from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_qa_eval_result`
            ADD COLUMN `manual_status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '人工审核: pending/approved/rejected' AFTER `status`,
            ADD COLUMN `manual_comment` TEXT NULL COMMENT '人工审核备注' AFTER `manual_status`,
            ADD COLUMN `manual_reviewed_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '审核人' AFTER `manual_comment`,
            ADD COLUMN `manual_reviewed_at` DATETIME NULL COMMENT '审核时间' AFTER `manual_reviewed_by`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_qa_eval_result`
            DROP COLUMN `manual_reviewed_at`,
            DROP COLUMN `manual_reviewed_by`,
            DROP COLUMN `manual_comment`,
            DROP COLUMN `manual_status`;
    """
