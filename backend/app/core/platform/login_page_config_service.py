"""登录页配置服务"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.core.infra.redis_client import redis_cli
from app.models.sys import SystemLoginPageConfig

logger = logging.getLogger(__name__)

CACHE_KEY = "system:login_page_config:v4"
CACHE_TTL_SECONDS = 120

# 清新 Pro：简约方案 opt1~opt4 + 自定义
PRO_BG_KEYS = frozenset({"opt1", "opt2", "opt3", "opt4", "custom"})
CLASSIC_BG_KEYS = frozenset({"classic1", "classic2", "classic3", "classic4", "legacy", "custom"})

LEGACY_PRO_KEY_MAP = {
    "pro1": "opt1",
    "pro2": "opt2",
    "pro3": "opt3",
    "pro4": "opt4",
}
LEGACY_CLASSIC_KEY_MAP = {
    "classic": "legacy",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "pro_bg_key": "opt3",
    "classic_bg_key": "classic1",
    "pro_bg_url": "",
    "classic_bg_url": "",
    "welcome_title": "欢迎登录 BrickCore",
    "footer_text": "© 2025-2026 BrickCore v1.7.0. All Rights Reserved.",
    "show_register": True,
    "bg_brick_count": 30,
    "bg_star_count": 15,
    "bg_dot_count": 15,
    "bg_motion_enabled": True,
}

BRICK_COUNT_MAX = 60
STAR_COUNT_MAX = 40
DOT_COUNT_MAX = 40


def _clamp_int(value: Any, default: int, max_value: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(max_value, n))


def normalize_pro_bg_key(key: str | None) -> str:
    value = (key or "").strip()
    value = LEGACY_PRO_KEY_MAP.get(value, value)
    if value in PRO_BG_KEYS:
        return value
    return DEFAULT_CONFIG["pro_bg_key"]


def normalize_classic_bg_key(key: str | None) -> str:
    value = (key or "").strip()
    value = LEGACY_CLASSIC_KEY_MAP.get(value, value)
    if value in CLASSIC_BG_KEYS:
        return value
    return DEFAULT_CONFIG["classic_bg_key"]


def _row_to_dict(row: SystemLoginPageConfig | None) -> dict[str, Any]:
    if not row:
        return {**DEFAULT_CONFIG, "update_by": "", "update_time": ""}
    return {
        "pro_bg_key": normalize_pro_bg_key(row.pro_bg_key),
        "classic_bg_key": normalize_classic_bg_key(row.classic_bg_key),
        "pro_bg_url": (getattr(row, "pro_bg_url", None) or "").strip(),
        "classic_bg_url": (getattr(row, "classic_bg_url", None) or "").strip(),
        "welcome_title": (row.welcome_title or DEFAULT_CONFIG["welcome_title"]).strip() or DEFAULT_CONFIG["welcome_title"],
        "footer_text": (row.footer_text or DEFAULT_CONFIG["footer_text"]).strip() or DEFAULT_CONFIG["footer_text"],
        "show_register": bool(row.show_register),
        "bg_brick_count": _clamp_int(getattr(row, "bg_brick_count", None), 30, BRICK_COUNT_MAX),
        "bg_star_count": _clamp_int(getattr(row, "bg_star_count", None), 15, STAR_COUNT_MAX),
        "bg_dot_count": _clamp_int(getattr(row, "bg_dot_count", None), 15, DOT_COUNT_MAX),
        "bg_motion_enabled": bool(getattr(row, "bg_motion_enabled", True)),
        "update_by": row.update_by or "",
        "update_time": row.update_time.strftime("%Y-%m-%d %H:%M:%S") if row.update_time else "",
    }


def _default_config_dict() -> dict[str, Any]:
    return {**DEFAULT_CONFIG, "update_by": "", "update_time": ""}


async def invalidate_login_page_config_cache() -> None:
    try:
        await redis_cli.delete(CACHE_KEY)
    except Exception as exc:
        logger.warning("登录页配置 Redis 删除失败: %s", exc)


async def get_login_page_config() -> dict[str, Any]:
    cached = None
    try:
        cached = await redis_cli.get(CACHE_KEY)
    except Exception as exc:
        logger.warning("登录页配置 Redis 读取失败，跳过缓存: %s", exc)

    if cached:
        try:
            return json.loads(cached)
        except (json.JSONDecodeError, TypeError):
            try:
                await invalidate_login_page_config_cache()
            except Exception:
                pass

    try:
        row = await SystemLoginPageConfig.first()
        data = _row_to_dict(row)
    except Exception as exc:
        logger.warning("读取登录页配置失败，使用默认值（请确认已执行数据库迁移 74/75）: %s", exc)
        data = _default_config_dict()

    try:
        await redis_cli.setex(CACHE_KEY, CACHE_TTL_SECONDS, json.dumps(data, ensure_ascii=False))
    except Exception as exc:
        logger.warning("登录页配置 Redis 写入失败: %s", exc)
    return data


async def get_login_page_public_config() -> dict[str, Any]:
    data = await get_login_page_config()
    return {
        "pro_bg_key": data["pro_bg_key"],
        "classic_bg_key": data["classic_bg_key"],
        "pro_bg_url": data.get("pro_bg_url", ""),
        "classic_bg_url": data.get("classic_bg_url", ""),
        "welcome_title": data["welcome_title"],
        "footer_text": data["footer_text"],
        "show_register": data["show_register"],
        "bg_brick_count": data["bg_brick_count"],
        "bg_star_count": data["bg_star_count"],
        "bg_dot_count": data["bg_dot_count"],
        "bg_motion_enabled": data["bg_motion_enabled"],
    }


async def save_login_page_config(
    *,
    pro_bg_key: str,
    classic_bg_key: str,
    pro_bg_url: str | None = None,
    classic_bg_url: str | None = None,
    welcome_title: str,
    footer_text: str,
    show_register: bool,
    bg_brick_count: int = 30,
    bg_star_count: int = 15,
    bg_dot_count: int = 15,
    bg_motion_enabled: bool = True,
    username: str,
) -> dict[str, Any]:
    pro_key = normalize_pro_bg_key(pro_bg_key)
    classic_key = normalize_classic_bg_key(classic_bg_key)
    payload: dict[str, Any] = {
        "pro_bg_key": pro_key,
        "classic_bg_key": classic_key,
        "welcome_title": (welcome_title or DEFAULT_CONFIG["welcome_title"]).strip()[:200],
        "footer_text": (footer_text or DEFAULT_CONFIG["footer_text"]).strip()[:500],
        "show_register": bool(show_register),
        "bg_brick_count": _clamp_int(bg_brick_count, 30, BRICK_COUNT_MAX),
        "bg_star_count": _clamp_int(bg_star_count, 15, STAR_COUNT_MAX),
        "bg_dot_count": _clamp_int(bg_dot_count, 15, DOT_COUNT_MAX),
        "bg_motion_enabled": bool(bg_motion_enabled),
        "update_by": username,
    }
    if pro_bg_url is not None:
        payload["pro_bg_url"] = (pro_bg_url or "").strip()[:500]
    if classic_bg_url is not None:
        payload["classic_bg_url"] = (classic_bg_url or "").strip()[:500]
    if pro_key != "custom":
        payload["pro_bg_url"] = ""
    if classic_key != "custom":
        payload["classic_bg_url"] = ""

    try:
        row = await SystemLoginPageConfig.first()
        if row:
            for k, v in payload.items():
                setattr(row, k, v)
            await row.save()
        else:
            row = await SystemLoginPageConfig.create(**payload)
        data = _row_to_dict(row)
    except Exception as exc:
        logger.exception("保存登录页配置失败: %s", exc)
        raise

    await invalidate_login_page_config_cache()
    return data
