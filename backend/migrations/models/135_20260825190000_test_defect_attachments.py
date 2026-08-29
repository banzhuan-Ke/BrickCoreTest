from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `test_defect`
            ADD COLUMN `attachments` JSON NULL COMMENT '附件列表' AFTER `external_url`;
        UPDATE `test_defect` SET `attachments` = JSON_ARRAY() WHERE `attachments` IS NULL;
        ALTER TABLE `test_defect`
            MODIFY COLUMN `attachments` JSON NOT NULL COMMENT '附件列表';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `test_defect` DROP COLUMN `attachments`;
    """
