"""
通用加密工具（用于加密存储敏感配置如 LLM API Key）
"""
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# 加密密钥来源优先级：环境变量 > SECRET_KEY 派生
_SECRET = os.getenv("AI_API_KEY_SECRET", "")


def _get_fernet() -> Fernet:
    """获取 Fernet 实例"""
    global _SECRET
    if not _SECRET:
        # 无环境变量时，从 config 导入 SECRET_KEY 派生（避免循环导入，延迟导入）
        from app.core.platform.config import SECRET_KEY

        _SECRET = SECRET_KEY

    # 使用 PBKDF2 派生 32 字节密钥
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"brickcore-ai-key-salt-v1",  # 固定 salt，确保同一环境加解密一致
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(_SECRET.encode()))
    return Fernet(key)


def encrypt_value(plain_text: str) -> str:
    """加密明文"""
    if not plain_text:
        return ""
    f = _get_fernet()
    return f.encrypt(plain_text.encode()).decode()


def decrypt_value(cipher_text: str) -> str:
    """解密密文"""
    if not cipher_text:
        return ""
    f = _get_fernet()
    return f.decrypt(cipher_text.encode()).decode()


def mask_key(key: str) -> str:
    """脱敏显示 API Key，如 sk-abc...xyz"""
    if not key or len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]
