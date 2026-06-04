from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `api_auth_config` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `project_id` INT NOT NULL COMMENT '所属项目',
            `environment_id` INT NOT NULL COMMENT '生效环境',
            `name` VARCHAR(100) NOT NULL COMMENT '授权名称',
            `auth_type` VARCHAR(20) NOT NULL DEFAULT 'api_login' COMMENT 'api_login/custom_code',
            `login_api_id` INT NULL COMMENT '登录接口定义ID',
            `extractors` JSON NOT NULL COMMENT '登录响应变量提取规则',
            `custom_code` LONGTEXT NULL COMMENT '自定义授权代码',
            `ttl_minutes` INT NOT NULL DEFAULT 1440 COMMENT '缓存有效期(分钟)',
            `refresh_before_minutes` INT NOT NULL DEFAULT 5 COMMENT '提前刷新(分钟)',
            `refresh_mode` VARCHAR(30) NOT NULL DEFAULT 'on_execute' COMMENT 'on_execute',
            `is_enabled` BOOL NOT NULL DEFAULT 1 COMMENT '是否启用',
            `cache_data` JSON NOT NULL COMMENT '当前授权缓存',
            `cache_expires_at` DATETIME(6) NULL COMMENT '缓存过期时间',
            `last_refresh_time` DATETIME(6) NULL COMMENT '最近刷新时间',
            `last_refresh_error` LONGTEXT NULL COMMENT '最近刷新错误',
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_api_auth_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_api_auth_env` FOREIGN KEY (`environment_id`) REFERENCES `environment` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_api_auth_login_api` FOREIGN KEY (`login_api_id`) REFERENCES `api_definition` (`id`) ON DELETE SET NULL,
            UNIQUE KEY `uk_api_auth_project_env_name` (`project_id`, `environment_id`, `name`)
        ) CHARACTER SET utf8mb4 COMMENT='API Token 授权配置';
        CREATE INDEX `idx_api_auth_project_env` ON `api_auth_config` (`project_id`, `environment_id`, `is_enabled`, `is_del`);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `api_auth_config`;
    """
