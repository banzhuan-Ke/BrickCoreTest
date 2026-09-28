"""W6：小测记忆 / feedback / turn_trace / session.summary_text。"""
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
        if not await _column_exists(db, "assistant_session", "summary_text"):
            await db.execute_script(
                "ALTER TABLE `assistant_session` "
                "ADD COLUMN `summary_text` LONGTEXT NULL "
                "COMMENT '会话摘要（W6）';"
            )

    if not await _table_exists(db, "assistant_memory"):
        await db.execute_script(
            """
CREATE TABLE `assistant_memory` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `project_id` INT NOT NULL COMMENT '项目ID',
    `user_id` INT NOT NULL COMMENT '用户ID',
    `mem_key` VARCHAR(64) NOT NULL COMMENT '记忆键',
    `mem_value` LONGTEXT NOT NULL COMMENT '记忆值',
    `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY `uid_assist_mem_proj_user_key` (`project_id`, `user_id`, `mem_key`),
    KEY `idx_assist_mem_proj_user` (`project_id`, `user_id`)
) CHARACTER SET utf8mb4 COMMENT='小测项目记忆';
"""
        )

    if not await _table_exists(db, "assistant_feedback"):
        await db.execute_script(
            """
CREATE TABLE `assistant_feedback` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `session_id` INT NOT NULL COMMENT 'assistant_session.id',
    `message_id` VARCHAR(64) NOT NULL COMMENT '消息标识',
    `user_id` INT NOT NULL COMMENT '用户ID',
    `project_id` INT NULL,
    `score` INT NOT NULL COMMENT '1=赞 -1=踩',
    `note` VARCHAR(500) NULL COMMENT '可选备注',
    `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY `uid_assist_fb_sess_msg_user` (`session_id`, `message_id`, `user_id`),
    KEY `idx_assist_fb_session` (`session_id`)
) CHARACTER SET utf8mb4 COMMENT='小测回复反馈';
"""
        )

    if not await _table_exists(db, "assistant_turn_trace"):
        await db.execute_script(
            """
CREATE TABLE `assistant_turn_trace` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `session_id` INT NULL,
    `user_id` INT NULL,
    `project_id` INT NULL,
    `mode` VARCHAR(16) NOT NULL DEFAULT 'standard',
    `stop_reason` VARCHAR(64) NULL,
    `tools_used` JSON NULL,
    `skills_used` JSON NULL,
    `rounds` INT NULL,
    `tokens_used` INT NULL,
    `duration_ms` INT NULL,
    `has_pending_confirm` BOOL NOT NULL DEFAULT 0,
    `has_pending_ask_user` BOOL NOT NULL DEFAULT 0,
    `error_code` VARCHAR(64) NULL,
    `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_assist_trace_time` (`create_time`),
    KEY `idx_assist_trace_user` (`user_id`),
    KEY `idx_assist_trace_project` (`project_id`)
) CHARACTER SET utf8mb4 COMMENT='小测回合追踪（脱敏，无 Prompt）';
"""
        )

    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    for table in (
        "assistant_turn_trace",
        "assistant_feedback",
        "assistant_memory",
    ):
        if await _table_exists(db, table):
            await db.execute_script(f"DROP TABLE IF EXISTS `{table}`;")
    if await _table_exists(db, "assistant_session"):
        if await _column_exists(db, "assistant_session", "summary_text"):
            await db.execute_script(
                "ALTER TABLE `assistant_session` DROP COLUMN `summary_text`;"
            )
    return "SELECT 1;"
