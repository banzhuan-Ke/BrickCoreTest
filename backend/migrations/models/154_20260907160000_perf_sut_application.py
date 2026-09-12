from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `sut_application` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '所属项目',
            `name` VARCHAR(100) NOT NULL COMMENT '应用名称',
            `roles_json` JSON NOT NULL COMMENT '角色清单',
            `remark` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '备注',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `create_by` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '创建人',
            KEY `idx_sut_app_project` (`project_id`),
            KEY `idx_sut_app_del` (`is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='被测应用';

        CREATE TABLE IF NOT EXISTS `sut_app_env_binding` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `application_id` INT NOT NULL COMMENT '被测应用',
            `environment_id` INT NOT NULL COMMENT '环境',
            `bindings_json` JSON NOT NULL COMMENT '角色→服务器',
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            UNIQUE KEY `uid_sut_app_env` (`application_id`, `environment_id`),
            KEY `idx_sut_app_env_env` (`environment_id`)
        ) CHARACTER SET utf8mb4 COMMENT='被测应用环境绑定';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `sut_app_env_binding`;
        DROP TABLE IF EXISTS `sut_application`;
    """
