from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_requirement_case`
            ADD COLUMN `product` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '所属产品' AFTER `project_id`,
            ADD COLUMN `related_story` LONGTEXT NULL COMMENT '相关研发需求' AFTER `module`,
            ADD COLUMN `stage` VARCHAR(50) NOT NULL DEFAULT '系统测试阶段' COMMENT '适用阶段' AFTER `type`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_requirement_case`
            DROP COLUMN `product`,
            DROP COLUMN `related_story`,
            DROP COLUMN `stage`;
    """
