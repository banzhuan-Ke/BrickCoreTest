from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ai_config` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `name` VARCHAR(100) NOT NULL DEFAULT '默认配置' COMMENT '配置名称',
            `provider` VARCHAR(20) NOT NULL COMMENT '供应商',
            `api_key` VARCHAR(255) NOT NULL COMMENT 'API Key（加密存储）',
            `api_base` VARCHAR(500) COMMENT '自定义 Base URL',
            `model` VARCHAR(100) NOT NULL DEFAULT 'gpt-4o' COMMENT '模型名称',
            `temperature` DOUBLE NOT NULL DEFAULT 0.7 COMMENT '温度(0-2)',
            `max_tokens` INT NOT NULL DEFAULT 4096 COMMENT '最大输出长度',
            `timeout` INT NOT NULL DEFAULT 60 COMMENT '请求超时(秒)',
            `is_default` BOOL NOT NULL DEFAULT 0 COMMENT '是否为默认配置',
            `is_enabled` BOOL NOT NULL DEFAULT 1 COMMENT '是否启用',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
            `create_by` VARCHAR(50) NOT NULL COMMENT '创建人'
        ) CHARACTER SET utf8mb4 COMMENT='AI LLM 配置';

        CREATE TABLE IF NOT EXISTS `ai_generate_record` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `generate_type` VARCHAR(30) NOT NULL COMMENT '生成类型',
            `input_summary` JSON NOT NULL COMMENT '输入摘要',
            `output_content` JSON NOT NULL COMMENT '生成结果',
            `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '状态: pending/imported/rejected',
            `imported_target_id` INT COMMENT '导入目标ID',
            `imported_target_type` VARCHAR(30) COMMENT '导入目标类型',
            `ai_config_id` INT COMMENT '使用的 AI 配置ID',
            `tokens_used` INT NOT NULL DEFAULT 0 COMMENT '消耗 Token 数',
            `duration_ms` INT NOT NULL DEFAULT 0 COMMENT '生成耗时(ms)',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
            `create_by` VARCHAR(50) NOT NULL COMMENT '创建人',
            `project_id` INT NOT NULL COMMENT '所属项目',
            CONSTRAINT `fk_ai_gener_project_8f267b75` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4 COMMENT='AI 生成历史记录';

        CREATE TABLE IF NOT EXISTS `ai_prompt_template` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `name` VARCHAR(100) NOT NULL COMMENT '模板名称',
            `code` VARCHAR(50) NOT NULL UNIQUE COMMENT '模板编码',
            `description` LONGTEXT COMMENT '模板描述',
            `scene_type` VARCHAR(30) NOT NULL COMMENT '场景类型',
            `system_prompt` LONGTEXT NOT NULL COMMENT 'System Prompt',
            `user_prompt_template` LONGTEXT NOT NULL COMMENT 'User Prompt 模板',
            `examples` JSON NOT NULL COMMENT 'Few-shot 示例',
            `version` INT NOT NULL DEFAULT 1 COMMENT '版本号',
            `is_default` BOOL NOT NULL DEFAULT 0 COMMENT '是否为默认模板',
            `is_enabled` BOOL NOT NULL DEFAULT 1 COMMENT '是否启用',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间'
        ) CHARACTER SET utf8mb4 COMMENT='AI Prompt 模板';

        CREATE TABLE IF NOT EXISTS `ai_requirement` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `name` VARCHAR(200) NOT NULL COMMENT '需求名称',
            `source_type` VARCHAR(20) NOT NULL DEFAULT 'text' COMMENT '来源: text/markdown/pdf/docx/url',
            `original_content` LONGTEXT NOT NULL COMMENT '原始需求文本内容',
            `parsed_content` JSON NOT NULL COMMENT '解析后的结构化内容',
            `generated_cases` JSON NOT NULL COMMENT '已生成的用例ID列表',
            `parse_status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '解析状态',
            `parse_error` LONGTEXT COMMENT '解析失败原因',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
            `create_by` VARCHAR(50) NOT NULL COMMENT '创建人',
            `project_id` INT NOT NULL COMMENT '所属项目',
            CONSTRAINT `fk_ai_requir_project_5e3a8c2b` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4 COMMENT='AI 需求文档';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ai_requirement`;
        DROP TABLE IF EXISTS `ai_prompt_template`;
        DROP TABLE IF EXISTS `ai_generate_record`;
        DROP TABLE IF EXISTS `ai_config`;
    """
