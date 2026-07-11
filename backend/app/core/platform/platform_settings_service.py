"""平台全局设置服务"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.core.infra.redis_client import redis_cli
from app.models.sys import SystemPlatformSettings
from app.models.ui import UiCaseExecution

logger = logging.getLogger(__name__)

CACHE_KEY = "system:platform_settings:v1"
CACHE_TTL_SECONDS = 120

DELETE_MODE_LOGICAL = "logical"
DELETE_MODE_PHYSICAL = "physical"
DELETE_MODE_RECYCLE_BIN = "recycle_bin"
DELETE_MODES = frozenset({DELETE_MODE_LOGICAL, DELETE_MODE_PHYSICAL, DELETE_MODE_RECYCLE_BIN})

DEFAULT_SETTINGS: dict[str, Any] = {
    "ui_case_record_delete_mode": DELETE_MODE_LOGICAL,
    "knowledge_report_delete_mode": DELETE_MODE_LOGICAL,
}


def normalize_ui_case_record_delete_mode(mode: str | None) -> str:
    value = (mode or "").strip()
    if value in DELETE_MODES:
        return value
    return DEFAULT_SETTINGS["ui_case_record_delete_mode"]


def normalize_knowledge_report_delete_mode(mode: str | None) -> str:
    value = (mode or "").strip()
    if value in {DELETE_MODE_LOGICAL, DELETE_MODE_PHYSICAL}:
        return value
    return DEFAULT_SETTINGS["knowledge_report_delete_mode"]


def _row_to_dict(row: SystemPlatformSettings | None) -> dict[str, Any]:
    if not row:
        return {**DEFAULT_SETTINGS, "update_by": "", "update_time": ""}
    return {
        "ui_case_record_delete_mode": normalize_ui_case_record_delete_mode(row.ui_case_record_delete_mode),
        "knowledge_report_delete_mode": normalize_knowledge_report_delete_mode(
            getattr(row, "knowledge_report_delete_mode", None)
        ),
        "update_by": row.update_by or "",
        "update_time": row.update_time.strftime("%Y-%m-%d %H:%M:%S") if row.update_time else "",
    }


async def invalidate_platform_settings_cache() -> None:
    try:
        await redis_cli.delete(CACHE_KEY)
    except Exception as exc:
        logger.warning("平台设置 Redis 删除失败: %s", exc)


async def get_platform_settings() -> dict[str, Any]:
    cached = None
    try:
        cached = await redis_cli.get(CACHE_KEY)
    except Exception as exc:
        logger.warning("平台设置 Redis 读取失败，跳过缓存: %s", exc)

    if cached:
        try:
            return json.loads(cached)
        except (json.JSONDecodeError, TypeError):
            try:
                await invalidate_platform_settings_cache()
            except Exception:
                pass

    try:
        row = await SystemPlatformSettings.first()
        data = _row_to_dict(row)
    except Exception as exc:
        logger.warning("读取平台设置失败，使用默认值: %s", exc)
        data = {**DEFAULT_SETTINGS, "update_by": "", "update_time": ""}

    try:
        await redis_cli.setex(CACHE_KEY, CACHE_TTL_SECONDS, json.dumps(data, ensure_ascii=False))
    except Exception as exc:
        logger.warning("平台设置 Redis 写入失败: %s", exc)
    return data


async def get_ui_case_record_delete_mode() -> str:
    settings = await get_platform_settings()
    return normalize_ui_case_record_delete_mode(settings.get("ui_case_record_delete_mode"))


async def get_knowledge_report_delete_mode() -> str:
    settings = await get_platform_settings()
    return normalize_knowledge_report_delete_mode(settings.get("knowledge_report_delete_mode"))


async def save_platform_settings(
    *,
    ui_case_record_delete_mode: str | None = None,
    knowledge_report_delete_mode: str | None = None,
    username: str,
) -> dict[str, Any]:
    current = await get_platform_settings()
    payload = {
        "ui_case_record_delete_mode": normalize_ui_case_record_delete_mode(
            ui_case_record_delete_mode if ui_case_record_delete_mode is not None else current.get("ui_case_record_delete_mode")
        ),
        "knowledge_report_delete_mode": normalize_knowledge_report_delete_mode(
            knowledge_report_delete_mode
            if knowledge_report_delete_mode is not None
            else current.get("knowledge_report_delete_mode")
        ),
        "update_by": username,
    }
    row = await SystemPlatformSettings.first()
    if row:
        for key, value in payload.items():
            setattr(row, key, value)
        await row.save()
    else:
        row = await SystemPlatformSettings.create(**payload)
    await invalidate_platform_settings_cache()
    return _row_to_dict(row)


async def delete_ui_case_execution(record: UiCaseExecution, *, permanent: bool = False) -> str:
    """删除用例运行记录，返回 soft_deleted 或 hard_deleted。"""
    if permanent:
        await record.delete()
        return "hard_deleted"

    mode = await get_ui_case_record_delete_mode()
    if mode == DELETE_MODE_PHYSICAL:
        await record.delete()
        return "hard_deleted"

    record.is_del = True
    await record.save()
    return "soft_deleted"


async def restore_ui_case_execution(record: UiCaseExecution) -> None:
    record.is_del = False
    await record.save()


async def delete_app_case_execution(record, *, permanent: bool = False) -> str:
    """删除 App 用例运行记录，遵循平台 ui_case_record_delete_mode 配置。"""
    if permanent:
        await record.delete()
        return "hard_deleted"

    mode = await get_ui_case_record_delete_mode()
    if mode == DELETE_MODE_PHYSICAL:
        await record.delete()
        return "hard_deleted"

    record.is_del = True
    await record.save()
    return "soft_deleted"


async def restore_app_case_execution(record) -> None:
    record.is_del = False
    await record.save()


async def delete_iteration_report_record(report, *, permanent: bool = False) -> str:
    """删除资料库生成记录，遵循平台 knowledge_report_delete_mode 配置。"""
    from app.modules.knowledge.knowledge_storage import purge_report_output_files

    if permanent:
        await purge_report_output_files(report)
        await report.delete()
        return "hard_deleted"

    mode = await get_knowledge_report_delete_mode()
    if mode == DELETE_MODE_PHYSICAL:
        await purge_report_output_files(report)
        await report.delete()
        return "hard_deleted"

    report.is_del = True
    await report.save()
    return "soft_deleted"


async def delete_knowledge_document_record(doc, *, permanent: bool = False) -> str:
    """删除资料库上传文档，遵循平台 knowledge_report_delete_mode 配置。"""
    from app.models.knowledge import AiKnowledgeChunk
    from app.modules.knowledge.knowledge_storage import purge_document_source_files

    async def _hard_delete() -> None:
        purge_document_source_files(doc)
        await AiKnowledgeChunk.filter(document_id=doc.id).delete()
        await doc.delete()

    if permanent:
        await _hard_delete()
        return "hard_deleted"

    mode = await get_knowledge_report_delete_mode()
    if mode == DELETE_MODE_PHYSICAL:
        await _hard_delete()
        return "hard_deleted"

    doc.is_del = True
    await doc.save()
    return "soft_deleted"
