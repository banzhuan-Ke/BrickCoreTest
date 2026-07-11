"""环境/项目 global_vars 校验、规范化与执行时扁平化"""
from __future__ import annotations

import re
from typing import Any, Dict

# 项目 global_vars 中的系统配置键（非用例变量，执行时跳过）
RESERVED_PROJECT_GLOBAL_VAR_KEYS = frozenset({"ai_settings", "zentao_export"})

_SECRET_KEY_PATTERN = re.compile(
    r"password|passwd|secret|token|api[_-]?key|authorization|credential|private",
    re.IGNORECASE,
)


def is_secret_key(key: str) -> bool:
    return bool(_SECRET_KEY_PATTERN.search(str(key or "")))


def extract_var_value(raw: Any) -> str:
    """从存储条目或 legacy 字符串提取变量值。"""
    if raw is None:
        return ""
    if isinstance(raw, dict):
        if "value" in raw:
            v = raw.get("value")
            if v is None:
                return ""
            if isinstance(v, (dict, list)):
                raise ValueError("变量值不能是嵌套对象或数组")
            return str(v)
        raise ValueError("变量扩展对象必须包含 value 字段")
    if isinstance(raw, (dict, list)):
        raise ValueError("变量值不能是嵌套对象或数组")
    return str(raw)


def normalize_var_entry(key: str, value: Any) -> Dict[str, Any]:
    """规范为扩展存储格式：{ value, description?, secret? }。"""
    k = str(key).strip()
    if isinstance(value, dict) and "value" in value:
        desc = str(value.get("description") or "").strip()
        secret = bool(value.get("secret")) if "secret" in value else is_secret_key(k)
        val = extract_var_value(value)
        out: Dict[str, Any] = {"value": val, "description": desc}
        if secret:
            out["secret"] = True
        return out

    val = extract_var_value(value)
    out = {"value": val, "description": ""}
    if is_secret_key(k):
        out["secret"] = True
    return out


def normalize_global_vars(raw: Any) -> Dict[str, Any]:
    """
    校验并规范化 global_vars（环境保存用）：
    - 必须是 dict
    - key 非空、不重复
    - 值规范为扩展对象 { value, description?, secret? }
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("环境变量必须是 JSON 对象（键值对）")
    if isinstance(raw, list):
        raise ValueError("环境变量不能是数组")

    out: Dict[str, Any] = {}
    for key, value in raw.items():
        k = str(key).strip()
        if not k:
            raise ValueError("变量名不能为空")
        if k in out:
            raise ValueError(f"变量名重复：{k}")
        if isinstance(value, dict) and "value" not in value:
            raise ValueError(f"变量「{k}」的值格式无效，需包含 value 字段或使用字符串")
        out[k] = normalize_var_entry(k, value)
    return out


def flatten_global_vars(raw: Any) -> Dict[str, str]:
    """
    执行/预览用：将 global_vars 扁平为 { 变量名: 值字符串 }。
    跳过项目级系统配置键及无 value 的嵌套对象。
    """
    if not raw or not isinstance(raw, dict):
        return {}
    out: Dict[str, str] = {}
    for key, value in raw.items():
        k = str(key).strip()
        if not k or k in RESERVED_PROJECT_GLOBAL_VAR_KEYS:
            continue
        if isinstance(value, dict):
            if "value" in value:
                out[k] = extract_var_value(value)
            continue
        try:
            out[k] = extract_var_value(value)
        except ValueError:
            continue
    return out
