"""AI 生成 SSE rule_based 解析规则草稿：样例归一、JSON 解析、规则校验。"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.modules.stream_phase.parsers.rule_based import DEFAULT_RULES

_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_KEY_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_DERIVED_EXPR_RE = re.compile(
    r"^[a-zA-Z_][a-zA-Z0-9_]*\s+-\s+[a-zA-Z_][a-zA-Z0-9_]*$"
)


def normalize_sample_lines(
    sample_text: Optional[str] = None,
    sample_lines: Optional[list[str]] = None,
) -> list[str]:
    """将样例归一成行列表；保留 data: 前缀，去掉空行。优先 sample_lines。"""
    raw_parts: list[str] = []
    if sample_lines:
        for item in sample_lines:
            if item is None:
                continue
            raw_parts.append(str(item))
    elif sample_text and str(sample_text).strip():
        raw_parts.append(str(sample_text))
    lines: list[str] = []
    for chunk in raw_parts:
        for part in chunk.splitlines():
            s = part.rstrip("\r")
            if s.strip():
                lines.append(s)
    return lines


def compact_sample_for_prompt(
    lines: list[str],
    *,
    max_lines: int = 80,
    max_line_chars: int = 600,
    max_total_chars: int = 12000,
) -> str:
    """压缩送入 Prompt 的样例：保留 data:/event:/id:，截断超长行（如 eof references）。"""
    preferred = [
        ln
        for ln in lines
        if ln.lstrip().startswith(("data:", "event:", "id:"))
    ]
    src = preferred or list(lines)
    out: list[str] = []
    total = 0
    for ln in src:
        if len(out) >= max_lines:
            out.append(f"...（已截断，仅保留前 {max_lines} 条 SSE 字段行供生成规则）")
            break
        piece = ln if len(ln) <= max_line_chars else (ln[:max_line_chars] + "...[truncated]")
        if total + len(piece) + 1 > max_total_chars:
            out.append("...（样例过长已截断，请只保留代表性阶段行）")
            break
        out.append(piece)
        total += len(piece) + 1
    return "\n".join(out)


def parse_llm_rules_json(raw: str) -> Optional[dict[str, Any]]:
    """从 LLM 响应提取 JSON 对象（含代码块与轻度截断修复）。"""
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    candidates: list[str] = []
    for match in _CODE_BLOCK_RE.findall(text):
        candidates.append(match.strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    candidates.append(text)

    for cand in candidates:
        if not cand:
            continue
        try:
            data = json.loads(cand)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        fixed = _try_fix_truncated_json(cand)
        if fixed:
            try:
                data = json.loads(fixed)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
    return None


def _try_fix_truncated_json(text: str) -> Optional[str]:
    text = (text or "").strip()
    if not text:
        return None
    # 从首个 { 起截取
    start = text.find("{")
    if start == -1:
        return None
    fixed = text[start:]
    if fixed.count('"') % 2:
        fixed += '"'
    open_braces = fixed.count("{") - fixed.count("}")
    open_brackets = fixed.count("[") - fixed.count("]")
    stripped = fixed.rstrip()
    if stripped.endswith(","):
        fixed = stripped[:-1]
    for _ in range(max(0, open_braces)):
        fixed += "}"
    for _ in range(max(0, open_brackets)):
        fixed += "]"
    try:
        json.loads(fixed)
        return fixed
    except json.JSONDecodeError:
        return None

_STRUCT_MATCH_KEYS = frozenset({"path_eq", "path_nonempty", "text_grew"})


def _clean_match(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in raw.items():
        key = str(k).strip()
        if not key:
            continue
        if key == "delta_nonempty":
            out[key] = bool(v)
            continue
        if key in _STRUCT_MATCH_KEYS:
            if isinstance(v, str) and key == "path_nonempty" and v.strip():
                out[key] = {"path": v.strip()}
                continue
            if not isinstance(v, dict):
                continue
            path = str(v.get("path") or "").strip()
            if not path:
                continue
            if key == "path_nonempty":
                out[key] = {"path": path}
            elif key == "path_eq":
                out[key] = {
                    "path": path,
                    "value": "" if v.get("value") is None else str(v.get("value")),
                }
            elif key == "text_grew":
                try:
                    min_chars = max(1, int(v.get("min_chars") or 1))
                except (TypeError, ValueError):
                    min_chars = 1
                out[key] = {"path": path, "min_chars": min_chars}
            continue
        if v is None or v == "":
            continue
        out[key] = str(v).strip() if not isinstance(v, (bool, int, float)) else v
    return out


def _clean_preprocess(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        op = str(item.get("op") or "").strip()
        if op not in ("unwrap_json_text", "json_patch"):
            continue
        step: dict[str, Any] = {"op": op}
        for k in ("path", "when_path", "when_eq"):
            val = item.get(k)
            if val is None or val == "":
                continue
            step[k] = str(val).strip()
        out.append(step)
    return out


def _validate_derived_expr(expr: str, phase_keys: set[str]) -> Optional[str]:
    expr = (expr or "").strip()
    if not expr:
        return "derived.expr 不能为空"
    if not _DERIVED_EXPR_RE.match(expr) and " - " not in expr:
        return f"derived.expr 仅支持 a - b 形式，当前: {expr}"
    if " - " not in expr:
        return f"derived.expr 仅支持 a - b 形式，当前: {expr}"
    left, right = [p.strip() for p in expr.split(" - ", 1)]
    allowed = set(phase_keys) | {"total_time"}
    if left not in allowed:
        return f"derived.expr 左侧未知阶段: {left}"
    if right not in allowed:
        return f"derived.expr 右侧未知阶段: {right}"
    return None


def validate_and_normalize_draft(
    raw: dict[str, Any],
    *,
    name_hint: Optional[str] = None,
) -> tuple[Optional[dict[str, Any]], list[str]]:
    """校验并归一 AI 草稿。

    对「空 match / 未知 derived 阶段」做降级：跳过坏项并继续，仅在无法得到任何有效 phase 时硬失败。
    返回 (draft, errors)。draft 结构：
    name / description / parser_id / parser_options / success_rule
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(raw, dict):
        return None, ["响应不是 JSON 对象"]

    parser_id = str(raw.get("parser_id") or "rule_based").strip() or "rule_based"
    if parser_id != "rule_based":
        warnings.append("parser_id 已纠正为 rule_based")
        parser_id = "rule_based"

    rules_src = raw.get("rules")
    if rules_src is None and isinstance(raw.get("parser_options"), dict):
        rules_src = raw["parser_options"].get("rules")
    if not isinstance(rules_src, dict):
        errors.append("缺少 rules 对象")
        return None, errors

    base = dict(DEFAULT_RULES)
    line_prefix = str(rules_src.get("line_prefix") or base["line_prefix"]).strip() or "data:"
    done_markers_raw = rules_src.get("done_markers")
    if isinstance(done_markers_raw, list) and done_markers_raw:
        done_markers = [str(x).strip() for x in done_markers_raw if str(x).strip()]
    else:
        done_markers = list(base["done_markers"])
    # 禁止把空 JSON 当成 DONE（常见幻觉）；流结束应靠 event:done / done_events
    _bad_done = {"{}", "data:{}", "data: {}"}
    cleaned_markers = [m for m in done_markers if m not in _bad_done]
    if cleaned_markers != done_markers:
        warnings.append("done_markers 中的 {} / data:{} 已移除，请用 event:done（done_events）表示流结束")
        done_markers = cleaned_markers or list(base["done_markers"])

    frame_mode = rules_src.get("frame_mode", base.get("frame_mode", True))
    if isinstance(frame_mode, str):
        frame_mode = frame_mode.strip().lower() not in ("0", "false", "no", "off")
    else:
        frame_mode = bool(frame_mode)

    done_events_raw = rules_src.get("done_events")
    if isinstance(done_events_raw, list) and done_events_raw:
        done_events = [str(x).strip() for x in done_events_raw if str(x).strip()]
    else:
        done_events = list(base.get("done_events") or ["done"])

    phases_out: list[dict[str, Any]] = []
    phase_keys: set[str] = set()
    for i, phase in enumerate(rules_src.get("phases") or []):
        if not isinstance(phase, dict):
            warnings.append(f"phases[{i}] 不是对象，已跳过")
            continue
        key = str(phase.get("key") or "").strip()
        label = str(phase.get("label") or key).strip()
        if not key or not _KEY_RE.match(key):
            warnings.append(f"phases[{i}].key 非法: {key!r}，已跳过")
            continue
        if key in phase_keys:
            warnings.append(f"phases[{i}].key 重复: {key}，已跳过")
            continue
        # 兼容模型把 match 写成 list / 字符串的情况
        match_raw = phase.get("match")
        if isinstance(match_raw, list) and match_raw and isinstance(match_raw[0], dict):
            match_raw = match_raw[0]
        elif isinstance(match_raw, str) and match_raw.strip():
            try:
                parsed_m = json.loads(match_raw)
                match_raw = parsed_m if isinstance(parsed_m, dict) else {}
            except json.JSONDecodeError:
                match_raw = {}
        match = _clean_match(match_raw)
        if not match:
            warnings.append(f"phases[{i}]({key or i}).match 为空，已跳过该阶段")
            continue
        trigger = str(phase.get("trigger") or "first").strip() or "first"
        if trigger not in ("first", "last"):
            trigger = "first"
        phases_out.append(
            {
                "key": key,
                "label": label or key,
                "match": match,
                "trigger": trigger,
            }
        )
        phase_keys.add(key)

    if not phases_out:
        errors.append(
            "rules.phases 没有可用阶段（match 不能为空，且须对齐样例里真实字段如 type/action/status）。"
            "请补充阶段说明后重试，例如：「检索=action=search；问答=action=done」"
        )
        return None, errors + warnings

    derived_out: list[dict[str, Any]] = []
    derived_keys: set[str] = set()
    for i, item in enumerate(rules_src.get("derived") or []):
        if not isinstance(item, dict):
            warnings.append(f"derived[{i}] 不是对象，已跳过")
            continue
        key = str(item.get("key") or "").strip()
        label = str(item.get("label") or key).strip()
        expr = str(item.get("expr") or "").strip()
        # 常见幻觉：end/finish 写成阶段名 → 改成 total_time；start 等无法表达则留给校验跳过
        expr = _rewrite_common_derived_aliases(expr, phase_keys)
        if not key or not _KEY_RE.match(key):
            warnings.append(f"derived[{i}].key 非法: {key!r}，已跳过")
            continue
        if key in derived_keys or key in phase_keys:
            warnings.append(f"derived[{i}].key 冲突或重复: {key}，已跳过")
            continue
        err = _validate_derived_expr(expr, phase_keys)
        if err:
            warnings.append(f"derived[{i}] 已跳过（{err}）")
            continue
        derived_out.append({"key": key, "label": label or key, "expr": expr})
        derived_keys.add(key)

    success_raw = raw.get("success_rule")
    if not isinstance(success_raw, dict):
        success_raw = {"type": "phase_exists", "phase": phases_out[-1]["key"]}
    stype = str(success_raw.get("type") or "phase_exists").strip()
    if stype == "status_ok":
        success_rule: dict[str, Any] = {"type": "status_ok"}
    else:
        phase = str(success_raw.get("phase") or "").strip()
        if phase and phase not in phase_keys and phase not in derived_keys and phase != "total_time":
            warnings.append(f"success_rule.phase={phase!r} 无效，已改用末阶段")
            phase = phases_out[-1]["key"]
        if not phase:
            phase = phases_out[-1]["key"]
        success_rule = {"type": "phase_exists", "phase": phase}

    name = str(raw.get("name") or name_hint or "").strip()[:100]
    if not name:
        name = (name_hint or "AI 生成 SSE 规则").strip()[:100]
    description = str(raw.get("description") or "").strip()[:4000]

    if errors:
        return None, errors + warnings

    preprocess = _clean_preprocess(rules_src.get("preprocess"))
    rules = {
        "line_prefix": line_prefix,
        "done_markers": done_markers,
        "frame_mode": frame_mode,
        "done_events": done_events,
        "preprocess": preprocess,
        "phases": phases_out,
        "derived": derived_out,
        "extras_extract": list(base.get("extras_extract") or []),
    }
    draft = {
        "name": name,
        "description": description,
        "parser_id": "rule_based",
        "parser_options": {"rules": rules},
        "success_rule": success_rule,
    }
    if warnings:
        draft["_ai_normalize_warnings"] = warnings
    return draft, []


def _rewrite_common_derived_aliases(expr: str, phase_keys: set[str]) -> str:
    """把模型常幻觉的 end/finish 改成 total_time；start 等无法映射则原样返回由校验跳过。"""
    expr = (expr or "").strip()
    if " - " not in expr:
        return expr
    left, right = [p.strip() for p in expr.split(" - ", 1)]
    allowed = set(phase_keys) | {"total_time"}

    def _fix(token: str) -> str:
        if token in allowed:
            return token
        low = token.lower()
        if low in ("end", "finish", "stream_end", "done_time", "eof"):
            return "total_time"
        return token

    return f"{_fix(left)} - {_fix(right)}"
