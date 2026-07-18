"""Runner 客户端 / 引擎版本校验"""
from __future__ import annotations

from fastapi import HTTPException

from app.core.platform import config as settings


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


def _looks_like_runner_engine_version(version: str) -> bool:
    """区分引擎 semver（如 1.0.3）与 OS build（如 Windows 10.0.26200）。"""
    parts = parse_version(version)
    if not parts:
        return False
    # 产品引擎主版本目前为 1.x；宿主 OS 常见 10+/13+，不得当作引擎版本放行
    return 0 < parts[0] <= 2


def ensure_engine_version_for_recording(engine_version: str) -> None:
    """录制依赖 recorder_locator_rank；引擎过低时在 Backend 显式拒绝，避免 Runner 侧 ImportError。"""
    minimum = getattr(settings, "RUNNER_ENGINE_VERSION_MIN", None) or settings.RUNNER_ENGINE_VERSION
    current = (engine_version or "").strip()
    if not current or not _looks_like_runner_engine_version(current):
        raise HTTPException(
            status_code=400,
            detail=(
                f"无法确认 Runner 引擎版本（当前上报: {current or '空'}）。"
                f"录制需要引擎 >= {minimum}，请升级执行器并重新上线后再录制。"
            ),
        )
    if compare_version(current, minimum) < 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Runner 引擎版本过低（当前 {current}，录制要求 >= {minimum}），"
                f"请升级执行器后再开始录制。"
            ),
        )


async def get_version_info(request_base_url: str = "") -> dict:
    from app.core.platform.edition import is_community_edition
    from app.core.runner.runner_release import build_client_release_info
    from app.core.runner.runner_release_config_service import enrich_release_info

    info = build_client_release_info(request_base_url)
    info = await enrich_release_info(info, request_base_url)
    info["community_edition"] = is_community_edition()
    info["platform_version"] = settings.PLATFORM_VERSION
    return info
