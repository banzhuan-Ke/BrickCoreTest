"""流式阶段计时辅助（按 SSE 行到达时刻，而非事后批量解析时刻）。"""
from __future__ import annotations

import time


def line_elapsed_at(index: int, line_elapsed: list[float] | None, start_time: float) -> float:
    if line_elapsed and 0 <= index < len(line_elapsed):
        return line_elapsed[index]
    return time.time() - start_time


def stream_end_elapsed(
    line_elapsed: list[float] | None,
    start_time: float,
    *,
    done_at: float | None = None,
) -> float:
    if done_at is not None:
        return done_at
    if line_elapsed:
        return line_elapsed[-1]
    return time.time() - start_time
