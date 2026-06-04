from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `api_test_plan` (
            `id`          INT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '计划ID',
            `name`        VARCHAR(100) NOT NULL COMMENT '计划名称',
            `project_id`  INT NOT NULL COMMENT '所属项目ID',
            `description` LONGTEXT NULL COMMENT '计划描述',
            `env_id`      INT NULL COMMENT '默认执行环境ID',
            `variables`   JSON NOT NULL COMMENT '计划级全局变量',
            `is_del`      BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            `create_by`   VARCHAR(50) NOT NULL COMMENT '创建人',
            `update_by`   VARCHAR(50) NULL COMMENT '修改人',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
            CONSTRAINT `fk_api_test_plan_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='接口测试计划';

        CREATE TABLE IF NOT EXISTS `api_plan_item` (
            `id`        INT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
            `plan_id`   INT NOT NULL COMMENT '所属计划ID',
            `item_type` VARCHAR(10) NOT NULL COMMENT '类型 suite/case',
            `suite_id`  INT NULL COMMENT '关联套件ID',
            `case_id`   INT NULL COMMENT '关联用例ID',
            `sort`      INT NOT NULL DEFAULT 0 COMMENT '排序',
            CONSTRAINT `fk_api_plan_item_plan`  FOREIGN KEY (`plan_id`)  REFERENCES `api_test_plan` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_api_plan_item_suite` FOREIGN KEY (`suite_id`) REFERENCES `api_test_suite` (`id`) ON DELETE SET NULL,
            CONSTRAINT `fk_api_plan_item_case`  FOREIGN KEY (`case_id`)  REFERENCES `api_test_case` (`id`)  ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='测试计划内容项';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `api_plan_item`;
        DROP TABLE IF EXISTS `api_test_plan`;
    """
