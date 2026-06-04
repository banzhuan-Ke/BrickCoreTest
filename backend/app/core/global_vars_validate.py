"""环境/项目 global_vars 校验与规范化"""
from __future__ import annotations

from typing import Any, Dict


def normalize_global_vars(raw: Any) -> Dict[str, Any]:
    """
    校验并规范化 global_vars：
    - 必须是 dict（非 list）
    - key 去首尾空格、非空、不重复
    - value 转为 str（None -> ''）
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
        if value is None:
            out[k] = ""
        elif isinstance(value, (dict, list)):
            raise ValueError(f"变量「{k}」的值不能是嵌套对象或数组，请使用字符串")
        else:
            out[k] = str(value)
    return out
