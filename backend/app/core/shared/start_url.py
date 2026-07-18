"""默认起始 URL / 录制 URL 校验与规范化（与 Browser Lab 对齐，允许 ${{var}} 模板）。"""
from __future__ import annotations

import re

_VAR_PATTERN = re.compile(r"\$\{\{([^}]+)\}\}")


def contains_unresolved_template(text: str) -> bool:
    return bool(text and ("${{" in text or "${" in text))


def validate_default_start_url(url: str) -> str:
    """
    校验项目/环境 default_start_url 存储值。
    - 空串允许（表示未配置）
    - 含 ${{var}} 时允许 URL 模板
    - 否则须以 http:// 或 https:// 开头
    """
    u = str(url or "").strip()
    if not u:
        return ""
    if len(u) > 500:
        raise ValueError("默认起始 URL 长度不能超过 500 字符")
    if " " in u:
        raise ValueError("默认起始 URL 不能包含空格")
    if "${{" in u:
        return u
    if not u.startswith(("http://", "https://")):
        raise ValueError("默认起始 URL 须以 http:// 或 https:// 开头，或使用 ${{变量名}} 模板")
    return u


def validate_record_start_url(url: str) -> str:
    """校验录制启动 URL（须为已解析的完整地址）。"""
    u = str(url or "").strip()
    if not u or u == "about:blank":
        return u
    if contains_unresolved_template(u):
        raise ValueError("录制 URL 仍含未替换变量，请检查环境变量或手动填写完整地址")
    if not u.startswith(("http://", "https://")):
        raise ValueError("录制起始 URL 须以 http:// 或 https:// 开头")
    if len(u) > 500:
        raise ValueError("录制 URL 长度不能超过 500 字符")
    return u
