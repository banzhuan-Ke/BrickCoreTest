from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `platform_doc`
            ADD COLUMN `builtin_id` VARCHAR(64) NULL COMMENT '内置文档/分组 ID 覆盖',
            ADD COLUMN `is_hidden` BOOL NOT NULL DEFAULT 0 COMMENT '隐藏内置条目';
        CREATE UNIQUE INDEX `idx_platform_doc_builtin_id` ON `platform_doc` (`builtin_id`);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX `idx_platform_doc_builtin_id` ON `platform_doc`;
        ALTER TABLE `platform_doc`
            DROP COLUMN `is_hidden`,
            DROP COLUMN `builtin_id`;
    """
