"""device.version / hostname：50 → 255（兼容 macOS Darwin 内核版本串）。"""
from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    await db.execute_script(
        """
        ALTER TABLE `device`
            MODIFY COLUMN `version` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '设备版本',
            MODIFY COLUMN `hostname` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '设备主机名';
        """
    )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    await db.execute_script(
        """
        ALTER TABLE `device`
            MODIFY COLUMN `version` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '设备版本',
            MODIFY COLUMN `hostname` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '设备主机名';
        """
    )
    return "SELECT 1;"
