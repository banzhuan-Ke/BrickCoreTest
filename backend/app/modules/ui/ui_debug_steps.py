"""UI 交互调试：步骤指纹与初始 URL 解析。"""
from __future__ import annotations

import hashlib
import json
import re
from typing import List, Optional

_VAR_PATTERN = re.compile(r"\$\{\{([^}]+)\}\}")


def compute_steps_fingerprint(steps: list) -> str:
    """对步骤快照计算稳定指纹（展开后的步骤列表）。"""
    payload = json.dumps(steps or [], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def resolve_debug_initial_url(env_config: dict, steps: list) -> Optional[str]:
    """
    解析调试浏览器打开后可选的初始导航地址。
    优先首步 open_url，其次环境 target_host。
    """
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        if step.get("method") == "open_url":
            url = (step.get("params") or {}).get("url") or step.get("url")
            url = str(url or "").strip()
            if url:
                return url

    host = str((env_config or {}).get("target_host") or "").strip()
    if not host:
        return None
    if host.startswith(("http://", "https://")):
        return host
    return f"https://{host}"


def substitute_variables_in_text(text: str, variables: dict) -> str:
    """将 ${{var}} 替换为环境变量（与 Runner VariableManager 语法一致）。"""
    if not text or "${{" not in text:
        return text

    def repl(match: re.Match) -> str:
        key = (match.group(1) or "").strip()
        if key in variables:
            return str(variables[key])
        return match.group(0)

    return _VAR_PATTERN.sub(repl, text)


def contains_unresolved_template(text: str) -> bool:
    return bool(text and ("${{" in text or "${" in text))


def resolve_debug_initial_url_with_variables(env_config: dict, steps: list) -> Optional[str]:
    """解析初始 URL，并尽量用 env.variables 替换 ${{var}}。"""
    raw = resolve_debug_initial_url(env_config, steps)
    if not raw:
        return None
    variables = (env_config or {}).get("variables") or {}
    if not isinstance(variables, dict):
        variables = {}
    resolved = substitute_variables_in_text(raw, variables)
    if contains_unresolved_template(resolved):
        return None
    return resolved
