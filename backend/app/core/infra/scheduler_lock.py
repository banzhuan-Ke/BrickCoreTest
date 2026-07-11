"""
APScheduler 分布式锁工具

用于防止多实例部署时同一定时任务被重复触发执行。
基于 Redis SET NX EX 实现轻量级分布式锁。
"""
import functools
from app.core.infra.redis_client import redis_cli


def with_scheduler_lock(lock_prefix: str, expire_seconds: int = 300):
    """
    APScheduler 任务分布式锁装饰器

    Args:
        lock_prefix: 锁key前缀，建议区分业务模块（如 scheduler:ui / scheduler:api）
        expire_seconds: 锁过期时间，默认 300 秒，需大于任务预期最大执行时长
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取 job_id：优先从 kwargs 中获取 cronjob_id / job_id，否则取第一个位置参数
            job_id = kwargs.get("cronjob_id") or kwargs.get("job_id") or (args[0] if args else "unknown")
            lock_key = f"{lock_prefix}:lock:{job_id}"

            # 尝试获取锁（SET NX EX）
            acquired = await redis_cli.set(lock_key, "1", nx=True, ex=expire_seconds)
            if not acquired:
                print(f"[SchedulerLock] {func.__name__} job={job_id} 已被其他实例锁定，跳过执行")
                return

            try:
                return await func(*args, **kwargs)
            finally:
                # 释放锁
                await redis_cli.delete(lock_key)

        return wrapper
    return decorator
