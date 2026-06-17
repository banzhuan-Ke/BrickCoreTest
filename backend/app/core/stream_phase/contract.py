"""流式阶段压测统一数据契约"""
from __future__ import annotations

from typing import Any, Optional

# 模式别名
STREAM_BURST_MODE = "stream_burst"
LEGACY_SSE_BURST_MODE = "sse_burst"


def normalize_perf_mode(mode: Optional[str]) -> str:
    m = (mode or "fixed").strip()
    if m == LEGACY_SSE_BURST_MODE:
        return STREAM_BURST_MODE
    return m


def is_stream_burst_mode(mode: Optional[str]) -> bool:
    return normalize_perf_mode(mode) == STREAM_BURST_MODE


def has_stream_profile_config(config: dict) -> bool:
    """场景 config 中显式配置了 stream_profile（含 parser_id）。"""
    raw = config.get("stream_profile")
    if not raw or not isinstance(raw, dict):
        return False
    return bool((raw.get("parser_id") or "").strip())


def use_stream_execution(config: dict) -> bool:
    """是否用流式引擎执行请求（stream_burst 或 fixed/loop/stepping 配置了 stream_profile）。"""
    if is_stream_burst_mode(config.get("mode")):
        return True
    return has_stream_profile_config(config)


def default_stream_profile(parser_id: str = "qa_sse_v1") -> dict[str, Any]:
    return {
        "transport": "sse",
        "parser_id": parser_id,
        "parser_options": {},
        "success_rule": {"type": "phase_exists", "phase": "first_char"},
        "timeout_seconds": 600,
    }


def normalize_stream_profile(config: dict) -> dict[str, Any]:
    """从场景 config 提取并补全 stream_profile（兼容旧 sse_burst 无 profile）。"""
    profile = dict(config.get("stream_profile") or {})
    if not profile.get("parser_id"):
        profile["parser_id"] = "qa_sse_v1"
    if not profile.get("transport"):
        profile["transport"] = "sse"
    if not profile.get("success_rule"):
        profile["success_rule"] = {"type": "phase_exists", "phase": "first_char"}
    if not profile.get("timeout_seconds"):
        profile["timeout_seconds"] = 600
    if "parser_options" not in profile:
        profile["parser_options"] = {}
    return profile


def empty_parse_result(parser_id: str, status_code: int = 0) -> dict[str, Any]:
    return {
        "parser_id": parser_id,
        "success": False,
        "total_time_s": None,
        "status_code": status_code,
        "phases": {},
        "extras": {},
        "error": None,
        "phase_schema": [],
    }
