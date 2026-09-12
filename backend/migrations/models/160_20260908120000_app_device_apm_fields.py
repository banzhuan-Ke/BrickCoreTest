"""App 执行记录增加设备性能 JSON 字段（A-5 M2）。"""
from tortoise import BaseDBAsyncClient


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


async def upgrade(db: BaseDBAsyncClient) -> str:
    specs = [
        (
            "app_case_execution",
            "device_apm_summary",
            "ADD COLUMN `device_apm_summary` JSON NULL COMMENT '设备性能汇总（A-5）'",
        ),
        (
            "app_case_execution",
            "device_apm_series",
            "ADD COLUMN `device_apm_series` JSON NULL COMMENT '设备性能降采样序列（A-5）'",
        ),
        (
            "app_suite_execution",
            "device_apm_summary",
            "ADD COLUMN `device_apm_summary` JSON NULL COMMENT '设备性能汇总（A-5）'",
        ),
        (
            "app_suite_execution",
            "device_apm_series",
            "ADD COLUMN `device_apm_series` JSON NULL COMMENT '设备性能降采样序列（A-5）'",
        ),
        (
            "app_plan_execution",
            "device_apm_summary",
            "ADD COLUMN `device_apm_summary` JSON NULL COMMENT '设备性能汇总（A-5）'",
        ),
        (
            "app_plan_execution",
            "device_apm_series",
            "ADD COLUMN `device_apm_series` JSON NULL COMMENT '设备性能降采样序列（A-5）'",
        ),
    ]
    for table, col, ddl in specs:
        if not await _column_exists(db, table, col):
            await db.execute_script(f"ALTER TABLE `{table}` {ddl};")
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    for table in ("app_case_execution", "app_suite_execution", "app_plan_execution"):
        for col in ("device_apm_series", "device_apm_summary"):
            if await _column_exists(db, table, col):
                await db.execute_script(f"ALTER TABLE `{table}` DROP COLUMN `{col}`;")
    return "SELECT 1;"
