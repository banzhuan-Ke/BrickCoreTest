from tortoise import BaseDBAsyncClient


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


async def upgrade(db: BaseDBAsyncClient) -> str:
    """定时任务持久化执行器配置（W-37）。"""
    table = "cronjob"
    if not await _column_exists(db, table, "run_config"):
        await db.execute_script(
            f"ALTER TABLE `{table}` "
            "ADD COLUMN `run_config` JSON NULL "
            "COMMENT '执行器配置：devices/weight/concurrency/browser/headless' "
            "AFTER `crontab`;"
        )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    return "SELECT 1;"
