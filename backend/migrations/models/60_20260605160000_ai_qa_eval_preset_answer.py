from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_qa_eval_case`
            ADD COLUMN `preset_answer` LONGTEXT NULL COMMENT '预置实际回答(外部API或导入)' AFTER `expected_answer`;

        ALTER TABLE `ai_qa_eval_run`
            MODIFY COLUMN `target_id` INT NULL COMMENT '被测API配置，仅评判模式可为空';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_qa_eval_run`
            MODIFY COLUMN `target_id` INT NOT NULL;

        ALTER TABLE `ai_qa_eval_case` DROP COLUMN `preset_answer`;
    """
