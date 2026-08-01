"""问答 SSE v1 阶段解析器（与 qa_eval_target_client.parse_qa_sse_v1 协议对齐）"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any

from app.modules.stream_phase.timing import line_elapsed_at, stream_end_elapsed

PARSER_ID = "qa_sse_v1"
DISPLAY_NAME = "问答流式 v1"

PHASE_SCHEMA = [
    {"key": "think_answer", "label": "问题理解首字(s)", "unit": "s", "aggregate": True},
    {"key": "intent_complete", "label": "意图完成(s)", "unit": "s", "aggregate": True},
    {"key": "first_char", "label": "首字时间(s)", "unit": "s", "aggregate": True},
    {"key": "total_time", "label": "整体耗时(s)", "unit": "s", "aggregate": True},
    {"key": "thinking_duration", "label": "思考耗时(s)", "unit": "s", "aggregate": True},
    {"key": "answer_streaming", "label": "答案流式输出(s)", "unit": "s", "aggregate": True},
]

EXTRA_SCHEMA = [
    {"key": "thread_id", "label": "会话ID"},
    {"key": "answer_length", "label": "答案长度"},
    {"key": "answer_preview", "label": "答案预览"},
    {"key": "reference_files", "label": "参考文件"},
    {"key": "intent_start_at", "label": "意图开始时间"},
    {"key": "thinking_start_at", "label": "思考开始时间"},
    {"key": "thinking", "label": "思考过程"},
    {"key": "references_all", "label": "参考资料(全部)"},
    {"key": "references_high", "label": "参考资料(高分)"},
]

_SKIP_DATA_MARKERS = ('"errorMessage"', '"duration"')


def _answer_length(text: str) -> int:
    if not text or text == "无答案返回":
        return 0
    text = re.sub(r"\[ref:\d+\]", "", text)
    chinese = len(re.findall(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]", text))
    non_cn = re.sub(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]", " ", text)
    return chinese + len(re.findall(r"[a-zA-Z]+", non_cn))


def _is_meaningful_delta(delta: Any) -> bool:
    if delta is None:
        return False
    s = delta if isinstance(delta, str) else str(delta)
    stripped = s.strip()
    return bool(stripped) and stripped != "\n\n"


def _extract_think_text(delta: Any) -> str:
    """解析 think / think_answer 的 delta。"""
    if not delta:
        return ""
    if isinstance(delta, str):
        raw = delta.strip()
        if not raw:
            return ""
        if raw[0] in ("{", "["):
            try:
                d = json.loads(raw)
                if isinstance(d, dict) and d.get("message_type") == "text":
                    return str((d.get("content") or {}).get("text") or "")
            except json.JSONDecodeError:
                pass
        return raw
    if isinstance(delta, dict) and delta.get("message_type") == "text":
        return str((delta.get("content") or {}).get("text") or "")
    return str(delta)


def _format_references(refs: list[tuple[str, float]], *, min_score: float = 0) -> str:
    filtered = [(n, s) for n, s in refs if s > min_score] if min_score else refs
    if not filtered:
        return ""
    return "；".join(f"{n} ({s:.2f})" for n, s in filtered)


def _dedupe_refs(refs: list[tuple[str, float]]) -> list[tuple[str, float]]:
    seen: set[str] = set()
    out: list[tuple[str, float]] = []
    for name, score in refs:
        if name not in seen:
            seen.add(name)
            out.append((name, score))
    return out


def parse_qa_sse_content(lines: list[str]) -> dict[str, Any]:
    """仅提取答案/思考/引用（无阶段计时）。"""
    result = parse_stream(lines, start_time=time.time(), status_code=200)
    extras = result.get("extras") or {}
    answer = extras.get("answer") or extras.get("answer_preview") or ""
    if answer == "无答案返回":
        answer = ""
    status = "success" if answer and not str(answer).startswith("请求") else "fail"
    return {
        "actual_answer": answer[:16000],
        "thinking": (extras.get("thinking") or "")[:8000],
        "references_all": (extras.get("references_all") or "")[:4000],
        "references_high": (extras.get("references_high") or "")[:4000],
        "status": status,
    }


def parse_stream(
    lines: list[str],
    *,
    start_time: float,
    status_code: int = 200,
    options: dict | None = None,
    line_elapsed: list[float] | None = None,
) -> dict[str, Any]:
    phases: dict[str, Any] = {}
    extras: dict[str, Any] = {}
    thinking_parts: list[str] = []
    answer_parts: list[str] = []
    refs: list[tuple[str, float]] = []

    done_time = None
    intent_started = intent_completed = thinking_completed = answer_started = False
    think_answer_start = False
    first_char_at = None
    eof_time = None
    error = None
    error_type = None

    for idx, line in enumerate(lines):
        if not line:
            continue
        elapsed = line_elapsed_at(idx, line_elapsed, start_time)
        line_str = line.decode("utf-8") if isinstance(line, bytes) else line
        txt = line_str.strip()
        if not txt or not txt.startswith("data:"):
            continue
        data_str = txt[5:].strip()
        if data_str == "[DONE]" or txt == "data:[DONE]":
            done_time = elapsed
            break
        if any(m in data_str for m in _SKIP_DATA_MARKERS):
            continue
        if data_str and data_str[0] not in ("{", "["):
            error = f"服务器返回错误: {data_str}"
            error_type = "ServerError"
            if "连接失败" in data_str or "timeout" in data_str.lower():
                break
            continue
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        msg_type = data.get("type", "")
        agent = data.get("agent", "")
        action = data.get("action", "")
        status = data.get("status", "")
        delta = data.get("delta", "")

        if not extras.get("thread_id") and data.get("id"):
            extras["thread_id"] = data.get("id")

        if (
            msg_type == "think_answer"
            and agent == "think"
            and action == "intent"
            and not think_answer_start
        ):
            phases["think_answer"] = round(elapsed, 3)
            think_answer_start = True

        if msg_type in ("think", "think_answer"):
            think_text = _extract_think_text(delta)
            if think_text:
                thinking_parts.append(think_text)
            # 兜底：部分接口不发 think_answer+intent 控制帧，仅在 think 流里带首字
            if not think_answer_start and (
                _is_meaningful_delta(think_text) or msg_type == "think_answer"
            ):
                phases["think_answer"] = round(elapsed, 3)
                think_answer_start = True

        if msg_type == "think" and agent == "think" and action == "intent" and status in ("pending", "success"):
            if status == "pending" and not intent_started:
                extras["intent_start_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                intent_started = True
            elif status == "success" and not intent_completed:
                phases["intent_complete"] = round(elapsed, 3)
                intent_completed = True
                extras["thinking_start_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

        if msg_type == "eof" and agent == "conventional_summary":
            if eof_time is None:
                eof_time = round(elapsed, 3)
            for ref in data.get("references") or []:
                if not isinstance(ref, dict):
                    continue
                name = ref.get("doc_name")
                if not name:
                    continue
                try:
                    score_val = float(ref.get("chunk_score", 0) or 0)
                except (TypeError, ValueError):
                    score_val = 0.0
                refs.append((str(name), score_val))
            if not thinking_completed:
                thinking_completed = True

        if msg_type == "output_text" and agent == "conventional_summary":
            delta_str = delta if isinstance(delta, str) else (str(delta) if delta is not None else "")
            if _is_meaningful_delta(delta_str):
                if not answer_started:
                    first_char_at = elapsed
                    phases["first_char"] = round(first_char_at, 3)
                    answer_started = True
                    thinking_completed = True
                    if phases.get("intent_complete") is not None:
                        phases["thinking_duration"] = round(phases["first_char"] - phases["intent_complete"], 3)
                answer_parts.append(re.sub(r"\[ref:\d+\]", "", delta_str))

    end_at = stream_end_elapsed(line_elapsed, start_time, done_at=done_time)
    total_time = round(end_at, 3)
    phases["total_time"] = total_time

    if first_char_at is not None:
        phases["answer_streaming"] = round(max(0, end_at - first_char_at), 3)

    if eof_time and not answer_started and phases.get("intent_complete") is not None:
        if phases.get("thinking_duration") is None:
            phases["thinking_duration"] = round(eof_time - phases["intent_complete"], 3)

    full_answer = re.sub(r"\[ref:\d+\]", "", "".join(answer_parts)).strip()
    thinking_str = "".join(thinking_parts).strip()
    unique_refs = _dedupe_refs(refs)

    if unique_refs:
        names = [n for n, _ in unique_refs]
        extras["reference_files"] = "; ".join(names)
    extras["thinking"] = thinking_str
    extras["references_all"] = _format_references(unique_refs)
    extras["references_high"] = _format_references(unique_refs, min_score=80)

    if full_answer:
        extras["answer"] = full_answer[:16000]
        extras["answer_preview"] = full_answer[:500]
        extras["answer_length"] = _answer_length(full_answer)
    else:
        extras["answer_preview"] = "无答案返回"
        extras["answer_length"] = 0

    success = bool(full_answer) and not full_answer.startswith("请求") and status_code == 200 and not error
    if thinking_completed and not answer_started and not full_answer:
        success = False
        if not error:
            error = "思考完成但未返回答案"

    if status_code >= 400 and not error:
        error = f"HTTP {status_code}"
        success = False

    return {
        "parser_id": PARSER_ID,
        "success": success,
        "total_time_s": total_time,
        "status_code": status_code,
        "phases": phases,
        "extras": extras,
        "error": error,
        "error_type": error_type,
        "phase_schema": PHASE_SCHEMA,
        "extra_schema": EXTRA_SCHEMA,
    }


# 供平台侧（含 CE，无 qa_eval 包）复用的薄封装
_LEGACY_SSE_PARSER_V1 = "kbs_qa_v1"


def normalize_sse_parser(parser: str | None) -> str:
    p = (parser or PARSER_ID).lower()
    if p == _LEGACY_SSE_PARSER_V1:
        return PARSER_ID
    return p


def is_qa_sse_v1_parser(parser: str | None) -> bool:
    return normalize_sse_parser(parser) == PARSER_ID


def parse_qa_sse_v1(lines: list[str]) -> dict[str, Any]:
    return parse_qa_sse_content(lines)
