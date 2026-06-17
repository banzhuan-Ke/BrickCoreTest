"""用例/套件执行时内联引用数据工厂工具：${{dt:md5|text=@token}}"""
from __future__ import annotations

import json
import urllib.parse
from typing import Any

from app.core.data_tools.errors import ToolExecutionError
from app.core.data_tools.executor import execute_tool
from app.core.data_tools.registry import get_tool_definition, list_tools

DT_CACHE_KEY = "__dt_cache__"
DT_EXPR_PREFIX = "dt:"

# 不适合作为请求参数内联（调试/多值/结构化输出）
INLINE_EXCLUDED_TOOL_IDS = frozenset({
    "json_compare",
    "json_keys",
    "json_format",
    "json_compress",
    "cron_validate",
    "cron_next",
    "code128_text",
    "str_split",
    "regex_findall",
})


def ensure_dt_cache(variables: dict | None) -> dict:
    """套件/计划串行执行时共享随机工具结果。"""
    merged = dict(variables or {})
    if DT_CACHE_KEY not in merged or not isinstance(merged.get(DT_CACHE_KEY), dict):
        merged[DT_CACHE_KEY] = {}
    return merged


def list_inline_insertable_tools() -> list[dict[str, Any]]:
    """返回可在用例中通过 ${{dt:...}} 引用的工具定义。"""
    out: list[dict[str, Any]] = []
    for tool in list_tools():
        if tool["id"] in INLINE_EXCLUDED_TOOL_IDS:
            continue
        item = dict(tool)
        item["insert_hint"] = _build_insert_hint(tool)
        out.append(item)
    return out


def _build_insert_hint(tool: dict[str, Any]) -> str:
    inputs = tool.get("inputs") or []
    tool_id = tool["id"]
    if not inputs:
        return "${{dt:" + tool_id + "}}"
    parts = [f"{f['key']}=@变量名" for f in inputs if f.get("required")]
    if not parts:
        parts = [f'{f["key"]}="固定值"' for f in inputs[:2]]
    return "${{dt:" + tool_id + "|" + "|".join(parts) + "}}"


def _split_pipe_outside_quotes(text: str) -> list[str]:
    """按 | 分段，引号内的 | 不参与分段。"""
    parts: list[str] = []
    buf: list[str] = []
    in_quote: str | None = None
    i = 0
    while i < len(text):
        ch = text[i]
        if in_quote:
            buf.append(ch)
            if ch == in_quote and not _is_escaped(text, i):
                in_quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "|":
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    j = index - 1
    while j >= 0 and text[j] == "\\":
        backslashes += 1
        j -= 1
    return backslashes % 2 == 1


def _unwrap_quoted_literal(raw: str) -> str | None:
    """解析 "..." 或 '...' 固定值（支持 \\\" \\\\ 转义）。"""
    s = raw.strip()
    if len(s) < 2:
        return None
    quote = s[0]
    if quote not in ("'", '"') or s[-1] != quote:
        return None
    inner = s[1:-1]
    if quote == '"':
        return inner.replace('\\"', '"').replace("\\\\", "\\")
    return inner.replace("\\'", "'").replace("\\\\", "\\")


def parse_dt_expression(expr: str) -> tuple[str, dict[str, str]]:
    """解析 dt:tool_id|k=v|k2="v2"（引号内可含 |、=、@）"""
    raw = expr.strip()
    if raw.startswith(DT_EXPR_PREFIX):
        raw = raw[len(DT_EXPR_PREFIX):]
    if not raw:
        raise ToolExecutionError("内联工具表达式无效")
    parts = _split_pipe_outside_quotes(raw)
    tool_id = parts[0].strip()
    params: dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if not key:
            continue
        params[key] = value.strip()
    return tool_id, params


def resolve_dt_param_value(raw: str, lookup_var) -> str:
    """
    参数取值规则：
    - "..." / '...' → 固定字面量（可含 |、=、@）
    - @var → 引用变量池
    - 其它 → 固定字面量（兼容旧写法；仍支持 URL 编码）
    """
    s = raw.strip()
    quoted = _unwrap_quoted_literal(s)
    if quoted is not None:
        return quoted
    if s.startswith("@"):
        name = s[1:].strip()
        if not name:
            raise ToolExecutionError("变量引用无效，请使用 @变量名")
        val = lookup_var(name)
        if val is None:
            raise ToolExecutionError(f"变量 {name} 未定义")
        return str(val)
    return urllib.parse.unquote(s)


def build_dt_cache_key(expr: str, resolved_inputs: dict[str, str]) -> str:
    if not resolved_inputs:
        return expr
    payload = json.dumps(resolved_inputs, ensure_ascii=False, sort_keys=True)
    return f"{expr}::{payload}"


def execute_inline_tool(
    expr: str,
    lookup_var,
    dt_cache: dict[str, str] | None = None,
) -> str:
    """
    执行内联工具表达式并写入执行级缓存（套件/计划内随机数等同表达式只算一次）。
    lookup_var(name) -> 从变量池取值，不应再触发 dt 表达式。
    """
    tool_id, params = parse_dt_expression(expr)
    definition = get_tool_definition(tool_id)
    if not definition:
        raise ToolExecutionError(f"未知内联工具: {tool_id}")
    if tool_id in INLINE_EXCLUDED_TOOL_IDS:
        raise ToolExecutionError(f"工具 {definition.get('name') or tool_id} 不支持内联引用")

    resolved_inputs: dict[str, str] = {}
    for key, raw in params.items():
        resolved_inputs[key] = resolve_dt_param_value(raw, lookup_var)

    cache_key = build_dt_cache_key(expr, resolved_inputs)
    cache = dt_cache if dt_cache is not None else {}
    if cache_key in cache:
        return cache[cache_key]

    typed_inputs: dict[str, Any] = {}
    for field in definition.get("inputs") or []:
        fkey = field["key"]
        if fkey not in resolved_inputs:
            if field.get("default") is not None:
                typed_inputs[fkey] = field["default"]
            continue
        raw_val = resolved_inputs[fkey]
        if field.get("type") == "number":
            try:
                typed_inputs[fkey] = int(raw_val) if "." not in raw_val else float(raw_val)
            except ValueError as exc:
                raise ToolExecutionError(f"{field.get('label') or fkey} 必须是数字") from exc
        else:
            typed_inputs[fkey] = raw_val

    try:
        result = execute_tool(tool_id, typed_inputs)
    except ToolExecutionError:
        raise
    except Exception as exc:
        raise ToolExecutionError(str(exc)) from exc

    text = str(result.get("output_text") or result.get("output") or "")
    cache[cache_key] = text
    return text
