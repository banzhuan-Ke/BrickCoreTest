"""构建 Runner 客户端连接配置（Phase 6：scoped MQ/Redis 凭证）"""
from __future__ import annotations

from app.core import config as settings


def resolve_public_base_url(request_base_url: str) -> str:
    return (request_base_url or "").rstrip("/")


def build_runner_connect_bundle(
    *,
    device_id: str,
    base_url: str,
    mq_username: str,
    mq_password: str,
    redis_username: str = "",
    redis_password: str = "",
    include_database: bool = False,
) -> dict:
    mq_host, mq_port = settings.runner_client_mq_endpoint()
    redis_host, redis_port = settings.runner_client_redis_endpoint()
    bundle = {
        "base_url": resolve_public_base_url(base_url),
        "engine_version": settings.RUNNER_ENGINE_VERSION,
        "client_version_min": settings.RUNNER_CLIENT_VERSION_MIN,
        "client_version_latest": settings.RUNNER_CLIENT_VERSION_LATEST,
        "storage_type": settings.STORAGE_TYPE.lower(),
        "upload_mode": "presigned" if settings.STORAGE_TYPE.lower() == "minio" else "legacy",
        "mq": {
            "host": mq_host,
            "port": mq_port,
            "username": mq_username,
            "password": mq_password,
            "queue": device_id,
        },
        "redis": {
            "host": redis_host,
            "port": redis_port,
            "username": redis_username or "",
            "password": redis_password if redis_password is not None else (settings.REDIS_CONFIG.get("password") or ""),
            "db": int(settings.REDIS_CONFIG.get("db", 15)),
        },
    }
    if include_database:
        db = settings.DATABASE
        bundle["database"] = {
            "host": db["host"],
            "port": int(db["port"]),
            "user": db["user"],
            "password": db["password"],
            "database": db["database"],
        }
    return bundle
