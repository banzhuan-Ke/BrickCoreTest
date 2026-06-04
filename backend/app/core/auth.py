"""
认证相关
"""
# 修复 passlib 1.7.4 + bcrypt 4.x 的兼容性警告
try:
    import bcrypt
    if not hasattr(bcrypt, '__about__'):
        bcrypt.__about__ = type('__about__', (), {'__version__': bcrypt.__version__})()
except Exception:
    pass

from passlib.context import CryptContext
from fastapi import HTTPException, Depends, Header, Query
from typing import Optional
import time
import jwt
from .config import SECRET_KEY, ALGORITHM, TOKEN_TIMEOUT, INTERNAL_API_KEY
from app.core import config as settings
from fastapi.security import OAuth2PasswordBearer

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/sys/users/token")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/sys/users/token", auto_error=False)


async def _authenticate_user_from_token(token: str) -> dict:
    """校验 JWT 并确认用户仍有效"""
    data = verify_token(token)

    from app.models.sys import User
    user = await User.get_or_none(id=data.get("id"), is_del=False)

    if not user:
        raise HTTPException(status_code=401, detail="用户不存在或已被删除")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="用户已被停用，请联系管理员")

    return data


async def is_authenticated(token: str = Depends(oauth2_scheme)) -> dict:
    """校验token中的用户信息，同时检查用户是否被停用"""
    return await _authenticate_user_from_token(token)


async def is_authenticated_from_header_or_query(
    header_token: Optional[str] = Depends(oauth2_scheme_optional),
    access_token: Optional[str] = Query(None, description="浏览器原生下载时在 URL 携带 token"),
) -> dict:
    """支持 Authorization 头或 access_token 查询参数（大文件浏览器下载）"""
    token = (header_token or access_token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="未登录或 token 缺失")
    return await _authenticate_user_from_token(token)


async def resolve_current_username(user_info: dict) -> str:
    """从 JWT 解析当前用户名；缺失时按用户 ID 查库（兼容旧 token）"""
    username = (user_info.get("username") or "").strip()
    if username:
        return username
    user_id = user_info.get("id")
    if user_id:
        from app.models.sys import User
        user = await User.get_or_none(id=user_id, is_del=False)
        if user and user.username:
            return user.username
    raise HTTPException(status_code=401, detail="无法识别当前登录用户，请重新登录")


async def get_current_username(user_info: dict = Depends(is_authenticated)) -> str:
    """从 JWT 获取当前登录用户名（用于创建人/修改人审计字段）"""
    return await resolve_current_username(user_info)


def require_permissions(*perms: str):
    """权限校验依赖工厂，超级管理员/admin角色自动跳过"""
    async def checker(token: str = Depends(oauth2_scheme)):
        user_data = await is_authenticated(token)
        from app.models.sys import User
        from app.core.permissions import get_user_permissions
        user = await User.get_or_none(id=user_data.get("id"), is_del=False).prefetch_related("roles")
        if user and user.is_superuser:
            return user_data
        allowed = set(await get_user_permissions(user))
        if not set(perms).issubset(allowed):
            role_names = [r.name for r in await user.roles.all()] if user else []
            raise HTTPException(
                status_code=403,
                detail=f"权限不足: 需要{perms}, 拥有{sorted(allowed)}, is_superuser={user.is_superuser if user else None}, roles={role_names}"
            )
        return user_data
    return checker


def create_token(userinfo: dict):
    """创建JWT Token"""
    expire = int(time.time()) + TOKEN_TIMEOUT
    userinfo['exp'] = expire
    return jwt.encode(userinfo, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token):
    """校验token"""
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return data
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="token校验失败或无效token")


def verify_password(plain_password, hashed_password):
    """校验密码"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    """哈希密码"""
    return pwd_context.hash(password)


async def verify_internal_token(x_internal_token: str = Header(..., alias="X-Internal-Token")):
    """校验内部服务调用的共享密钥（Runner 等）"""
    if x_internal_token != INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid internal token")
    return {"internal": True}


def create_runner_token(*, device_id: str, user_id: int, jti: str) -> str:
    """签发 Runner 会话 JWT"""
    expire = int(time.time()) + settings.RUNNER_TOKEN_TIMEOUT
    payload = {
        "typ": "runner",
        "device_id": device_id,
        "user_id": user_id,
        "jti": jti,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def verify_runner_token(x_runner_token: str = Header(..., alias="X-Runner-Token")) -> dict:
    """校验 Runner 客户端会话 token"""
    from app.models.sys import Device

    try:
        data = jwt.decode(x_runner_token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Runner token 已过期，请重新连接")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Runner token 无效")

    if data.get("typ") != "runner":
        raise HTTPException(status_code=401, detail="非 Runner token")

    device_id = data.get("device_id")
    jti = data.get("jti")
    if not device_id or not jti:
        raise HTTPException(status_code=401, detail="Runner token 缺少设备信息")

    device = await Device.get_or_none(id=device_id, is_del=False)
    if not device or device.runner_session_jti != jti:
        raise HTTPException(status_code=401, detail="Runner 会话已失效，请重新连接")

    return data


async def verify_runner_or_internal(
    x_runner_token: str | None = Header(None, alias="X-Runner-Token"),
    x_internal_token: str | None = Header(None, alias="X-Internal-Token"),
) -> dict:
    """Runner token 或内部密钥（过渡期兼容同机 Runner）"""
    if x_runner_token:
        return await verify_runner_token(x_runner_token)
    if x_internal_token and x_internal_token == INTERNAL_API_KEY:
        return {"internal": True}
    raise HTTPException(status_code=401, detail="需要 X-Runner-Token 或有效的 X-Internal-Token")
