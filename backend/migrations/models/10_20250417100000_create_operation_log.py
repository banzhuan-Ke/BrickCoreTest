from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `operation_log` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '日志id',
    `user_id` INT NOT NULL COMMENT '操作人ID',
    `username` VARCHAR(50) NOT NULL COMMENT '操作人用户名',
    `action` VARCHAR(100) NOT NULL COMMENT '操作行为',
    `module` VARCHAR(50) NOT NULL COMMENT '所属模块',
    `method` VARCHAR(10) NOT NULL COMMENT '请求方法',
    `path` VARCHAR(255) NOT NULL COMMENT '请求路径',
    `params` JSON NOT NULL COMMENT '请求参数',
    `ip` VARCHAR(50) NOT NULL COMMENT '客户端IP',
    `status_code` INT NOT NULL COMMENT '响应状态码' DEFAULT 200,
    `create_time` DATETIME(6) NOT NULL COMMENT '操作时间' DEFAULT CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4 COMMENT='操作日志';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `operation_log`;
    """
