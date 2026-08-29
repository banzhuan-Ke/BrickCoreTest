from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    rows = await db.execute_query_dict(
        f"SELECT 1 FROM information_schema.columns "
        f"WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s LIMIT 1",
        [table, column],
    )
    return bool(rows)


async def upgrade(db: BaseDBAsyncClient) -> str:
    table = "user_notification_preference"
    if not await _column_exists(db, table, "dnd_timezone"):
        await db.execute_script(
            f"ALTER TABLE `{table}` ADD COLUMN `dnd_timezone` "
            f"VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai' "
            f"COMMENT '免打扰时段时区（IANA）' AFTER `dnd_mute_inbox`;"
        )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    table = "user_notification_preference"
    if await _column_exists(db, table, "dnd_timezone"):
        await db.execute_script(f"ALTER TABLE `{table}` DROP COLUMN `dnd_timezone`;")
    return "SELECT 1;"
