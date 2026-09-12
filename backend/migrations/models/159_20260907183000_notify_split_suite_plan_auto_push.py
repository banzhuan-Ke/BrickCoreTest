"""拆分接口/Web/App 套件与计划的自动推报告开关（NOTIFY-1）。"""
from tortoise import BaseDBAsyncClient


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


async def upgrade(db: BaseDBAsyncClient) -> str:
    table = "notification_config"
    adds = [
        (
            "api_suite_auto_push_report",
            "ADD COLUMN `api_suite_auto_push_report` BOOL NOT NULL DEFAULT 0 "
            "COMMENT 'API套件执行完成后自动推送报告（含定时）' AFTER `api_auto_push_report`",
        ),
        (
            "api_plan_auto_push_report",
            "ADD COLUMN `api_plan_auto_push_report` BOOL NOT NULL DEFAULT 0 "
            "COMMENT 'API计划执行完成后自动推送报告（含定时）' AFTER `api_suite_auto_push_report`",
        ),
        (
            "ui_suite_auto_push_report",
            "ADD COLUMN `ui_suite_auto_push_report` BOOL NOT NULL DEFAULT 0 "
            "COMMENT 'Web独立套件执行完成后自动推送报告（含定时）' AFTER `ui_auto_push_report`",
        ),
        (
            "ui_plan_auto_push_report",
            "ADD COLUMN `ui_plan_auto_push_report` BOOL NOT NULL DEFAULT 0 "
            "COMMENT 'Web计划执行完成后自动推送报告（含定时）' AFTER `ui_suite_auto_push_report`",
        ),
        (
            "app_suite_auto_push_report",
            "ADD COLUMN `app_suite_auto_push_report` BOOL NOT NULL DEFAULT 0 "
            "COMMENT 'App独立套件执行完成后自动推送报告（含定时）' AFTER `app_auto_push_report`",
        ),
        (
            "app_plan_auto_push_report",
            "ADD COLUMN `app_plan_auto_push_report` BOOL NOT NULL DEFAULT 0 "
            "COMMENT 'App计划执行完成后自动推送报告（含定时）' AFTER `app_suite_auto_push_report`",
        ),
    ]
    for col, ddl in adds:
        if not await _column_exists(db, table, col):
            await db.execute_script(f"ALTER TABLE `{table}` {ddl};")

    # 回填：旧合并开关 → 对应新开关（不覆盖已显式配置）
    await db.execute_script(
        f"""
        UPDATE `{table}` SET
          `api_suite_auto_push_report` = IF(`api_auto_push_report` = 1, 1, `api_suite_auto_push_report`),
          `api_plan_auto_push_report` = IF(`api_auto_push_report` = 1, 1, `api_plan_auto_push_report`),
          `ui_plan_auto_push_report` = IF(`ui_auto_push_report` = 1, 1, `ui_plan_auto_push_report`),
          `app_suite_auto_push_report` = IF(`app_auto_push_report` = 1, 1, `app_suite_auto_push_report`),
          `app_plan_auto_push_report` = IF(`app_auto_push_report` = 1, 1, `app_plan_auto_push_report`);
        """
    )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    table = "notification_config"
    for col in (
        "app_plan_auto_push_report",
        "app_suite_auto_push_report",
        "ui_plan_auto_push_report",
        "ui_suite_auto_push_report",
        "api_plan_auto_push_report",
        "api_suite_auto_push_report",
    ):
        if await _column_exists(db, table, col):
            await db.execute_script(f"ALTER TABLE `{table}` DROP COLUMN `{col}`;")
    return "SELECT 1;"
