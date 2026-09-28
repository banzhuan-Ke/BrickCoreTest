"""平台设置：小测 P1 护栏（轮次/工具数/压缩/会话摘要）。"""
from tortoise import BaseDBAsyncClient


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


async def upgrade(db: BaseDBAsyncClient) -> str:
    cols = [
        (
            "assist_max_plan_rounds",
            "INT NOT NULL DEFAULT 5 COMMENT '小测多轮最大规划轮次'",
        ),
        (
            "assist_max_tools_per_round",
            "INT NOT NULL DEFAULT 4 COMMENT '小测每轮最多工具数'",
        ),
        (
            "assist_tool_result_max_chars",
            "INT NOT NULL DEFAULT 6000 COMMENT '工具结果注入 LLM 的最大字符'",
        ),
        (
            "assist_tool_list_item_limit",
            "INT NOT NULL DEFAULT 8 COMMENT '工具结果列表最多保留条数'",
        ),
        (
            "assist_session_summary_trigger",
            "INT NOT NULL DEFAULT 16 COMMENT '会话消息数超过后折叠进摘要'",
        ),
        (
            "assist_history_turns",
            "INT NOT NULL DEFAULT 4 COMMENT 'Agent Loop 注入的近期对话轮数'",
        ),
    ]
    after = "assist_max_tokens_total"
    for name, ddl in cols:
        if not await _column_exists(db, "system_platform_settings", name):
            await db.execute_script(
                f"ALTER TABLE `system_platform_settings` "
                f"ADD COLUMN `{name}` {ddl} AFTER `{after}`;"
            )
        after = name
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    for name in (
        "assist_history_turns",
        "assist_session_summary_trigger",
        "assist_tool_list_item_limit",
        "assist_tool_result_max_chars",
        "assist_max_tools_per_round",
        "assist_max_plan_rounds",
    ):
        if await _column_exists(db, "system_platform_settings", name):
            await db.execute_script(
                f"ALTER TABLE `system_platform_settings` DROP COLUMN `{name}`;"
            )
    return "SELECT 1;"
