"""W1.1：ai_skill_run_record 治理字段（user_id / session / tokens / ai_config）。"""
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


_COLS = (
    ("user_id", "INT NULL COMMENT '用户ID（审计）'"),
    ("session_id", "INT NULL COMMENT 'assistant_session.id'"),
    ("ai_config_id", "INT NULL COMMENT '实际 AI 配置'"),
    ("tokens_used", "INT NULL COMMENT 'Skill 汇总 token'"),
    ("prompt_tokens", "INT NULL"),
    ("completion_tokens", "INT NULL"),
)


async def upgrade(db: BaseDBAsyncClient) -> str:
    if not await _table_exists(db, "ai_skill_run_record"):
        return "SELECT 1;"
    for name, decl in _COLS:
        if not await _column_exists(db, "ai_skill_run_record", name):
            await db.execute_script(
                f"ALTER TABLE `ai_skill_run_record` ADD COLUMN `{name}` {decl};"
            )
    for idx_sql in (
        "CREATE INDEX `idx_skill_run_user` ON `ai_skill_run_record` (`user_id`)",
        "CREATE INDEX `idx_skill_run_status_time` ON `ai_skill_run_record` (`status`, `create_time`)",
    ):
        try:
            await db.execute_script(idx_sql + ";")
        except Exception:
            pass
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    if not await _table_exists(db, "ai_skill_run_record"):
        return "SELECT 1;"
    for name, _ in reversed(_COLS):
        if await _column_exists(db, "ai_skill_run_record", name):
            await db.execute_script(
                f"ALTER TABLE `ai_skill_run_record` DROP COLUMN `{name}`;"
            )
    return "SELECT 1;"
