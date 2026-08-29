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


def validate_apm_trace_base_url(url: str) -> str:
    """
    校验 APM 链路前缀：仅允许 http(s)，防 javascript:/data: 等存储型 XSS。
    空串表示未配置。
    """
    u = str(url or "").strip()
    if not u:
        return ""
    if len(u) > 500:
        raise ValueError("APM 链路前缀长度不能超过 500 字符")
    if any(c.isspace() for c in u):
        raise ValueError("APM 链路前缀不能包含空白字符")
    if not u.lower().startswith(("http://", "https://")):
        raise ValueError("APM 链路前缀须以 http:// 或 https:// 开头")
    return u


def build_apm_trace_url(base: str, request_id: str) -> str:
    """将校验过的 base 与 request_id 拼成可打开外链；非法 scheme 返回空。"""
    from urllib.parse import quote

    try:
        prefix = validate_apm_trace_base_url(base)
    except ValueError:
        return ""
    rid = str(request_id or "").strip()
    if not prefix or not rid:
        return ""
    encoded = quote(rid, safe="")
    if "{rid}" in prefix or "{request_id}" in prefix:
        return prefix.replace("{rid}", encoded).replace("{request_id}", encoded)
    if not prefix.endswith(("/", "=", "&", "?")):
        prefix = f"{prefix}/"
    return f"{prefix}{encoded}"


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
