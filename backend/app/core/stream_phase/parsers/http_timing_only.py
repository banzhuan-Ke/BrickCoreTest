"""仅统计整体耗时的流式解析器（无阶段拆分）"""
from __future__ import annotations

import time
from typing import Any

from app.core.stream_phase.timing import stream_end_elapsed

PARSER_ID = "http_timing_only"
DISPLAY_NAME = "仅总耗时"

PHASE_SCHEMA = [
    {"key": "total_time", "label": "整体耗时(s)", "unit": "s", "aggregate": True},
]


def parse_stream(
    lines: list[str],
    *,
    start_time: float,
    status_code: int = 200,
    options: dict | None = None,
    line_elapsed: list[float] | None = None,
) -> dict[str, Any]:
    total_time = round(stream_end_elapsed(line_elapsed, start_time), 3)
    success = status_code < 400
    error = None if success else f"HTTP {status_code}"
    return {
        "parser_id": PARSER_ID,
        "success": success,
        "total_time_s": total_time,
        "status_code": status_code,
        "phases": {"total_time": total_time},
        "extras": {"lines_received": len(lines)},
        "error": error,
        "phase_schema": PHASE_SCHEMA,
        "extra_schema": [{"key": "lines_received", "label": "接收行数"}],
    }
