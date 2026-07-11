"""JSON 输入解析（标准 JSON + Python 字面量容错）"""
from __future__ import annotations

import ast
import json
from typing import Any

from app.modules.data_tools.errors import ToolExecutionError


def parse_json_text(text: str, *, label: str = "JSON") -> Any:
    raw = str(text or "").strip()
    if not raw:
        raise ToolExecutionError(f"请填写{label}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    try:
        value = ast.literal_eval(raw)
    except (ValueError, SyntaxError) as exc:
        raise ToolExecutionError(f"{label} 无效: {exc}") from exc
    if not isinstance(value, (dict, list)):
        raise ToolExecutionError(f"{label} 需要对象或数组")
    return value
