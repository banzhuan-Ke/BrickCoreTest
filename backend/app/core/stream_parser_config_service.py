"""SSE 流式解析配置 CRUD 与跑批解析复用。"""
from __future__ import annotations

import json
import time
from typing import Any

from app.core.stream_phase.parsers.rule_based import DEFAULT_RULES
from app.core.stream_phase.registry import get_parser, list_parsers, parse_stream_lines
from app.models.sys import SystemStreamParserConfig

BUILTIN_QA_SSE_CODE = "builtin_qa_sse_v1"
BUILTIN_RULE_KCF_CODE = "builtin_rule_kcf_v1"


def _default_success_rule(parser_id: str) -> dict[str, Any]:
    meta = get_parser(parser_id) or {}
    return dict(meta.get("default_success_rule") or {"type": "phase_exists", "phase": "first_char"})


def _row_to_dict(row: SystemStreamParserConfig) -> dict[str, Any]:
    meta = get_parser(row.parser_id) or {}
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description or "",
        "parser_id": row.parser_id,
        "parser_display_name": meta.get("display_name") or row.parser_id,
        "parser_options": row.parser_options if isinstance(row.parser_options, dict) else {},
        "success_rule": row.success_rule if isinstance(row.success_rule, dict) else {},
        "is_builtin": bool(row.is_builtin),
        "is_enabled": bool(row.is_enabled),
        "sort_order": row.sort_order or 0,
        "create_by": row.create_by or "",
        "update_by": row.update_by or "",
        "create_time": row.create_time.isoformat() if row.create_time else None,
        "update_time": row.update_time.isoformat() if row.update_time else None,
    }


async def ensure_builtin_stream_parser_configs() -> None:
    """启动时幂等写入内置解析配置。"""
    seeds = [
        {
            "code": BUILTIN_QA_SSE_CODE,
            "name": "问答流式 v1（KCF 默认）",
            "description": (
                "适用于 KCF `/api/v1/qa` 标准 SSE 协议：think / output_text / eof references。\n\n"
                "压测「流式阶段」与接口流式调试均可选用。"
            ),
            "parser_id": "qa_sse_v1",
            "parser_options": {},
            "success_rule": _default_success_rule("qa_sse_v1"),
            "sort_order": 10,
        },
        {
            "code": BUILTIN_RULE_KCF_CODE,
            "name": "KCF 规则版（可自定义阶段）",
            "description": (
                "基于「规则配置」解析器，预置 KCF 问答 SSE 阶段匹配规则。\n\n"
                "当被测接口字段与默认 v1 不一致时，可在此配置副本上调整 phases / derived 规则。"
            ),
            "parser_id": "rule_based",
            "parser_options": {"rules": DEFAULT_RULES},
            "success_rule": _default_success_rule("rule_based"),
            "sort_order": 20,
        },
    ]
    for spec in seeds:
        row = await SystemStreamParserConfig.get_or_none(
            name=spec["name"],
            is_del=False,
        )
        if row:
            if row.is_builtin and row.parser_id != spec["parser_id"]:
                row.parser_id = spec["parser_id"]
                await row.save(update_fields=["parser_id", "update_time"])
            continue
        await SystemStreamParserConfig.create(
            name=spec["name"],
            description=spec["description"],
            parser_id=spec["parser_id"],
            parser_options=spec["parser_options"],
            success_rule=spec["success_rule"],
            is_builtin=True,
            is_enabled=True,
            sort_order=spec["sort_order"],
            create_by="system",
            update_by="system",
        )


async def list_stream_parser_configs(*, enabled_only: bool = False) -> list[dict[str, Any]]:
    qs = SystemStreamParserConfig.filter(is_del=False)
    if enabled_only:
        qs = qs.filter(is_enabled=True)
    rows = await qs.order_by("sort_order", "id")
    return [_row_to_dict(r) for r in rows]


async def get_stream_parser_config(config_id: int) -> dict[str, Any] | None:
    row = await SystemStreamParserConfig.get_or_none(id=config_id, is_del=False)
    return _row_to_dict(row) if row else None


async def create_stream_parser_config(data: dict[str, Any], *, username: str) -> dict[str, Any]:
    parser_id = (data.get("parser_id") or "").strip()
    if not get_parser(parser_id):
        raise ValueError(f"未知解析器: {parser_id}")
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("配置名称不能为空")
    row = await SystemStreamParserConfig.create(
        name=name,
        description=(data.get("description") or "").strip() or None,
        parser_id=parser_id,
        parser_options=data.get("parser_options") if isinstance(data.get("parser_options"), dict) else {},
        success_rule=data.get("success_rule") if isinstance(data.get("success_rule"), dict) else _default_success_rule(parser_id),
        is_builtin=False,
        is_enabled=bool(data.get("is_enabled", True)),
        sort_order=int(data.get("sort_order") or 0),
        create_by=username,
        update_by=username,
    )
    return _row_to_dict(row)


async def update_stream_parser_config(config_id: int, data: dict[str, Any], *, username: str) -> dict[str, Any]:
    row = await SystemStreamParserConfig.get_or_none(id=config_id, is_del=False)
    if not row:
        raise ValueError("配置不存在")
    if "parser_id" in data:
        parser_id = (data.get("parser_id") or "").strip()
        if not get_parser(parser_id):
            raise ValueError(f"未知解析器: {parser_id}")
        row.parser_id = parser_id
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("配置名称不能为空")
        row.name = name
    if "description" in data:
        row.description = (data.get("description") or "").strip() or None
    if "parser_options" in data and isinstance(data.get("parser_options"), dict):
        row.parser_options = data["parser_options"]
    if "success_rule" in data and isinstance(data.get("success_rule"), dict):
        row.success_rule = data["success_rule"]
    if "is_enabled" in data:
        row.is_enabled = bool(data["is_enabled"])
    if "sort_order" in data:
        row.sort_order = int(data.get("sort_order") or 0)
    row.update_by = username
    await row.save()
    return _row_to_dict(row)


async def delete_stream_parser_config(config_id: int, *, username: str) -> None:
    row = await SystemStreamParserConfig.get_or_none(id=config_id, is_del=False)
    if not row:
        raise ValueError("配置不存在")
    if row.is_builtin:
        raise ValueError("内置配置不可删除，可改为停用")
    row.is_del = True
    row.update_by = username
    await row.save(update_fields=["is_del", "update_by", "update_time"])


async def resolve_parser_spec(cfg: dict[str, Any]) -> dict[str, Any]:
    """从被测 API 配置或解析配置 ID 解析出 parser_id / options / success_rule。"""
    config_id = cfg.get("sse_parser_config_id")
    if config_id:
        row = await SystemStreamParserConfig.get_or_none(
            id=int(config_id),
            is_del=False,
            is_enabled=True,
        )
        if row:
            return {
                "parser_id": row.parser_id,
                "parser_options": row.parser_options if isinstance(row.parser_options, dict) else {},
                "success_rule": row.success_rule if isinstance(row.success_rule, dict) else {},
                "config_id": row.id,
                "config_name": row.name,
            }
    from app.modules.stream_phase.parsers.qa_sse_v1 import normalize_sse_parser

    parser_id = normalize_sse_parser(cfg.get("sse_parser"))
    return {
        "parser_id": parser_id,
        "parser_options": cfg.get("parser_options") if isinstance(cfg.get("parser_options"), dict) else {},
        "success_rule": cfg.get("success_rule") if isinstance(cfg.get("success_rule"), dict) else {},
        "config_id": None,
        "config_name": None,
    }


def extract_qa_fields_from_parse_result(result: dict[str, Any]) -> dict[str, Any]:
    extras = result.get("extras") if isinstance(result.get("extras"), dict) else {}
    answer = extras.get("answer") or extras.get("answer_preview") or ""
    if answer == "无答案返回":
        answer = ""
    success = bool(result.get("success")) and bool(str(answer).strip())
    if not success and result.get("success") and not answer:
        success = False
    return {
        "actual_answer": str(answer)[:16000],
        "thinking": (extras.get("thinking") or "")[:8000],
        "references_all": (extras.get("references_all") or "")[:4000],
        "references_high": (extras.get("references_high") or "")[:4000],
        "status": "success" if success else "fail",
    }


def parse_sse_lines_for_stream_qa(
    lines: list[str],
    *,
    parser_id: str,
    parser_options: dict | None = None,
    success_rule: dict | None = None,
    started: float | None = None,
) -> dict[str, Any]:
    """统一 SSE 解析入口（流式接口调试 / 压测）。"""
    from app.modules.stream_phase.parsers.qa_sse_v1 import is_qa_sse_v1_parser, parse_qa_sse_v1

    if is_qa_sse_v1_parser(parser_id):
        return parse_qa_sse_v1(lines)

    st = started if started is not None else time.perf_counter()
    options = dict(parser_options or {})
    sr = success_rule if isinstance(success_rule, dict) and success_rule else options.pop("success_rule", None)
    result = parse_stream_lines(
        parser_id,
        lines,
        start_time=st,
        options=options,
        success_rule=sr,
    )
    return extract_qa_fields_from_parse_result(result)


def list_builtin_parsers() -> list[dict[str, Any]]:
    return list_parsers()


async def test_stream_parser_config(
    *,
    parser_id: str,
    lines: list[str],
    parser_options: dict | None = None,
    success_rule: dict | None = None,
) -> dict[str, Any]:
    if not get_parser(parser_id):
        raise ValueError(f"未知解析器: {parser_id}")
    started = time.perf_counter()
    qa_fields = parse_sse_lines_for_stream_qa(
        lines,
        parser_id=parser_id,
        parser_options=parser_options,
        success_rule=success_rule,
        started=started,
    )
    raw = parse_stream_lines(
        parser_id,
        lines,
        start_time=started,
        options=parser_options or {},
        success_rule=success_rule,
    )
    return {
        "qa_fields": qa_fields,
        "parse_result": raw,
        "raw_line_count": len(lines),
    }
