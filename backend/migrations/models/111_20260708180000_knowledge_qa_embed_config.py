from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ai_embed_config` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `name` VARCHAR(100) NOT NULL DEFAULT '默认 Embedding' COMMENT '配置名称',
            `provider` VARCHAR(20) NOT NULL COMMENT '供应商',
            `api_key` VARCHAR(255) NOT NULL COMMENT 'API Key（加密）',
            `api_base` VARCHAR(500) NULL COMMENT '自定义 Base URL',
            `model` VARCHAR(100) NOT NULL DEFAULT 'text-embedding-v3' COMMENT 'Embedding 模型',
            `timeout` INT NOT NULL DEFAULT 120 COMMENT '请求超时(秒)',
            `is_default` BOOL NOT NULL DEFAULT 0 COMMENT '是否默认',
            `is_enabled` BOOL NOT NULL DEFAULT 1 COMMENT '是否启用',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '逻辑删除',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `create_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '创建人'
        ) CHARACTER SET utf8mb4 COMMENT='Embedding 模型配置';

        CREATE TABLE IF NOT EXISTS `ai_knowledge_qa_record` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '项目ID',
            `username` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '提问人',
            `mode` VARCHAR(20) NOT NULL DEFAULT 'retrieve' COMMENT 'retrieve|smart',
            `query` VARCHAR(500) NOT NULL COMMENT '问题',
            `answer` LONGTEXT NULL COMMENT '智能模式回答',
            `strategy` VARCHAR(20) NOT NULL DEFAULT 'none' COMMENT '检索策略',
            `folder_ids` JSON NOT NULL COMMENT '限定文件夹',
            `document_ids` JSON NOT NULL COMMENT '限定文档',
            `top_k` INT NOT NULL DEFAULT 12 COMMENT '返回条数',
            `hit_count` INT NOT NULL DEFAULT 0 COMMENT '命中分块数',
            `doc_count` INT NOT NULL DEFAULT 0 COMMENT '涉及文档数',
            `tokens_used` INT NOT NULL DEFAULT 0 COMMENT 'Token消耗',
            `duration_ms` INT NOT NULL DEFAULT 0 COMMENT '耗时ms',
            `sources_json` JSON NOT NULL COMMENT '引用来源摘要',
            `result_json` JSON NOT NULL COMMENT '完整结果快照',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '逻辑删除',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            KEY `idx_kqa_project_time` (`project_id`, `create_time`),
            KEY `idx_kqa_project_user` (`project_id`, `username`)
        ) CHARACTER SET utf8mb4 COMMENT='资料库问答历史';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ai_knowledge_qa_record`;
        DROP TABLE IF EXISTS `ai_embed_config`;
    """
