from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `api_test_case`
            ADD COLUMN `pre_script`  TEXT NULL COMMENT '前置脚本（Python，请求前执行）',
            ADD COLUMN `post_script` TEXT NULL COMMENT '后置脚本（Python，请求后执行）',
            ADD COLUMN `data_set`    JSON NOT NULL DEFAULT (JSON_ARRAY()) COMMENT '数据集，格式: [{col1:v1, col2:v2}, ...]';
        ALTER TABLE `api_run_record`
            ADD COLUMN `data_run_index` INT NULL COMMENT '数据驱动第几轮（0-based），null 表示非数据驱动',
            ADD COLUMN `data_row_label` VARCHAR(200) NULL COMMENT '本轮数据摘要（用于展示）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `api_test_case`
            DROP COLUMN `pre_script`,
            DROP COLUMN `post_script`,
            DROP COLUMN `data_set`;
        ALTER TABLE `api_run_record`
            DROP COLUMN `data_run_index`,
            DROP COLUMN `data_row_label`;
    """
