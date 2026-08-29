"""跨环境批量增删 / 同步变量键。"""
from __future__ import annotations

from typing import Any, Literal

from app.core.shared.global_vars_validate import (
    RESERVED_ENV_GLOBAL_VAR_KEYS,
    normalize_global_vars,
    normalize_var_entry,
)

BatchMode = Literal["add_keys", "delete_keys", "sync_values"]


def _is_user_key(key: str) -> bool:
    k = (key or "").strip()
    return bool(k) and k not in RESERVED_ENV_GLOBAL_VAR_KEYS and not k.startswith("__")


def apply_batch_to_global_vars(
    global_vars: dict | None,
    *,
    mode: BatchMode,
    keys: list[str],
    source_vars: dict | None = None,
    default_values: dict | None = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    """
    返回规范化后的新 global_vars。
    - add_keys: 目标缺少该键时写入 default_values[key] 或空值；已有则跳过
    - delete_keys: 删除用户键
    - sync_values: 从 source_vars 复制键值；overwrite=False 时仅补缺
    """
    current = dict(global_vars or {})
    cleaned_keys = [k.strip() for k in (keys or []) if _is_user_key(k)]
    if not cleaned_keys:
        return normalize_global_vars(current)

    src = source_vars or {}
    defaults = default_values or {}

    if mode == "delete_keys":
        for k in cleaned_keys:
            current.pop(k, None)
        return normalize_global_vars(current)

    if mode == "add_keys":
        for k in cleaned_keys:
            if k in current:
                continue
            raw = defaults[k] if k in defaults else {"value": "", "description": ""}
            current[k] = normalize_var_entry(k, raw)
        return normalize_global_vars(current)

    if mode == "sync_values":
        for k in cleaned_keys:
            if k not in src:
                continue
            if k in current and not overwrite:
                continue
            current[k] = normalize_var_entry(k, src[k])
        return normalize_global_vars(current)

    raise ValueError(f"不支持的模式：{mode}")
