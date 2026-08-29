"""测试管理扩展包网关：探测 brickcore_tm、统一未安装错误契约。"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Optional

from fastapi import HTTPException

TM_PREMIUM_REQUIRED_CODE = "tm_premium_required"
TM_PREMIUM_INCOMPATIBLE_CODE = "tm_premium_incompatible"

DOC_PATH = "/guide/brickcore-tm-pack.html"

PREMIUM_MODULE_NAMES: frozenset[str] = frozenset(
    {
        "quality_gate",
        "quality_service",
        "tm_quality_gate_settings",
        "assignment_notify_service",
        "inbox_sse",
        "tm_notify_settings",
        "user_notify_prefs",
        "release_intelligence_service",
        "export_service",
        "project_global_vars_patch",
    }
)


def _disabled_by_env() -> bool:
    raw = os.getenv("BRICKCORE_TM_DISABLED", "").strip().lower()
    return raw in ("1", "true", "on", "yes")


@lru_cache(maxsize=1)
def tm_premium_available() -> bool:
    """扩展包是否可导入（Pro 内置或 CE 已安装）。"""
    if _disabled_by_env():
        return False
    try:
        import brickcore_tm  # noqa: F401

        return True
    except ImportError:
        return False


def clear_tm_premium_cache() -> None:
    tm_premium_available.cache_clear()
    get_tm_premium_info.cache_clear()


@lru_cache(maxsize=1)
def get_tm_premium_info() -> dict[str, Any]:
    if not tm_premium_available():
        return {
            "installed": False,
            "compatible": False,
            "version": None,
            "code": TM_PREMIUM_REQUIRED_CODE,
            "message": "未检测到测试管理扩展包 brickcore_tm，高级能力不可用",
            "doc": DOC_PATH,
            "capabilities": [],
        }
    import brickcore_tm

    platform_ver = None
    try:
        from app.core.platform.config import PLATFORM_VERSION

        platform_ver = str(PLATFORM_VERSION)
    except Exception:
        platform_ver = os.getenv("PLATFORM_VERSION") or None

    compatible = bool(brickcore_tm.is_compatible(platform_ver))
    info = brickcore_tm.package_info()
    if not compatible:
        return {
            "installed": True,
            "compatible": False,
            "version": info.get("version"),
            "platform_version": platform_ver,
            "code": TM_PREMIUM_INCOMPATIBLE_CODE,
            "message": (
                f"测试管理扩展包 {info.get('version')} 与平台版本 "
                f"{platform_ver or '?'} 不兼容，请升级扩展包"
            ),
            "doc": DOC_PATH,
            "capabilities": info.get("capabilities") or [],
            "compatible_platform_prefixes": info.get("compatible_platform_prefixes") or [],
        }
    return {
        "installed": True,
        "compatible": True,
        "version": info.get("version"),
        "platform_version": platform_ver,
        "code": None,
        "message": "测试管理扩展包已就绪",
        "doc": DOC_PATH,
        "capabilities": info.get("capabilities") or [],
        "compatible_platform_prefixes": info.get("compatible_platform_prefixes") or [],
    }


def tm_premium_ready() -> bool:
    info = get_tm_premium_info()
    return bool(info.get("installed") and info.get("compatible"))


def premium_http_detail(info: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    data = info or get_tm_premium_info()
    return {
        "code": data.get("code") or TM_PREMIUM_REQUIRED_CODE,
        "message": data.get("message") or "请安装测试管理扩展包",
        "doc": data.get("doc") or DOC_PATH,
        "version": data.get("version"),
        "platform_version": data.get("platform_version"),
    }


def raise_tm_premium_required(info: Optional[dict[str, Any]] = None) -> None:
    detail = premium_http_detail(info)
    raise HTTPException(status_code=503, detail=detail)


def require_tm_premium() -> dict[str, Any]:
    """路由依赖：未安装或不兼容时抛 503。"""
    info = get_tm_premium_info()
    if not (info.get("installed") and info.get("compatible")):
        raise_tm_premium_required(info)
    return info


def load_premium_module(name: str) -> Any:
    """加载 brickcore_tm 子模块；不可用时返回 None。"""
    if name not in PREMIUM_MODULE_NAMES:
        raise ValueError(f"unknown premium module: {name}")
    if not tm_premium_ready():
        return None
    import importlib

    return importlib.import_module(f"brickcore_tm.{name}")


async def soft_premium_call(
    module_name: str,
    attr: str,
    *args,
    default: Any = None,
    **kwargs,
) -> Any:
    """副作用调用：未装扩展包时静默跳过，避免拖垮基础 CRUD。"""
    mod = load_premium_module(module_name)
    if mod is None:
        return default
    fn = getattr(mod, attr)
    return await fn(*args, **kwargs)