from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ai_functional_case` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `product` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '所属产品',
            `module` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '所属模块',
            `related_story` LONGTEXT COMMENT '相关研发需求',
            `title` VARCHAR(500) NOT NULL COMMENT '用例标题',
            `naming_template_id` VARCHAR(50) COMMENT '标题模板ID',
            `naming_template_version` INT COMMENT '标题模板版本',
            `naming_slots` JSON NOT NULL COMMENT '标题槽位',
            `precondition` LONGTEXT COMMENT '前置条件',
            `steps` JSON NOT NULL COMMENT '步骤列表',
            `priority` VARCHAR(10) NOT NULL DEFAULT '2' COMMENT '优先级',
            `type` VARCHAR(50) NOT NULL DEFAULT '功能测试' COMMENT '用例类型',
            `stage` VARCHAR(50) NOT NULL DEFAULT '系统测试阶段' COMMENT '适用阶段',
            `keywords` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '关键词',
            `status` VARCHAR(20) NOT NULL DEFAULT 'confirmed' COMMENT '状态',
            `source_type` VARCHAR(30) NOT NULL DEFAULT 'manual' COMMENT '来源类型',
            `source_requirement_id` INT COMMENT '来源需求ID',
            `source_requirement_case_id` INT COMMENT '来源工作区用例ID',
            `source_import_batch` VARCHAR(64) COMMENT '导入批次',
            `source_file_name` VARCHAR(255) COMMENT '导入文件名',
            `extra` JSON NOT NULL COMMENT '扩展',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `create_by` VARCHAR(50) NOT NULL COMMENT '创建人',
            `project_id` INT NOT NULL COMMENT '所属项目',
            CONSTRAINT `fk_ai_func_case_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            KEY `idx_ai_func_case_proj_del` (`project_id`, `is_del`, `create_time`),
            KEY `idx_ai_func_case_title` (`project_id`, `title`(191))
        ) CHARACTER SET utf8mb4 COMMENT='功能测试用例库';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ai_functional_case`;
    """
