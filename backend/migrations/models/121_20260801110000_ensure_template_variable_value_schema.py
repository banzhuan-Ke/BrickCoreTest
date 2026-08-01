from tortoise import BaseDBAsyncClient


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


async def upgrade(db: BaseDBAsyncClient) -> str:
    """幂等补齐模板变量类型字段（兼容 aerich 已记账但列缺失的库）。"""
    table = "ai_knowledge_template_variable"
    if not await _column_exists(db, table, "value_type"):
        await db.execute_script(
            f"ALTER TABLE `{table}` "
            "ADD COLUMN `value_type` VARCHAR(20) NOT NULL DEFAULT 'text' "
            "COMMENT '变量值类型' AFTER `category`;"
        )
    if not await _column_exists(db, table, "value_schema"):
        after = "value_type" if await _column_exists(db, table, "value_type") else "category"
        await db.execute_script(
            f"ALTER TABLE `{table}` "
            "ADD COLUMN `value_schema` JSON NULL "
            f"COMMENT '表格等结构化类型配置' AFTER `{after}`;"
        )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    return "SELECT 1;"
