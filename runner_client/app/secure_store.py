"""本机凭据加密存储（机器绑定，仅降低明文落盘风险）"""
from __future__ import annotations

import base64
import hashlib
import uuid


def _machine_key() -> bytes:
    node = str(uuid.getnode()).encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", node, b"brickcore-runner-client", 120_000, dklen=32)


def encrypt_text(plain: str) -> str:
    if not plain:
        return ""
    key = _machine_key()
    data = plain.encode("utf-8")
    xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.urlsafe_b64encode(xored).decode("ascii")


def decrypt_text(token: str) -> str:
    if not token:
        return ""
    try:
        key = _machine_key()
        xored = base64.urlsafe_b64decode(token.encode("ascii"))
        plain = bytes(b ^ key[i % len(key)] for i, b in enumerate(xored))
        return plain.decode("utf-8")
    except Exception:
        return ""
