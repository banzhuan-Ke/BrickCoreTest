from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_iteration_report`
            ADD COLUMN `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '逻辑删除' AFTER `update_time`;
        ALTER TABLE `system_platform_settings`
            ADD COLUMN `knowledge_report_delete_mode` VARCHAR(20) NOT NULL DEFAULT 'logical'
            COMMENT '资料库生成记录删除模式：logical|physical' AFTER `ui_case_record_delete_mode`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_iteration_report` DROP COLUMN `is_del`;
        ALTER TABLE `system_platform_settings` DROP COLUMN `knowledge_report_delete_mode`;
    """
