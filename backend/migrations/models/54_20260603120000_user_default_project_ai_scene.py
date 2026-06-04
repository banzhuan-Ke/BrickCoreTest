from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `user`
            ADD COLUMN `default_project_id` INT NULL COMMENT '登录后默认项目';

        CREATE TABLE IF NOT EXISTS `ai_scene_binding` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `scene` VARCHAR(64) NOT NULL UNIQUE COMMENT '场景编码',
            `config_id` INT NULL COMMENT '绑定的 ai_config.id',
            `update_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '最后修改人',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
        ) CHARACTER SET utf8mb4 COMMENT='AI 场景模型绑定';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ai_scene_binding`;
        ALTER TABLE `user` DROP COLUMN `default_project_id`;
    """
