from passlib.context import CryptContext
from fastapi import HTTPException, Depends
import time
import jwt
from .config import TOKEN_TIMEOUT, SECRET_KEY, ALGORITHM
from fastapi.security import OAuth2PasswordBearer

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/sys/users/token")


async def is_authenticated(token: str = Depends(oauth2_scheme)) -> dict:
    """校验token中的用户信息，同时检查用户是否被停用"""
    data = verify_token(token)
    
    # 导入 User 模型检查用户状态（避免循环导入）
    from app.models.sys import User
    user = await User.get_or_none(id=data.get("id"), is_del=False)
    
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在或已被删除")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="用户已被停用，请联系管理员")
    
    return data


def create_token(userinfo: dict):
    # 过期时间
    expire = int(time.time()) + TOKEN_TIMEOUT
    userinfo['exp'] = expire
    # 使用pyjwt生成token
    return jwt.encode(userinfo, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token):
    """校验token"""
    try:
        data = jwt.decode(token, settings.SECRET_KEY, algorithms=settings.ALGORITHM)
        return data
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token校验失败或者无效token！")


def verify_password(plain_password, hashed_password):
    """
    校验密码
    :param plain_password: 明文密码
    :param hashed_password: 密文密码
    :return:
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    """
    哈希密码
    :param password: 明文密码
    :return:
    """
    return pwd_context.hash(password)
