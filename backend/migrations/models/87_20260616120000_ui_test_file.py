from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ui_test_file` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '所属项目',
            `file_name` VARCHAR(255) NOT NULL COMMENT '原始文件名',
            `file_key` VARCHAR(500) NOT NULL COMMENT 'MinIO 对象键',
            `file_bucket` VARCHAR(100) NOT NULL COMMENT 'MinIO bucket',
            `mime_type` VARCHAR(128) NOT NULL DEFAULT 'application/octet-stream' COMMENT 'MIME 类型',
            `size` INT NOT NULL DEFAULT 0 COMMENT '文件大小（字节）',
            `username` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '上传人',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_ui_test_file_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            KEY `idx_ui_test_file_project` (`project_id`),
            KEY `idx_ui_test_file_key` (`file_key`(191))
        ) CHARACTER SET utf8mb4 COMMENT='UI自动化测试文件';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ui_test_file`;
    """
