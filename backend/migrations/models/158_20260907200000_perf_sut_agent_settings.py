from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `sut_server`
            ADD COLUMN `agent_settings_json` JSON NULL COMMENT '采集器运行参数（平台下发）' AFTER `schedule_json`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `sut_server` DROP COLUMN `agent_settings_json`;
    """
