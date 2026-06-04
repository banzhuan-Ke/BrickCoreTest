from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_qa_eval_case`
            ADD COLUMN `seq_no` INT NULL COMMENT 'Excel序号，合并排序用' AFTER `set_id`,
            ADD COLUMN `chat_path` JSON NULL COMMENT '问答目录 chatPath' AFTER `preset_answer`,
            ADD COLUMN `multi_turn` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否多轮会话' AFTER `chat_path`,
            ADD COLUMN `scenario_type` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '场景类型' AFTER `multi_turn`,
            ADD COLUMN `source_file` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '来源文件' AFTER `scenario_type`,
            ADD COLUMN `file_type` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '文件类型' AFTER `source_file`;

        ALTER TABLE `ai_qa_eval_result`
            ADD COLUMN `api_meta` JSON NULL COMMENT 'API扩展: thinking/references等' AFTER `api_latency_ms`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_qa_eval_result` DROP COLUMN `api_meta`;

        ALTER TABLE `ai_qa_eval_case`
            DROP COLUMN `file_type`,
            DROP COLUMN `source_file`,
            DROP COLUMN `scenario_type`,
            DROP COLUMN `multi_turn`,
            DROP COLUMN `chat_path`,
            DROP COLUMN `seq_no`;
    """
