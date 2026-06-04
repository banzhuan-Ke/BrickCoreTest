from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `platform_doc` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `title` VARCHAR(200) NOT NULL COMMENT '标题',
            `parent_id` INT NULL COMMENT '父级ID',
            `doc_type` VARCHAR(20) NOT NULL DEFAULT 'markdown' COMMENT 'markdown/video/file/link',
            `content` LONGTEXT NULL COMMENT 'Markdown正文',
            `file_key` VARCHAR(500) NULL COMMENT 'MinIO对象键',
            `link_url` VARCHAR(1000) NULL COMMENT '外部链接',
            `sort_order` INT NOT NULL DEFAULT 0 COMMENT '排序',
            `is_published` BOOL NOT NULL DEFAULT 1 COMMENT '是否发布',
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            INDEX `idx_platform_doc_parent` (`parent_id`, `is_del`, `sort_order`)
        ) CHARACTER SET utf8mb4 COMMENT='平台文档中心';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `platform_doc`;
    """
