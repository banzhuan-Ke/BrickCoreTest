from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_requirement_case`
            ADD COLUMN `naming_template_id` VARCHAR(50) NULL COMMENT '标题模板ID',
            ADD COLUMN `naming_template_version` INT NULL COMMENT '标题模板版本',
            ADD COLUMN `naming_slots` JSON NOT NULL DEFAULT (JSON_OBJECT()) COMMENT '标题语义槽位快照';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_requirement_case`
            DROP COLUMN `naming_template_id`,
            DROP COLUMN `naming_template_version`,
            DROP COLUMN `naming_slots`;
    """
