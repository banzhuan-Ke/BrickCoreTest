from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `sut_server`
            ADD COLUMN `config_rev` INT NOT NULL DEFAULT 1 COMMENT '监控配置版本' AFTER `schedule_json`;
        CREATE UNIQUE INDEX `uid_sut_server_agent_uid` ON `sut_server` (`agent_uid`);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX `uid_sut_server_agent_uid` ON `sut_server`;
        ALTER TABLE `sut_server` DROP COLUMN `config_rev`;
    """
