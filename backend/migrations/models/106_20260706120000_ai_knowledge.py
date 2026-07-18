from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ai_knowledge_folder` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '项目ID',
            `name` VARCHAR(100) NOT NULL COMMENT '文件夹名称',
            `description` LONGTEXT NULL COMMENT '说明',
            `iteration_label` VARCHAR(50) NULL COMMENT '迭代标签',
            `date_start` DATE NULL COMMENT '迭代开始',
            `date_end` DATE NULL COMMENT '迭代结束',
            `sort` INT NOT NULL DEFAULT 0 COMMENT '排序',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '逻辑删除',
            `created_by` VARCHAR(50) NULL COMMENT '创建人',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_ai_knowledge_folder_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            INDEX `idx_ai_knowledge_folder_project` (`project_id`, `is_del`, `sort`)
        ) CHARACTER SET utf8mb4 COMMENT='迭代测试资料库-文件夹';

        CREATE TABLE IF NOT EXISTS `ai_knowledge_document` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '项目ID',
            `folder_id` INT NULL COMMENT '文件夹ID',
            `title` VARCHAR(200) NOT NULL COMMENT '标题',
            `doc_type` VARCHAR(32) NOT NULL COMMENT '文档类型',
            `file_name` VARCHAR(255) NOT NULL COMMENT '原始文件名',
            `storage` JSON NOT NULL COMMENT '存储元数据',
            `parse_status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '解析状态',
            `parse_error` LONGTEXT NULL COMMENT '解析错误',
            `char_count` INT NOT NULL DEFAULT 0 COMMENT '字符数',
            `chunk_count` INT NOT NULL DEFAULT 0 COMMENT '分块数',
            `sections_json` JSON NULL COMMENT '章节结构',
            `source_requirement_id` INT NULL COMMENT '来源需求ID',
            `embed_status` VARCHAR(20) NOT NULL DEFAULT 'none' COMMENT '向量索引状态',
            `template_schema` JSON NULL COMMENT '模板占位符',
            `is_default_template` BOOL NOT NULL DEFAULT 0 COMMENT '默认输出模板',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '逻辑删除',
            `created_by` VARCHAR(50) NULL COMMENT '创建人',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_ai_knowledge_doc_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_ai_knowledge_doc_folder` FOREIGN KEY (`folder_id`) REFERENCES `ai_knowledge_folder` (`id`) ON DELETE SET NULL,
            INDEX `idx_ai_knowledge_doc_project` (`project_id`, `is_del`, `doc_type`),
            INDEX `idx_ai_knowledge_doc_folder` (`folder_id`, `is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='迭代测试资料库-文档';

        CREATE TABLE IF NOT EXISTS `ai_knowledge_chunk` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `document_id` INT NOT NULL COMMENT '文档ID',
            `project_id` INT NOT NULL COMMENT '项目ID',
            `chunk_index` INT NOT NULL COMMENT '分块序号',
            `section_title` VARCHAR(200) NULL COMMENT '章节标题',
            `chunk_text` LONGTEXT NOT NULL COMMENT '分块文本',
            `char_count` INT NOT NULL DEFAULT 0 COMMENT '字符数',
            `embedding` JSON NULL COMMENT '向量',
            `embedding_model` VARCHAR(80) NULL COMMENT 'Embedding模型',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_ai_knowledge_chunk_doc` FOREIGN KEY (`document_id`) REFERENCES `ai_knowledge_document` (`id`) ON DELETE CASCADE,
            INDEX `idx_ai_knowledge_chunk_project` (`project_id`, `document_id`)
        ) CHARACTER SET utf8mb4 COMMENT='迭代测试资料库-分块';

        CREATE TABLE IF NOT EXISTS `ai_iteration_report` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '项目ID',
            `folder_id` INT NULL COMMENT '文件夹ID',
            `title` VARCHAR(200) NOT NULL COMMENT '标题',
            `report_kind` VARCHAR(32) NOT NULL DEFAULT 'iteration_report' COMMENT '报告类型',
            `config_json` JSON NOT NULL COMMENT '生成配置',
            `content_md` LONGTEXT NULL COMMENT 'Markdown',
            `file_path` VARCHAR(500) NULL COMMENT '输出路径',
            `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '状态',
            `ai_usage_tokens` INT NOT NULL DEFAULT 0 COMMENT 'Token',
            `created_by` VARCHAR(50) NULL COMMENT '创建人',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_ai_iteration_report_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_ai_iteration_report_folder` FOREIGN KEY (`folder_id`) REFERENCES `ai_knowledge_folder` (`id`) ON DELETE SET NULL,
            INDEX `idx_ai_iteration_report_project` (`project_id`, `create_time`)
        ) CHARACTER SET utf8mb4 COMMENT='迭代测试资料库-生成记录';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ai_iteration_report`;
        DROP TABLE IF EXISTS `ai_knowledge_chunk`;
        DROP TABLE IF EXISTS `ai_knowledge_document`;
        DROP TABLE IF EXISTS `ai_knowledge_folder`;
    """
