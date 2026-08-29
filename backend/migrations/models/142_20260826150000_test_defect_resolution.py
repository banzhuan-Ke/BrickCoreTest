"""缺陷处理方案 / 当前处理人 / 根因"""
from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `test_defect`
            ADD COLUMN `handler_id` INT NULL COMMENT '当前处理人' AFTER `reporter_id`,
            ADD COLUMN `resolution_type` VARCHAR(32) NULL COMMENT '处理方案类型' AFTER `external_url`,
            ADD COLUMN `resolution_detail` TEXT NULL COMMENT '处理说明' AFTER `resolution_type`,
            ADD COLUMN `root_cause` TEXT NULL COMMENT '产生原因' AFTER `resolution_detail`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `test_defect`
            DROP COLUMN `handler_id`,
            DROP COLUMN `resolution_type`,
            DROP COLUMN `resolution_detail`,
            DROP COLUMN `root_cause`;
    """
