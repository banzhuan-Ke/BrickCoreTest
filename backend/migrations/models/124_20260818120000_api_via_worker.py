from tortoise import BaseDBAsyncClient


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


async def _add_int_null(db: BaseDBAsyncClient, table: str, column: str, comment: str, after: str) -> None:
    if await _column_exists(db, table, column):
        return
    await db.execute_script(
        f"ALTER TABLE `{table}` "
        f"ADD COLUMN `{column}` INT NULL COMMENT '{comment}' AFTER `{after}`;"
    )


async def _add_varchar_null(
    db: BaseDBAsyncClient, table: str, column: str, comment: str, after: str
) -> None:
    if await _column_exists(db, table, column):
        return
    await db.execute_script(
        f"ALTER TABLE `{table}` "
        f"ADD COLUMN `{column}` VARCHAR(100) NULL COMMENT '{comment}' AFTER `{after}`;"
    )


async def upgrade(db: BaseDBAsyncClient) -> str:
    """接口执行经 Worker 代发：定时任务与套件/计划记录落库执行机。"""
    await _add_int_null(db, "api_cron_job", "worker_id", "经执行机代发时的 Worker ID", "env_id")
    await _add_int_null(db, "api_suite_run_record", "worker_id", "经执行机代发时的 Worker ID", "env_name")
    await _add_varchar_null(
        db, "api_suite_run_record", "worker_name", "执行机名称", "worker_id"
    )
    await _add_int_null(db, "api_plan_run_record", "worker_id", "经执行机代发时的 Worker ID", "env_name")
    await _add_varchar_null(
        db, "api_plan_run_record", "worker_name", "执行机名称", "worker_id"
    )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    drops = (
        ("api_cron_job", "worker_id"),
        ("api_suite_run_record", "worker_name"),
        ("api_suite_run_record", "worker_id"),
        ("api_plan_run_record", "worker_name"),
        ("api_plan_run_record", "worker_id"),
    )
    for table, column in drops:
        if await _column_exists(db, table, column):
            await db.execute_script(f"ALTER TABLE `{table}` DROP COLUMN `{column}`;")
    return "SELECT 1;"
