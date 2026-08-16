"""遗留鉴权模块：统一转发到 auth，避免双份实现漂移。"""
from app.core.platform.auth import (  # noqa: F401
    create_token,
    get_password_hash,
    is_authenticated,
    verify_password,
    verify_token,
)
