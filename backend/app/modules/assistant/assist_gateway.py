"""小测 / AI Skill 扩展包网关：探测 brickcore_assist、统一未安装错误契约。"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from fastapi import HTTPException

ASSIST_PREMIUM_REQUIRED_CODE = "assist_premium_required"
ASSIST_PREMIUM_INCOMPATIBLE_CODE = "assist_premium_incompatible"

DOC_PATH = "/guide/platform-assistant.html"


def _disabled_by_env() -> bool:
    raw = os.getenv("BRICKCORE_ASSIST_DISABLED", "").strip().lower()
    return raw in ("1", "true", "on", "yes")


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "on", "yes")


def standard_enabled_by_env() -> bool:
    """ASSIST_STANDARD_ENABLED=0|1。未设置时默认 0（单测/裸机）。

    Pro Docker 现网在 docker-compose.yml 写死 "1"；改 compose 后须 recreate backend。
    """
    raw = os.getenv("ASSIST_STANDARD_ENABLED", "0").strip().lower()
    return raw in ("1", "true", "on", "yes")


def _pack_meets_compat_min(pack_version: str | None) -> bool:
    floor = (os.getenv("BRICKCORE_ASSIST_COMPAT_MIN_PACK") or "").strip()
    if not floor or not pack_version:
        return False
    try:
        from app.core.runner.runner_version import compare_version

        return compare_version(str(pack_version), floor) >= 0
    except Exception:
        return False


def _resolve_compatible(mod: Any, platform_ver: str | None, pack_version: str | None) -> bool:
    if _truthy_env("BRICKCORE_ASSIST_SKIP_COMPAT_CHECK"):
        return True
    if bool(mod.is_compatible(platform_ver)):
        return True
    if _pack_meets_compat_min(pack_version):
        return True
    extra = (os.getenv("BRICKCORE_ASSIST_EXTRA_COMPAT_PREFIXES") or "").strip()
    if extra and platform_ver:
        ver = str(platform_ver).split("+")[0].split("-")[0].strip()
        for p in (x.strip() for x in extra.split(",")):
            if p and (ver == p or ver.startswith(p + ".")):
                return True
    return False


@lru_cache(maxsize=1)
def assist_premium_available() -> bool:
    """True=可探测到包；损坏包见 get_assist_premium_info.reason=package_import_error。"""
    if _disabled_by_env():
        return False
    try:
        import brickcore_assist  # noqa: F401

        return True
    except ImportError:
        return False
    except Exception:
        # 包文件存在但 import 异常：仍视为「已安装」，由 get_assist_premium_info 细化为损坏态
        return True


def clear_assist_premium_cache() -> None:
    assist_premium_available.cache_clear()
    get_assist_premium_info.cache_clear()


@lru_cache(maxsize=1)
def get_assist_premium_info() -> dict[str, Any]:
    """状态：未安装 / 损坏 / 不兼容 / 已装未 ready / ready。始终可安全调用（勿抛）。"""
    if _disabled_by_env():
        return {
            "installed": False,
            "compatible": False,
            "ready": False,
            "version": None,
            "api_version": None,
            "mode": "lite",
            "reason": "not_installed_or_disabled",
            "code": ASSIST_PREMIUM_REQUIRED_CODE,
            "message": "未检测到小测扩展包 brickcore_assist，已使用基础助手模式",
            "doc": DOC_PATH,
            "capabilities": [],
        }

    try:
        import brickcore_assist
    except ImportError:
        return {
            "installed": False,
            "compatible": False,
            "ready": False,
            "version": None,
            "api_version": None,
            "mode": "lite",
            "reason": "not_installed_or_disabled",
            "code": ASSIST_PREMIUM_REQUIRED_CODE,
            "message": "未检测到小测扩展包 brickcore_assist，已使用基础助手模式",
            "doc": DOC_PATH,
            "capabilities": [],
        }
    except Exception:
        return {
            "installed": True,
            "compatible": False,
            "ready": False,
            "version": None,
            "api_version": None,
            "mode": "lite",
            "reason": "package_import_error",
            "code": ASSIST_PREMIUM_REQUIRED_CODE,
            "message": "小测扩展包已安装但无法加载，已回退基础助手模式",
            "doc": DOC_PATH,
            "capabilities": [],
        }

    platform_ver = None
    try:
        from app.core.platform.config import PLATFORM_VERSION

        platform_ver = str(PLATFORM_VERSION)
    except Exception:
        platform_ver = os.getenv("PLATFORM_VERSION") or None

    try:
        info = brickcore_assist.package_info()
    except Exception:
        return {
            "installed": True,
            "compatible": False,
            "ready": False,
            "version": getattr(brickcore_assist, "__version__", None),
            "api_version": None,
            "mode": "lite",
            "reason": "package_import_error",
            "code": ASSIST_PREMIUM_REQUIRED_CODE,
            "message": "小测扩展包元数据读取失败，已回退基础助手模式",
            "doc": DOC_PATH,
            "capabilities": [],
        }

    pack_version = info.get("version")
    compatible = _resolve_compatible(brickcore_assist, platform_ver, pack_version)
    if not compatible:
        return {
            "installed": True,
            "compatible": False,
            "ready": False,
            "version": pack_version,
            "api_version": info.get("api_version"),
            "mode": "lite",
            "reason": "incompatible_platform",
            "code": ASSIST_PREMIUM_INCOMPATIBLE_CODE,
            "message": f"brickcore_assist {pack_version} 与平台 {platform_ver} 不兼容",
            "doc": DOC_PATH,
            "capabilities": [],
        }

    ready = bool(info.get("ready")) and standard_enabled_by_env()
    reason = None
    if not info.get("ready"):
        reason = info.get("reason") or "api_not_ready"
    elif not standard_enabled_by_env():
        reason = "standard_disabled_by_env"

    mode = "standard" if ready else "lite"
    return {
        "installed": True,
        "compatible": True,
        "ready": ready,
        "version": pack_version,
        "api_version": info.get("api_version"),
        "mode": mode,
        "reason": reason,
        "code": None if ready else None,
        "message": "ok" if ready else f"扩展包已安装，当前使用基础模式（{reason}）",
        "doc": DOC_PATH,
        "capabilities": list(info.get("capabilities") or []) if ready else [],
    }


def assist_premium_ready() -> bool:
    return bool(get_assist_premium_info().get("ready"))


def require_assist_premium() -> None:
    """skill-only / 高级 API：无包或未 ready 时抛业务错误（不用于普通 chat）。"""
    info = get_assist_premium_info()
    if info.get("ready"):
        return
    if info.get("installed") and not info.get("compatible"):
        raise HTTPException(
            status_code=503,
            detail={
                "code": ASSIST_PREMIUM_INCOMPATIBLE_CODE,
                "message": info.get("message"),
                "doc": DOC_PATH,
            },
        )
    raise HTTPException(
        status_code=503,
        detail={
            "code": ASSIST_PREMIUM_REQUIRED_CODE,
            "message": info.get("message")
            or "需要安装小测扩展包 brickcore_assist 后使用该能力",
            "doc": DOC_PATH,
            "reason": info.get("reason"),
        },
    )


def resolve_chat_mode() -> str:
    """chat 实际模式：仅 ready 时 standard，否则 lite。"""
    return str(get_assist_premium_info().get("mode") or "lite")
