from tortoise import BaseDBAsyncClient


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


_ALERT_COLS = (
    ("api_alert_on_failure", "API套件执行失败时发送告警"),
    ("ui_alert_on_failure", "Web计划/套件执行失败时发送告警"),
    ("perf_alert_on_failure", "性能测试执行失败时发送告警"),
    ("app_alert_on_failure", "App计划/套件执行失败时发送告警"),
)


async def upgrade(db: BaseDBAsyncClient) -> str:
    """通知配置：失败告警按 API/Web/压测/App 分项，与自动推报告对齐。"""
    table = "notification_config"
    for col, comment in _ALERT_COLS:
        if not await _column_exists(db, table, col):
            await db.execute_script(
                f"ALTER TABLE `{table}` "
                f"ADD COLUMN `{col}` BOOL NOT NULL DEFAULT 1 "
                f"COMMENT '{comment}' AFTER `enabled`;"
            )

    # 兼容此前未发版的单字段 alert_on_failure：值拷到四项后删除
    if await _column_exists(db, table, "alert_on_failure"):
        await db.execute_script(
            f"UPDATE `{table}` SET "
            "`api_alert_on_failure` = `alert_on_failure`, "
            "`ui_alert_on_failure` = `alert_on_failure`, "
            "`perf_alert_on_failure` = `alert_on_failure`, "
            "`app_alert_on_failure` = `alert_on_failure`;"
        )
        await db.execute_script(f"ALTER TABLE `{table}` DROP COLUMN `alert_on_failure`;")

    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    table = "notification_config"
    if not await _column_exists(db, table, "alert_on_failure"):
        await db.execute_script(
            f"ALTER TABLE `{table}` "
            "ADD COLUMN `alert_on_failure` BOOL NOT NULL DEFAULT 1 "
            "COMMENT '执行失败时是否发送告警' AFTER `enabled`;"
        )
        if await _column_exists(db, table, "ui_alert_on_failure"):
            await db.execute_script(
                f"UPDATE `{table}` SET `alert_on_failure` = "
                "(`api_alert_on_failure` OR `ui_alert_on_failure` OR "
                "`perf_alert_on_failure` OR `app_alert_on_failure`);"
            )
    for col, _ in _ALERT_COLS:
        if await _column_exists(db, table, col):
            await db.execute_script(f"ALTER TABLE `{table}` DROP COLUMN `{col}`;")
    return "SELECT 1;"
