"""平台全局设置服务"""
from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import Any

from app.core.infra.redis_client import redis_cli
from app.models.sys import SystemPlatformSettings
from app.models.ui import UiCaseExecution, UiPlanExecution, UiSuiteExecution

logger = logging.getLogger(__name__)

CACHE_KEY = "system:platform_settings:v4"
CACHE_TTL_SECONDS = 120

DELETE_MODE_LOGICAL = "logical"
DELETE_MODE_PHYSICAL = "physical"
DELETE_MODE_RECYCLE_BIN = "recycle_bin"
DELETE_MODES = frozenset({DELETE_MODE_LOGICAL, DELETE_MODE_PHYSICAL, DELETE_MODE_RECYCLE_BIN})

# 小测护栏：平台配置优先；与 GuardConfig.from_env 范围对齐
ASSIST_LLM_TIMEOUT_MIN = 20
ASSIST_LLM_TIMEOUT_MAX = 600
ASSIST_MAX_WALL_MIN = 30
ASSIST_MAX_WALL_MAX = 600
ASSIST_FAILURE_DIGEST_ROUNDS_MIN = 1
ASSIST_FAILURE_DIGEST_ROUNDS_MAX = 8
ASSIST_MAX_TOKENS_MIN = 8_000
ASSIST_MAX_TOKENS_MAX = 200_000
ASSIST_MAX_PLAN_ROUNDS_MIN = 1
ASSIST_MAX_PLAN_ROUNDS_MAX = 12
ASSIST_MAX_TOOLS_PER_ROUND_MIN = 1
ASSIST_MAX_TOOLS_PER_ROUND_MAX = 8
ASSIST_TOOL_RESULT_CHARS_MIN = 2_000
ASSIST_TOOL_RESULT_CHARS_MAX = 20_000
ASSIST_TOOL_LIST_LIMIT_MIN = 3
ASSIST_TOOL_LIST_LIMIT_MAX = 30
ASSIST_SUMMARY_TRIGGER_MIN = 8
ASSIST_SUMMARY_TRIGGER_MAX = 40
ASSIST_HISTORY_TURNS_MIN = 2
ASSIST_HISTORY_TURNS_MAX = 12

DEFAULT_SETTINGS: dict[str, Any] = {
    "ui_case_record_delete_mode": DELETE_MODE_LOGICAL,
    "knowledge_report_delete_mode": DELETE_MODE_LOGICAL,
    "assist_llm_timeout_sec": 180,
    "assist_max_wall_sec": 240,
    "assist_failure_digest_max_rounds": 4,
    "assist_max_tokens_total": 80_000,
    "assist_max_plan_rounds": 5,
    "assist_max_tools_per_round": 4,
    "assist_tool_result_max_chars": 6_000,
    "assist_tool_list_item_limit": 8,
    "assist_session_summary_trigger": 16,
    "assist_history_turns": 4,
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


def normalize_assist_llm_timeout_sec(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = int(DEFAULT_SETTINGS["assist_llm_timeout_sec"])
    return max(ASSIST_LLM_TIMEOUT_MIN, min(ASSIST_LLM_TIMEOUT_MAX, n))


def normalize_assist_max_wall_sec(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = int(DEFAULT_SETTINGS["assist_max_wall_sec"])
    return max(ASSIST_MAX_WALL_MIN, min(ASSIST_MAX_WALL_MAX, n))


def normalize_assist_failure_digest_max_rounds(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = int(DEFAULT_SETTINGS["assist_failure_digest_max_rounds"])
    return max(ASSIST_FAILURE_DIGEST_ROUNDS_MIN, min(ASSIST_FAILURE_DIGEST_ROUNDS_MAX, n))


def normalize_assist_max_tokens_total(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = int(DEFAULT_SETTINGS["assist_max_tokens_total"])
    return max(ASSIST_MAX_TOKENS_MIN, min(ASSIST_MAX_TOKENS_MAX, n))


def _clamp_int(value: Any, *, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def normalize_assist_max_plan_rounds(value: Any) -> int:
    return _clamp_int(
        value,
        default=int(DEFAULT_SETTINGS["assist_max_plan_rounds"]),
        lo=ASSIST_MAX_PLAN_ROUNDS_MIN,
        hi=ASSIST_MAX_PLAN_ROUNDS_MAX,
    )


def normalize_assist_max_tools_per_round(value: Any) -> int:
    return _clamp_int(
        value,
        default=int(DEFAULT_SETTINGS["assist_max_tools_per_round"]),
        lo=ASSIST_MAX_TOOLS_PER_ROUND_MIN,
        hi=ASSIST_MAX_TOOLS_PER_ROUND_MAX,
    )


def normalize_assist_tool_result_max_chars(value: Any) -> int:
    return _clamp_int(
        value,
        default=int(DEFAULT_SETTINGS["assist_tool_result_max_chars"]),
        lo=ASSIST_TOOL_RESULT_CHARS_MIN,
        hi=ASSIST_TOOL_RESULT_CHARS_MAX,
    )


def normalize_assist_tool_list_item_limit(value: Any) -> int:
    return _clamp_int(
        value,
        default=int(DEFAULT_SETTINGS["assist_tool_list_item_limit"]),
        lo=ASSIST_TOOL_LIST_LIMIT_MIN,
        hi=ASSIST_TOOL_LIST_LIMIT_MAX,
    )


def normalize_assist_session_summary_trigger(value: Any) -> int:
    return _clamp_int(
        value,
        default=int(DEFAULT_SETTINGS["assist_session_summary_trigger"]),
        lo=ASSIST_SUMMARY_TRIGGER_MIN,
        hi=ASSIST_SUMMARY_TRIGGER_MAX,
    )


def normalize_assist_history_turns(value: Any) -> int:
    return _clamp_int(
        value,
        default=int(DEFAULT_SETTINGS["assist_history_turns"]),
        lo=ASSIST_HISTORY_TURNS_MIN,
        hi=ASSIST_HISTORY_TURNS_MAX,
    )


def _row_to_dict(row: SystemPlatformSettings | None) -> dict[str, Any]:
    if not row:
        return {**DEFAULT_SETTINGS, "update_by": "", "update_time": ""}
    return {
        "ui_case_record_delete_mode": normalize_ui_case_record_delete_mode(row.ui_case_record_delete_mode),
        "knowledge_report_delete_mode": normalize_knowledge_report_delete_mode(
            getattr(row, "knowledge_report_delete_mode", None)
        ),
        "assist_llm_timeout_sec": normalize_assist_llm_timeout_sec(
            getattr(row, "assist_llm_timeout_sec", None)
        ),
        "assist_max_wall_sec": normalize_assist_max_wall_sec(
            getattr(row, "assist_max_wall_sec", None)
        ),
        "assist_failure_digest_max_rounds": normalize_assist_failure_digest_max_rounds(
            getattr(row, "assist_failure_digest_max_rounds", None)
        ),
        "assist_max_tokens_total": normalize_assist_max_tokens_total(
            getattr(row, "assist_max_tokens_total", None)
        ),
        "assist_max_plan_rounds": normalize_assist_max_plan_rounds(
            getattr(row, "assist_max_plan_rounds", None)
        ),
        "assist_max_tools_per_round": normalize_assist_max_tools_per_round(
            getattr(row, "assist_max_tools_per_round", None)
        ),
        "assist_tool_result_max_chars": normalize_assist_tool_result_max_chars(
            getattr(row, "assist_tool_result_max_chars", None)
        ),
        "assist_tool_list_item_limit": normalize_assist_tool_list_item_limit(
            getattr(row, "assist_tool_list_item_limit", None)
        ),
        "assist_session_summary_trigger": normalize_assist_session_summary_trigger(
            getattr(row, "assist_session_summary_trigger", None)
        ),
        "assist_history_turns": normalize_assist_history_turns(
            getattr(row, "assist_history_turns", None)
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


async def resolve_assist_guard_config():
    """平台配置覆盖超时 / Token / 轮次 / 压缩参数；其余护栏仍读环境变量。"""
    from brickcore_assist.orchestrator.guards import GuardConfig

    base = GuardConfig.from_env()
    try:
        settings = await get_platform_settings()
        llm_to = float(
            normalize_assist_llm_timeout_sec(settings.get("assist_llm_timeout_sec"))
        )
        wall = float(normalize_assist_max_wall_sec(settings.get("assist_max_wall_sec")))
        tokens = int(
            normalize_assist_max_tokens_total(settings.get("assist_max_tokens_total"))
        )
        if wall < llm_to:
            wall = llm_to
        return replace(
            base,
            llm_timeout_sec=llm_to,
            max_wall_sec=wall,
            max_tokens_total=tokens,
            max_plan_rounds=normalize_assist_max_plan_rounds(
                settings.get("assist_max_plan_rounds")
            ),
            max_tools_per_round=normalize_assist_max_tools_per_round(
                settings.get("assist_max_tools_per_round")
            ),
            tool_result_max_chars=normalize_assist_tool_result_max_chars(
                settings.get("assist_tool_result_max_chars")
            ),
            tool_list_item_limit=normalize_assist_tool_list_item_limit(
                settings.get("assist_tool_list_item_limit")
            ),
            history_turns=normalize_assist_history_turns(
                settings.get("assist_history_turns")
            ),
        )
    except Exception as exc:
        logger.warning("读取小测护栏配置失败，回退环境变量: %s", exc)
        return base


async def save_platform_settings(
    *,
    ui_case_record_delete_mode: str | None = None,
    knowledge_report_delete_mode: str | None = None,
    assist_llm_timeout_sec: int | None = None,
    assist_max_wall_sec: int | None = None,
    assist_failure_digest_max_rounds: int | None = None,
    assist_max_tokens_total: int | None = None,
    assist_max_plan_rounds: int | None = None,
    assist_max_tools_per_round: int | None = None,
    assist_tool_result_max_chars: int | None = None,
    assist_tool_list_item_limit: int | None = None,
    assist_session_summary_trigger: int | None = None,
    assist_history_turns: int | None = None,
    username: str,
) -> dict[str, Any]:
    current = await get_platform_settings()

    def _pick(key: str, incoming: Any, normalizer):
        raw = incoming if incoming is not None else current.get(key)
        return normalizer(raw)

    payload = {
        "ui_case_record_delete_mode": normalize_ui_case_record_delete_mode(
            ui_case_record_delete_mode
            if ui_case_record_delete_mode is not None
            else current.get("ui_case_record_delete_mode")
        ),
        "knowledge_report_delete_mode": normalize_knowledge_report_delete_mode(
            knowledge_report_delete_mode
            if knowledge_report_delete_mode is not None
            else current.get("knowledge_report_delete_mode")
        ),
        "assist_llm_timeout_sec": _pick(
            "assist_llm_timeout_sec", assist_llm_timeout_sec, normalize_assist_llm_timeout_sec
        ),
        "assist_max_wall_sec": _pick(
            "assist_max_wall_sec", assist_max_wall_sec, normalize_assist_max_wall_sec
        ),
        "assist_failure_digest_max_rounds": _pick(
            "assist_failure_digest_max_rounds",
            assist_failure_digest_max_rounds,
            normalize_assist_failure_digest_max_rounds,
        ),
        "assist_max_tokens_total": _pick(
            "assist_max_tokens_total", assist_max_tokens_total, normalize_assist_max_tokens_total
        ),
        "assist_max_plan_rounds": _pick(
            "assist_max_plan_rounds", assist_max_plan_rounds, normalize_assist_max_plan_rounds
        ),
        "assist_max_tools_per_round": _pick(
            "assist_max_tools_per_round",
            assist_max_tools_per_round,
            normalize_assist_max_tools_per_round,
        ),
        "assist_tool_result_max_chars": _pick(
            "assist_tool_result_max_chars",
            assist_tool_result_max_chars,
            normalize_assist_tool_result_max_chars,
        ),
        "assist_tool_list_item_limit": _pick(
            "assist_tool_list_item_limit",
            assist_tool_list_item_limit,
            normalize_assist_tool_list_item_limit,
        ),
        "assist_session_summary_trigger": _pick(
            "assist_session_summary_trigger",
            assist_session_summary_trigger,
            normalize_assist_session_summary_trigger,
        ),
        "assist_history_turns": _pick(
            "assist_history_turns", assist_history_turns, normalize_assist_history_turns
        ),
        "update_by": username,
    }
    if payload["assist_max_wall_sec"] < payload["assist_llm_timeout_sec"]:
        payload["assist_max_wall_sec"] = payload["assist_llm_timeout_sec"]
    row = await SystemPlatformSettings.first()
    if row:
        for key, value in payload.items():
            setattr(row, key, value)
        await row.save()
    else:
        row = await SystemPlatformSettings.create(**payload)
    await invalidate_platform_settings_cache()
    return _row_to_dict(row)


async def _ui_record_should_hard_delete(*, permanent: bool = False) -> bool:
    if permanent:
        return True
    mode = await get_ui_case_record_delete_mode()
    return mode == DELETE_MODE_PHYSICAL


async def delete_ui_case_execution(record: UiCaseExecution, *, permanent: bool = False) -> str:
    """删除用例运行记录，返回 soft_deleted 或 hard_deleted。"""
    if await _ui_record_should_hard_delete(permanent=permanent):
        await record.delete()
        return "hard_deleted"

    record.is_del = True
    await record.save()
    return "soft_deleted"


async def restore_ui_case_execution(record: UiCaseExecution) -> None:
    record.is_del = False
    await record.save()


async def delete_ui_suite_execution(record: UiSuiteExecution, *, permanent: bool = False) -> str:
    """删除套件运行记录并级联处理下属用例记录。套件/计划无回收站时 recycle_bin 等同逻辑删除。"""
    suite_id = record.id
    hard = await _ui_record_should_hard_delete(permanent=permanent)
    if hard:
        await UiCaseExecution.filter(suite_execution_id=suite_id).delete()
        await record.delete()
        return "hard_deleted"

    await UiCaseExecution.filter(suite_execution_id=suite_id, is_del=False).update(is_del=True)
    record.is_del = True
    await record.save()
    return "soft_deleted"


async def delete_ui_plan_execution(record: UiPlanExecution, *, permanent: bool = False) -> str:
    """删除计划运行记录并级联处理下属套件与用例记录。"""
    plan_id = record.id
    suite_ids = list(
        await UiSuiteExecution.filter(plan_execution_id=plan_id).values_list("id", flat=True)
    )
    hard = await _ui_record_should_hard_delete(permanent=permanent)
    if hard:
        if suite_ids:
            await UiCaseExecution.filter(suite_execution_id__in=suite_ids).delete()
            await UiSuiteExecution.filter(id__in=suite_ids).delete()
        await record.delete()
        return "hard_deleted"

    if suite_ids:
        await UiCaseExecution.filter(suite_execution_id__in=suite_ids, is_del=False).update(is_del=True)
        await UiSuiteExecution.filter(id__in=suite_ids, is_del=False).update(is_del=True)
    record.is_del = True
    await record.save()
    return "soft_deleted"


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


async def delete_app_device_apm_session(record, *, permanent: bool = False) -> str:
    """删除独立设备性能监控记录，遵循平台 ui_case_record_delete_mode 配置。"""
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
    try:
        from app.modules.knowledge.knowledge_storage import purge_report_output_files
    except ImportError:
        # CE：资料库模块未打包
        if permanent:
            await report.delete()
            return "hard_deleted"
        report.is_del = True
        await report.save()
        return "soft_deleted"

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

    try:
        from app.modules.knowledge.knowledge_storage import purge_document_source_files
    except ImportError:
        async def _hard_delete() -> None:
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
