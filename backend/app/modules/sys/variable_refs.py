"""从任意 JSON/文本中提取 ${{name}} / ${name} / {{name}} 与 dt: 内 @var。"""
from __future__ import annotations

import re
from typing import Any, Iterable

# 与 VariableResolver 对齐，并兼容前端 caseVarRefs
_VAR_PATTERN = re.compile(r"\$\{\{([^}]+)\}\}|\$\{([^}]+)\}|\{\{([^}]+)\}\}")
_AT_VAR_IN_DT = re.compile(r"@([a-zA-Z_][\w.]*)")

_SKIP_PREFIXES = ("df:", "dt:", "csv.", "fragment.")
_BUILTIN = frozenset(
    {
        "random_name",
        "random_phone",
        "random_email",
        "random_address",
        "random_company",
        "random_int",
        "random_str",
        "timestamp",
        "now_time",
        "today",
    }
)


def _normalize_plain_name(raw: str) -> str | None:
    expr = (raw or "").strip()
    if not expr:
        return None
    if any(expr.startswith(p) for p in _SKIP_PREFIXES):
        return None
    # 去掉可能的管道参数：name|default=x（极少见；保守只取第一段）
    name = expr.split("|", 1)[0].strip()
    if not name or name in _BUILTIN:
        return None
    if name.startswith("__"):
        return None
    return name


def extract_plain_var_names(value: Any, *, into: set[str] | None = None) -> set[str]:
    """递归扫描，返回普通环境/项目变量名集合（不含 df/dt/csv/fragment/内置）。"""
    found = into if into is not None else set()
    if value is None:
        return found
    if isinstance(value, str):
        if "${{" in value or "${" in value or "{{" in value:
            for m in _VAR_PATTERN.finditer(value):
                inner = (m.group(1) or m.group(2) or m.group(3) or "").strip()
                plain = _normalize_plain_name(inner)
                if plain:
                    found.add(plain)
                if inner.startswith("dt:"):
                    at = _AT_VAR_IN_DT.search(inner)
                    if at:
                        plain_at = _normalize_plain_name(at.group(1))
                        if plain_at:
                            found.add(plain_at)
        return found
    if isinstance(value, dict):
        for v in value.values():
            extract_plain_var_names(v, into=found)
        return found
    if isinstance(value, (list, tuple)):
        for item in value:
            extract_plain_var_names(item, into=found)
        return found
    return found


def value_references_var(value: Any, name: str) -> bool:
    target = (name or "").strip()
    if not target:
        return False
    return target in extract_plain_var_names(value)
