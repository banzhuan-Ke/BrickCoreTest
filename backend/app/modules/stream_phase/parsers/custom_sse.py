"""自定义 SSE：规则匹配 + 可配置行前缀（datas:/events: 等）。

复用 rule_based 解析逻辑；默认规则含 data/event/id 前缀，供其它组非标准 SSE 使用。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.modules.stream_phase.parsers import rule_based as _rb

PARSER_ID = "custom_sse"
DISPLAY_NAME = "自定义 SSE"

DEFAULT_RULES = deepcopy(_rb.DEFAULT_RULES)
DEFAULT_RULES.update({
    "data_prefix": "data:",
    "event_prefix": "event:",
    "id_prefix": "id:",
    # 非帧模式时与 data_prefix 对齐；UI 改 data_prefix 时会同步
    "line_prefix": "data:",
})


def parse_stream(
    lines: list[str],
    *,
    start_time: float,
    status_code: int = 200,
    options: dict | None = None,
    line_elapsed: list[float] | None = None,
) -> dict[str, Any]:
    opts = dict(options or {})
    rules = deepcopy(DEFAULT_RULES)
    user_rules = opts.get("rules") or {}
    if isinstance(user_rules, dict):
        rules.update(user_rules)
    # 未显式配 line_prefix 时跟随 data_prefix
    if "line_prefix" not in user_rules and rules.get("data_prefix"):
        rules["line_prefix"] = rules["data_prefix"]
    opts["rules"] = rules
    return _rb.parse_stream(
        lines,
        start_time=start_time,
        status_code=status_code,
        options=opts,
        line_elapsed=line_elapsed,
    )
