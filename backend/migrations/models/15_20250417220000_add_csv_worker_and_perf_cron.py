from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    # 此迁移已废弃：MySQL DDL 隐式提交导致字段在第一次失败时已部分写入
    # 实际字段和表由 16 号迁移负责
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    return "SELECT 1;"
