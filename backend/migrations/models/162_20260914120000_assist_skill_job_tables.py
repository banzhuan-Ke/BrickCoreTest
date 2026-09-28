"""AI Skill RunRecord / JobLink / session pin 列（W0；无 Prompt 正文列）。"""
from tortoise import BaseDBAsyncClient


async def _table_exists(db: BaseDBAsyncClient, table: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = %s",
        [table],
    )
    return bool(rows and rows[0]["cnt"])


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


async def upgrade(db: BaseDBAsyncClient) -> str:
    if await _table_exists(db, "assistant_session"):
        if not await _column_exists(db, "assistant_session", "pinned_context_json"):
            await db.execute_script(
                "ALTER TABLE `assistant_session` "
                "ADD COLUMN `pinned_context_json` JSON NULL "
                "COMMENT '钉住实体上下文（W2 预留）';"
            )

    if not await _table_exists(db, "ai_skill_run_record"):
        await db.execute_script(
            """
            CREATE TABLE `ai_skill_run_record` (
              `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
              `skill_code` VARCHAR(64) NOT NULL COMMENT '技能编码',
              `skill_version` VARCHAR(32) NULL COMMENT '技能版本',
              `prompt_key` VARCHAR(64) NULL COMMENT 'Prompt 引用 key（无正文）',
              `prompt_version` VARCHAR(32) NULL COMMENT 'Prompt 版本',
              `project_id` INT NULL,
              `target_type` VARCHAR(64) NULL,
              `target_id` VARCHAR(64) NULL,
              `entry_source` VARCHAR(32) NULL,
              `run_mode` VARCHAR(16) NULL,
              `status` VARCHAR(32) NOT NULL DEFAULT 'running',
              `input_summary` LONGTEXT NULL,
              `tool_calls` JSON NULL,
              `output_summary` LONGTEXT NULL,
              `error_message` LONGTEXT NULL,
              `duration_ms` INT NULL,
              `scene` VARCHAR(64) NULL,
              `username` VARCHAR(64) NULL,
              `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
              KEY `idx_skill_run_code` (`skill_code`),
              KEY `idx_skill_run_project` (`project_id`)
            ) COMMENT='AI Skill 执行记录（无 Prompt 正文）';
            """
        )

    if not await _table_exists(db, "assistant_job_link"):
        await db.execute_script(
            """
            CREATE TABLE `assistant_job_link` (
              `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
              `session_id` INT NOT NULL COMMENT 'assistant_session.id',
              `job_type` VARCHAR(64) NOT NULL,
              `job_id` VARCHAR(64) NOT NULL,
              `status` VARCHAR(32) NOT NULL DEFAULT 'pending',
              `payload_json` JSON NULL,
              `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
              `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
              KEY `idx_assist_job_session` (`session_id`),
              KEY `idx_assist_job_type_id` (`job_type`, `job_id`)
            ) COMMENT='小测会话 Job 关联';
            """
        )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    if await _table_exists(db, "assistant_job_link"):
        await db.execute_script("DROP TABLE `assistant_job_link`;")
    if await _table_exists(db, "ai_skill_run_record"):
        await db.execute_script("DROP TABLE `ai_skill_run_record`;")
    if await _table_exists(db, "assistant_session") and await _column_exists(
        db, "assistant_session", "pinned_context_json"
    ):
        await db.execute_script(
            "ALTER TABLE `assistant_session` DROP COLUMN `pinned_context_json`;"
        )
    return "SELECT 1;"
