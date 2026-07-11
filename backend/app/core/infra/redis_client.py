from app.core.platform import config as settings
from redis.asyncio import Redis

# 配置 Redis 连接（限制连接/读写超时，避免接口长时间挂起）
redis_cli = Redis(
    host=settings.REDIS_CONFIG['host'],
    port=settings.REDIS_CONFIG['port'],
    db=settings.REDIS_CONFIG['db'],
    password=settings.REDIS_CONFIG['password'],
    socket_connect_timeout=3,
    socket_timeout=5,
)
