from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ai_requirement_case` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `module` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '所属模块',
            `title` VARCHAR(500) NOT NULL COMMENT '用例标题',
            `precondition` LONGTEXT COMMENT '前置条件',
            `steps` JSON NOT NULL COMMENT '步骤列表',
            `priority` VARCHAR(10) NOT NULL DEFAULT '2' COMMENT '优先级',
            `type` VARCHAR(50) NOT NULL DEFAULT '功能测试' COMMENT '用例类型',
            `keywords` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '关键词',
            `status` VARCHAR(20) NOT NULL DEFAULT 'draft' COMMENT '状态',
            `source_ref` VARCHAR(200) COMMENT '来源引用',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `create_by` VARCHAR(50) NOT NULL COMMENT '创建人',
            `project_id` INT NOT NULL COMMENT '所属项目',
            `requirement_id` INT NOT NULL COMMENT '所属需求',
            CONSTRAINT `fk_ai_req_case_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_ai_req_case_requirement` FOREIGN KEY (`requirement_id`) REFERENCES `ai_requirement` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4 COMMENT='AI 需求功能测试用例';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ai_requirement_case`;
    """
