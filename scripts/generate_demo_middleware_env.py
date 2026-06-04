#!/usr/bin/env python3
"""生成演示机中间件密码文件（不提交 Git）。"""
from __future__ import annotations

import secrets
import string
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "ce-stubs" / "demo-middleware.env"
ALPHABET = string.ascii_letters + string.digits


def gen(n: int = 24) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


def main() -> None:
    body = f"""# 演示机中间件密码（勿提交 Git；同步 CE 时复制为仓库根目录 .env）
# 平台登录 admin / BrickCore123456 不变

MYSQL_ROOT_PASSWORD={gen()}
MYSQL_PASSWORD={gen()}
REDIS_PASSWORD={gen()}
RABBITMQ_PASSWORD={gen()}
MINIO_ROOT_USER=admin
MINIO_PASSWORD={gen()}
"""
    OUT.write_text(body, encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
