from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ai_vision_image_cache` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '项目ID',
            `image_hash` VARCHAR(64) NOT NULL COMMENT '图片内容 SHA256',
            `scene` VARCHAR(64) NOT NULL COMMENT '读图场景/Prompt',
            `model` VARCHAR(100) NOT NULL COMMENT 'Vision 模型名',
            `vision_text` LONGTEXT NOT NULL COMMENT '读图结果文本',
            `raw_content` LONGTEXT NULL COMMENT '模型原始输出',
            `tokens_used` INT NOT NULL DEFAULT 0 COMMENT '首次识图 Token 消耗',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            UNIQUE KEY `uid_ai_vision_cache_proj_hash_scene_model` (`project_id`, `image_hash`, `scene`, `model`),
            KEY `idx_ai_vision_cache_project_id` (`project_id`)
        ) CHARACTER SET utf8mb4 COMMENT='Vision 读图结果缓存';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ai_vision_image_cache`;
    """
