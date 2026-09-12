"""被测监控采集器 Token：生成明文、只存 hash、校验。"""
from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_sut_token() -> str:
    """生成一次性展示给用户的明文 token（约 48 字符）。"""
    return secrets.token_urlsafe(36)


def hash_sut_token(plain: str) -> str:
    """SHA-256 hex；与明文对比用 compare_digest。"""
    raw = (plain or "").strip().encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def verify_sut_token(plain: str, token_hash: str) -> bool:
    if not plain or not token_hash:
        return False
    expected = hash_sut_token(plain)
    return hmac.compare_digest(expected, token_hash.strip())
