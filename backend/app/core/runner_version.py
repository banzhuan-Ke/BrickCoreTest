"""Runner 客户端 / 引擎版本校验"""
from __future__ import annotations

from fastapi import HTTPException

from app.core import config as settings


def parse_version(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for segment in (version or "0").strip().split("."):
        token = segment.split("-")[0].split("+")[0]
        try:
            parts.append(int(token))
        except ValueError:
            parts.append(0)
    return tuple(parts or (0,))


def compare_version(left: str, right: str) -> int:
    """left > right 返回 1，相等 0，小于 -1"""
    a = parse_version(left)
    b = parse_version(right)
    length = max(len(a), len(b))
    a = a + (0,) * (length - len(a))
    b = b + (0,) * (length - len(b))
    if a > b:
        return 1
    if a < b:
        return -1
    return 0


def ensure_client_version(client_version: str) -> None:
    minimum = settings.RUNNER_CLIENT_VERSION_MIN
    if compare_version(client_version or "0", minimum) < 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Runner 客户端版本过低（当前 {client_version or '未知'}，"
                f"要求 >= {minimum}），请升级客户端。"
            ),
        )


async def get_version_info(request_base_url: str = "") -> dict:
    from app.core.runner_release import build_client_release_info
    from app.core.runner_release_config_service import enrich_release_info

    info = build_client_release_info(request_base_url)
    return await enrich_release_info(info, request_base_url)
