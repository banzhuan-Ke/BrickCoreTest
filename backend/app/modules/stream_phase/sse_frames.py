"""SSE 帧拼包：将 event:/id:/data: 行合成可匹配的一帧。

与 runner/tools/stream_phase/sse_frames.py 保持同步（仅允许模块 docstring 差异）。
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional


def _line_text(line: Any) -> str:
    if line is None:
        return ""
    if isinstance(line, bytes):
        return line.decode("utf-8", errors="replace")
    return str(line)


def _elapsed_at(
    index: int,
    line_elapsed: list[float] | None,
    start_time: float | None,
) -> float:
    if line_elapsed and 0 <= index < len(line_elapsed):
        return float(line_elapsed[index])
    if start_time is not None:
        return time.time() - start_time
    return 0.0


def _looks_complete_json(raw: str) -> bool:
    s = (raw or "").strip()
    if not s or s[0] not in ("{", "["):
        return False
    try:
        json.loads(s)
        return True
    except json.JSONDecodeError:
        return False


def _parse_data_obj(raw: str) -> Optional[dict[str, Any]]:
    s = (raw or "").strip()
    if not s:
        return {}
    if s[0] not in ("{", "["):
        return None
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        return data
    # 顶层数组：不展开进 match，保留空 dict，原始在 data_raw
    return {}


def _norm_field_prefix(value: Any, default: str) -> str:
    s = str(value if value is not None else "").strip() or default
    return s


def coalesce_sse_frames(
    lines: list[Any],
    *,
    line_elapsed: list[float] | None = None,
    start_time: float | None = None,
    data_prefix: str = "data:",
    event_prefix: str = "event:",
    id_prefix: str = "id:",
) -> list[dict[str, Any]]:
    """将原始 SSE 行拼成帧列表。

    每帧：
      event: Optional[str]   # 无 event 行为 None（注入匹配时用空串）
      id: Optional[str]
      data_raw: str
      data_obj: Optional[dict]  # JSON 对象；解析失败为 None；空 data 为 {}
      elapsed: float          # 帧内最后一行耗时
      line_indices: list[int]

    可通过 data_prefix / event_prefix / id_prefix 适配非标准行首（如 datas: / events:）。
    匹配按前缀长度从长到短，避免 data: 误吃 datas:。
    """
    data_pfx = _norm_field_prefix(data_prefix, "data:")
    event_pfx = _norm_field_prefix(event_prefix, "event:")
    id_pfx = _norm_field_prefix(id_prefix, "id:")
    # 最长优先，避免短前缀抢匹配
    prefix_kinds = sorted(
        [
            ("event", event_pfx),
            ("id", id_pfx),
            ("data", data_pfx),
        ],
        key=lambda x: len(x[1]),
        reverse=True,
    )

    frames: list[dict[str, Any]] = []

    cur_event: Optional[str] = None
    cur_id: Optional[str] = None
    cur_data_parts: list[str] = []
    cur_indices: list[int] = []
    cur_elapsed = 0.0
    has_field = False

    def _reset() -> None:
        nonlocal cur_event, cur_id, cur_data_parts, cur_indices, cur_elapsed, has_field
        cur_event = None
        cur_id = None
        cur_data_parts = []
        cur_indices = []
        cur_elapsed = 0.0
        has_field = False

    def _flush() -> None:
        nonlocal has_field
        if not has_field:
            return
        data_raw = "\n".join(cur_data_parts)
        frames.append(
            {
                "event": cur_event,
                "id": cur_id,
                "data_raw": data_raw,
                "data_obj": _parse_data_obj(data_raw) if data_raw.strip() else {},
                "elapsed": cur_elapsed,
                "line_indices": list(cur_indices),
            }
        )
        _reset()

    for idx, raw_line in enumerate(lines or []):
        line = _line_text(raw_line).rstrip("\r")
        elapsed = _elapsed_at(idx, line_elapsed, start_time)

        # 空行：结束一帧
        if not line.strip():
            _flush()
            continue

        # SSE 注释
        if line.startswith(":"):
            continue

        kind = None
        matched_pfx = ""
        for k, pfx in prefix_kinds:
            if pfx and line.startswith(pfx):
                kind = k
                matched_pfx = pfx
                break
        if kind is None:
            # 其它行（如 retry:）忽略，不打断当前帧
            continue

        payload = line[len(matched_pfx):]
        if kind == "event":
            val = payload.lstrip()
            if has_field and cur_event is not None:
                _flush()
            cur_event = val
            cur_indices.append(idx)
            cur_elapsed = elapsed
            has_field = True
            continue

        if kind == "id":
            val = payload.lstrip()
            if has_field and cur_id is not None:
                _flush()
            cur_id = val
            cur_indices.append(idx)
            cur_elapsed = elapsed
            has_field = True
            continue

        # data
        if payload.startswith(" "):
            payload = payload[1:]
        if (
            has_field
            and cur_data_parts
            and _looks_complete_json("\n".join(cur_data_parts))
            and payload.lstrip()[:1] in ("{", "[")
        ):
            _flush()
        cur_data_parts.append(payload)
        cur_indices.append(idx)
        cur_elapsed = elapsed
        has_field = True

    _flush()
    return frames


def frame_match_context(frame: dict[str, Any]) -> dict[str, Any]:
    """构造 rule_based 可匹配的上下文（JSON 顶层 + sse_event/sse_id）。"""
    data_obj = frame.get("data_obj")
    ctx: dict[str, Any] = dict(data_obj) if isinstance(data_obj, dict) else {}
    # 无 event: 行时为空串，便于 match 显式要求或省略
    ctx["sse_event"] = frame.get("event") if frame.get("event") is not None else ""
    if frame.get("id") is not None:
        ctx["sse_id"] = frame.get("id")
    return ctx
