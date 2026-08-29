from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `test_release` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `release_key` VARCHAR(64) NOT NULL COMMENT '项目内版本键',
            `name` VARCHAR(200) NOT NULL COMMENT '版本名称',
            `description` LONGTEXT NULL COMMENT '说明',
            `status` VARCHAR(32) NOT NULL DEFAULT 'draft' COMMENT '状态',
            `owner_id` INT NULL COMMENT '测试负责人',
            `planned_start_at` DATETIME(6) NULL COMMENT '计划开始',
            `planned_release_at` DATETIME(6) NULL COMMENT '计划发布',
            `actual_release_at` DATETIME(6) NULL COMMENT '实际发布',
            `external_url` VARCHAR(500) NULL COMMENT '外部链接',
            `quality_status` VARCHAR(32) NULL COMMENT '质量判定冗余',
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL,
            CONSTRAINT `fk_test_release_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            KEY `idx_test_release_proj_del` (`project_id`, `is_del`, `create_time`),
            KEY `idx_test_release_key` (`project_id`, `release_key`, `is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='测试管理-版本';

        CREATE TABLE IF NOT EXISTS `test_release_requirement` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `requirement_key` VARCHAR(128) NOT NULL COMMENT '外部需求编号',
            `title` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '标题',
            `url` VARCHAR(500) NULL COMMENT '外部链接',
            `note` LONGTEXT NULL COMMENT '备注',
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL,
            `release_id` INT NOT NULL,
            CONSTRAINT `fk_test_rel_req_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_test_rel_req_release` FOREIGN KEY (`release_id`) REFERENCES `test_release` (`id`) ON DELETE CASCADE,
            KEY `idx_test_rel_req_release` (`release_id`, `is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='测试管理-版本需求';

        CREATE TABLE IF NOT EXISTS `test_release_scope` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `functional_case_id` INT NOT NULL COMMENT '功能用例库ID',
            `scope_status` VARCHAR(32) NOT NULL DEFAULT 'planned' COMMENT '范围状态',
            `risk_level` VARCHAR(32) NOT NULL DEFAULT 'medium' COMMENT '风险',
            `requirement_key` VARCHAR(128) NULL COMMENT '需求编号冗余',
            `automation_status` VARCHAR(32) NOT NULL DEFAULT 'none' COMMENT '自动化覆盖',
            `owner_id` INT NULL COMMENT '负责人',
            `note` LONGTEXT NULL COMMENT '说明',
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL,
            `release_id` INT NOT NULL,
            CONSTRAINT `fk_test_scope_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_test_scope_release` FOREIGN KEY (`release_id`) REFERENCES `test_release` (`id`) ON DELETE CASCADE,
            KEY `idx_test_scope_release` (`release_id`, `is_del`),
            KEY `idx_test_scope_case` (`release_id`, `functional_case_id`, `is_del`),
            KEY `idx_test_scope_proj_case` (`project_id`, `functional_case_id`, `is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='测试管理-版本范围';

        CREATE TABLE IF NOT EXISTS `test_asset_link` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `functional_case_id` INT NOT NULL COMMENT '功能用例库ID',
            `asset_type` VARCHAR(32) NOT NULL COMMENT '资产类型',
            `asset_id` INT NOT NULL COMMENT '资产主键',
            `link_type` VARCHAR(32) NOT NULL DEFAULT 'primary' COMMENT '映射用途',
            `coverage_note` LONGTEXT NULL COMMENT '覆盖说明',
            `health_status` VARCHAR(32) NOT NULL DEFAULT 'unknown' COMMENT '健康度',
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL,
            CONSTRAINT `fk_test_asset_link_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            KEY `idx_test_asset_link_case` (`project_id`, `functional_case_id`, `is_del`),
            KEY `idx_test_asset_link_uniq` (`functional_case_id`, `asset_type`, `asset_id`, `is_del`),
            KEY `idx_test_asset_link_asset` (`asset_type`, `asset_id`, `is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='测试管理-资产映射';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `test_asset_link`;
        DROP TABLE IF EXISTS `test_release_scope`;
        DROP TABLE IF EXISTS `test_release_requirement`;
        DROP TABLE IF EXISTS `test_release`;
    """
