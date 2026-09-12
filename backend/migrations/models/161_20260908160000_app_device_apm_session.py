"""独立设备性能监控会话表（A-5 M3）。"""
from tortoise import BaseDBAsyncClient


async def _table_exists(db: BaseDBAsyncClient, table: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = %s",
        [table],
    )
    return bool(rows and rows[0]["cnt"])


async def upgrade(db: BaseDBAsyncClient) -> str:
    if not await _table_exists(db, "app_device_apm_session"):
        await db.execute_script(
            """
            CREATE TABLE `app_device_apm_session` (
              `id` VARCHAR(64) NOT NULL PRIMARY KEY COMMENT '会话 ID',
              `project_id` INT NOT NULL COMMENT '所属项目',
              `device_id` VARCHAR(100) NOT NULL COMMENT '执行设备 ID',
              `app_udid` VARCHAR(128) NOT NULL COMMENT '设备 UDID',
              `pkg_name` VARCHAR(255) NOT NULL COMMENT '监控包名',
              `status` VARCHAR(32) NOT NULL DEFAULT 'finished' COMMENT '状态',
              `interval_ms` INT NOT NULL DEFAULT 1000,
              `metrics` JSON NULL,
              `thresholds` JSON NULL,
              `summary` JSON NULL,
              `series` JSON NULL,
              `error` VARCHAR(500) NULL,
              `username` VARCHAR(50) NOT NULL COMMENT '创建人',
              `is_del` BOOL NOT NULL DEFAULT 0,
              `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
              `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
              CONSTRAINT `fk_app_apm_session_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
            ) CHARACTER SET utf8mb4;
            """
        )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    if await _table_exists(db, "app_device_apm_session"):
        await db.execute_script("DROP TABLE IF EXISTS `app_device_apm_session`;")
    return "SELECT 1;"
