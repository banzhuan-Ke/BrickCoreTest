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
from app.core.platform import config as settings
from fastapi.security import OAuth2PasswordBearer

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/sys/users/token")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/sys/users/token", auto_error=False)


async def _authenticate_user_from_token(token: str) -> dict:
    """校验 JWT 并确认用户仍有效"""
    data = verify_token(token)

    from app.models.sys import User
    user_id = data.get("id")
    # 用 values 读标量，避开偶发「模型实例缺字段」导致 AttributeError
    rows = (
        await User.filter(id=user_id, is_del=False).values("id", "is_active", "is_superuser")
        if user_id is not None
        else []
    )
    if not rows:
        raise HTTPException(status_code=401, detail="用户不存在或已被删除")

    row = rows[0]
    if not row.get("is_active", True):
        raise HTTPException(status_code=403, detail="用户已被停用，请联系管理员")

    # 回填 JWT 中可能缺失的字段，供后续权限依赖使用
    data.setdefault("is_superuser", bool(row.get("is_superuser")))
    return data


async def is_authenticated(token: str = Depends(oauth2_scheme)) -> dict:
    """校验token中的用户信息，同时检查用户是否被停用"""
    return await _authenticate_user_from_token(token)


INBOX_STREAM_TOKEN_TIMEOUT = 900  # 15 分钟，仅用于 SSE 连接


def create_inbox_stream_token(user_id: int) -> str:
    """签发站内信 SSE 专用短效 token（避免主会话 JWT 出现在 URL）。"""
    expire = int(time.time()) + INBOX_STREAM_TOKEN_TIMEOUT
    payload = {"typ": "inbox_stream", "id": user_id, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def is_authenticated_inbox_stream(
    access_token: Optional[str] = Query(None, description="站内信 SSE 短效 token"),
) -> dict:
    token = (access_token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="未登录或 token 缺失")
    data = verify_token(token)
    if data.get("typ") != "inbox_stream":
        raise HTTPException(status_code=401, detail="无效的站内信流 token")
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
        rows = await User.filter(id=user_id, is_del=False).values("username")
        if rows and rows[0].get("username"):
            return rows[0]["username"]
    raise HTTPException(status_code=401, detail="无法识别当前登录用户，请重新登录")


async def get_current_username(user_info: dict = Depends(is_authenticated)) -> str:
    """从 JWT 获取当前登录用户名（用于创建人/修改人审计字段）"""
    return await resolve_current_username(user_info)


async def _load_user_permission_codes(user_id: int) -> set[str]:
    """按用户 ID 拉角色权限，不依赖可能不完整的 User 实例。"""
    from app.core.platform.permissions import get_user_permissions

    return set(await get_user_permissions(user_id))


def require_permissions(*perms: str):
    """权限校验依赖工厂，超级管理员/admin角色自动跳过"""
    async def checker(token: str = Depends(oauth2_scheme)):
        user_data = await is_authenticated(token)
        if user_data.get("is_superuser"):
            return user_data
        uid = user_data.get("id")
        if uid is None:
            raise HTTPException(status_code=401, detail="用户不存在或已被删除")
        allowed = await _load_user_permission_codes(int(uid))
        if not set(perms).issubset(allowed):
            from app.models.sys import Role
            role_names = [
                r["name"]
                for r in await Role.filter(users__id=uid, is_del=False).values("name")
            ]
            raise HTTPException(
                status_code=403,
                detail=(
                    f"权限不足: 需要{perms}, 拥有{sorted(allowed)}, "
                    f"is_superuser={bool(user_data.get('is_superuser'))}, roles={role_names}"
                ),
            )
        return user_data
    return checker


def require_any_permissions(*perms: str):
    """满足任一权限即可（超级管理员自动跳过）"""
    async def checker(token: str = Depends(oauth2_scheme)):
        user_data = await is_authenticated(token)
        if user_data.get("is_superuser"):
            return user_data
        uid = user_data.get("id")
        if uid is None:
            raise HTTPException(status_code=401, detail="用户不存在或已被删除")
        allowed = await _load_user_permission_codes(int(uid))
        if not any(p in allowed for p in perms):
            from app.models.sys import Role
            role_names = [
                r["name"]
                for r in await Role.filter(users__id=uid, is_del=False).values("name")
            ]
            raise HTTPException(
                status_code=403,
                detail=(
                    f"权限不足: 需要以下任一权限 {list(perms)}, "
                    f"拥有{sorted(allowed)}, roles={role_names}"
                ),
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

    rows = await Device.filter(id=device_id, is_del=False).values(
        "id", "runner_session_jti", "status"
    )
    if not rows or rows[0].get("runner_session_jti") != jti:
        raise HTTPException(status_code=401, detail="Runner 会话已失效，请重新连接")
    if rows[0].get("status") == "已停止":
        raise HTTPException(status_code=403, detail="设备已被管理员停止，请重新上线")

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
